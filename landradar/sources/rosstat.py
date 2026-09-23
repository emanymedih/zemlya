from __future__ import annotations

from dataclasses import dataclass, asdict
from html.parser import HTMLParser
from urllib.parse import urljoin
from typing import Any, Callable
from datetime import datetime
import csv
import io
import re

from .base import HttpTransport, RequestsTransport, RawSnapshot, save_raw_snapshot

OKTMO_PASSPORT_URL = "https://rosstat.gov.ru/opendata/7708234640-oktmo"
ROSTAT_OPENDATA_TERMS_URL = "https://rosstat.gov.ru/opendata"
ROSTAT_OPENDATA_USE_TERMS = (
    "Rosstat standard open-data terms: free reuse, including modification and "
    "commercial use; preserve a link to the source. See terms URL."
)


class _CsvLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.hrefs.append(href)


@dataclass
class RosstatDataset:
    dataset_id: str
    passport_url: str
    data_url: str
    rows: list[dict[str, str]]
    use_terms: str = ROSTAT_OPENDATA_USE_TERMS
    use_terms_url: str = ROSTAT_OPENDATA_TERMS_URL

    @property
    def published_version(self) -> str | None:
        match = re.search(r"data-(\d{8}T\d{4})", self.data_url)
        return match.group(1) if match else None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RosstatOpenDataAdapter:
    source_key = "rosstat_opendata"
    kaluga_subject_code = "29"

    def __init__(self, transport: HttpTransport | None = None):
        self.transport = transport or RequestsTransport()

    @staticmethod
    def resolve_latest_data_url(passport_html: str, passport_url: str) -> str:
        parser = _CsvLinkParser()
        parser.feed(passport_html)
        candidates = [h for h in parser.hrefs if "data-" in h and h.lower().endswith(".csv")]
        if not candidates:
            import re
            candidates = re.findall(r'(?:https?://[^\s"\'<>]+/)?data-[A-Za-z0-9_.\-]+\.csv', passport_html)
        if not candidates:
            raise ValueError("Rosstat passport does not expose a data-*.csv resource")
        import re
        def key(href: str) -> str:
            m = re.search(r"data-(\d{8}T\d{4})", href)
            return m.group(1) if m else ""
        current = max(candidates, key=key)
        return urljoin(passport_url.rstrip("/") + "/", current)

    @staticmethod
    def parse_csv(payload: bytes) -> list[dict[str, str]]:
        text: str | None = None
        for encoding in ("utf-8-sig", "cp1251", "utf-8"):
            try:
                text = payload.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise ValueError("Unable to decode Rosstat CSV")

        rows = list(csv.reader(io.StringIO(text), delimiter=";"))
        if not rows:
            raise ValueError("Rosstat CSV is empty")

        fields = [
            "subject_code", "municipality_code", "territory_code",
            "locality_code", "control_digit", "record_type",
            "name", "parent_name", "additional_name",
            "legacy_code", "legacy_control_digit", "valid_from", "valid_to",
        ]
        result: list[dict[str, str]] = []
        widths = (2, 3, 3, 3)
        for row_number, values in enumerate(rows, start=1):
            if len(values) != len(fields):
                raise ValueError(
                    f"Rosstat OKTMO row {row_number} has {len(values)} fields; expected 13"
                )
            item = {field: value.strip() for field, value in zip(fields, values)}
            for field, width in zip(fields[:4], widths):
                if re.fullmatch(rf"\d{{{width}}}", item[field]) is None:
                    raise ValueError(
                        f"Rosstat OKTMO row {row_number}: invalid {field}={item[field]!r}"
                    )
            if re.fullmatch(r"\d", item["control_digit"]) is None:
                raise ValueError(f"Rosstat OKTMO row {row_number}: invalid control digit")
            if re.fullmatch(r"\d", item["record_type"]) is None:
                raise ValueError(f"Rosstat OKTMO row {row_number}: invalid record type")
            if not item["name"]:
                raise ValueError(f"Rosstat OKTMO row {row_number}: empty name")
            parsed_dates = []
            for field in ("valid_from", "valid_to"):
                try:
                    parsed_dates.append(datetime.strptime(item[field], "%d.%m.%Y").date())
                except ValueError as exc:
                    raise ValueError(
                        f"Rosstat OKTMO row {row_number}: invalid {field}={item[field]!r}"
                    ) from exc
            if parsed_dates[0] > parsed_dates[1]:
                item["_source_row_number"] = str(row_number)
                item["_source_quality_issues"] = ["valid_from_after_valid_to"]
            item["oktmo_code"] = "".join(item[key] for key in fields[:4])
            result.append(item)
        return result

    def fetch_dataset(self, *, dataset_id: str, passport_url: str, raw_dir: str,
                      timeout: float = 30.0,
                      on_snapshot: Callable[[RawSnapshot], None] | None = None
                      ) -> tuple[RosstatDataset, list[RawSnapshot]]:
        passport = self.transport.get(passport_url, headers={"Accept": "text/html"}, timeout=timeout)
        if passport.status_code != 200:
            raise RuntimeError(f"Rosstat passport HTTP {passport.status_code}: {passport.text[:300]}")
        p_snapshot = save_raw_snapshot(
            source_key=f"{self.source_key}_{dataset_id}_passport",
            method="GET", response=passport, raw_dir=raw_dir, suffix="html",
        )
        if on_snapshot:
            on_snapshot(p_snapshot)
        data_url = self.resolve_latest_data_url(passport.text, passport.url)
        data = self.transport.get(data_url, headers={"Accept": "text/csv,*/*"}, timeout=timeout)
        if data.status_code != 200:
            raise RuntimeError(f"Rosstat data HTTP {data.status_code}: {data.text[:300]}")
        d_snapshot = save_raw_snapshot(
            source_key=f"{self.source_key}_{dataset_id}_data",
            method="GET", response=data, raw_dir=raw_dir, suffix="csv",
        )
        if on_snapshot:
            on_snapshot(d_snapshot)
        rows = self.parse_csv(data.content)
        if not rows:
            raise ValueError("Rosstat dataset is empty")
        return RosstatDataset(dataset_id, passport.url, data_url, rows), [p_snapshot, d_snapshot]

    def fetch_oktmo(self, *, raw_dir: str, timeout: float = 30.0,
                    on_snapshot: Callable[[RawSnapshot], None] | None = None
                    ) -> tuple[RosstatDataset, list[RawSnapshot]]:
        return self.fetch_dataset(
            dataset_id="7708234640-oktmo",
            passport_url=OKTMO_PASSPORT_URL,
            raw_dir=raw_dir,
            timeout=timeout,
            on_snapshot=on_snapshot,
        )

    @staticmethod
    def filter_rows_containing(rows: list[dict[str, str]], needle: str) -> list[dict[str, str]]:
        n = needle.casefold()
        return [row for row in rows if any(n in str(v).casefold() for v in row.values())]

    def healthcheck(self, *, raw_dir: str, timeout: float = 30.0) -> dict[str, Any]:
        try:
            dataset, snapshots = self.fetch_oktmo(raw_dir=raw_dir, timeout=timeout)
            kaluga_rows = [
                row for row in dataset.rows
                if row.get("subject_code") == self.kaluga_subject_code
            ]
            quality_issues = [
                row for row in dataset.rows if row.get("_source_quality_issues")
            ]
            kaluga_issues = [
                row for row in kaluga_rows if row.get("_source_quality_issues")
            ]
            if not kaluga_rows:
                raise ValueError(
                    f"Rosstat OKTMO dataset has no rows for official subject code {self.kaluga_subject_code}"
                )
            return {
                "source": self.source_key,
                "ok": True,
                "dataset_id": dataset.dataset_id,
                "records": len(dataset.rows),
                "kaluga_subject_records": len(kaluga_rows),
                "published_version": dataset.published_version,
                "latest_advertised_file": True,
                "quality_status": "warnings" if quality_issues else "clean",
                "source_quality_issue_count": len(quality_issues),
                "kaluga_quality_issue_count": len(kaluga_issues),
                "quality_issue_samples": [
                    {
                        "source_row": row["_source_row_number"],
                        "oktmo_code": row["oktmo_code"],
                        "valid_from": row["valid_from"],
                        "valid_to": row["valid_to"],
                    }
                    for row in quality_issues[:20]
                ],
                "data_url": dataset.data_url,
                "use_terms": dataset.use_terms,
                "use_terms_url": dataset.use_terms_url,
                "source_attribution": dataset.passport_url,
                "snapshots": [s.to_dict() for s in snapshots],
            }
        except Exception as exc:
            return {
                "source": self.source_key,
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

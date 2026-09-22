from __future__ import annotations

from dataclasses import dataclass, asdict
from html.parser import HTMLParser
from urllib.parse import urljoin
from typing import Any
import csv
import io

from .base import HttpTransport, RequestsTransport, RawSnapshot, save_raw_snapshot

OKTMO_PASSPORT_URL = "https://rosstat.gov.ru/opendata/7708234640-oktmo"


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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RosstatOpenDataAdapter:
    source_key = "rosstat_opendata"

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
        sample = text[:8192]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
            reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        except csv.Error:
            reader = csv.DictReader(io.StringIO(text), delimiter=";")
        if not reader.fieldnames:
            raise ValueError("Rosstat CSV has no header")
        return [
            {str(k).strip(): (v.strip() if isinstance(v, str) else "") for k, v in row.items() if k is not None}
            for row in reader
        ]

    def fetch_dataset(self, *, dataset_id: str, passport_url: str, raw_dir: str,
                      timeout: float = 30.0) -> tuple[RosstatDataset, list[RawSnapshot]]:
        passport = self.transport.get(passport_url, headers={"Accept": "text/html"}, timeout=timeout)
        if passport.status_code != 200:
            raise RuntimeError(f"Rosstat passport HTTP {passport.status_code}: {passport.text[:300]}")
        p_snapshot = save_raw_snapshot(
            source_key=f"{self.source_key}_{dataset_id}_passport",
            method="GET", response=passport, raw_dir=raw_dir, suffix="html",
        )
        data_url = self.resolve_latest_data_url(passport.text, passport.url)
        data = self.transport.get(data_url, headers={"Accept": "text/csv,*/*"}, timeout=timeout)
        if data.status_code != 200:
            raise RuntimeError(f"Rosstat data HTTP {data.status_code}: {data.text[:300]}")
        d_snapshot = save_raw_snapshot(
            source_key=f"{self.source_key}_{dataset_id}_data",
            method="GET", response=data, raw_dir=raw_dir, suffix="csv",
        )
        rows = self.parse_csv(data.content)
        if not rows:
            raise ValueError("Rosstat dataset is empty")
        return RosstatDataset(dataset_id, passport.url, data_url, rows), [p_snapshot, d_snapshot]

    def fetch_oktmo(self, *, raw_dir: str, timeout: float = 30.0) -> tuple[RosstatDataset, list[RawSnapshot]]:
        return self.fetch_dataset(
            dataset_id="7708234640-oktmo",
            passport_url=OKTMO_PASSPORT_URL,
            raw_dir=raw_dir,
            timeout=timeout,
        )

    @staticmethod
    def filter_rows_containing(rows: list[dict[str, str]], needle: str) -> list[dict[str, str]]:
        n = needle.casefold()
        return [row for row in rows if any(n in str(v).casefold() for v in row.values())]

    def healthcheck(self, *, raw_dir: str, timeout: float = 30.0) -> dict[str, Any]:
        try:
            dataset, snapshots = self.fetch_oktmo(raw_dir=raw_dir, timeout=timeout)
            kaluga_rows = self.filter_rows_containing(dataset.rows, "Калуж")
            return {
                "source": self.source_key,
                "ok": True,
                "dataset_id": dataset.dataset_id,
                "records": len(dataset.rows),
                "kaluga_name_matches": len(kaluga_rows),
                "data_url": dataset.data_url,
                "snapshots": [s.to_dict() for s in snapshots],
            }
        except Exception as exc:
            return {
                "source": self.source_key,
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

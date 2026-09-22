from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Protocol
import json

import requests


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    url: str
    headers: Mapping[str, str]
    content: bytes

    @property
    def text(self) -> str:
        encoding = "utf-8"
        content_type = self.headers.get("content-type", "")
        if "charset=" in content_type:
            encoding = content_type.split("charset=", 1)[1].split(";", 1)[0].strip()
        return self.content.decode(encoding, errors="replace")


class HttpTransport(Protocol):
    def get(self, url: str, *, params: Mapping[str, Any] | None = None,
            headers: Mapping[str, str] | None = None, timeout: float = 30.0) -> HttpResponse: ...

    def post(self, url: str, *, data: Mapping[str, Any] | str | bytes | None = None,
             headers: Mapping[str, str] | None = None, timeout: float = 30.0) -> HttpResponse: ...


class RequestsTransport:
    def __init__(self, user_agent: str = "ZemlyaRadar/0.2 (source-audit)", retries: int = 2):
        self.user_agent = user_agent
        self.retries = retries
        self.session = requests.Session()

    def _request(self, method: str, url: str, *, timeout: float,
                 headers: Mapping[str, str] | None = None, **kwargs: Any) -> HttpResponse:
        merged_headers = {"User-Agent": self.user_agent, "Accept": "*/*"}
        if headers:
            merged_headers.update(headers)
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                r = self.session.request(method, url, headers=merged_headers, timeout=timeout, **kwargs)
                if r.status_code in {500, 502, 503, 504} and attempt < self.retries:
                    continue
                return HttpResponse(r.status_code, r.url, dict(r.headers), r.content)
            except requests.RequestException as exc:
                last_exc = exc
                if attempt >= self.retries:
                    raise
        assert last_exc is not None
        raise last_exc

    def get(self, url: str, *, params: Mapping[str, Any] | None = None,
            headers: Mapping[str, str] | None = None, timeout: float = 30.0) -> HttpResponse:
        return self._request("GET", url, params=params, headers=headers, timeout=timeout)

    def post(self, url: str, *, data: Mapping[str, Any] | str | bytes | None = None,
             headers: Mapping[str, str] | None = None, timeout: float = 30.0) -> HttpResponse:
        return self._request("POST", url, data=data, headers=headers, timeout=timeout)


@dataclass
class RawSnapshot:
    source_key: str
    fetched_at: str
    request_method: str
    request_url: str
    status_code: int
    content_type: str | None
    byte_count: int
    sha256: str
    raw_path: str
    request_payload_sha256: str | None = None
    request_payload: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save_raw_snapshot(*, source_key: str, method: str, response: HttpResponse,
                      raw_dir: str | Path, suffix: str, request_payload: str | None = None) -> RawSnapshot:
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    digest = sha256(response.content).hexdigest()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{source_key}_{stamp}_{digest[:12]}.{suffix.lstrip('.')}"
    raw_path = raw_dir / filename
    raw_path.write_bytes(response.content)

    request_digest = sha256(request_payload.encode("utf-8")).hexdigest() if request_payload is not None else None
    snapshot = RawSnapshot(
        source_key=source_key,
        fetched_at=utc_now_iso(),
        request_method=method,
        request_url=response.url,
        status_code=response.status_code,
        content_type=response.headers.get("content-type"),
        byte_count=len(response.content),
        sha256=digest,
        raw_path=str(raw_path),
        request_payload_sha256=request_digest,
        request_payload=request_payload,
    )
    meta_path = raw_path.with_suffix(raw_path.suffix + ".meta.json")
    meta_path.write_text(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return snapshot

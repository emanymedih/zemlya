from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from hashlib import md5, sha256
from pathlib import Path
from typing import Any
import json
import os
import shutil
import struct
import tempfile
import zlib

import requests

from .osm_ingest import StreamingDownloader, DownloadReceipt

GEOFABRIK_INDEX_URL = "https://download.geofabrik.de/index-v1-nogeom.json"
REGION_ID = "central-fed-district"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while True:
        if pos >= len(buf) or shift >= 70:
            raise ValueError("Invalid protobuf varint")
        b = buf[pos]
        pos += 1
        value |= (b & 0x7F) << shift
        if not (b & 0x80):
            return value, pos
        shift += 7


def _iter_proto_fields(buf: bytes):
    pos = 0
    while pos < len(buf):
        key, pos = _read_varint(buf, pos)
        field_no, wire = key >> 3, key & 0x07
        if wire == 0:
            value, pos = _read_varint(buf, pos)
            yield field_no, wire, value
        elif wire == 1:
            if pos + 8 > len(buf):
                raise ValueError("Truncated protobuf fixed64")
            yield field_no, wire, buf[pos:pos+8]
            pos += 8
        elif wire == 2:
            length, pos = _read_varint(buf, pos)
            end = pos + length
            if end > len(buf):
                raise ValueError("Truncated protobuf bytes field")
            yield field_no, wire, buf[pos:end]
            pos = end
        elif wire == 5:
            if pos + 4 > len(buf):
                raise ValueError("Truncated protobuf fixed32")
            yield field_no, wire, buf[pos:pos+4]
            pos += 4
        else:
            raise ValueError(f"Unsupported protobuf wire type: {wire}")


@dataclass(frozen=True)
class GeofabrikRegionRecord:
    region_id: str
    name: str
    parent: str | None
    pbf_url: str
    index_url: str

    @property
    def md5_url(self) -> str:
        return self.pbf_url + ".md5"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GeofabrikIndexAdapter:
    """Read Geofabrik's documented machine-readable download index."""

    def __init__(self, index_url: str = GEOFABRIK_INDEX_URL, session: requests.Session | None = None):
        self.index_url = index_url
        self.session = session or requests.Session()

    @staticmethod
    def parse_region(payload: bytes | str, region_id: str = REGION_ID, *, index_url: str = GEOFABRIK_INDEX_URL) -> GeofabrikRegionRecord:
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        raw = json.loads(payload)
        features = raw.get("features")
        if not isinstance(features, list):
            raise ValueError("Geofabrik index missing features[]")
        matches = []
        for feature in features:
            props = (feature or {}).get("properties") or {}
            if props.get("id") == region_id:
                matches.append(props)
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one Geofabrik region {region_id!r}, found {len(matches)}")
        props = matches[0]
        urls = props.get("urls") or {}
        pbf = urls.get("pbf")
        if not isinstance(pbf, str) or not pbf.endswith(".osm.pbf"):
            raise ValueError(f"Geofabrik region {region_id!r} has no valid pbf URL")
        return GeofabrikRegionRecord(
            region_id=region_id,
            name=str(props.get("name") or region_id),
            parent=props.get("parent"),
            pbf_url=pbf,
            index_url=index_url,
        )

    def fetch_region(self, region_id: str = REGION_ID, *, timeout: tuple[float, float] = (20.0, 60.0)) -> tuple[GeofabrikRegionRecord, bytes]:
        response = self.session.get(
            self.index_url,
            headers={"User-Agent": "ZemlyaRadar/0.4 (Geofabrik PBF ingestion)", "Accept": "application/json"},
            timeout=timeout,
        )
        response.raise_for_status()
        record = self.parse_region(response.content, region_id, index_url=response.url)
        return record, response.content


@dataclass(frozen=True)
class PbfHeaderInfo:
    blob_type: str
    required_features: list[str]
    optional_features: list[str]
    writing_program: str | None
    source: str | None
    replication_timestamp: int | None
    replication_sequence_number: int | None
    replication_base_url: str | None

    @property
    def replication_timestamp_iso(self) -> str | None:
        if self.replication_timestamp is None:
            return None
        return datetime.fromtimestamp(self.replication_timestamp, tz=timezone.utc).isoformat(timespec="seconds")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["replication_timestamp_iso"] = self.replication_timestamp_iso
        return d


def parse_pbf_header(path: str | Path) -> PbfHeaderInfo:
    path = Path(path)
    with path.open("rb") as f:
        size_raw = f.read(4)
        if len(size_raw) != 4:
            raise ValueError("Truncated PBF: missing BlobHeader size")
        header_len = struct.unpack(">I", size_raw)[0]
        if header_len <= 0 or header_len > 64 * 1024:
            raise ValueError(f"Invalid PBF BlobHeader length: {header_len}")
        blob_header = f.read(header_len)
        if len(blob_header) != header_len:
            raise ValueError("Truncated PBF BlobHeader")

        blob_type = None
        data_size = None
        for field_no, wire, value in _iter_proto_fields(blob_header):
            if field_no == 1 and wire == 2:
                blob_type = value.decode("utf-8")
            elif field_no == 3 and wire == 0:
                data_size = int(value)
        if blob_type != "OSMHeader":
            raise ValueError(f"First PBF blob type is {blob_type!r}, expected 'OSMHeader'")
        if data_size is None or data_size <= 0 or data_size > 64 * 1024 * 1024:
            raise ValueError(f"Invalid PBF blob data size: {data_size}")
        blob = f.read(data_size)
        if len(blob) != data_size:
            raise ValueError("Truncated PBF first Blob")

    raw_payload = None
    raw_size = None
    zlib_payload = None
    for field_no, wire, value in _iter_proto_fields(blob):
        if field_no == 1 and wire == 2:
            raw_payload = value
        elif field_no == 2 and wire == 0:
            raw_size = int(value)
        elif field_no == 3 and wire == 2:
            zlib_payload = value
    if raw_payload is not None:
        header_block = raw_payload
    elif zlib_payload is not None:
        header_block = zlib.decompress(zlib_payload)
        if raw_size is not None and len(header_block) != raw_size:
            raise ValueError(f"PBF header raw_size mismatch: expected {raw_size}, got {len(header_block)}")
    else:
        raise ValueError("Unsupported PBF first Blob compression (expected raw or zlib_data)")

    required: list[str] = []
    optional: list[str] = []
    writing_program = source = base_url = None
    timestamp = sequence = None
    for field_no, wire, value in _iter_proto_fields(header_block):
        if field_no == 4 and wire == 2:
            required.append(value.decode("utf-8"))
        elif field_no == 5 and wire == 2:
            optional.append(value.decode("utf-8"))
        elif field_no == 16 and wire == 2:
            writing_program = value.decode("utf-8")
        elif field_no == 17 and wire == 2:
            source = value.decode("utf-8")
        elif field_no == 32 and wire == 0:
            timestamp = int(value)
        elif field_no == 33 and wire == 0:
            sequence = int(value)
        elif field_no == 34 and wire == 2:
            base_url = value.decode("utf-8")

    if "OsmSchema-V0.6" not in required:
        raise ValueError(f"PBF missing required OsmSchema-V0.6 feature; required={required}")
    return PbfHeaderInfo(
        blob_type=blob_type,
        required_features=required,
        optional_features=optional,
        writing_program=writing_program,
        source=source,
        replication_timestamp=timestamp,
        replication_sequence_number=sequence,
        replication_base_url=base_url,
    )


def _parse_md5_sidecar(content: bytes, expected_filename: str | None = None) -> str:
    text = content.decode("ascii", errors="strict").strip()
    if not text:
        raise ValueError("Empty MD5 sidecar")
    parts = text.split()
    digest = parts[0].lower()
    if len(digest) != 32 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError(f"Invalid MD5 digest: {digest!r}")
    if expected_filename and len(parts) >= 2:
        name = parts[-1].lstrip("*")
        if Path(name).name != expected_filename:
            raise ValueError(f"MD5 sidecar filename mismatch: expected {expected_filename}, got {name}")
    return digest


@dataclass(frozen=True)
class GeofabrikPbfReleaseManifest:
    source: str
    region_id: str
    region_name: str
    index_url: str
    pbf_url: str
    md5_url: str
    release_id: str
    created_at: str
    pbf: DownloadReceipt
    publisher_md5: str
    md5_verified: bool
    header: PbfHeaderInfo
    gdal_layers: list[str]
    index_relative_path: str
    md5_relative_path: str
    index_sha256: str
    license_note: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["header"]["replication_timestamp_iso"] = self.header.replication_timestamp_iso
        return d


class GeofabrikPbfIngestor:
    def __init__(self, root_dir: str | Path, *, downloader: StreamingDownloader | None = None,
                 index: GeofabrikIndexAdapter | None = None, session: requests.Session | None = None):
        self.root_dir = Path(root_dir)
        self.releases_dir = self.root_dir / "releases"
        self.current_path = self.root_dir / "current.json"
        self.downloader = downloader or StreamingDownloader(user_agent="ZemlyaRadar/0.4 (Geofabrik PBF ingestion)")
        self.index = index or GeofabrikIndexAdapter(session=session)
        self.session = session or requests.Session()

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise

    def _fetch_md5(self, url: str, *, timeout: tuple[float, float] = (20.0, 60.0)) -> tuple[str, bytes]:
        r = self.session.get(url, headers={"User-Agent":"ZemlyaRadar/0.4 (Geofabrik PBF ingestion)"}, timeout=timeout)
        r.raise_for_status()
        return _parse_md5_sidecar(r.content, Path(url[:-4] if url.endswith('.md5') else url).name), r.content

    @staticmethod
    def _gdal_validate(path: Path) -> list[str]:
        import pyogrio
        layers = [str(row[0]) for row in pyogrio.list_layers(path)]
        expected = {"points", "lines", "multilinestrings", "multipolygons", "other_relations"}
        missing = sorted(expected - set(layers))
        if missing:
            raise ValueError(f"GDAL OSM driver opened PBF but expected layers are missing: {missing}; layers={layers}")
        return layers

    def healthcheck(self, *, region_id: str = REGION_ID) -> dict[str, Any]:
        try:
            region, raw_index = self.index.fetch_region(region_id)
            publisher_md5, sidecar = self._fetch_md5(region.md5_url)
            return {
                "source": "Geofabrik / OpenStreetMap raw PBF",
                "ok": True,
                "region": region.to_dict(),
                "publisher_md5": publisher_md5,
                "index_sha256": sha256(raw_index).hexdigest(),
                "md5_sidecar_sha256": sha256(sidecar).hexdigest(),
            }
        except Exception as exc:
            return {
                "source": "Geofabrik / OpenStreetMap raw PBF",
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    def current_manifest(self) -> GeofabrikPbfReleaseManifest | None:
        if not self.current_path.exists():
            return None
        pointer = json.loads(self.current_path.read_text(encoding="utf-8"))
        manifest_path = Path(pointer["manifest"])
        if not manifest_path.exists():
            raise FileNotFoundError(f"current.json points to missing manifest: {manifest_path}")
        return self._from_raw(json.loads(manifest_path.read_text(encoding="utf-8")))

    def verify_current(self) -> dict[str, Any]:
        current = self.current_manifest()
        if current is None:
            return {"ok": False, "error_type": "FileNotFoundError", "error": "No current Geofabrik PBF release"}
        pbf_path = self.releases_dir / current.release_id / "source.osm.pbf"
        try:
            if not pbf_path.exists():
                raise FileNotFoundError(str(pbf_path))
            h_sha = sha256()
            h_md5 = md5()
            byte_count = 0
            with pbf_path.open("rb") as f:
                for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
                    h_sha.update(chunk)
                    h_md5.update(chunk)
                    byte_count += len(chunk)
            actual_sha = h_sha.hexdigest()
            actual_md5 = h_md5.hexdigest()
            if actual_sha != current.pbf.sha256:
                raise ValueError(f"SHA-256 mismatch: manifest={current.pbf.sha256}, actual={actual_sha}")
            if actual_md5 != current.publisher_md5:
                raise ValueError(f"MD5 mismatch: publisher={current.publisher_md5}, actual={actual_md5}")
            if byte_count != current.pbf.byte_count:
                raise ValueError(f"Byte-count mismatch: manifest={current.pbf.byte_count}, actual={byte_count}")
            header = parse_pbf_header(pbf_path)
            layers = self._gdal_validate(pbf_path)
            return {
                "ok": True,
                "release_id": current.release_id,
                "path": str(pbf_path),
                "byte_count": byte_count,
                "sha256": actual_sha,
                "md5": actual_md5,
                "replication_timestamp_iso": header.replication_timestamp_iso,
                "gdal_layers": layers,
            }
        except Exception as exc:
            return {
                "ok": False,
                "release_id": current.release_id,
                "path": str(pbf_path),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    def ingest(self, *, region_id: str = REGION_ID, direct_pbf_url: str | None = None,
               direct_md5_url: str | None = None, index_payload: bytes | None = None) -> GeofabrikPbfReleaseManifest:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.releases_dir.mkdir(parents=True, exist_ok=True)
        staging = self.root_dir / "staging"
        staging.mkdir(parents=True, exist_ok=True)

        if direct_pbf_url is None:
            if index_payload is None:
                region, raw_index = self.index.fetch_region(region_id)
            else:
                raw_index = index_payload
                region = GeofabrikIndexAdapter.parse_region(raw_index, region_id)
            pbf_url = region.pbf_url
            md5_url = region.md5_url
        else:
            pbf_url = direct_pbf_url
            md5_url = direct_md5_url or direct_pbf_url + ".md5"
            region = GeofabrikRegionRecord(region_id, region_id, None, pbf_url, "direct")
            raw_index = index_payload or b"{}"

        publisher_md5, raw_md5_sidecar = self._fetch_md5(md5_url)
        current = self.current_manifest()
        if current is not None and current.publisher_md5.lower() == publisher_md5.lower():
            current_file = self.releases_dir / current.release_id / "source.osm.pbf"
            if current_file.exists() and current.pbf.sha256:
                return current

        pbf_name = Path(pbf_url).name
        staging_pbf = staging / pbf_name
        receipt = self.downloader.download(pbf_url, staging_pbf)
        actual_md5 = receipt.md5
        if actual_md5 is None:
            h = md5()
            with staging_pbf.open("rb") as f:
                for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
                    h.update(chunk)
            actual_md5 = h.hexdigest()
        if actual_md5.lower() != publisher_md5.lower():
            staging_pbf.unlink(missing_ok=True)
            raise ValueError(f"Publisher MD5 mismatch: expected {publisher_md5}, got {actual_md5}")

        publisher_md5_after, _ = self._fetch_md5(md5_url)
        if publisher_md5_after.lower() != publisher_md5.lower():
            staging_pbf.unlink(missing_ok=True)
            raise RuntimeError(
                "Geofabrik PBF changed while it was being downloaded; refusing to promote a moving 'latest' artifact"
            )

        header = parse_pbf_header(staging_pbf)
        layers = self._gdal_validate(staging_pbf)
        release_id = receipt.sha256[:12]
        release_dir = self.releases_dir / release_id
        manifest_path = release_dir / "manifest.json"
        final_pbf = release_dir / "source.osm.pbf"

        if manifest_path.exists() and final_pbf.exists():
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            if existing.get("pbf", {}).get("sha256") == receipt.sha256:
                staging_pbf.unlink(missing_ok=True)
                self._write_json_atomic(self.current_path, {"release_id": release_id, "manifest": str(manifest_path)})
                return self._from_raw(existing)

        tmp_release = self.releases_dir / (release_id + ".tmp")
        if tmp_release.exists():
            shutil.rmtree(tmp_release)
        tmp_release.mkdir(parents=True)
        try:
            os.replace(staging_pbf, tmp_release / "source.osm.pbf")
            metadata_dir = tmp_release / "metadata"
            metadata_dir.mkdir(parents=True, exist_ok=True)
            index_rel = "metadata/index-v1-nogeom.json"
            md5_rel = "metadata/publisher.md5"
            (tmp_release / index_rel).write_bytes(raw_index)
            (tmp_release / md5_rel).write_bytes(raw_md5_sidecar)
            promoted_receipt = DownloadReceipt(**{**receipt.to_dict(), "path": str(final_pbf)})
            manifest = GeofabrikPbfReleaseManifest(
                source="Geofabrik / OpenStreetMap raw PBF",
                region_id=region.region_id,
                region_name=region.name,
                index_url=region.index_url,
                pbf_url=pbf_url,
                md5_url=md5_url,
                release_id=release_id,
                created_at=_utc_now(),
                pbf=promoted_receipt,
                publisher_md5=publisher_md5,
                md5_verified=True,
                header=header,
                gdal_layers=layers,
                index_relative_path=index_rel,
                md5_relative_path=md5_rel,
                index_sha256=sha256(raw_index).hexdigest(),
                license_note="OpenStreetMap data © OpenStreetMap contributors, ODbL; Geofabrik extract.",
            )
            self._write_json_atomic(tmp_release / "manifest.json", manifest.to_dict())
            if release_dir.exists():
                shutil.rmtree(release_dir)
            os.replace(tmp_release, release_dir)
            self._write_json_atomic(self.current_path, {"release_id": release_id, "manifest": str(manifest_path)})
            return manifest
        except Exception:
            shutil.rmtree(tmp_release, ignore_errors=True)
            staging_pbf.unlink(missing_ok=True)
            raise

    @staticmethod
    def _from_raw(raw: dict[str, Any]) -> GeofabrikPbfReleaseManifest:
        hdr = dict(raw["header"])
        hdr.pop("replication_timestamp_iso", None)
        return GeofabrikPbfReleaseManifest(
            source=raw["source"],
            region_id=raw["region_id"],
            region_name=raw["region_name"],
            index_url=raw["index_url"],
            pbf_url=raw["pbf_url"],
            md5_url=raw["md5_url"],
            release_id=raw["release_id"],
            created_at=raw["created_at"],
            pbf=DownloadReceipt(**raw["pbf"]),
            publisher_md5=raw["publisher_md5"],
            md5_verified=raw["md5_verified"],
            header=PbfHeaderInfo(**hdr),
            gdal_layers=list(raw["gdal_layers"]),
            index_relative_path=raw["index_relative_path"],
            md5_relative_path=raw["md5_relative_path"],
            index_sha256=raw["index_sha256"],
            license_note=raw["license_note"],
        )

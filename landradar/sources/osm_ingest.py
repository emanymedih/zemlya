from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from hashlib import md5, sha256
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile

import requests

from .osm import OSMGeofabrikCatalogAdapter, OSMGeofabrikGpkgAdapter


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_filename_from_url(url: str) -> str:
    name = Path(urlparse(url).path).name
    if not name or name in {".", ".."}:
        raise ValueError(f"Cannot derive filename from URL: {url}")
    return name


@dataclass(frozen=True)
class DownloadReceipt:
    url: str
    path: str
    fetched_at: str
    status_code: int
    byte_count: int
    content_length: int | None
    sha256: str
    etag: str | None
    last_modified: str | None
    md5: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GpkgValidation:
    gpkg_path: str
    sqlite_integrity: str
    layers: list[str]
    road_layer: str
    road_crs: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GeofabrikReleaseManifest:
    source: str
    catalog_url: str
    extract_url: str
    release_id: str
    created_at: str
    archive: DownloadReceipt
    archive_zip_crc_ok: bool
    gpkg_relative_path: str
    gpkg_byte_count: int
    gpkg_archive_uncompressed_bytes: int
    gpkg_sha256: str
    validation: GpkgValidation
    license_note: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StreamingDownloader:
    def __init__(self, *, user_agent: str = "ZemlyaRadar/0.3 (Geofabrik ingestion)", chunk_size: int = 4 * 1024 * 1024):
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        self.user_agent = user_agent
        self.chunk_size = chunk_size

    def download(self, url: str, dest: str | Path, *, timeout: tuple[float, float] = (20.0, 180.0)) -> DownloadReceipt:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".part")
        tmp.unlink(missing_ok=True)
        h = sha256()
        h_md5 = md5()
        byte_count = 0
        try:
            with requests.get(
                url,
                headers={"User-Agent": self.user_agent, "Accept": "application/octet-stream,*/*"},
                timeout=timeout,
                stream=True,
                allow_redirects=True,
            ) as response:
                response.raise_for_status()
                content_length = response.headers.get("Content-Length")
                expected = int(content_length) if content_length and content_length.isdigit() else None
                if expected is not None:
                    free = shutil.disk_usage(dest.parent).free
                    required = expected + 512 * 1024 * 1024
                    if free < required:
                        raise OSError(
                            f"Insufficient free disk space for download: need at least {required} bytes, have {free}"
                        )
                with tmp.open("wb") as f:
                    for chunk in response.iter_content(chunk_size=self.chunk_size):
                        if not chunk:
                            continue
                        f.write(chunk)
                        h.update(chunk)
                        h_md5.update(chunk)
                        byte_count += len(chunk)
                    f.flush()
                    os.fsync(f.fileno())
                if expected is not None and byte_count != expected:
                    raise IOError(f"Content-Length mismatch: expected {expected}, got {byte_count}")
                os.replace(tmp, dest)
                return DownloadReceipt(
                    url=response.url,
                    path=str(dest),
                    fetched_at=_utc_now(),
                    status_code=response.status_code,
                    byte_count=byte_count,
                    content_length=expected,
                    sha256=h.hexdigest(),
                    etag=response.headers.get("ETag"),
                    last_modified=response.headers.get("Last-Modified"),
                    md5=h_md5.hexdigest(),
                )
        except Exception:
            tmp.unlink(missing_ok=True)
            raise


class GeofabrikGpkgIngestor:
    source_key = "osm_geofabrik_gpkg"

    def __init__(self, root_dir: str | Path, *, downloader: StreamingDownloader | None = None,
                 catalog: OSMGeofabrikCatalogAdapter | None = None):
        self.root_dir = Path(root_dir)
        self.releases_dir = self.root_dir / "releases"
        self.current_path = self.root_dir / "current.json"
        self.downloader = downloader or StreamingDownloader()
        self.catalog = catalog or OSMGeofabrikCatalogAdapter()

    @staticmethod
    def _sha256_file(path: Path) -> str:
        h = sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _validate_zip_and_find_gpkg(archive: Path) -> tuple[str, int]:
        if not zipfile.is_zipfile(archive):
            raise ValueError("Downloaded Geofabrik artifact is not a valid ZIP")
        with zipfile.ZipFile(archive) as zf:
            bad = zf.testzip()
            if bad is not None:
                raise ValueError(f"ZIP CRC failure in member: {bad}")
            gpkg_members = [n for n in zf.namelist() if n.lower().endswith(".gpkg") and not n.endswith("/")]
            if len(gpkg_members) != 1:
                raise ValueError(f"Expected exactly one .gpkg in archive, found {len(gpkg_members)}")
            member = gpkg_members[0]
            target = Path(member)
            if target.is_absolute() or ".." in target.parts:
                raise ValueError(f"Unsafe archive member path: {member}")
            info = zf.getinfo(member)
            return member, int(info.file_size)

    @staticmethod
    def _extract_member(archive: Path, member: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as zf, zf.open(member) as src, dest.open("wb") as out:
            shutil.copyfileobj(src, out, length=8 * 1024 * 1024)
            out.flush()
            os.fsync(out.fileno())

    @staticmethod
    def _sqlite_integrity(path: Path) -> str:
        uri = f"file:{path.resolve().as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
            result = str(row[0]) if row else ""
            if result.casefold() != "ok":
                raise ValueError(f"SQLite integrity_check failed: {result}")
            required = {"gpkg_contents", "gpkg_spatial_ref_sys", "gpkg_geometry_columns"}
            names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            missing = sorted(required - names)
            if missing:
                raise ValueError(f"Missing required GeoPackage tables: {missing}")
            return result
        finally:
            conn.close()

    @classmethod
    def validate_gpkg(cls, gpkg_path: str | Path) -> GpkgValidation:
        gpkg_path = Path(gpkg_path)
        sqlite_status = cls._sqlite_integrity(gpkg_path)
        adapter = OSMGeofabrikGpkgAdapter(str(gpkg_path))
        layers = adapter.list_layers()
        road_layer = adapter.find_road_layer()

        import pyogrio
        info = pyogrio.read_info(str(gpkg_path), layer=road_layer)
        crs = info.get("crs")
        if not crs:
            raise ValueError("OSM GeoPackage road layer has no CRS")
        from pyproj import CRS
        parsed = CRS.from_user_input(crs)
        if parsed.to_epsg() != 4326:
            raise ValueError(f"Unexpected OSM GeoPackage road CRS: {crs}; expected EPSG:4326")
        return GpkgValidation(
            gpkg_path=str(gpkg_path),
            sqlite_integrity=sqlite_status,
            layers=layers,
            road_layer=road_layer,
            road_crs=parsed.to_string(),
        )

    def _write_json_atomic(self, path: Path, payload: dict[str, Any]) -> None:
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

    def ingest(self, *, catalog_raw_dir: str | Path | None = None, timeout: float = 30.0,
               extract_url: str | None = None, catalog_url: str | None = None) -> GeofabrikReleaseManifest:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.releases_dir.mkdir(parents=True, exist_ok=True)

        if extract_url is None:
            raw_dir = Path(catalog_raw_dir) if catalog_raw_dir else self.root_dir / "catalog_raw"
            links, _ = self.catalog.fetch_catalog(raw_dir=str(raw_dir), timeout=timeout)
            extract_url = links.gpkg_url
            catalog_url = links.page_url
        elif catalog_url is None:
            catalog_url = "injected"

        staging_dir = self.root_dir / "staging"
        staging_dir.mkdir(parents=True, exist_ok=True)
        archive_name = _safe_filename_from_url(extract_url)
        staging_archive = staging_dir / archive_name
        receipt = self.downloader.download(extract_url, staging_archive)
        member, uncompressed_bytes = self._validate_zip_and_find_gpkg(staging_archive)
        free_bytes = shutil.disk_usage(self.root_dir).free
        required_free = uncompressed_bytes + 512 * 1024 * 1024
        if free_bytes < required_free:
            staging_archive.unlink(missing_ok=True)
            raise OSError(
                f"Insufficient free disk space for GeoPackage extraction: need at least {required_free} bytes, have {free_bytes}"
            )

        release_id = receipt.sha256[:12]
        release_dir = self.releases_dir / release_id
        final_archive = release_dir / "source.zip"
        final_gpkg = release_dir / Path(member).name
        manifest_path = release_dir / "manifest.json"

        if manifest_path.exists():
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            if existing.get("archive", {}).get("sha256") == receipt.sha256 and final_gpkg.exists():
                staging_archive.unlink(missing_ok=True)
                self._write_json_atomic(self.current_path, {"release_id": release_id, "manifest": str(manifest_path)})
                return GeofabrikReleaseManifest(**{
                    **{k: existing[k] for k in ["source", "catalog_url", "extract_url", "release_id", "created_at", "archive_zip_crc_ok", "gpkg_relative_path", "gpkg_byte_count", "gpkg_archive_uncompressed_bytes", "gpkg_sha256", "license_note"]},
                    "archive": DownloadReceipt(**existing["archive"]),
                    "validation": GpkgValidation(**existing["validation"]),
                })

        tmp_release = self.releases_dir / (release_id + ".tmp")
        if tmp_release.exists():
            shutil.rmtree(tmp_release)
        tmp_release.mkdir(parents=True)
        try:
            tmp_archive = tmp_release / "source.zip"
            os.replace(staging_archive, tmp_archive)
            tmp_gpkg = tmp_release / Path(member).name
            self._extract_member(tmp_archive, member, tmp_gpkg)
            validation = self.validate_gpkg(tmp_gpkg)
            gpkg_sha = self._sha256_file(tmp_gpkg)
            gpkg_size = tmp_gpkg.stat().st_size

            promoted_receipt = DownloadReceipt(**{**receipt.to_dict(), "path": str(final_archive)})
            manifest = GeofabrikReleaseManifest(
                source="Geofabrik / OpenStreetMap",
                catalog_url=catalog_url,
                extract_url=extract_url,
                release_id=release_id,
                created_at=_utc_now(),
                archive=promoted_receipt,
                archive_zip_crc_ok=True,
                gpkg_relative_path=final_gpkg.name,
                gpkg_byte_count=gpkg_size,
                gpkg_archive_uncompressed_bytes=uncompressed_bytes,
                gpkg_sha256=gpkg_sha,
                validation=GpkgValidation(
                    gpkg_path=str(final_gpkg),
                    sqlite_integrity=validation.sqlite_integrity,
                    layers=validation.layers,
                    road_layer=validation.road_layer,
                    road_crs=validation.road_crs,
                ),
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
            staging_archive.unlink(missing_ok=True)
            raise

    def current_manifest(self) -> GeofabrikReleaseManifest | None:
        if not self.current_path.exists():
            return None
        pointer = json.loads(self.current_path.read_text(encoding="utf-8"))
        manifest_path = Path(pointer["manifest"])
        if not manifest_path.exists():
            raise FileNotFoundError(f"current.json points to missing manifest: {manifest_path}")
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        return GeofabrikReleaseManifest(
            source=raw["source"],
            catalog_url=raw["catalog_url"],
            extract_url=raw["extract_url"],
            release_id=raw["release_id"],
            created_at=raw["created_at"],
            archive=DownloadReceipt(**raw["archive"]),
            archive_zip_crc_ok=raw["archive_zip_crc_ok"],
            gpkg_relative_path=raw["gpkg_relative_path"],
            gpkg_byte_count=raw["gpkg_byte_count"],
            gpkg_archive_uncompressed_bytes=raw["gpkg_archive_uncompressed_bytes"],
            gpkg_sha256=raw["gpkg_sha256"],
            validation=GpkgValidation(**raw["validation"]),
            license_note=raw["license_note"],
        )

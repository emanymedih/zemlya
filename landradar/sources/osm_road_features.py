from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timezone
from functools import lru_cache
from importlib import metadata
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from time import perf_counter
from typing import Any
import warnings


TARGET_REGION_NAME = "Калужская область"
_CACHE_FORMAT = "geofabrik-road-extraction-cache/v2"


@dataclass(frozen=True)
class OSMRoadExtraction:
    boundary_osm_id: str
    boundary_name: str
    boundary_geometry_wkb_hex: str
    features: list[dict[str, Any]]
    candidate_count: int
    rejected_outside_boundary: int
    source_warnings: list[str]
    feature_version_available: bool
    feature_timestamp_available: bool
    feature_versions_available_count: int
    feature_timestamps_available_count: int
    extraction_duration_seconds: float
    cache_status: str = "disabled"
    cache_io_duration_seconds: float = 0.0
    cache_write_error: str | None = None
    source_stage_status: str = "not_staged"
    source_stage_duration_seconds: float = 0.0
    source_stage_error: str | None = None


class GeofabrikRoadFeatureAdapter:
    """Read highway ways inside the OSM-mapped target-region boundary."""

    source_key = "geofabrik_osm_road_features"

    @staticmethod
    @lru_cache(maxsize=1)
    def _extractor_fingerprint() -> str:
        inputs = {
            "adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "dependencies": {
                name: metadata.version(name) for name in ("pyogrio", "shapely", "osmium")
            },
            "osm_config_file": os.environ.get("OSM_CONFIG_FILE"),
            "accept_unclosed_ring": os.environ.get("OGR_GEOMETRY_ACCEPT_UNCLOSED_RING"),
        }
        config_file = inputs["osm_config_file"]
        if config_file:
            inputs["osm_config_sha256"] = hashlib.sha256(Path(config_file).read_bytes()).hexdigest()
        return hashlib.sha256(GeofabrikRoadFeatureAdapter._canonical_json(inputs)).hexdigest()

    @classmethod
    def _cache_path(cls, cache_dir: str | Path, source_sha256: str, region_name: str) -> Path:
        digest = source_sha256.casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Road extraction cache requires a SHA-256 source key")
        region_digest = hashlib.sha256(region_name.encode("utf-8")).hexdigest()[:12]
        return Path(cache_dir) / f"{digest}-{region_digest}-{cls._extractor_fingerprint()[:12]}.json.gz"

    @staticmethod
    def _cache_payload(extraction: OSMRoadExtraction) -> dict[str, Any]:
        return {
            "boundary_osm_id": extraction.boundary_osm_id,
            "boundary_name": extraction.boundary_name,
            "boundary_geometry_wkb_hex": extraction.boundary_geometry_wkb_hex,
            "features": extraction.features,
            "candidate_count": extraction.candidate_count,
            "rejected_outside_boundary": extraction.rejected_outside_boundary,
            "source_warnings": extraction.source_warnings,
            "feature_version_available": extraction.feature_version_available,
            "feature_timestamp_available": extraction.feature_timestamp_available,
            "feature_versions_available_count": extraction.feature_versions_available_count,
            "feature_timestamps_available_count": extraction.feature_timestamps_available_count,
        }

    @staticmethod
    def _canonical_json(value: Any) -> bytes:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")

    @classmethod
    def _load_cache(
        cls, path: Path, source_sha256: str, region_name: str,
    ) -> OSMRoadExtraction | None:
        try:
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                envelope = json.load(stream)
            payload = envelope["payload"]
            if (
                envelope.get("format") != _CACHE_FORMAT
                or envelope.get("source_pbf_sha256") != source_sha256.casefold()
                or envelope.get("region_name") != region_name
                or envelope.get("extractor_fingerprint") != cls._extractor_fingerprint()
                or hashlib.sha256(cls._canonical_json(payload)).hexdigest()
                != envelope.get("payload_sha256")
            ):
                return None
            return OSMRoadExtraction(
                **payload, extraction_duration_seconds=0.0,
                cache_status="hit",
            )
        except (OSError, EOFError, UnicodeError, ValueError, TypeError, KeyError):
            return None

    @classmethod
    def _write_cache(
        cls, path: Path, source_sha256: str, region_name: str,
        extraction: OSMRoadExtraction,
    ) -> None:
        payload = cls._cache_payload(extraction)
        envelope = {
            "format": _CACHE_FORMAT,
            "source_pbf_sha256": source_sha256.casefold(),
            "region_name": region_name,
            "extractor_fingerprint": cls._extractor_fingerprint(),
            "payload_sha256": hashlib.sha256(cls._canonical_json(payload)).hexdigest(),
            "payload": payload,
        }
        encoded = cls._canonical_json(envelope)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix=path.name + ".", suffix=".tmp", dir=path.parent,
        )
        try:
            with os.fdopen(fd, "wb") as raw:
                with gzip.GzipFile(
                    fileobj=raw, mode="wb", compresslevel=6, mtime=0,
                ) as stream:
                    stream.write(encoded)
            os.replace(temporary, path)
        except Exception:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise

    def _extract_staged(
        self, pbf_path: str | Path, source_sha256: str, region_name: str,
    ) -> tuple[OSMRoadExtraction, float, str, str | None]:
        source = Path(pbf_path)
        stage_started = perf_counter()
        stage_dir: Path | None = None
        staged: Path | None = None
        stage_error: str | None = None
        try:
            required_bytes = source.stat().st_size
            stage_root = Path(os.environ.get("LANDRADAR_PBF_WORK_DIR") or tempfile.gettempdir())
            stage_root.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(stage_root).free < required_bytes:
                stage_error = (
                    f"Temporary storage has less than {required_bytes} bytes free"
                )
            else:
                stage_dir = Path(tempfile.mkdtemp(prefix="landradar-pbf-", dir=stage_root))
                candidate = stage_dir / source.name
                shutil.copyfile(source, candidate)
                with candidate.open("rb") as stream:
                    staged_sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
                if staged_sha256.casefold() != source_sha256.casefold():
                    raise ValueError(
                        "Staged Geofabrik PBF SHA-256 differs from the verified source"
                    )
                staged = candidate
        except OSError as exc:
            stage_error = f"{type(exc).__name__}: {exc}"
        except Exception:
            if stage_dir is not None:
                shutil.rmtree(stage_dir, ignore_errors=True)
            raise

        if staged is None:
            if stage_dir is not None:
                shutil.rmtree(stage_dir, ignore_errors=True)
            with source.open("rb") as stream:
                direct_sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
            if direct_sha256.casefold() != source_sha256.casefold():
                raise ValueError("Direct Geofabrik PBF SHA-256 differs from the cache key")
            return (
                self.extract(source, region_name=region_name),
                round(perf_counter() - stage_started, 3),
                "fallback_direct",
                stage_error,
            )

        stage_duration = round(perf_counter() - stage_started, 3)
        try:
            return (
                self.extract(staged, region_name=region_name),
                stage_duration,
                "staged",
                None,
            )
        finally:
            if stage_dir is not None:
                shutil.rmtree(stage_dir, ignore_errors=True)

    def extract_cached(
        self, pbf_path: str | Path, *, cache_dir: str | Path,
        source_sha256: str, region_name: str = TARGET_REGION_NAME,
        stage_source: bool = True,
    ) -> OSMRoadExtraction:
        """Reuse verified features; stage_source=False requires a caller-verified PBF."""
        started = perf_counter()
        cache_path = self._cache_path(cache_dir, source_sha256, region_name)
        cache = self._load_cache(cache_path, source_sha256, region_name)
        if cache is not None:
            if stage_source:
                with Path(pbf_path).open("rb") as stream:
                    actual_sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
                if actual_sha256.casefold() != source_sha256.casefold():
                    raise ValueError("Geofabrik PBF SHA-256 differs from the cache key")
            return replace(
                cache,
                cache_io_duration_seconds=round(perf_counter() - started, 3),
                source_stage_status="skipped_cache_hit",
            )
        invalid_cache = cache_path.exists()
        if stage_source:
            extraction, stage_duration, stage_status, stage_error = self._extract_staged(
                pbf_path, source_sha256, region_name,
            )
        else:
            extraction = self.extract(pbf_path, region_name=region_name)
            stage_duration, stage_status, stage_error = 0.0, "verified_source", None
        write_error = None
        try:
            self._write_cache(cache_path, source_sha256, region_name, extraction)
        except OSError as exc:
            write_error = f"{type(exc).__name__}: {exc}"
        elapsed = perf_counter() - started
        return replace(
            extraction,
            cache_status="invalid_rebuilt" if invalid_cache else "miss",
            cache_io_duration_seconds=round(
                max(0.0, elapsed - extraction.extraction_duration_seconds - stage_duration), 3,
            ),
            cache_write_error=write_error,
            source_stage_status=stage_status,
            source_stage_duration_seconds=stage_duration,
            source_stage_error=stage_error,
        )

    @staticmethod
    def _read_way_metadata(pbf_path: str, way_ids: set[int]) -> dict[int, dict[str, Any]]:
        if not way_ids:
            return {}
        import osmium

        processor = osmium.FileProcessor(pbf_path, osmium.osm.WAY).with_filter(
            osmium.filter.IdFilter(way_ids)
        )
        metadata: dict[int, dict[str, Any]] = {}
        for way in processor:
            way_id = int(way.id)
            if way_id in metadata:
                raise ValueError(f"Duplicate OSM way metadata in PBF: {way_id}")
            timestamp = way.timestamp
            if timestamp is not None:
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                timestamp = timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            version = int(way.version) if way.version else None
            metadata[way_id] = {"osm_version": version, "osm_timestamp": timestamp}
        missing = sorted(way_ids - metadata.keys())
        if missing:
            raise ValueError(f"PBF metadata missing for selected OSM ways: {missing[:10]}")
        return metadata

    @staticmethod
    def _columns_as_lists(fields: list[str], arrays: list[Any]) -> dict[str, list[Any]]:
        if len(fields) != len(arrays):
            raise ValueError("GDAL OSM attribute field/array count mismatch")
        return {
            name: [value.item() if hasattr(value, "item") else value for value in values]
            for name, values in zip(fields, arrays)
        }

    def extract(self, pbf_path: str | Path, *,
                region_name: str = TARGET_REGION_NAME) -> OSMRoadExtraction:
        started = perf_counter()
        import pyogrio
        from shapely import from_wkb

        pbf_path = str(pbf_path)
        area_info = pyogrio.read_info(pbf_path, layer="multipolygons")
        if area_info.get("crs") != "EPSG:4326":
            raise ValueError(f"Unexpected OSM boundary CRS: {area_info.get('crs')!r}")
        source_warnings: list[str] = []
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", RuntimeWarning)
            _, _, boundary_wkbs, boundary_arrays = pyogrio.raw.read(
                pbf_path,
                layer="multipolygons",
                where="admin_level = '4' AND boundary = 'administrative'",
                columns=["osm_id", "name", "admin_level", "boundary"],
                return_fids=True,
            )
        source_warnings.extend(
            f"multipolygons: {str(item.message)}"
            for item in caught if issubclass(item.category, RuntimeWarning)
        )
        boundary_fields = self._columns_as_lists(
            ["osm_id", "name", "admin_level", "boundary"], boundary_arrays
        )
        matches = [
            index for index, name in enumerate(boundary_fields["name"])
            if name == region_name
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Expected one OSM level-4 boundary named {region_name!r}, "
                f"found {len(matches)}"
            )
        boundary_index = matches[0]
        boundary_wkb = boundary_wkbs[boundary_index]
        boundary = from_wkb(boundary_wkb)
        if boundary.is_empty or not boundary.is_valid:
            raise ValueError(f"OSM boundary geometry is empty or invalid: {region_name}")
        boundary_osm_id = str(boundary_fields["osm_id"][boundary_index])

        roads_info = pyogrio.read_info(pbf_path, layer="lines")
        if roads_info.get("crs") != "EPSG:4326":
            raise ValueError(f"Unexpected OSM roads CRS: {roads_info.get('crs')!r}")
        available_fields = [str(name) for name in roads_info["fields"]]
        required_fields = {"osm_id", "highway"}
        if not required_fields.issubset(available_fields):
            raise ValueError(f"OSM roads layer missing fields: {sorted(required_fields - set(available_fields))}")
        selected_fields = [
            name for name in (
                "osm_id", "name", "highway", "waterway", "aerialway",
                "barrier", "man_made", "railway", "z_order", "other_tags",
            ) if name in available_fields
        ]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", RuntimeWarning)
            _, _, road_wkbs, road_arrays = pyogrio.raw.read(
                pbf_path,
                layer="lines",
                where="highway IS NOT NULL",
                columns=selected_fields,
                mask=boundary,
            )
        source_warnings.extend(
            f"lines: {str(item.message)}"
            for item in caught if issubclass(item.category, RuntimeWarning)
        )
        road_data = self._columns_as_lists(selected_fields, road_arrays)
        features: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        rejected_outside = 0
        candidate_count = len(road_data["osm_id"])
        for index, raw_id in enumerate(road_data["osm_id"]):
            osm_id = str(raw_id)
            highway = road_data["highway"][index]
            if not osm_id.isdigit() or int(osm_id) <= 0:
                raise ValueError(f"Invalid OSM way id: {raw_id!r}")
            if not isinstance(highway, str) or not highway.strip():
                raise ValueError(f"Road way {osm_id} has an empty highway tag")
            if osm_id in seen_ids:
                raise ValueError(f"Duplicate OSM way id in selected roads: {osm_id}")
            seen_ids.add(osm_id)
            raw_geometry = road_wkbs[index]
            if raw_geometry is None:
                raise ValueError(f"Road way {osm_id} has no geometry")
            geometry = from_wkb(raw_geometry)
            if geometry.is_empty or not geometry.is_valid or geometry.geom_type != "LineString":
                raise ValueError(f"Road way {osm_id} has invalid/non-LineString geometry")
            if not boundary.intersects(geometry):
                rejected_outside += 1
                continue
            attributes = {
                name: values[index]
                for name, values in road_data.items()
                if name not in {"osm_id", "highway"} and values[index] is not None
            }
            features.append({
                "osm_type": "way",
                "osm_id": int(osm_id),
                "highway": highway,
                "source_tags": attributes,
                "geometry_wkb_hex": bytes(raw_geometry).hex(),
                "geometry_crs": "EPSG:4326",
                "scope_boundary": {
                    "source": "OpenStreetMap / Geofabrik PBF",
                    "osm_id": boundary_osm_id,
                    "name": region_name,
                    "admin_level": "4",
                    "predicate": "geometry_intersects",
                },
            })
        way_metadata = self._read_way_metadata(
            pbf_path, {int(feature["osm_id"]) for feature in features}
        )
        for feature in features:
            feature.update(way_metadata[int(feature["osm_id"])])
        version_count = sum(feature["osm_version"] is not None for feature in features)
        timestamp_count = sum(feature["osm_timestamp"] is not None for feature in features)
        return OSMRoadExtraction(
            boundary_osm_id=boundary_osm_id,
            boundary_name=region_name,
            boundary_geometry_wkb_hex=bytes(boundary_wkb).hex(),
            features=features,
            candidate_count=candidate_count,
            rejected_outside_boundary=rejected_outside,
            source_warnings=source_warnings,
            feature_version_available=bool(features) and version_count == len(features),
            feature_timestamp_available=bool(features) and timestamp_count == len(features),
            feature_versions_available_count=version_count,
            feature_timestamps_available_count=timestamp_count,
            extraction_duration_seconds=round(perf_counter() - started, 3),
        )

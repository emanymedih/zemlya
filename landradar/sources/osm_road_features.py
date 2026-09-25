from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from pathlib import Path
from time import perf_counter
from typing import Any
import warnings


TARGET_REGION_NAME = "Калужская область"


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


class GeofabrikRoadFeatureAdapter:
    """Read highway ways inside the OSM-mapped target-region boundary."""

    source_key = "geofabrik_osm_road_features"

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

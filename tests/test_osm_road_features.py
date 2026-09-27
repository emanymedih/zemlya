import hashlib
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
from shapely import to_wkb
from shapely.geometry import LineString, box

from landradar.sources.osm_road_features import (
    GeofabrikRoadFeatureAdapter, OSMRoadExtraction,
)


class RoadFeatureAdapterTests(unittest.TestCase):
    def _mock_reads(self, *, duplicate=False, boundary_name="Калужская область"):
        boundary = to_wkb(box(1, 1, 2, 2))
        crossing = to_wkb(LineString([(0.5, 1.5), (2.5, 1.5)]))
        outside = to_wkb(LineString([(5, 5), (6, 6)]))
        ids = ["100", "100" if duplicate else "101"]
        road_geometries = [crossing, outside]
        if duplicate:
            road_geometries[1] = crossing
        boundary_result = (
            {"fields": np.array(["osm_id", "name", "admin_level", "boundary"])},
            np.array([900]),
            [boundary],
            [
                np.array(["900"]), np.array([boundary_name]),
                np.array(["4"]), np.array(["administrative"]),
            ],
        )
        road_result = (
            {"fields": np.array(["osm_id", "name", "highway", "other_tags"])},
            np.array([100, 101]),
            road_geometries,
            [
                np.array(ids), np.array(["Main road", None]),
                np.array(["residential", "service"]),
                np.array([None, '"surface"=>"asphalt"']),
            ],
        )
        return boundary_result, road_result

    def _metadata_processor(self, ids=(100, 101), *, timestamp=True):
        processor = MagicMock()
        processor.with_filter.return_value = [
            SimpleNamespace(
                id=osm_id,
                version=7,
                timestamp=datetime(2026, 9, 23, 20, 0, tzinfo=timezone.utc)
                if timestamp else None,
            )
            for osm_id in ids
        ]
        return processor

    def test_selects_highways_in_named_boundary_and_keeps_metadata(self):
        boundary_result, road_result = self._mock_reads()
        info = {
            "crs": "EPSG:4326",
            "fields": np.array(["osm_id", "name", "highway", "other_tags"]),
        }
        processor = self._metadata_processor()
        with (
            patch("pyogrio.read_info", side_effect=[{"crs": "EPSG:4326"}, info]),
            patch("pyogrio.raw.read", side_effect=[boundary_result, road_result]) as read,
            patch("osmium.FileProcessor", return_value=processor),
        ):
            result = GeofabrikRoadFeatureAdapter().extract("fixture.osm.pbf")

        self.assertEqual(result.boundary_osm_id, "900")
        self.assertEqual(result.candidate_count, 2)
        self.assertEqual(result.rejected_outside_boundary, 1)
        self.assertEqual([r["osm_id"] for r in result.features], [100])
        self.assertEqual(result.features[0]["highway"], "residential")
        self.assertEqual(result.features[0]["source_tags"]["name"], "Main road")
        self.assertEqual(result.features[0]["geometry_crs"], "EPSG:4326")
        self.assertEqual(result.features[0]["osm_version"], 7)
        self.assertEqual(result.features[0]["osm_timestamp"], "2026-09-23T20:00:00Z")
        self.assertTrue(result.feature_version_available)
        self.assertTrue(result.feature_timestamp_available)
        self.assertEqual(result.feature_versions_available_count, 1)
        self.assertEqual(read.call_args_list[1].kwargs["where"], "highway IS NOT NULL")
        self.assertEqual(read.call_args_list[1].kwargs["mask"].geom_type, "Polygon")
        processor.with_filter.assert_called_once()

    def test_duplicate_osm_way_ids_fail_closed(self):
        boundary_result, road_result = self._mock_reads(duplicate=True)
        info = {
            "crs": "EPSG:4326",
            "fields": np.array(["osm_id", "name", "highway", "other_tags"]),
        }
        with (
            patch("pyogrio.read_info", side_effect=[{"crs": "EPSG:4326"}, info]),
            patch("pyogrio.raw.read", side_effect=[boundary_result, road_result]),
        ):
            with self.assertRaisesRegex(ValueError, "Duplicate OSM way id"):
                GeofabrikRoadFeatureAdapter().extract("fixture.osm.pbf")

    def test_missing_named_boundary_fails_closed(self):
        boundary_result, _ = self._mock_reads(boundary_name="Другой регион")
        with (
            patch("pyogrio.read_info", return_value={"crs": "EPSG:4326"}),
            patch("pyogrio.raw.read", return_value=boundary_result),
        ):
            with self.assertRaisesRegex(ValueError, "Expected one OSM level-4 boundary"):
                GeofabrikRoadFeatureAdapter().extract("fixture.osm.pbf")

    def test_gdal_source_warnings_are_preserved(self):
        import warnings

        boundary_result, road_result = self._mock_reads()
        info = {
            "crs": "EPSG:4326",
            "fields": np.array(["osm_id", "name", "highway", "other_tags"]),
        }

        def read_with_warning(*args, **kwargs):
            if kwargs["layer"] == "multipolygons":
                warnings.warn("Non closed ring detected", RuntimeWarning)
                return boundary_result
            return road_result

        with (
            patch("pyogrio.read_info", side_effect=[{"crs": "EPSG:4326"}, info]),
            patch("pyogrio.raw.read", side_effect=read_with_warning),
            patch("osmium.FileProcessor", return_value=self._metadata_processor()),
        ):
            result = GeofabrikRoadFeatureAdapter().extract("fixture.osm.pbf")
        self.assertEqual(result.source_warnings, ["multipolygons: Non closed ring detected"])

    def test_missing_way_metadata_fails_closed(self):
        processor = MagicMock()
        processor.with_filter.return_value = []
        with patch("osmium.FileProcessor", return_value=processor):
            with self.assertRaisesRegex(ValueError, "PBF metadata missing"):
                GeofabrikRoadFeatureAdapter._read_way_metadata("fixture.osm.pbf", {100})

    def test_missing_timestamp_is_reported_as_partial_coverage(self):
        boundary_result, road_result = self._mock_reads()
        info = {
            "crs": "EPSG:4326",
            "fields": np.array(["osm_id", "name", "highway", "other_tags"]),
        }
        with (
            patch("pyogrio.read_info", side_effect=[{"crs": "EPSG:4326"}, info]),
            patch("pyogrio.raw.read", side_effect=[boundary_result, road_result]),
            patch(
                "osmium.FileProcessor",
                return_value=self._metadata_processor(timestamp=False),
            ),
        ):
            result = GeofabrikRoadFeatureAdapter().extract("fixture.osm.pbf")
        self.assertTrue(result.feature_version_available)
        self.assertFalse(result.feature_timestamp_available)
        self.assertIsNone(result.features[0]["osm_timestamp"])


    @staticmethod
    def _sample_extraction():
        return OSMRoadExtraction(
            boundary_osm_id="900",
            boundary_name="Калужская область",
            boundary_geometry_wkb_hex="00",
            features=[{
                "osm_type": "way", "osm_id": 100, "highway": "residential",
                "osm_version": 7, "osm_timestamp": "2026-09-23T20:00:00Z",
            }],
            candidate_count=1,
            rejected_outside_boundary=0,
            source_warnings=[],
            feature_version_available=True,
            feature_timestamp_available=True,
            feature_versions_available_count=1,
            feature_timestamps_available_count=1,
            extraction_duration_seconds=2.5,
        )

    def test_cached_extraction_is_reused_for_same_pbf_hash(self):
        adapter = GeofabrikRoadFeatureAdapter()
        with TemporaryDirectory() as cache_dir:
            with patch.object(adapter, "extract", return_value=self._sample_extraction()) as scan:
                first = adapter.extract_cached(
                    "fixture.osm.pbf", cache_dir=cache_dir, source_sha256="a" * 64,
                    stage_source=False,
                )
                second = adapter.extract_cached(
                    "fixture.osm.pbf", cache_dir=cache_dir, source_sha256="a" * 64,
                    stage_source=False,
                )
        self.assertEqual(first.cache_status, "miss")
        self.assertEqual(second.cache_status, "hit")
        self.assertEqual(second.features, first.features)
        self.assertEqual(second.extraction_duration_seconds, 0.0)
        self.assertEqual(scan.call_count, 1)

    def test_cache_hit_rejects_changed_unverified_source(self):
        adapter = GeofabrikRoadFeatureAdapter()
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source.osm.pbf"
            source.write_bytes(b"first version")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            with patch.object(adapter, "extract", return_value=self._sample_extraction()) as scan:
                adapter.extract_cached(source, cache_dir=directory, source_sha256=digest)
                source.write_bytes(b"changed version")
                with self.assertRaisesRegex(ValueError, "SHA-256 differs from the cache key"):
                    adapter.extract_cached(source, cache_dir=directory, source_sha256=digest)
            self.assertEqual(scan.call_count, 1)

    def test_cache_is_invalidated_when_extractor_changes(self):
        adapter = GeofabrikRoadFeatureAdapter()
        with TemporaryDirectory() as cache_dir:
            with patch.object(adapter, "extract", return_value=self._sample_extraction()) as scan:
                with patch.object(GeofabrikRoadFeatureAdapter, "_extractor_fingerprint", return_value="a" * 64):
                    first = adapter.extract_cached(
                        "fixture.osm.pbf", cache_dir=cache_dir, source_sha256="b" * 64,
                        stage_source=False,
                    )
                with patch.object(GeofabrikRoadFeatureAdapter, "_extractor_fingerprint", return_value="c" * 64):
                    changed = adapter.extract_cached(
                        "fixture.osm.pbf", cache_dir=cache_dir, source_sha256="b" * 64,
                        stage_source=False,
                    )
        self.assertEqual(first.cache_status, "miss")
        self.assertEqual(changed.cache_status, "miss")
        self.assertEqual(scan.call_count, 2)

    def test_pbf_is_staged_and_checksum_verified_before_extraction(self):
        adapter = GeofabrikRoadFeatureAdapter()
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.osm.pbf"
            source.write_bytes(b"verified pbf fixture")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            seen_paths = []

            def inspect_staged(path, *, region_name):
                staged = Path(path)
                self.assertEqual(staged.read_bytes(), source.read_bytes())
                seen_paths.append(staged)
                return self._sample_extraction()

            work_root = Path(temp_dir) / "dedicated-work-volume"
            with (
                patch.dict("os.environ", {"LANDRADAR_PBF_WORK_DIR": str(work_root)}),
                patch.object(adapter, "extract", side_effect=inspect_staged),
            ):
                _, duration, status, error = adapter._extract_staged(
                    source, digest, "Калужская область",
                )
        self.assertEqual(seen_paths[0].parent.parent, work_root)
        self.assertGreaterEqual(duration, 0.0)
        self.assertEqual(status, "staged")
        self.assertIsNone(error)
        self.assertNotEqual(seen_paths[0], source)
        self.assertFalse(seen_paths[0].exists())

    def test_staging_rejects_checksum_mismatch(self):
        adapter = GeofabrikRoadFeatureAdapter()
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.osm.pbf"
            source.write_bytes(b"verified pbf fixture")
            with self.assertRaisesRegex(ValueError, "SHA-256 differs"):
                adapter._extract_staged(
                    source, "0" * 64, "Калужская область",
                )

    def test_direct_fallback_still_checks_source_hash(self):
        adapter = GeofabrikRoadFeatureAdapter()
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.osm.pbf"
            source.write_bytes(b"verified pbf fixture")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            with (
                patch("landradar.sources.osm_road_features.shutil.disk_usage", return_value=SimpleNamespace(free=0)),
                patch.object(adapter, "extract", return_value=self._sample_extraction()) as scan,
            ):
                _, _, status, error = adapter._extract_staged(
                    source, digest, "Калужская область",
                )
                with self.assertRaisesRegex(ValueError, "Direct Geofabrik PBF SHA-256"):
                    adapter._extract_staged(source, "0" * 64, "Калужская область")
            self.assertEqual(status, "fallback_direct")
            self.assertIsNotNone(error)
            self.assertEqual(scan.call_count, 1)

    def test_corrupt_cache_is_rebuilt_from_pbf(self):
        adapter = GeofabrikRoadFeatureAdapter()
        digest = "b" * 64
        with TemporaryDirectory() as cache_dir:
            cache_path = adapter._cache_path(cache_dir, digest, "Калужская область")
            with patch.object(
                adapter, "extract",
                side_effect=[self._sample_extraction(), self._sample_extraction()],
            ) as scan:
                adapter.extract_cached(
                    "fixture.osm.pbf", cache_dir=cache_dir, source_sha256=digest,
                    stage_source=False,
                )
                cache_path.write_bytes(b"corrupt")
                rebuilt = adapter.extract_cached(
                    "fixture.osm.pbf", cache_dir=cache_dir, source_sha256=digest,
                    stage_source=False,
                )
        self.assertEqual(rebuilt.cache_status, "invalid_rebuilt")
        self.assertEqual(rebuilt.features[0]["osm_id"], 100)
        self.assertEqual(scan.call_count, 2)


if __name__ == "__main__":
    unittest.main()

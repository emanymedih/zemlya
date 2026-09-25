import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
from shapely import to_wkb
from shapely.geometry import LineString, box

from landradar.sources.osm_road_features import GeofabrikRoadFeatureAdapter


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


if __name__ == "__main__":
    unittest.main()

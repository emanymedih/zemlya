import unittest
from unittest.mock import patch

import numpy as np
from shapely.geometry import LineString, box
from shapely import to_wkb

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

    def test_selects_only_highway_ways_intersecting_named_region_boundary(self):
        boundary_result, road_result = self._mock_reads()
        info = {"crs": "EPSG:4326", "fields": np.array(["osm_id", "name", "highway", "other_tags"])}
        with patch("pyogrio.read_info", side_effect=[{"crs": "EPSG:4326"}, info]), \
             patch("pyogrio.raw.read", side_effect=[boundary_result, road_result]) as read:
            result = GeofabrikRoadFeatureAdapter().extract("fixture.osm.pbf")
        self.assertEqual(result.boundary_osm_id, "900")
        self.assertEqual(result.candidate_count, 2)
        self.assertEqual(result.rejected_outside_boundary, 1)
        self.assertEqual([r["osm_id"] for r in result.features], [100])
        self.assertEqual(result.features[0]["highway"], "residential")
        self.assertEqual(result.features[0]["source_tags"]["name"], "Main road")
        self.assertEqual(result.features[0]["geometry_crs"], "EPSG:4326")
        self.assertEqual(read.call_args_list[1].kwargs["where"], "highway IS NOT NULL")
        self.assertEqual(read.call_args_list[1].kwargs["mask"].geom_type, "Polygon")

    def test_duplicate_osm_way_ids_fail_closed(self):
        boundary_result, road_result = self._mock_reads(duplicate=True)
        info = {"crs": "EPSG:4326", "fields": np.array(["osm_id", "name", "highway", "other_tags"])}
        with patch("pyogrio.read_info", side_effect=[{"crs": "EPSG:4326"}, info]), \
             patch("pyogrio.raw.read", side_effect=[boundary_result, road_result]):
            with self.assertRaisesRegex(ValueError, "Duplicate OSM way id"):
                GeofabrikRoadFeatureAdapter().extract("fixture.osm.pbf")

    def test_missing_named_boundary_fails_closed(self):
        boundary_result, road_result = self._mock_reads(boundary_name="Другой регион")
        info = {"crs": "EPSG:4326", "fields": np.array(["osm_id", "name", "highway", "other_tags"])}
        with patch("pyogrio.read_info", return_value={"crs": "EPSG:4326"}), \
             patch("pyogrio.raw.read", return_value=boundary_result):
            with self.assertRaisesRegex(ValueError, "Expected one OSM level-4 boundary"):
                GeofabrikRoadFeatureAdapter().extract("fixture.osm.pbf")


    def test_gdal_source_warnings_are_preserved_in_extraction_report(self):
        import warnings

        boundary_result, road_result = self._mock_reads()
        info = {"crs": "EPSG:4326", "fields": np.array(["osm_id", "name", "highway", "other_tags"])}

        def read_with_warning(*args, **kwargs):
            if kwargs["layer"] == "multipolygons":
                warnings.warn("Non closed ring detected", RuntimeWarning)
                return boundary_result
            return road_result

        with patch("pyogrio.read_info", side_effect=[{"crs": "EPSG:4326"}, info]), \
             patch("pyogrio.raw.read", side_effect=read_with_warning):
            result = GeofabrikRoadFeatureAdapter().extract("fixture.osm.pbf")
        self.assertEqual(result.source_warnings, ["multipolygons: Non closed ring detected"])


if __name__ == "__main__":
    unittest.main()

import unittest

from landradar.pipeline.quality import (
    KNOWN_GDAL_WARNING, POLICY_VERSION, assess_source_quality,
)


def accepted_summary():
    return {
        "geofabrik_freshness": {
            "status": "current", "replication_age_hours": 14.0,
        },
        "geofabrik_road_features": {
            "selected_feature_count": 4,
            "feature_versions_available_count": 4,
            "feature_timestamps_available_count": 4,
            "invalid_geometry_count": 0, "duplicate_osm_id_count": 0,
            "source_quality_warning_count": 9,
            "source_quality_warning_counts": [
                {"message": KNOWN_GDAL_WARNING, "count": 9},
            ],
        },
        "rosstat_hierarchy": {
            "status": "complete", "total_rows": 4,
            "child_rows": 3, "resolved_parent_relations": 3,
        },
        "rosstat_selected_records": 4,
        "rosstat_oktmo_recode": {"status": "complete", "selected_rows": 2},
        "rosstat_latest_advertised_file": True,
        "rosstat_publication_date_age_days": 27,
        "rosstat_codingtable_publication_date_age_days": 27,
    }


class SourceQualityTests(unittest.TestCase):
    def test_current_checked_sources_pass_with_explicit_limits(self):
        result = assess_source_quality(accepted_summary(), "git:abcdef012345")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["policy_version"], POLICY_VERSION)
        self.assertTrue(all(result["checks"].values()))

    def test_stale_unknown_and_future_sources_fail_closed(self):
        for field, value in (
            ("replication_age_hours", 49),
            ("replication_age_hours", -1),
        ):
            summary = accepted_summary()
            summary["geofabrik_freshness"][field] = value
            self.assertEqual(assess_source_quality(summary, "git:abc")["status"], "FAIL")
        for key, value in (
            ("rosstat_publication_date_age_days", None),
            ("rosstat_publication_date_age_days", 46),
            ("rosstat_codingtable_publication_date_age_days", -1),
        ):
            summary = accepted_summary()
            summary[key] = value
            self.assertEqual(assess_source_quality(summary, "git:abc")["status"], "FAIL")

    def test_new_warning_or_missing_metadata_blocks_publication(self):
        summary = accepted_summary()
        summary["geofabrik_road_features"]["source_quality_warning_counts"] = [
            {"message": "different GDAL warning", "count": 9},
        ]
        self.assertFalse(assess_source_quality(summary, "git:abc")["checks"]["gdal_warning_baseline"])
        summary = accepted_summary()
        summary["geofabrik_road_features"]["feature_timestamps_available_count"] = 3
        self.assertFalse(assess_source_quality(summary, "git:abc")["checks"]["road_count_and_metadata"])
        self.assertEqual(assess_source_quality(accepted_summary(), "unknown")["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()

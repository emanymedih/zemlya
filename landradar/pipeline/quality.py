"""Versioned, source-specific acceptance policy for the interim core."""

from __future__ import annotations

from typing import Any


POLICY_VERSION = "interim-core-quality/v1"
MAX_GEOFABRIK_REPLICATION_AGE_HOURS = 48
MAX_ROSSTAT_PUBLICATION_AGE_DAYS = 45
KNOWN_GDAL_WARNING = (
    "multipolygons: Non closed ring detected. To avoid accepting it, set the "
    "OGR_GEOMETRY_ACCEPT_UNCLOSED_RING configuration option to NO"
)
MAX_KNOWN_GDAL_WARNINGS = 9


def assess_source_quality(summary: dict[str, Any], code_version: str) -> dict[str, Any]:
    """Return explicit PASS/FAIL checks; unknown source ages fail closed."""
    freshness = summary.get("geofabrik_freshness", {})
    roads = summary.get("geofabrik_road_features", {})
    hierarchy = summary.get("rosstat_hierarchy", {})
    recode = summary.get("rosstat_oktmo_recode", {})
    warnings = roads.get("source_quality_warning_counts", [])
    road_count = roads.get("selected_feature_count")
    checks = {
        "code_version": code_version.startswith("git:") and not code_version.endswith("-dirty"),
        "geofabrik_publisher_checksum": freshness.get("status") == "current",
        "geofabrik_replication_age": (
            isinstance(freshness.get("replication_age_hours"), (int, float))
            and 0 <= freshness["replication_age_hours"] <= MAX_GEOFABRIK_REPLICATION_AGE_HOURS
        ),
        "road_count_and_metadata": (
            isinstance(road_count, int) and road_count > 0
            and roads.get("feature_versions_available_count") == road_count
            and roads.get("feature_timestamps_available_count") == road_count
            and roads.get("invalid_geometry_count") == 0
            and roads.get("duplicate_osm_id_count") == 0
        ),
        "gdal_warning_baseline": (
            all(item.get("message") == KNOWN_GDAL_WARNING for item in warnings)
            and sum(item.get("count", 0) for item in warnings) <= MAX_KNOWN_GDAL_WARNINGS
            and roads.get("source_quality_warning_count") == sum(
                item.get("count", 0) for item in warnings
            )
        ),
        "oktmo_hierarchy": (
            hierarchy.get("status") == "complete"
            and hierarchy.get("total_rows") == summary.get("rosstat_selected_records")
            and hierarchy.get("resolved_parent_relations") == hierarchy.get("child_rows")
        ),
        "oktmo_recode": (
            recode.get("status") == "complete" and recode.get("selected_rows", 0) > 0
        ),
        "rosstat_advertised_file": summary.get("rosstat_latest_advertised_file") is True,
    }
    for dataset, age_key in (
        ("oktmo", "rosstat_publication_date_age_days"),
        ("codingtable", "rosstat_codingtable_publication_date_age_days"),
    ):
        age = summary.get(age_key)
        checks[f"rosstat_{dataset}_publication_age"] = (
            isinstance(age, int) and 0 <= age <= MAX_ROSSTAT_PUBLICATION_AGE_DAYS
        )
    return {
        "policy_version": POLICY_VERSION,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "limits": {
            "geofabrik_replication_age_hours": MAX_GEOFABRIK_REPLICATION_AGE_HOURS,
            "rosstat_publication_age_days": MAX_ROSSTAT_PUBLICATION_AGE_DAYS,
            "known_gdal_warning_count": MAX_KNOWN_GDAL_WARNINGS,
        },
        "policy_note": "Project acceptance limits; no publisher update SLA is inferred.",
    }

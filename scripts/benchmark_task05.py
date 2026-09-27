"""Isolate the uncached Task 5 OSM scan from pipeline SQLite commits."""

import argparse
import json
import tempfile
from time import perf_counter

from landradar.sources.osm_road_features import GeofabrikRoadFeatureAdapter


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pbf", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--work-dir", required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(
        prefix="landradar-benchmark-cache-", dir=args.work_dir,
    ) as cache_dir:
        started = perf_counter()
        result = GeofabrikRoadFeatureAdapter().extract_cached(
            args.pbf, cache_dir=cache_dir, source_sha256=args.sha256,
        )
        print(json.dumps({
            "elapsed_seconds": round(perf_counter() - started, 3),
            "extraction_seconds": result.extraction_duration_seconds,
            "staging_seconds": result.source_stage_duration_seconds,
            "staging_status": result.source_stage_status,
            "cache_status": result.cache_status,
            "selected_features": len(result.features),
            "source_warnings": len(result.source_warnings),
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()

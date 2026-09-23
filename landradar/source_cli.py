from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

from .sources import BBox, OSMOverpassAdapter, OSMGeofabrikCatalogAdapter, GeofabrikGpkgIngestor, GeofabrikPbfIngestor, RosstatOpenDataAdapter
from .pipeline import UnifiedPipelineRunner


def write_json_atomic(path: str | Path, payload: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=target.name + ".", suffix=".tmp", dir=target.parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Zemlya Radar — source connectors")
    sub = parser.add_subparsers(dest="command", required=True)

    osm = sub.add_parser("osm-roads", help="Fetch OSM highway ways for a bbox")
    osm.add_argument("--bbox", nargs=4, type=float, metavar=("S", "W", "N", "E"), required=True)
    osm.add_argument("--raw-dir", default="data/raw")
    osm.add_argument("--output", default="osm_roads.json")

    osm_h = sub.add_parser("osm-health", help="Run a small live OSM protocol/schema check")
    osm_h.add_argument("--raw-dir", default="data/raw")

    gf_h = sub.add_parser("geofabrik-health", help="Run live Geofabrik Central FD catalog check")
    gf_h.add_argument("--raw-dir", default="data/raw")

    gf_i = sub.add_parser("geofabrik-ingest", help="Download, validate and atomically promote Geofabrik Central FD GeoPackage")
    gf_i.add_argument("--root-dir", default="data/osm/geofabrik")
    gf_i.add_argument("--catalog-raw-dir", default=None)
    gf_i.add_argument("--extract-url", default=None)
    gf_i.add_argument("--catalog-url", default=None)

    gf_pbf_h = sub.add_parser("geofabrik-pbf-health", help="Check Geofabrik JSON index and publisher MD5")
    gf_pbf_h.add_argument("--root-dir", default="data/osm/geofabrik-pbf")

    gf_pbf_v = sub.add_parser("geofabrik-pbf-verify", help="Re-hash and re-validate current local Geofabrik PBF")
    gf_pbf_v.add_argument("--root-dir", default="data/osm/geofabrik-pbf")

    gf_pbf = sub.add_parser("geofabrik-pbf-ingest", help="Download, verify and atomically promote raw Geofabrik OSM PBF")
    gf_pbf.add_argument("--root-dir", default="data/osm/geofabrik-pbf")
    gf_pbf.add_argument("--pbf-url", default=None)
    gf_pbf.add_argument("--md5-url", default=None)

    rs = sub.add_parser("rosstat-oktmo", help="Fetch current Rosstat OKTMO open dataset")
    rs.add_argument("--raw-dir", default="data/raw")
    rs.add_argument("--output", default="rosstat_oktmo_kaluga.json")
    selector = rs.add_mutually_exclusive_group()
    selector.add_argument("--subject-code", default=None, help="Official 2-digit subject code; default: 29 (Kaluga)")
    selector.add_argument("--filter", default=None, help="Explicit full-row text filter; use only for diagnostics")

    rs_h = sub.add_parser("rosstat-health", help="Run live Rosstat passport + CSV check")
    rs_h.add_argument("--raw-dir", default="data/raw")

    pipeline = sub.add_parser("pipeline-run", help="Run validated Geofabrik + Rosstat pipeline")
    pipeline.add_argument("--geofabrik-root", default="data/osm/geofabrik-pbf")
    pipeline.add_argument("--raw-dir", default="data/raw/pipeline/rosstat")
    pipeline.add_argument("--database", default="data/normalized/landradar.sqlite")
    pipeline.add_argument("--subject-code", default="29")
    pipeline.add_argument(
        "--allow-stale-geofabrik", action="store_true",
        help="Allow a verified local PBF when publisher latest MD5 has changed",
    )
    pipeline.add_argument("--report", default=None)
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    args = build_parser().parse_args(argv)
    if args.command == "rosstat-oktmo" and args.subject_code is None and args.filter is None:
        args.subject_code = RosstatOpenDataAdapter.kaluga_subject_code
    return args


def main() -> None:
    args = parse_args()
    if args.command == "osm-roads":
        adapter = OSMOverpassAdapter()
        roads, snapshot = adapter.fetch_roads(BBox(*args.bbox), raw_dir=args.raw_dir)
        write_json_atomic(args.output, {
            "source": "OpenStreetMap",
            "attribution": "© OpenStreetMap contributors; ODbL",
            "snapshot": snapshot.to_dict(),
            "records": [r.to_dict() for r in roads],
        })
        print(f"OSM roads: {len(roads)} -> {args.output}")
    elif args.command == "osm-health":
        result = OSMOverpassAdapter().healthcheck(raw_dir=args.raw_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get("ok"):
            raise SystemExit(2)
    elif args.command == "geofabrik-health":
        result = OSMGeofabrikCatalogAdapter().healthcheck(raw_dir=args.raw_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get("ok"):
            raise SystemExit(2)
    elif args.command == "geofabrik-ingest":
        manifest = GeofabrikGpkgIngestor(args.root_dir).ingest(
            catalog_raw_dir=args.catalog_raw_dir, extract_url=args.extract_url, catalog_url=args.catalog_url
        )
        print(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2))
    elif args.command == "geofabrik-pbf-health":
        result = GeofabrikPbfIngestor(args.root_dir).healthcheck()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get("ok"):
            raise SystemExit(2)
    elif args.command == "geofabrik-pbf-verify":
        result = GeofabrikPbfIngestor(args.root_dir).verify_current()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get("ok"):
            raise SystemExit(2)
    elif args.command == "geofabrik-pbf-ingest":
        manifest = GeofabrikPbfIngestor(args.root_dir).ingest(
            direct_pbf_url=args.pbf_url, direct_md5_url=args.md5_url
        )
        print(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2))
    elif args.command == "rosstat-oktmo":
        adapter = RosstatOpenDataAdapter()
        dataset, snapshots = adapter.fetch_oktmo(raw_dir=args.raw_dir)
        if args.subject_code is not None:
            rows = [row for row in dataset.rows if row.get("subject_code") == args.subject_code]
            selection = {"subject_code": args.subject_code}
        else:
            rows = adapter.filter_rows_containing(dataset.rows, args.filter)
            selection = {"text_filter": args.filter}
        if not rows:
            raise SystemExit(f"No Rosstat OKTMO rows matched {selection}")
        invalid_rows = [row for row in rows if row.get("_source_quality_issues")]
        if invalid_rows:
            first = invalid_rows[0]
            raise SystemExit(
                "Selected Rosstat rows contain invalid validity interval: "
                f"row={first['_source_row_number']} code={first['oktmo_code']} "
                f"valid_from={first['valid_from']} valid_to={first['valid_to']}"
            )
        quality_issues = [
            row for row in dataset.rows if row.get("_source_quality_issues")
        ]
        write_json_atomic(args.output, {
            "source": "Росстат",
            "dataset_id": dataset.dataset_id,
            "passport_url": dataset.passport_url,
            "data_url": dataset.data_url,
            "published_version": dataset.published_version,
            "latest_advertised_file": True,
            "source_quality_issue_count": len(quality_issues),
            "source_quality_issue_samples": [
                {
                    "source_row": row["_source_row_number"],
                    "oktmo_code": row["oktmo_code"],
                    "issue": row["_source_quality_issues"][0],
                    "valid_from": row["valid_from"],
                    "valid_to": row["valid_to"],
                }
                for row in quality_issues[:20]
            ],
            "use_terms": dataset.use_terms,
            "use_terms_url": dataset.use_terms_url,
            "source_attribution": dataset.passport_url,
            "snapshots": [s.to_dict() for s in snapshots],
            "selection": selection,
            "all_records_count": len(dataset.rows),
            "records": rows,
        })
        label = next(iter(selection.items()))
        print(f"Rosstat rows for {label[0]}={label[1]!r}: {len(rows)} -> {args.output}")
    elif args.command == "rosstat-health":
        result = RosstatOpenDataAdapter().healthcheck(raw_dir=args.raw_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get("ok"):
            raise SystemExit(2)
    elif args.command == "pipeline-run":
        report = UnifiedPipelineRunner(
            geofabrik_root=args.geofabrik_root,
            rosstat_raw_dir=args.raw_dir,
            database_path=args.database,
            subject_code=args.subject_code,
            require_latest_geofabrik=not args.allow_stale_geofabrik,
        ).run()
        if args.report:
            write_json_atomic(args.report, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

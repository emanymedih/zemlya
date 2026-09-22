from __future__ import annotations

import argparse
import json
from pathlib import Path

from .sources import BBox, OSMOverpassAdapter, OSMGeofabrikCatalogAdapter, GeofabrikGpkgIngestor, GeofabrikPbfIngestor, RosstatOpenDataAdapter


def main() -> None:
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
    rs.add_argument("--filter", default="Калуж")
    rs.add_argument("--subject-code", default=None)

    rs_h = sub.add_parser("rosstat-health", help="Run live Rosstat passport + CSV check")
    rs_h.add_argument("--raw-dir", default="data/raw")

    args = parser.parse_args()
    if args.command == "osm-roads":
        adapter = OSMOverpassAdapter()
        roads, snapshot = adapter.fetch_roads(BBox(*args.bbox), raw_dir=args.raw_dir)
        Path(args.output).write_text(json.dumps({
            "source": "OpenStreetMap",
            "attribution": "© OpenStreetMap contributors; ODbL",
            "snapshot": snapshot.to_dict(),
            "records": [r.to_dict() for r in roads],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
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
        rows = (
            [row for row in dataset.rows if row.get("subject_code") == args.subject_code]
            if args.subject_code
            else adapter.filter_rows_containing(dataset.rows, args.filter)
        )
        Path(args.output).write_text(json.dumps({
            "source": "Росстат",
            "dataset_id": dataset.dataset_id,
            "passport_url": dataset.passport_url,
            "data_url": dataset.data_url,
            "snapshots": [s.to_dict() for s in snapshots],
            "filter": args.filter,
            "records": rows,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        label = f"subject_code={args.subject_code!r}" if args.subject_code else f"filter={args.filter!r}"
        print(f"Rosstat rows for {label}: {len(rows)} -> {args.output}")
    elif args.command == "rosstat-health":
        result = RosstatOpenDataAdapter().healthcheck(raw_dir=args.raw_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get("ok"):
            raise SystemExit(2)


if __name__ == "__main__":
    main()

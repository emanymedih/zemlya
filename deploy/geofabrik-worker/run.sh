#!/bin/sh
set -eu

DATA_ROOT="${RAILWAY_VOLUME_MOUNT_PATH:-/data}"
ROOT_DIR="${LANDRADAR_GEOFABRIK_ROOT:-${DATA_ROOT}/geofabrik-pbf}"
MIN_FREE_BYTES="${LANDRADAR_MIN_FREE_BYTES:-2000000000}"

mkdir -p "$ROOT_DIR"

python - "$ROOT_DIR" "$MIN_FREE_BYTES" <<'PY'
from pathlib import Path
import shutil, sys
root = Path(sys.argv[1])
required = int(sys.argv[2])
usage = shutil.disk_usage(root)
print(f"storage_preflight root={root} free={usage.free} required={required}")
if usage.free < required:
    raise SystemExit(
        f"Insufficient free storage: {usage.free} bytes available, {required} required"
    )
PY

python -m landradar.source_cli geofabrik-pbf-health --root-dir "$ROOT_DIR"
python -m landradar.source_cli geofabrik-pbf-ingest --root-dir "$ROOT_DIR"
python -m landradar.source_cli geofabrik-pbf-verify --root-dir "$ROOT_DIR"

#!/bin/sh
set -eu

REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
DATA_DIR="${1:-$REPO_DIR/geofabrik-worker-data}"
mkdir -p "$DATA_DIR"
ABS_DATA_DIR=$(cd "$DATA_DIR" && pwd)
CODE_VERSION=$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || printf 'unknown')
if [ -n "$(git -C "$REPO_DIR" status --porcelain 2>/dev/null)" ]; then
  CODE_VERSION="${CODE_VERSION}-dirty"
fi

printf 'Using persistent data directory: %s\n' "$ABS_DATA_DIR"
docker build --build-arg "LANDRADAR_CODE_VERSION=git:$CODE_VERSION" -f "$REPO_DIR/deploy/geofabrik-worker/Dockerfile" -t zemlya-radar-geofabrik:task01 "$REPO_DIR"
docker run --rm \
  -e LANDRADAR_GEOFABRIK_ROOT=/data/geofabrik-pbf \
  -e LANDRADAR_PBF_WORK_DIR=/fast \
  -e TMPDIR=/fast \
  -e CPL_TMPDIR=/fast \
  -v "$ABS_DATA_DIR:/data" \
  -v landradar-pbf-work:/fast \
  zemlya-radar-geofabrik:task01

printf '\nLive-run completed. Expected current pointer:\n%s\n' "$ABS_DATA_DIR/geofabrik-pbf/current.json"

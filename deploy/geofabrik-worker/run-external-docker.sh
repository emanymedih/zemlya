#!/bin/sh
set -eu

DATA_DIR="${1:-$(pwd)/geofabrik-worker-data}"
mkdir -p "$DATA_DIR"
ABS_DATA_DIR=$(cd "$DATA_DIR" && pwd)
CODE_VERSION=$(git rev-parse HEAD 2>/dev/null || printf 'unknown')
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
  CODE_VERSION="${CODE_VERSION}-dirty"
fi

printf 'Using persistent data directory: %s\n' "$ABS_DATA_DIR"
docker build --build-arg "LANDRADAR_CODE_VERSION=git:$CODE_VERSION" -f deploy/geofabrik-worker/Dockerfile -t zemlya-radar-geofabrik:task01 .
docker run --rm \
  -e LANDRADAR_GEOFABRIK_ROOT=/data/geofabrik-pbf \
  -v "$ABS_DATA_DIR:/data" \
  zemlya-radar-geofabrik:task01

printf '\nLive-run completed. Expected current pointer:\n%s\n' "$ABS_DATA_DIR/geofabrik-pbf/current.json"

#!/bin/sh
set -eu

DATA_DIR="${1:-$(pwd)/geofabrik-worker-data}"
mkdir -p "$DATA_DIR"
ABS_DATA_DIR=$(cd "$DATA_DIR" && pwd)

printf 'Using persistent data directory: %s\n' "$ABS_DATA_DIR"
docker build -f deploy/geofabrik-worker/Dockerfile -t zemlya-radar-geofabrik:task01 .
docker run --rm \
  -e LANDRADAR_GEOFABRIK_ROOT=/data/geofabrik-pbf \
  -v "$ABS_DATA_DIR:/data" \
  zemlya-radar-geofabrik:task01

printf '\nLive-run completed. Expected current pointer:\n%s\n' "$ABS_DATA_DIR/geofabrik-pbf/current.json"

param(
    [string]$DataDir = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "geofabrik-worker-data")
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$DataDir = [System.IO.Path]::GetFullPath($DataDir)
$codeVersion = (git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw "Unable to determine repository commit" }
if (git -C $repo status --porcelain) { $codeVersion += "-dirty" }
New-Item -ItemType Directory -Force $DataDir | Out-Null
docker build --build-arg "LANDRADAR_CODE_VERSION=git:$codeVersion" -f (Join-Path $repo "deploy/geofabrik-worker/Dockerfile") -t zemlya-radar-geofabrik:task01 $repo
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
docker run --rm -e LANDRADAR_GEOFABRIK_ROOT=/data/geofabrik-pbf -e LANDRADAR_PBF_WORK_DIR=/fast -e TMPDIR=/fast -e CPL_TMPDIR=/fast -v ($DataDir + ":/data") -v landradar-pbf-work:/fast zemlya-radar-geofabrik:task01
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Output ("Live-run completed. Current pointer: " + (Join-Path $DataDir "geofabrik-pbf\current.json"))

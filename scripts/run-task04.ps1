param(
    [string]$DataDir = (Join-Path (Split-Path -Parent $PSScriptRoot) "geofabrik-worker-data"),
    [string]$Image = "zemlya-radar-geofabrik:task04"
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$codeVersion = (git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw "Unable to determine repository commit" }
if (git -C $repo status --porcelain) { $codeVersion += "-dirty" }
New-Item -ItemType Directory -Force $DataDir | Out-Null
docker build --build-arg "LANDRADAR_CODE_VERSION=git:$codeVersion" -f (Join-Path $repo "deploy/geofabrik-worker/Dockerfile") -t $Image $repo
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
docker run --rm --entrypoint python -v ($DataDir + ":/data") $Image -m landradar.source_cli pipeline-run --geofabrik-root /data/geofabrik-pbf --raw-dir /data/pipeline/raw/rosstat --database /data/pipeline/landradar.sqlite --subject-code 29 --report /data/pipeline/current-report.json
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Output ("Task 4 pipeline completed. Report: " + (Join-Path $DataDir "pipeline\current-report.json"))

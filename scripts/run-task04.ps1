param(
    [string]$DataDir = (Join-Path (Split-Path -Parent $PSScriptRoot) "geofabrik-worker-data"),
    [string]$Image = "zemlya-radar-geofabrik:task04",
    [switch]$UseDockerCatalog,
    [switch]$AllowHostCatalog
)
$ErrorActionPreference = "Stop"
$catalogVolume = "landradar-catalog"
if ($UseDockerCatalog -and $AllowHostCatalog) { throw "Choose one catalog mode" }
if (-not $UseDockerCatalog) {
    $volumeNames = @(docker volume ls --format '{{.Name}}' --filter "name=^${catalogVolume}$")
    if ($LASTEXITCODE -ne 0) { throw "Unable to inspect Docker catalog volumes" }
    if ($volumeNames -contains $catalogVolume -and -not $AllowHostCatalog) {
        throw "An existing Docker catalog volume is present. Use -UseDockerCatalog for the active catalog or -AllowHostCatalog for an explicit legacy/diagnostic run."
    }
}
$repo = Split-Path -Parent $PSScriptRoot
$codeVersion = (git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw "Unable to determine repository commit" }
if (git -C $repo status --porcelain) { $codeVersion += "-dirty" }
New-Item -ItemType Directory -Force $DataDir | Out-Null
docker build --build-arg "LANDRADAR_CODE_VERSION=git:$codeVersion" -f (Join-Path $repo "deploy/geofabrik-worker/Dockerfile") -t $Image $repo
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$database = "/data/pipeline/landradar.sqlite"
$catalogMount = @()
if ($UseDockerCatalog) {
    $catalogMount = @("-v", "${catalogVolume}:/catalog")
    docker run --rm --entrypoint python -v ($DataDir + ":/data") @catalogMount $Image -m landradar.pipeline.catalog_migrate --source /data/pipeline/landradar.sqlite --destination /catalog/landradar.sqlite
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $database = "/catalog/landradar.sqlite"
}
docker run --rm --entrypoint python -e LANDRADAR_PBF_WORK_DIR=/fast -e TMPDIR=/fast -e CPL_TMPDIR=/fast -v ($DataDir + ":/data") -v landradar-pbf-work:/fast @catalogMount $Image -m landradar.source_cli pipeline-run --geofabrik-root /data/geofabrik-pbf --raw-dir /data/pipeline/raw/rosstat --database $database --subject-code 29 --report /data/pipeline/current-report.json
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if ($UseDockerCatalog) {
    $report = Get-Content -Raw (Join-Path $DataDir "pipeline\current-report.json") | ConvertFrom-Json
    & (Join-Path $PSScriptRoot "export-catalog.ps1") -DataDir $DataDir -Image $Image -ExpectedRunId $report.current_run_id
}
Write-Output ("Task 4 pipeline completed. Report: " + (Join-Path $DataDir "pipeline\current-report.json"))

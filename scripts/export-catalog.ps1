param(
    [string]$DataDir = (Join-Path (Split-Path -Parent $PSScriptRoot) "geofabrik-worker-data"),
    [string]$Image = "zemlya-radar-geofabrik:task04",
    [string]$CatalogVolume = "landradar-catalog",
    [string]$Destination = "",
    [string]$ExpectedRunId = ""
)
$ErrorActionPreference = "Stop"
if (-not $Destination) { $Destination = Join-Path $DataDir "pipeline\volume-backup.sqlite" }
$Destination = [System.IO.Path]::GetFullPath($Destination)
New-Item -ItemType Directory -Force (Split-Path -Parent $Destination) | Out-Null
$stateJson = docker run --rm --entrypoint python -v "${CatalogVolume}:/catalog:ro" $Image -m landradar.pipeline.catalog_migrate --source /catalog/landradar.sqlite --inspect
if ($LASTEXITCODE -ne 0) { throw "Native catalog failed integrity validation" }
$state = $stateJson | ConvertFrom-Json
if ($ExpectedRunId -and $state.current_run_id -ne $ExpectedRunId) {
    throw "Native catalog pointer differs from the successful pipeline report"
}
$hashLine = docker run --rm --entrypoint sha256sum -v "${CatalogVolume}:/catalog:ro" $Image /catalog/landradar.sqlite
if ($LASTEXITCODE -ne 0) { throw "Unable to hash native catalog" }
$sourceHash = ($hashLine -split '\s+')[0]
$temporary = "$Destination.$([guid]::NewGuid().ToString('N')).tmp"
$containerId = ""
try {
    $containerId = (docker create --entrypoint true -v "${CatalogVolume}:/catalog:ro" $Image).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $containerId) { throw "Unable to create export container" }
    docker cp "${containerId}:/catalog/landradar.sqlite" $temporary
    if ($LASTEXITCODE -ne 0) { throw "Unable to copy catalog from Docker volume" }
    $copiedHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $temporary).Hash
    if ($copiedHash -ne $sourceHash) { throw "Exported catalog checksum differs from native source" }
    if (Test-Path -LiteralPath $Destination) {
        [System.IO.File]::Replace($temporary, $Destination, $null)
    } else {
        [System.IO.File]::Move($temporary, $Destination)
    }
    Write-Output ("Catalog backup: " + $Destination + " SHA-256=" + $sourceHash +
        " current_run_id=" + $state.current_run_id)
} finally {
    if ($containerId) { docker rm $containerId | Out-Null }
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
}

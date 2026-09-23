param(
  [string]$Image='zemlya-radar-geofabrik:task01',
  [Int64]$MinFreeBytes=2000000000
)
$ErrorActionPreference='Stop'
$repo='C:\Users\admla\zemlya'
$data=Join-Path $repo 'geofabrik-worker-data'
$outdir=Join-Path $data 'task03'
New-Item -ItemType Directory -Force $outdir | Out-Null
function HostCheck($name,$url) {
  $code=& curl.exe -L -sS -o NUL --connect-timeout 15 --max-time 30 -w '%{http_code}' $url
  [ordered]@{name=$name;url=$url;transport='windows_schannel';status=[int]$code;ok=($LASTEXITCODE -eq 0 -and [int]$code -ge 200 -and [int]$code -lt 400)}
}
$docker=& docker version --format 'Client={{.Client.Version}};Server={{.Server.Version}};Context={{.Client.Context}}'
$disk=Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
if($disk.FreeSpace -lt $MinFreeBytes){exit 30}
$hostChecks=@(
  (HostCheck 'geofabrik' 'https://download.geofabrik.de/index-v1-nogeom.json'),
  (HostCheck 'rosstat' 'https://rosstat.gov.ru/opendata/7708234640-oktmo'),
  (HostCheck 'github' 'https://github.com/emanymedih/zemlya')
)
$containerReport=Join-Path $outdir 'container-report.json'
$repoMount=($repo+':/app')
docker run --rm --entrypoint python -v $repoMount $Image /app/scripts/task03-container-probe.py | Set-Content $containerReport -Encoding utf8
if($LASTEXITCODE -ne 0){exit 31}
$containerData=Get-Content $containerReport -Raw | ConvertFrom-Json
if($hostChecks | Where-Object { -not $_.ok }){exit 32}
if($containerData.checks | Where-Object { -not $_.ok }){exit 33}
$report=[ordered]@{
  gate='Task 3 - execution environment'
  checked_at=(Get-Date).ToUniversalTime().ToString('o')
  docker=$docker
  container_image=$Image
  disk=[ordered]@{drive='C:';free_bytes=$disk.FreeSpace;size_bytes=$disk.Size;required_free_bytes=$MinFreeBytes}
  host_checks=$hostChecks
  container_report=$containerData
  tls_policy=[ordered]@{verification='enabled';ca_bundle='/opt/zemlya/certs/ca-bundle.pem';rosstat_direct=$true}
}
$report | ConvertTo-Json -Depth 10 | Set-Content (Join-Path $outdir 'task03-preflight-report.json') -Encoding utf8
$report | ConvertTo-Json -Depth 10

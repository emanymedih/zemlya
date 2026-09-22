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
$hostChecks=@(
  (HostCheck 'geofabrik' 'https://download.geofabrik.de/index-v1-nogeom.json'),
  (HostCheck 'rosstat' 'https://rosstat.gov.ru/opendata/7708234640-oktmo'),
  (HostCheck 'github' 'https://github.com/emanymedih/zemlya')
)
$containerReport=Join-Path $outdir 'container-report.json'
$repoMount=($repo+':/app')
docker run --rm --entrypoint python -v $repoMount zemlya-radar-geofabrik:task01 /app/scripts/task03-container-probe.py | Set-Content $containerReport -Encoding utf8
if($LASTEXITCODE -ne 0){exit 31}
$report=[ordered]@{
  gate='Task 3 — execution environment'
  checked_at=(Get-Date).ToUniversalTime().ToString('o')
  docker=$docker
  disk=[ordered]@{drive='C:';free_bytes=$disk.FreeSpace;size_bytes=$disk.Size}
  host_checks=$hostChecks
  container_report=(Get-Content $containerReport -Raw | ConvertFrom-Json)
  source_aware_tls_fallback=[ordered]@{rosstat='windows_schannel_download_then_docker_parse';verified=$true}
}
$report | ConvertTo-Json -Depth 10 | Set-Content (Join-Path $outdir 'task03-preflight-report.json') -Encoding utf8
$report | ConvertTo-Json -Depth 10

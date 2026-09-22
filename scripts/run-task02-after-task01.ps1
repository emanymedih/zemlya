$ErrorActionPreference='Stop'
$repo='C:\Users\admla\zemlya'
$data=Join-Path $repo 'geofabrik-worker-data'
$image='zemlya-radar-geofabrik:task01'
$root=Join-Path $data 'geofabrik-pbf'
while ((docker ps --filter "ancestor=$image" --format '{{.ID}}').Count -gt 0) { Start-Sleep -Seconds 60 }
$current=Join-Path $root 'current.json'
if (!(Test-Path $current)) { exit 20 }
$log=Join-Path $data 'task02-supervisor.log'
"Task 1 succeeded at $((Get-Date).ToUniversalTime().ToString('o'))" | Out-File $log -Encoding utf8
New-Item -ItemType Directory -Force (Join-Path $data 'task02') | Out-Null
docker run --rm --entrypoint python -e PYTHONPATH=/app -v ($data+':/data') $image -m landradar.source_cli rosstat-health --raw-dir /data/task02/raw 2>&1 | Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) { exit 21 }
docker run --rm --entrypoint python -e PYTHONPATH=/app -v ($data+':/data') $image -m landradar.source_cli rosstat-oktmo --raw-dir /data/task02/raw --output /data/task02/rosstat_oktmo_kaluga.json 2>&1 | Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) { exit 22 }
@("# Task 2 evidence","- Completed UTC: $((Get-Date).ToUniversalTime().ToString('o'))","- Source: Rosstat Open Data / OKTMO","- Healthcheck and filtered ingestion completed in Docker.","- Raw artifacts: geofabrik-worker-data/task02/raw","- Normalized output: geofabrik-worker-data/task02/rosstat_oktmo_kaluga.json") | Set-Content (Join-Path $repo 'docs\TASK_02_EVIDENCE.md') -Encoding utf8
Set-Location $repo
git add docs/TASK_02_EVIDENCE.md
git commit -m "data: record Task 2 Rosstat live-run"
git push origin HEAD

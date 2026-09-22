$ErrorActionPreference='Stop'
$repo='C:\Users\admla\zemlya'
$base=Join-Path $repo 'geofabrik-worker-data\task02-host'
$raw=Join-Path $base 'raw'
New-Item -ItemType Directory -Force $raw | Out-Null
$passportUrl='https://rosstat.gov.ru/opendata/7708234640-oktmo'
$passport=Join-Path $raw 'rosstat-passport.html'
Invoke-WebRequest -Uri $passportUrl -UseBasicParsing -OutFile $passport
$html=Get-Content $passport -Raw
$links=[regex]::Matches($html,'(?:https?://[^"''<> ]+/)?data-[A-Za-z0-9_.-]+\.csv') | ForEach-Object Value | Sort-Object -Unique
if(!$links){throw 'No Rosstat data CSV link found'}
$href=$links | Sort-Object -Descending | Select-Object -First 1
$dataUrl=([Uri]::new([Uri]$passportUrl,$href)).AbsoluteUri
$csv=Join-Path $raw 'rosstat-oktmo.csv'
Invoke-WebRequest -Uri $dataUrl -UseBasicParsing -OutFile $csv
$snapshots=@()
foreach($f in @($passport,$csv)){
  $h=(Get-FileHash $f -Algorithm SHA256).Hash.ToLower()
  $snapshots += [ordered]@{path=$f;sha256=$h;bytes=(Get-Item $f).Length}
}
[ordered]@{passport_url=$passportUrl;data_url=$dataUrl;snapshots=$snapshots} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $raw 'fetch-meta.json') -Encoding utf8
$data=Join-Path $repo 'geofabrik-worker-data'
docker run --rm --entrypoint python -v ($repo+':/app') -v ($data+':/data') zemlya-radar-geofabrik:task01 /app/scripts/parse_task02.py
if($LASTEXITCODE -ne 0){exit 30}
$evidence=@(
'# Task 2 evidence',
"- Completed UTC: $((Get-Date).ToUniversalTime().ToString('o'))",
'- Source: Rosstat Open Data / OKTMO',
'- Windows host TLS download succeeded; Docker performed parsing and normalization.',
'- Raw artifacts: geofabrik-worker-data/task02-host/raw',
'- Normalized output: geofabrik-worker-data/task02-host/rosstat_oktmo_kaluga.json'
)
Set-Content (Join-Path $repo 'docs\TASK_02_EVIDENCE.md') $evidence -Encoding utf8
Set-Location $repo
git add scripts/parse_task02.py scripts/run-task02-host.ps1 docs/TASK_02_EVIDENCE.md
git commit -m 'fix: use host TLS for Rosstat Task 2 ingestion'
git push origin HEAD

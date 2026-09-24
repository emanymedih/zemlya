# Task 5 — live evidence and repeatability audit

Date: 2026-09-24. Device: Windows PC with Docker Desktop.
Image built from the Task 5 working tree as `git:63b3cc9+dirty`.
Runs use an isolated SQLite database under `geofabrik-worker-data/task05-validation`.

## Current source checks (Tasks 1–3)

- Geofabrik index and publisher sidecar returned HTTP 200.
- Before refresh, local MD5 `e6eefa1f1574bbce61ed1566f9356ab0`
  differed from current publisher MD5 `c3ccc030e62f1c96334123ba4c366a99`.
  Strict freshness detection correctly identified the local PBF as behind.
- Atomic PBF ingest promoted release `db16c79fbca7` only after validation:
  878,129,435 bytes; publisher MD5 matched; SHA-256
  `db16c79fbca751be122b30a4f13bebe1e6adf6e3e3ad39c5b49ebb7885300f20`.
- PBF header replication timestamp: `2026-09-23T20:22:04Z`;
  fetched `2026-09-24T10:51:09Z`; age at first pipeline check: 14.5 h.
  Five GDAL layers opened successfully.
- Rosstat health: HTTP 200; latest advertised CSV
  `20260901T1609`; 186,533 rows, 3,283 rows for subject code 29.
  Publication age: 23 calendar days. Two reversed validity intervals are
  warnings outside subject 29; selected subject has zero such anomalies.
- Container HTTPS requests with default certificate verification: HTTP 200
  for Geofabrik, Rosstat and GitHub. No TLS verification bypass used.
## Task 5 extraction

- OSM operational AOI: Kaluga Oblast, admin_level=4, OSM ID `81995`;
  this is cartographic scope evidence, not a legal boundary.
- Source release: `db16c79fbca7`. Selected highway ways: 91,455.
- Candidate/selected counts: 91,455 / 91,455; rejected outside AOI: 0.
- Invalid geometry and duplicate OSM ID counts: 0 / 0; CRS: EPSG:4326.
- Per-way version and timestamp are unavailable in this GDAL lines layer.
  The report therefore uses the PBF replication timestamp only.
- Nine GDAL warnings about non-closed rings in the multipolygon layer
  were captured in the machine report. The selected region boundary itself
  passed geometry validity checks.

## Full pipeline and repeat

- Unit suite in Docker: 26/26 PASS.
- First current-data run: `8b6c8bc5-cfcc-44f8-9452-8ef5fc7cdf77`,
  SUCCESS, 2026-09-24T10:51:53Z–10:54:26Z.
- Same-input repeat: `0a628e46-f944-4678-aaf2-c54f81d16296`,
  SUCCESS, 2026-09-24T11:00:55Z–11:08:37Z.
- Both runs report 3 artifacts, 94,740 normalized records, 94,746
  entities and 94,743 relations. The repeat added no normalized records,
  entities or relations to the unique catalog.
- Repeat fetched a changed Rosstat passport HTML snapshot (new SHA-256);
  this correctly created one new content-addressed raw artifact. The CSV hash remained `c91a45c85d25c881b9a87cd9973a663e004b5d1b0e83d335778fcd4965ff558f`.
  Per-run membership/provenance rows grow with each run by design.
- Isolated DB after repeat: 4 pipeline runs (3 success, 1 failed), 6 unique
  raw artifacts, 186,172 normalized records, 94,761 entities and
  186,178 relations. Current pointer is the second successful run above.
- Earlier failed repeat `7e4d8bdc-9eee-4d70-b20e-0eb5831881ad` retained
  its input PBF artifact and did not move the pointer. GDAL had attempted
  to create temporary files under read-only `/work`; rerunning with
  writable `/tmp` fixed the execution setup.

## Scope

Task 5 is technically complete with source warnings disclosed.
No parcel-to-road relation was created: official parcel geometry is not yet
ingested. Full audit and next-work plan are in
`TASKS_01_05_AUDIT_2026-09-24.md`.
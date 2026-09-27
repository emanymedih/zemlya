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
  Publication age: 23 calendar days. Correction on 2026-09-27: the two
  purported reversed intervals were false warnings caused by misnamed dates.
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

## Follow-up 2026-09-25 — per-way metadata and current release

- Docker unit suite after metadata/runtime changes: 28/28 PASS.
- Added PyOsmium 4.3.1 metadata pass for selected OSM ways. Runtime image now
  installs system libexpat1, required by the PyOsmium wheel. Schema is
  osm-road-feature/v2 so v1 observations remain available and v2 records with
  version/timestamp receive their own stable identities.
- Geofabrik release: a56d6dd698ea, URL
  https://download.geofabrik.de/russia/central-fed-district-260924.osm.pbf.
  Bytes: 878,243,084; publisher MD5
  c1c40923efc89bbad2865455a2726e81 verified; SHA-256
  a56d6dd698ea6c8e3220af9793a8191d1b46ee4572042ec68076a2641a4eb3b0.
  PBF replication timestamp: 2026-09-24T20:21:20Z.
- Strict pipeline run, no allow-stale flag:
  66dffa25-1f30-48d7-b9c1-d17cd388d78b, SUCCESS,
  2026-09-25T08:26:10Z–08:28:45Z. Geofabrik freshness was current against
  publisher MD5; replication age was 12.08 h at check.
- Selected highway ways: 91,495; candidates 91,495; rejected outside AOI 0;
  invalid geometries 0; duplicate IDs 0. Version coverage 91,495/91,495 and
  timestamp coverage 91,495/91,495. Extraction duration: 140.697 seconds.
- The SQLite catalog contains 91,495 records with schema v2. Verified stored
  example: way 10254583, version 37, timestamp 2026-07-28T17:29:38Z, in
  release a56d6dd698ea. This timestamp describes the OSM object version;
  the PBF replication timestamp describes the regional snapshot.
- Warning report groups 9 identical non-closed-ring GDAL messages as one
  message with count 9 and retains the original events. The target AOI passed
  geometry validation. Pipeline counts: 3 raw artifacts, 94,780 normalized
  records, 94,786 entities, 94,783 relations.
- Source metadata documentation:
  https://docs.osmcode.org/pyosmium/latest/user_manual/02-Extracting-Object-Data/
  and https://docs.osmcode.org/pyosmium/latest/reference/File-Processing/.

- Same-input repeat on commit 9027cdc and the same current PBF completed:
  run 652369c9-e0b2-4e8c-9e27-68bef013f661, SUCCESS,
  2026-09-25T08:39:25Z–08:41:58Z. Catalog before/after retained 94,780
  normalized records, 94,786 entities, 94,783 relations and 91,495 road-v2
  records; no domain duplicates were added. Pipeline run count increased
  from 1 to 2.
- Raw artifacts increased from 3 to 4 because the Rosstat passport HTML
  response had a new content hash. The PBF and Rosstat CSV hashes remained
  identical.

## Performance and vulnerability follow-up — 2026-09-27

All runs below used the same verified local Geofabrik release
`a56d6dd698ea`, SHA-256 `a56d6dd698ea6c8e3220af9793a8191d1b46ee4572042ec68076a2641a4eb3b0`.
Its replication timestamp is 2026-09-24T20:21:20Z. On 2026-09-27,
publisher MD5 was `65cf1a8b7fd3790ef97507678cc9d077` versus local
`c1c40923efc89bbad2865455a2726e81`; replication age reached 68.06 h.
The 2026-09-27 benchmarks explicitly used `--allow-stale-geofabrik` and
isolated catalogs. A normal strict run correctly requires a new PBF ingest.

- Docker suite after the final cache integrity fixes: 39/39 PASS. Container HTTPS probe at
  2026-09-27T16:22Z returned HTTP 200 with TLS verification for Geofabrik,
  Rosstat and GitHub.
- Uncached extraction on the Docker named volume with `CPL_TMPDIR=/fast`:
  106.648 s scan, 5.220 s staging, 113.695 s total; 91,495 roads and 9
  source warnings. Earlier `/tmp` extraction of this release took 1,981.592 s.
  GDAL documents that the OSM driver may spill its geometry index to a
  temporary SQLite file in the current directory unless `CPL_TMPDIR` is set:
  https://gdal.org/en/stable/drivers/vector/osm.html
- Cached full run with SQLite on the Windows bind mount:
  run `39017d58-e426-4475-b8ff-89dce5a537ab`, 170.62 s wall time.
  Road cache hit took 1.084 s; PBF staging took 4.500 s.
- Same source with an isolated SQLite database in Docker named volume:
  run `7e23aced-d815-43dd-aef1-87ae886e9d15`, 22.83 s wall time.
  The storage location accounts for most of the observed repeat delay.
- The cache now includes the adapter source fingerprint, pinned dependency
  versions and relevant OSM configuration; its envelope checks that fingerprint
  and payload checksum. Existing v1 caches remain on disk but cannot be used
  by the new v2 adapter. A real v2 cache miss on the named-volume catalog
  completed as run `679a6289-c7b1-44f4-97d1-350407771644`:
  126.31 s wall time, 104.370 s extraction, 91,495 selected roads.
- Repeat run `97f27e61-f80a-4ef4-973e-0a75444a69f3`:
  21.33 s wall time, cache hit 1.017 s, extraction 0.000 s.
  Both v2 runs have 94,780 normalized records, 94,786 entities and
  94,783 relations in the bundle. Isolated catalog after three volume runs:
  3 pipeline runs, 5 raw artifacts, 94,780 unique normalized records,
  94,786 unique entities, 94,783 unique relations and 91,495 road-v2
  records; SQLite integrity check `ok`. Run-membership rows grow by design;
  passport HTML changes created additional raw artifacts.
- Image for the v2 live validation recorded code version
  `git:6de0223b49f4fe76842680aedf90820603b895ee-dirty`.
  Reports are under `geofabrik-worker-data/task05-performance-staged/`
  (`fingerprint-cold-volume-report.json` and
  `fingerprint-warm-volume-report.json`).

The main host SQLite file was left intact. `run-task04.ps1 -UseDockerCatalog`
provides an opt-in native-volume catalog: it verifies and copies the existing
host database once, refuses invalid input, and after each successful run
exports an atomic verified snapshot as `pipeline/volume-backup.sqlite`.
The separate diagnostic seed of the existing 20 MB host catalog retained
current run `a751c04d-5c96-4850-a2e5-bfca771d5373` and 11 run rows.
A full strict run with a freshly ingested publisher-current PBF is still
required before production acceptance of the new fast mode.

The first SQLite backup written directly through the Windows bind mount took
137.13 s for a 337 MB catalog, so the launcher now uses Docker's sequential
copy: the diagnostic `docker cp` took 3.229 s. The copied file passed SQLite
integrity check, retained the same counts/current pointer, and matched the
native volume SHA-256 exactly:
`5e89e22a9d8f31f057a65990870d595b8ebde9e4f5c6db32eb709b05a5f54a4f`.
The export script validates integrity on the native volume and compares
source/copy hashes before atomically replacing the host backup. Its PowerShell
syntax parsed successfully; an end-to-end script run was blocked by the PC's
current Restricted execution policy for .ps1 files. The Docker copy/hash
components were exercised separately. No execution policy was changed.

Final pre-refresh regression on the last code revision: run
`c6c41a32-25fd-49a4-8fb9-3ab628e1fb32` completed in 125.50 s
with a v2 cache miss, 103.942 s extraction, 91,495 ways and
9 warnings. Repeat `0cfbe844-7131-414b-95e0-b21bdce144b5`
completed in 20.03 s with cache hit 1.005 s. Reports:
`final-cold-volume-report.json` and `final-warm-volume-report.json`.
The adapter now rechecks source SHA-256 on both a cache hit (when called
without a caller-verified source) and a direct fallback after staging
failure. Those failure paths are covered by the 39-test suite.

## Current strict run and source schema correction — 2026-09-27

- Atomic Geofabrik ingest promoted `29d06dc7ff03`: 878,411,413 bytes,
  publisher MD5 `65cf1a8b7fd3790ef97507678cc9d077`, SHA-256
  `29d06dc7ff03f91452502c5166b89c29dc4210bc708378b691bb75d312b763c0`.
  Replication timestamp: 2026-09-26T20:22:51Z; local and publisher MD5
  matched at strict pipeline checks (age 21.88–22.1 hours).
- On the isolated native-volume catalog, strict cold run
  `9c7e318f-31fb-4f8c-b5bc-aa6691ebe61f` succeeded in 120 s
  (road extraction 103.011 s), followed by a 15 s warm repeat
  `fd111235-83f4-4fc6-916b-f11de4032e5f`. Both selected 91,512 ways;
  version and timestamp coverage 91,512/91,512, 9 GDAL ring warnings,
  0 invalid road geometries and 0 duplicate OSM IDs.
- The official Rosstat structure `structure-20260210T1102.csv` identifies
  fields 6–13 as section, name, additional information, description,
  change number, change type, acceptance date and introduction date.
  Earlier names `parent_name`, `legacy_code`, `valid_from`, `valid_to` were
  incorrect. Dates do not define a validity interval. The 2 older warnings
  were false and are retracted. Unexpected structure versions now fail closed.
- Corrected v2 normalization strict run
  `f3fe15b4-9408-4dca-a5a3-ee6dc9065e5d` succeeded in 15 s;
  repeat `74404220-9ddc-405e-bdaf-ca85f016b18a` succeeded in 45 s.
  Both: 94,797 records, 94,803 entities, 94,800 relations per bundle;
  Rosstat 186,533 total / 3,283 selected, 0 false date issues.
- Corrected snapshot and same-input repeat left unique catalog totals stable:
  189,577 records (including historical schemas/releases), 94,809 entities,
  186,300 relations; SQLite integrity `ok`. Nine diagnostic runs remain in
  the isolated catalog, with the last strict run as current pointer.
  Reports: `strict-fresh-*.json` under `task05-performance-staged/`.
- Full Docker unit suite after the parser correction: 39/39 PASS.
  The production host catalog remains unchanged. Manual Docker validation
  did not exercise the `.ps1` launcher because Windows policy is Restricted.

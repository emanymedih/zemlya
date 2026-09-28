# Interim core quality gate, 2026-09-28

## Scope and decision

Tasks 8–12 apply to the current Geofabrik road and Rosstat OKTMO core. Parcel
data and parcel-to-road relations remain outside this gate (Task 13). The
operational acceptance policy is `interim-core-quality/v1`. Its 48-hour PBF
replication age, 45-day publication age for **each** Rosstat CSV, and allowance
for the nine exact known GDAL warnings are project limits, not publisher SLAs.
An unknown/future age, changed publisher checksum, new GDAL warning, missing
OSM object version/timestamp, incomplete hierarchy/recode, or dirty/unknown
code version blocks publication. Counts and individual booleans are in each
`source_summary.quality_gate`.

## Resolved audit points

| Area | Change and check |
| --- | --- |
| One active catalog | `.cmd` uses the Python launcher, which locks the data directory for build, run and export. An existing native volume blocks an implicit host-catalog run. An explicit legacy diagnostic flag remains available. |
| Schema and migration | SQLite v1 migrates transactionally to v2 on first open. Unsupported/unversioned catalogs fail closed. Native volume was migrated only after a verified, independent pre-v2 copy. |
| Repeated raw snapshots | Content identity remains immutable; each successful or failed run gets its own capture event with URL, time, path, checksum and `download`/`verified_local` kind. Historical v1 capture events were not invented. |
| Row provenance | Every current production relation links to its supporting normalized record. Reused OKTMO code entities carry every additional row observation, including coding table rows. Endpoint types, dataset-specific CSV evidence and natural IDs are checked before commit. |
| Transaction | Immutable ID collisions with different content fail. Foreign keys and SQLite integrity are checked before pointer promotion. An older run cannot move `current_run_id` backwards. |
| Rosstat parsers | Small byte-for-byte excerpts from the official 20260901 CSVs pin SHA-256 and expected section, dates, replacement and annulment. The fixture stores original physical line numbers separately from the parser's excerpt-relative numbers. |
| Failure and repeat | Tests cover changed payload collision, corrupted backup, divergent host/volume runs, parser failure with preserved raw input, SQLite rollback, unchanged snapshot capture events, and Windows handle closure. |

## Local Windows gate

Device `PC`, `C:\Users\admla\zemlya`, Docker Desktop with the existing
`landradar-catalog`. PowerShell execution policy is `Restricted`; the gate
used `scripts\run-task04.cmd --use-docker-catalog` without policy changes.
Before active migration, the v1 native volume was copied to
`geofabrik-worker-data/pipeline/pre-v2-20260928.sqlite`. Its source had 14
runs, 101,094 records, 101,079 entities, 104,384 relations and pointer
`865aa3a0-1cff-4368-a2d7-9d55c5b42314`. On the independent copy, v2
retained these values and `PRAGMA integrity_check=ok`,
`foreign_key_check` returned no rows. The copy took 180.51 s on the Windows
bind mount; this is a safety backup cost, not the native-volume pipeline time.

The first live attempt with `67c9b88` exposed an overly exact record/artifact
source-key check for the Rosstat dataset CSV. It exited with code 1 and wrote a
failed run; the prior successful pointer stayed in place. The check was
corrected to accept only `rosstat_opendata_{dataset_id}_data` for a Rosstat
record, with a negative test for a passport artifact. The corrected code
commit is `c0ae30e1247693060ec945f998632f15f33932b0`.

Two consecutive corrected strict launches completed with exit code 0:

| Measure | First | Repeat |
| --- | --- | --- |
| Run ID | `ccb9f479-23d5-4d08-ab2c-fa8bec140080` | `daef8ccd-1712-40f0-8c51-f27ac83e1782` |
| Launcher wall time including build, preflight and backup | 66.16 s | 67.92 s |
| Parallel Rosstat fetch and parse | 7.547 s | 7.945 s |
| PBF staging | 5.071 s | 5.603 s |
| Geofabrik | publisher MD5 `54090e39e2886ff0e143e793ca178fd3`, 91,515 roads, 9 known warnings | same source, age 16.29 h |
| Rosstat | OKTMO and coding table `20260901T1609` | same versions |
| Bundle counts | 5 artifacts, 97,809 records, 101,067 entities, 104,374 relations | identical |
| Quality and catalog | `PASS`, integrity `ok`, FK issues 0, schema v2 | identical |
| Exported backup SHA-256 | `fd18441d6d31aeb2e55f67890f00754c1cfbe281628c6dae927da4176a5631aa` | `0ba042f746d6df664c5e7507fe91246e9f6af356f962c862af0b870682c0ab91` |

The active volume after the repeat has 17 runs (13 successful, 4 failed),
101,094 distinct records, 101,079 entities and 104,384 relations. The repeat
has 5 capture events, 104,106 entity evidence links, and 104,374 relation
record evidence links. `integrity_check=ok`, no foreign-key issue, and its
current pointer matches the exported backup. The historical pre-v2 run has
zero fabricated capture events. Both launcher exports verified native-source
and host-copy SHA-256 before replacing `volume-backup.sqlite`.

The Docker test suite on the PC passed 72/72 at `67c9b88`; after the
Rosstat contract fix the local suite passed 73/73. CI status for the final
commit is recorded separately once its Docker/Windows and external live
workflows finish.

## Remaining operating boundaries

- A successful run observes the current publishers at that moment; the age
  thresholds may deliberately stop a later run until a new publisher release
  is ingested or the policy is reviewed with evidence.
- The nine GDAL warnings remain in the report. A changed warning baseline
  blocks promotion and requires source-specific review.
- Historical v1 entity/relation evidence lacks row-level per-run receipts;
  only new v2 runs provide them. The raw snapshots and original historical
  links remain readable.
- `.ps1` execution as a whole remains blocked by the PC's `Restricted`
  policy. The production local gate is the tested `.cmd` path.

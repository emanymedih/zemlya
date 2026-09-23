# Audit — Tasks 1–3 test-run review

## Task 1 — Geofabrik / OSM

Result: PASS.
- Docker verify-current passed for release 8f7ab17b3321.
- Byte count: 877774222.
- MD5 and SHA-256 match manifest.
- Five GDAL OSM layers opened.
- GitHub external gate and idempotent second run are recorded.
- Added a Windows PowerShell runner because Unix shell is absent on PC.

## Task 2 — Rosstat / OKTMO

Initial result: INVALID DATA MODEL.
- The CSV is headerless.
- DictReader treated the first data row as headers.
- The previous 15 matches were text coincidences, not Kaluga rows.

Correction:
- Explicit 13-column headerless schema.
- oktmo_code built from four code parts.
- Kaluga is selected by official subject code 29.
- Correct result: 186533 total rows, 3283 Kaluga rows.
- Added a regression test for the schema.
- Raw snapshots use timestamped names and are not overwritten.
- Operational CLI drift was found on final E2E: the old default text filter still returned 15 rows.
- CLI default now uses official `subject_code=29`; full container ingest returns 3283 rows.

## Task 3 — execution environment

Result: PASS / DONE.
- Host Docker/DNS/HTTPS and disk checks pass.
- Container Geofabrik, Rosstat and GitHub HTTPS return HTTP 200.
- Rosstat root and intermediate CA are pinned by DER SHA-256 and verified during image build.
- Runtime uses an app-local CA bundle; certificate and hostname verification stay enabled.
- Preflight passed twice on the test tag and again on the canonical `task01` tag.

## Test run

- Current smoke suite: 10/10 PASS, including the CLI selection regression test.
- Task 1 verify-current: PASS for release `8f7ab17b3321`.
- Task 2 direct container health and full ingest: 186533 total / 3283 subject-code-29.
- Task 3 preflight: repeated successfully with direct Rosstat TLS.

## Verdict

Task 1: DONE.
Task 2: DONE, corrected, E2E-tested and regression-backed.
Task 3: DONE with direct verified container TLS.

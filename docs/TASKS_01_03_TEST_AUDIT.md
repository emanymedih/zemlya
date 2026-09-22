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

## Task 3 — execution environment

Result: PARTIAL / BLOCKED.
- Host Docker/DNS/HTTPS and disk checks pass.
- Container Geofabrik and GitHub HTTPS pass.
- Container Rosstat direct TLS fails certificate verification.
- Host Schannel download plus Docker parsing works and is tested.
- Full DONE requires direct container TLS or an explicitly accepted runtime CA policy.

## Test run

- Current smoke suite: 9/9 PASS.
- Task 1 verify-current: PASS.
- Task 2 live parser: 186533 total / 3283 subject-code-29.
- Task 3 preflight: repeated successfully.

## Verdict

Task 1: DONE.
Task 2: CORRECTED and test-backed.
Task 3: PARTIAL / BLOCKED, with a working documented fallback.

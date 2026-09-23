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


## Повторный аудит Tasks 1–4 — 2026-09-23

- Task 1: новый current release `82d8e131284a` скачан и проверен; publisher
  MD5 и локальный MD5 совпали (`e6eefa1f1574bbce61ed1566f9356ab0`), SHA-256,
  PBF header и 5 GDAL layers подтверждены. Строгий pipeline сравнивает sidecar
  снова непосредственно перед использованием; старый release остаётся только
  историческим доказательством GitHub gate.
- Task 2: schema/field validation прошли для 186533 строк. Обнаружены две
  инверсии интервала дат в subject 95, вне выбранной Калужской области (29).
  Raw source сохранён; строки помечаются, не исправляются эвристикой; выбранный
  субъект блокируется, если в нём есть такие строки. Возраст latest Rosstat
  файла показывается: версия 20260901T1609, 22 календарных дня на запуск.
- Task 3: прямой HTTPS/TLS был повторно использован внутри последнего live
  Docker pipeline; проверка сертификатов/hostname не отключалась. Ранее
  измеренный запас диска превышал preflight минимум на несколько сотен GB.
- Task 4: current run `a751c04d-5c96-4850-a2e5-bfca771d5373` завершился
  успешно: 3 raw artifacts, 3284 normalized records, 3290 entities, 3288
  relations; target subject содержит 3283 записи. Неуспешный source parse
  сохранён как failed run без продвижения current pointer.
- Финальная локальная Docker regression suite: **22/22 PASS**; проверены
  row validation, freshness helper, code version, failed raw artifact links,
  idempotence и rollback. Workflow на push/PR добавляет постоянный CI gate.
- Обнаружен и исправлен эксплуатационный дефект: Task 4 launcher строил
  default data path из текущего каталога, из-за чего запуск вне repo root
  находил пустой volume. Теперь путь вычисляется от repo root.

Вывод: Tasks 1–4 технически пригодны в объявленной границе; качество источника
Росстат не идеально, это теперь явно видно как 2 source warnings. Готовность
означает воспроизводимый ingestion/provenance, не безошибочность upstream data.

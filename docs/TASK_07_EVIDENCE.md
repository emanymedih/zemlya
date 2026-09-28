# Task 7 — evidence и проверки (2026-09-28)

Официальный набор Росстата: `7708234640-codingtable`, текущий файл
`data-20260901T1609-structure-20231110T1511.csv`.
Паспорт набора публикует версии данных отдельно от основного ОКТМО.

## Live result

- Калужская область: 3 009 evidence rows.
- 3 007 прямых отношений `oktmo_replaced_by`.
- 2 аннулированных кода без указанной замены.
- Изменения источника: 609/2023, 814/2025, 815/2025, 834/2025 ОКТМО.
- Есть 1 прямая цепочка, где target одного отношения сам является cancelled code.
  Поэтому transitive replacement не материализуется.
- One-to-many для Калужской области: 0; циклы: 0; исключения: 0.
## Реальный edge case федерального набора

Первый strict-run остановился на строках Москвы: официальный CSV содержит
8-значные коды и continuation rows с пустыми subject/cancel/change.
Также встречается `*` после действующего кода. Парсер расширен под фактический
официальный формат, сохраняя note и номер физической строки.

После исправления Docker suite: 54/54 PASS.

## Предварительный strict-run

Geofabrik release `36d270c5b4b6`, publisher MD5
`54090e39e2886ff0e143e793ca178fd3`, SHA-256
`36d270c5b4b6787bcd1de06d490548773c5e429882ef0c905c236862d8155b20`.
Run `f99581cf-f9fa-42e9-b973-7ec50a37c7f8` завершён успешно.
Bundle: 5 raw artifacts, 97 809 normalized records, 101 067 entities,
104 374 relations.

Machine report:
`geofabrik-worker-data/task07-validation/strict-recode-report.json`.

Финальная committed-image проверка выполняется после фиксации implementation
commit; этот предварительный run не используется как доказательство code version,
поскольку базовый image ещё содержал предыдущий `LANDRADAR_CODE_VERSION`.

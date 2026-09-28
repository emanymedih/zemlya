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

## Финальная committed-code проверка

Implementation commit: `a4abcd8c7652`. Docker image собран с
`LANDRADAR_CODE_VERSION=git:a4abcd8c7652`.

Geofabrik release `36d270c5b4b6`, publisher MD5
`54090e39e2886ff0e143e793ca178fd3`, SHA-256
`36d270c5b4b6787bcd1de06d490548773c5e429882ef0c905c236862d8155b20`.

Strict run `7b17df74-9097-4938-8132-43fc512fe941` и повтор
`865c1342-c1be-41a7-b95f-b1b3577df945` завершены успешно с
`code_version=git:a4abcd8c7652`. Оба сохранили 3 009 evidence rows,
3 007 `oktmo_replaced_by`, 2 аннулирования без замены, 0 циклов и
0 исключений. Bundle каждого запуска: 5 raw artifacts, 97 809 normalized
records, 101 067 entities, 104 374 relations.

Финальный SQLite-каталог: 2 успешных pipeline runs, `integrity=ok`,
current run `865c1342-c1be-41a7-b95f-b1b3577df945`.
Machine reports:
`geofabrik-worker-data/task07-validation/strict-recode-final-report.json` и
`strict-recode-final-repeat-report.json`.

# Task 2 evidence

- Первичное выполнение: 2026-09-22; прямой container rerun: 2026-09-23.
- Source: Rosstat Open Data / OKTMO; dataset `7708234640-oktmo`.
- Актуальный CSV: `data-20260901T1609-structure-20260210T1102.csv`.
- Всего записей: 186533.
- Официальный код субъекта Калужской области: `29`.
- Записей Калужской области: 3283.
- CSV не содержит header; parser назначает явную схему из 13 колонок.
- OKTMO code собирается из первых четырёх кодовых частей.
- Default `rosstat-oktmo` выбирает `subject_code=29`; текстовый поиск доступен только как явный диагностический `--filter`.
- Прямой TLS download и нормализация успешно выполнены внутри рабочего Docker image.
- Нормализованный результат: `geofabrik-worker-data/task02-direct/rosstat_oktmo_kaluga.json`.
- CSV snapshot: 20125498 байт; SHA-256 `c91a45c85d25c881b9a87cd9973a663e004b5d1b0e83d335778fcd4965ff558f`.
- Windows-host download остаётся аварийным fallback, canonical path теперь полностью контейнерный.
- Regression suite после аудита Tasks 1–4: 22/22 PASS в Docker.
- Каждая из 186533 строк проходит проверку 13 полей, кодовых ширин,
  control/record type, непустого имени и календарного синтаксиса.
- Обнаружены две строки с обратным интервалом дат вне subject 29;
  они видны в Task 4 quality warnings, не переписываются; целевой subject
  блокируется, если аномальная строка относится к нему.
- Terms URL и source attribution сохраняются в результате.

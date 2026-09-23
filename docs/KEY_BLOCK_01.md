# Ключевой блок 01

## Состав

1. Production-ingestion OSM/Geofabrik.
2. Production-ingestion Росстат/ОКТМО.
3. Рабочая execution-среда с outbound DNS/HTTPS.
4. Общий pipeline raw → normalized → entity → relations.
5. RoadFeature и spatial relations.
6. Иерархия ОКТМО Калужской области.
7. История/перекодировка ОКТМО.
8. Строгая schema validation.
9. Реальные snapshots.
10. Проверка checksum/структуры/воспроизводимости.
11. Повторная загрузка.
12. Только после этого источники получают DONE.

## Состояние задач 1–3

Task 1/12 — OSM/Geofabrik production ingestion.

Статус: DONE.

Внешний gate закрыт 2026-09-22.

Результат live-run:
- runtime: GitHub Actions `ubuntu-24.04` + Docker;
- workflow run: `35697364896`;
- Geofabrik release: `8f7ab17b3321`;
- byte count: `877774222`;
- publisher MD5: `d1af4ac63f1ba9110f736b41031d98a1`;
- SHA-256: `8f7ab17b33214a1a22be740387880e1c5156bf932e994170a84e2d60a8367be5`;
- PBF header и пять GDAL/OSM-слоёв проверены;
- `verify-current` прошёл после первого и второго запуска;
- второй запуск сохранил тот же current pointer, manifest, SHA-256, размер и mtime PBF;
- компактный evidence artifact сохранён workflow на 30 дней.

Task 1 соответствует критериям DONE.

### Task 2/12 — Росстат / ОКТМО

Статус: **DONE**. Headerless-схема из 13 колонок зафиксирована явно;
Калужская область выбирается по официальному коду субъекта `29`.
Прямой container ingest: 186533 строк всего, 3283 строки региона.

### Task 3/12 — execution environment

Статус: **DONE**. Docker, storage, host/container DNS и HTTPS проверены.
Прямой TLS к Rosstat работает через закреплённый app-local CA bundle при
включённой проверке сертификата и hostname.

Следующая задача блока: Task 4 — общий pipeline `raw → normalized → entity → relations`.

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

## Текущая задача

Task 1/12 — OSM/Geofabrik production ingestion.

Статус: READY_FOR_EXTERNAL_LIVE_RUN.

Единственный незакрытый gate — настоящий live-run на внешнем worker с интернетом и повторный запуск. Код, локальная E2E-проверка, checksums, fail-safe promotion, provenance и Docker worker готовы.

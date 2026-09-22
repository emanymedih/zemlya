# Changelog

## 2026-09-22 — facts-only reset

Удалены неподтверждённые инвестиционные оценки: LandScore, веса, ROI, маржа, прогнозная выручка, условные рыночные ориентиры и упрощённый расчёт раздела.

Ядро оставляет только факты с источниками, provenance, конфликты и аудит отсутствующих данных.

## 2026-09-22 — source pass 01

Начаты интеграции:
- OpenStreetMap / Geofabrik;
- Росстат Open Data / ОКТМО.

Добавлены raw snapshots, SHA-256, fail-closed поведение и health-check команды.

## 2026-09-22 — Key Block Task 1

OSM source-of-truth переключён на raw Geofabrik PBF. Реализованы:
- официальный machine-readable Geofabrik index;
- publisher MD5;
- SHA-256;
- PBF header parsing;
- GDAL OSM validation;
- immutable releases;
- provenance;
- moving-latest protection;
- verify-current;
- Docker worker;
- storage preflight.

Текущий статус: READY_FOR_EXTERNAL_LIVE_RUN. Task 1 не считается DONE до настоящего внешнего live-run и второго идемпотентного запуска.

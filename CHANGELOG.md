# Changelog

## 2026-09-23 — Task 3 direct container TLS

Закрыт gate execution-среды без отключения TLS verification. В Docker image
добавлена закреплённая CA-цепочка Rosstat и app-local bundle; прямой HTTPS из
контейнера возвращает HTTP 200 для Geofabrik, Rosstat и GitHub.

Финальный E2E также обнаружил старый default text-filter в `rosstat-oktmo`.
Default заменён на официальный `subject_code=29`: полный ingest даёт 3283
строки Калужской области из 186533. Добавлен regression-test; suite 10/10.

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

Статус после внешнего gate: DONE. Второй идемпотентный запуск подтверждён в GitHub Actions; локальный verify-current также прошёл.

## 2026-09-22 — Key Block Task 3

Зафиксирован частичный результат execution-среды: Docker, storage, host HTTPS,
container DNS/HTTPS и повторяемый preflight. Прямой container TLS Rosstat
оставался блокером; Windows Schannel использовался как временный fallback.

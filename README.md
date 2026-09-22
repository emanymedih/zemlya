# Земля Радар

Система сбора, проверки и последующего анализа фактических данных о земельных участках. Первый целевой регион — Калужская область, основной практический фокус — участки под ИЖС.

## Базовый принцип

В рабочее ядро попадают только данные с явным источником. Отсутствующее значение остаётся отсутствующим. Неподтверждённые оценки, LandScore, ROI и другие прогнозные показатели сейчас отключены.

## Архитектура

```text
source
  ↓
raw immutable snapshot
  ↓
normalized source data
  ↓
entities + relations
  ↓
ParcelRecord
  ↓
audit / conflicts / missing facts
```

Для каждого факта сохраняется provenance: источник, URL/идентификатор, дата получения, статус и связь с исходным snapshot.

## Текущий ключевой блок

Работа ведётся последовательно. Следующий блок не начинается, пока текущий не закрыт по критериям приёмки либо не найден более эффективный рабочий способ решить ту же задачу.

**Task 1/12 — OSM / Geofabrik production ingestion**

Статус: **READY_FOR_EXTERNAL_LIVE_RUN**.

Готово:
- canonical source-of-truth: raw Geofabrik `.osm.pbf`;
- machine-readable Geofabrik index;
- publisher MD5 + SHA-256;
- PBF-header validation;
- GDAL/OSM validation;
- immutable releases;
- provenance;
- fail-safe promotion;
- повторная `verify-current`;
- Docker worker;
- локальные E2E и failure-тесты.

Оставшийся gate: один настоящий внешний live-run на хосте с outbound DNS/HTTPS, затем повторный запуск для проверки идемпотентности. До этого Task 1 не считается DONE.

## Источники в работе

- OpenStreetMap / Geofabrik — пространственные данные и дорожная сеть.
- Росстат Open Data / ОКТМО — официальная территориальная привязка. Адаптер существует, но следующий блок не начинается до закрытия Task 1.

## Тесты

```bash
python -m unittest discover -s tests -v
```

## Live worker

```bash
./deploy/geofabrik-worker/run-external-docker.sh
```

Подробности: `docs/BLOCK_02_TASK_01_GEOFABRIK_PRODUCTION_INGEST.md`.

## Важно

OSM может подтверждать наличие картографированной дороги и её тегов. OSM сам по себе не подтверждает юридическое право подъезда к земельному участку.

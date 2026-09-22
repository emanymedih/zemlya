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

Статус: **DONE**.

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

Внешний gate закрыт 2026-09-22 в GitHub Actions (`ubuntu-24.04` + Docker): реальный PBF Geofabrik скачан и проверен, `verify-current` прошёл после обоих запусков, второй запуск подтвердил идемпотентное переиспользование того же release. Evidence: workflow run `35697364896`, release `8f7ab17b3321`.

## Источники в работе

- OpenStreetMap / Geofabrik — пространственные данные и дорожная сеть.
- Росстат Open Data / ОКТМО — официальная территориальная привязка. Адаптер существует; Task 2 может быть начат.

## Тесты

```bash
python -m unittest discover -s tests -v
```

Полный локальный рабочий suite текущей разработки: 20/20 PASS. В репозитории также лежат базовые smoke-тесты для ядра и PBF-контракта.

## Live worker

```bash
sh deploy/geofabrik-worker/run-external-docker.sh
```

Подробности: `docs/KEY_BLOCK_01.md`.

## Важно

OSM может подтверждать наличие картографированной дороги и её тегов. OSM сам по себе не подтверждает юридическое право подъезда к земельному участку.

## Task 3 — execution environment

Статус: **DONE**.

Проверены Docker API, storage preflight, Windows Schannel HTTPS,
container DNS/HTTPS и повторный preflight. Для Rosstat зафиксирован
source-aware transport: Windows выполняет TLS-загрузку, Docker —
парсинг и нормализацию локального snapshot. Evidence: `docs/TASK_03_EVIDENCE.md`.

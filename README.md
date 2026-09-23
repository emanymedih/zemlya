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
- Росстат Open Data / ОКТМО — официальная территориальная привязка. Task 2 live-ingestion выполнен; schema и subject-code filter проверены.

## Тесты

```bash
python -m unittest discover -s tests -v
```

Текущий suite: 14/14 PASS. Включает pipeline-контракты, идемпотентность каталога, проверку связей и rollback failed run. Task 4 live E2E на PC обработал 3 raw artifacts, 3284 normalized records, 3290 entities и 3288 relations. Повторный прогон сохранил размеры каталога. Подробности: `docs/TASK_04_EVIDENCE.md`.

## Live worker

```bash
sh deploy/geofabrik-worker/run-external-docker.sh
# Windows PowerShell:
./deploy/geofabrik-worker/run-external-docker.ps1
```

Подробности: `docs/KEY_BLOCK_01.md`.

## Важно

OSM может подтверждать наличие картографированной дороги и её тегов. OSM сам по себе не подтверждает юридическое право подъезда к земельному участку.

## Task 3 — execution environment

Статус: **DONE**.

Docker API, storage, host HTTPS и прямой container HTTPS проверены для
Geofabrik, Rosstat и GitHub. Для неполной серверной цепочки Rosstat runtime
использует закреплённые root/intermediate CA в app-local bundle; TLS и
hostname verification остаются включёнными. Полный Rosstat ingest теперь
работает внутри контейнера и по умолчанию выбирает официальный код субъекта
Калужской области `29`: 3283 строки из 186533. Evidence:
`docs/TASK_03_EVIDENCE.md`.

## Task 4 — общий pipeline

Статус: **DONE**. Команда `pipeline-run` объединяет проверенные Geofabrik и
Rosstat snapshots в общий SQLite-каталог: `raw → normalized → entity → relations`.
Runs сохраняют provenance; стабильные ID обеспечивают идемпотентность, а
неуспешный запуск не двигает указатель на последний успешный run. Реализация
ограничена release/layers и ОКТМО; связи участков с дорогами — следующая Task 5.
Evidence: `docs/TASK_04_EVIDENCE.md`.

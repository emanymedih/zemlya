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

Внешний gate закрыт 2026-09-22 в GitHub Actions (`ubuntu-24.04` + Docker): release `8f7ab17b3321` проверен идемпотентно. Для рабочего контура 2026-09-23 загружен новый release `82d8e131284a`; его MD5 совпал с текущим publisher sidecar и прошли `verify-current`/GDAL checks. Старый workflow gate остаётся историческим доказательством; current-freshness проверяется при каждом pipeline-run.

## Источники в работе

- OpenStreetMap / Geofabrik — пространственные данные и дорожная сеть.
- Росстат Open Data / ОКТМО — официальная территориальная привязка. Task 2 live-ingestion выполнен; schema и subject-code filter проверены.

## Тесты

```bash
python -m unittest discover -s tests -v
```

На 2026-09-27 Docker suite: 45/45 PASS. Он проверяет pipeline, кэш дорог, иерархию ОКТМО, миграцию SQLite и rollback. Свежий выпуск Geofabrik `29d06dc7ff03` прошёл строгий запуск и повтор. Результаты и ограничения: `docs/TASK_05_EVIDENCE.md`, `docs/TASK_06_EVIDENCE.md` и `docs/TASKS_01_05_AUDIT_2026-09-24.md`.

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
неуспешный запуск не двигает указатель на последний успешный run. На этапе
Task 4 слой ограничивался release/layers и ОКТМО; дороги добавлены в Task 5,
а связь с участком требует официальной геометрии Parcel (Task 13).
Evidence: `docs/TASK_04_EVIDENCE.md`.

## Task 5 — дорожный слой OSM

Статус: **DONE_WITH_WARNINGS**. Из проверенного Geofabrik PBF извлекаются дороги Калужской области с геометрией, тегами, OSM version/timestamp и provenance. Кэш привязан к исходному SHA-256 и версии адаптера; временные файлы PBF/GDAL можно разместить в Docker volume `/fast`. Результат не подтверждает юридический подъезд к конкретному участку. Для ускорения SQLite доступен режим `./scripts/run-task04.ps1 -UseDockerCatalog`: перед первым использованием он проверяет исходную базу и копирует её в отдельный volume, оставляя исходный файл на месте. На проверенном ПК исполнение .ps1 пока блокирует Windows Restricted execution policy; Docker-компоненты режима испытаны отдельно. Подробности: `docs/TASK_05_EVIDENCE.md`.


## Task 6 — иерархия кодов ОКТМО

Статус: **DONE**. Из официальных полей `TER/KOD1/KOD2/KOD3` построены
3 281 связь родительского кода для 3 283 строк Калужской области.
Каждая связь подтверждена CSV snapshot; проверки дублей, отсутствующих
родителей и циклов прошли без исключений. Это иерархия кодов, не границы
земельных участков. Подробности: `docs/TASK_06_PLAN.md` и
`docs/TASK_06_EVIDENCE.md`.

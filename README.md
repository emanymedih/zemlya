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

На 2026-09-28 локальный и Docker CI suites: 73/73 PASS; Windows launcher CI тоже успешен. Свежий выпуск Geofabrik `36d270c5b4b6` прошёл строгий запуск и повтор на ПК и во внешнем CI. Результаты и ограничения: `docs/CORE_QUALITY_GATE_2026-09-28.md`, `docs/TASK_05_EVIDENCE.md`, `docs/TASK_06_EVIDENCE.md`, `docs/TASK_07_EVIDENCE.md`.

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

Статус: **DONE_WITH_WARNINGS**. Из проверенного Geofabrik PBF извлекаются дороги Калужской области с геометрией, тегами, OSM version/timestamp и provenance. Кэш привязан к исходному SHA-256 и версии адаптера; временные файлы PBF/GDAL можно разместить в Docker volume `/fast`. Результат не подтверждает юридический подъезд к конкретному участку. Для ускорения SQLite используется `scripts\run-task04.cmd --use-docker-catalog` в Windows. При существующем native volume launcher блокирует случайный запуск в отдельный host-каталог. `.cmd` требует Docker Desktop, Git и Python 3 (`py -3` либо `python`) в PATH и работает при PowerShell `Restricted`. Резервная копия `geofabrik-worker-data/pipeline/volume-backup.sqlite` проходит проверку хэша и указателя текущего запуска. Местный gate и миграция v2: `docs/CORE_QUALITY_GATE_2026-09-28.md`.


## Task 6 — иерархия кодов ОКТМО

Статус: **DONE**. Из официальных полей `TER/KOD1/KOD2/KOD3` построены
3 281 связь родительского кода для 3 283 строк Калужской области.
Каждая связь подтверждена CSV snapshot; проверки дублей, отсутствующих
родителей и циклов прошли без исключений. Это иерархия кодов, не границы
земельных участков. Подробности: `docs/TASK_06_PLAN.md` и
`docs/TASK_06_EVIDENCE.md`.


## Task 7 — история и перекодировка ОКТМО

Статус: **DONE**. Подключена официальная перекодировочная таблица Росстата.
Для Калужской области сохранено 3 009 строк evidence и 3 007 прямых
`oktmo_replaced_by`; 2 аннулирования идут без замены, циклов нет.
Транзитивная замена автоматически не выводится. Поддержаны 8/11-значные
коды, continuation rows и source note `*` из федерального CSV.
Подробности: `docs/TASK_07_PLAN.md` и `docs/TASK_07_EVIDENCE.md`.

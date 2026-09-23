# Task 4 — общий pipeline данных

Статус: **DONE**.

## Цель

Объединить проверенные ingestion Task 1–3 в один запуск, где raw snapshots,
нормализованные записи, сущности и связи сохраняются с общей provenance и
могут быть повторно воспроизведены.

## Поток данных

    Geofabrik PBF ── verify ──┐
                              ├─ raw artifacts → normalized records
    Rosstat CSV ─── parse ────┘                 → entities → relations
                                                    → SQLite + report

## Реализация

1. Сохранить source-specific проверки: PBF checksum/header/GDAL и
   Rosstat headerless 13-column schema.
2. Ввести канонические контракты RawArtifact, NormalizedRecord, Entity,
   Relation и PipelineRun.
3. Давать артефактам/записям/сущностям/связям детерминированные ID.
4. Хранить immutable snapshots и историю runs в SQLite.
5. Публиковать current_run только после атомарного успешного commit.
6. На повторных запусках повторно связывать те же ID, не дублируя
   catalog records/entities/relations.
7. Создавать только подтверждаемые relations: release → layers и
   OKTMO unit → subject code 29.
8. Добавить команду pipeline-run и PowerShell launcher для PC.
9. Проверить повторный live-run, целостность provenance и failure rollback.

## Хранилище

SQLite содержит pipeline_runs, raw_artifacts, normalized_records,
entities, entity_observations, relations и таблицы связей runs-to-data.
Исходные raw-файлы остаются в файловой системе; SQLite хранит их metadata,
checksum и путь.

## Критерии приёмки

- один pipeline-run обрабатывает текущий проверенный Geofabrik release
  и текущий Rosstat CSV;
- каждая normalized record ссылается на raw artifact и schema version;
- каждая entity и relation имеет устойчивый идентификатор и evidence;
- relation без известных endpoint/evidence не проходит validation;
- повторный запуск не увеличивает число уникальных artifacts/records/entities/relations;
- каждый запуск сохраняется отдельно и связан с использованными данными;
- failed run не меняет указатель на последний успешный run;
- machine-readable report содержит counts, source keys, hashes и run_id;
- тесты и live E2E проходят в Docker на PC.

## Границы задачи

Task 4 создаёт сущности для Geofabrik release/layers и OKTMO units.
Она ещё не извлекает все OSM features в доменные entities и не связывает
участки с дорогами. Пространственные отношения относятся к Task 5.
Task 4 также не добавляет LandScore, цены или прогнозные выводы.

## План-факт и проверка

- Реализованы контракты в `landradar/pipeline/contracts.py`, SQLite-каталог
  в `store.py` и объединяющий runner в `runner.py`.
- Добавлены `pipeline-run`, PowerShell launcher и Docker E2E.
- Финальный live run: `5bbcfa06-181b-403d-8ad0-6329ba4a1466`; 3 raw
  artifacts, 3284 normalized records, 3290 entities, 3288 relations.
- Повторный прогон создал отдельный run и не увеличил число уникальных
  записей/сущностей/связей. Изменившиеся HTML snapshots сохранены по хэшу.
- SQLite содержит 3 успешных и 1 неуспешный run; последний оставил
  `current_run_id` на последнем успешном run. Проверены rollback и TLS.
- Docker suite: 14/14 PASS. Подробные счётчики и hashes —
  `docs/TASK_04_EVIDENCE.md`.

Задача закрыта в пределах заявленной границы: полный импорт OSM features,
пространственный join участков и дорог остаются в Task 5.

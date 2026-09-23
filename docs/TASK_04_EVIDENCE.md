# Task 4 — evidence

Дата выполнения: 2026-09-23. Устройство: Windows PC; запуск в Docker.

## Результат

Финальный run_id: `5bbcfa06-181b-403d-8ad0-6329ba4a1466`.

| Слой | Число в финальном run |
|---|---:|
| Raw artifacts | 3 |
| Normalized records | 3284 |
| Entities | 3290 |
| Relations | 3288 |

Состав normalized records: один manifest Geofabrik и 3283 строки ОКТМО
Калужской области из 186533 записей источника. Код субъекта — `29`.

## Provenance

- Geofabrik release: `8f7ab17b3321`
- PBF SHA-256: `8f7ab17b33214a1a22be740387880e1c5156bf932e994170a84e2d60a8367be5`
- Rosstat CSV SHA-256: `c91a45c85d25c881b9a87cd9973a663e004b5d1b0e83d335778fcd4965ff558f`
- Rosstat passport SHA-256: `8c269df34f9d1dca99ce047f2f85f1cee1db8e0915633fb739420e07399ecc06`
- Машиночитаемый report: `geofabrik-worker-data/pipeline/current-report.json`

## Проверки

- Docker build завершился успешно; suite — **14/14 PASS**.
- Task 1 `verify-current`: PASS; PBF 877774222 bytes, SHA-256 совпадает,
  проверены пять GDAL/OSM layers.
- Task 3 preflight: host и container HTTPS 200 для Geofabrik, Rosstat и GitHub;
  TLS verification включена; свободное место выше установленного порога.
- Повторный E2E создал новый run с теми же per-run counts; каталог записей,
  сущностей и связей не раздулся от повторной обработки одинаковых snapshots.
- В локальной рабочей БД записано 3 успешных и 1 failed runs. Failed run не
  сменил current pointer; текущий указатель указывает на
  `5bbcfa06-181b-403d-8ad0-6329ba4a1466`.
- Уникальные raw artifacts — 5: PBF и CSV переиспользуются по хэшу; три
  успешно полученных HTML passport snapshots различаются и сохранены отдельно.
- Отношения ограничены пятью `contains_layer` и 3283 `within_subject`.
  OSM features и spatial join участков с дорогами не входят в Task 4.

## Каталог после live-повторов

| Таблица | Записей |
|---|---:|
| raw_artifacts | 5 |
| normalized_records | 3284 |
| entities | 3290 |
| entity_observations | 3290 |
| relations | 3288 |
| run_artifacts / run_records | 9 / 9852 |
| run_entities / run_relations | 9870 / 9864 |

DB aggregate включает связи трёх успешных запусков с общим набором данных;
per-run counts выше показывают объём одного запуска.

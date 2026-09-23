# Task 4 — evidence

Дата финальной проверки: 2026-09-23. Устройство: Windows PC; Docker Desktop.
Финальный live run: `73ba6438-1801-4111-855f-90ea2d74165f`.
Код образа: `git:63230eb9f8ab9d8b6acc12c840a6328e574fc4db-dirty`
(базовый commit + незакоммиченные изменения этой корректировки).

## Объём и свежесть

| Слой | Записей в финальном run |
|---|---:|
| Raw artifacts | 3 |
| Normalized records | 3284 |
| Entities | 3290 |
| Relations | 3288 |

Normalized records: manifest Geofabrik + 3283 строки ОКТМО Калужской
области (код субъекта `29`) из 186533 строк источника; 3252 уникальных кода.

- Geofabrik latest publisher MD5 совпал с локальным: `e6eefa1f1574bbce61ed1566f9356ab0`;
  freshness=`current`; репликация `2026-09-22T20:22:59Z`, возраст 14.31 ч.
- Выполнен новый PBF ingest и атомарное продвижение release `82d8e131284a`.
- Росстат выбрал последний файл, рекламируемый паспортом: `data-20260901T1609`;
  возраст даты публикации на запуске — 22 календарных дня; скачан 2026-09-23 в 10:41 UTC.
- В полном CSV обнаружены и отражены как warnings две инверсии дат вне субъекта
  29: строки 181856/181857, коды 95612700000/95612701000,
  valid_from 06.03.2014 > valid_to 01.03.2014. Они не нормализованы для субъекта 29.

## Provenance

- Geofabrik PBF: 877941905 bytes; MD5 `e6eefa1f1574bbce61ed1566f9356ab0`;
  SHA-256 `82d8e131284aa54f913dc31e80c19be48bb4829e362f3a5437ffec5fd058f57c`.
- Rosstat CSV SHA-256: `c91a45c85d25c881b9a87cd9973a663e004b5d1b0e83d335778fcd4965ff558f`.
- Machine-readable report: `geofabrik-worker-data/pipeline/current-report.json`.

## Аудит и тесты

- Docker image собран; прямой HTTPS/TLS к источникам остаётся с полной
  проверкой сертификата и hostname.
- Core suite: **22/22 PASS** на Docker image, включая валидаторы ОКТМО,
  publication-version, provenance failed-run, идемпотентность и rollback.
- Live `rosstat-health`: HTTP 200, 186533 строк; для subject 29 — 3283 строки,
  0 target anomalies; источник в целом показывает 2 warnings с кодами/датами.
- Task 1 live refresh: новый release checksum/header/GDAL проверены,
  `verify-current` PASS; текущий sidecar сравнен повторно во время pipeline.
- Повторные одинаковые входы сохраняют content-addressed IDs; новый HTML
  паспорта создаёт отдельный raw artifact, не раздувая доменную модель.
- Сбой parser сохраняет полученные raw snapshots и не перемещает current
  pointer; успешный run выше является новым current.
- Launcher Task 4 теперь разрешает data dir относительно корня репозитория,
  поэтому одинаково работает при вызове из другого текущего каталога.

## Ограничения и решение

Источник Росстата содержит две семантически некорректные даты для другого
субъекта. Pipeline завершает импорт Калужской области с явным quality warning;
если такие записи обнаружатся в целевом субъекте, запуск будет остановлен.
Источник не «чинится» эвристикой. У Росстата файл датирован 2026-09-01 и был
последним доступным на паспорте 2026-09-23; строгий SLA свежести пока не задан
и запланирован в Task 10.

Task 4 DONE в объявленной границе: release/layers и ОКТМО; OSM feature
extraction и spatial join остаются Task 5. Полный отчёт и hashes — выше.

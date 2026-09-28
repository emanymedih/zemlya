# Продолжение после сбоя: ограничения запуска и производительности

## Восстановленное состояние

- В `main` уже записаны Task 7 implementation `a4abcd8` и live evidence
  `d6f204e`; повторять их реализацию не требуется. На `d6f204e` CI зелёный.
- Исходный checkout этой Work-среды был пустым; после клонирования `main`
  незакоммиченных изменений предыдущего прогона здесь не найдено.
- Task 7: 3 009 строк evidence, 3 007 прямых замен, 2 аннулирования без
  замены; два строгих запуска и SQLite integrity `ok` описаны в
  `TASK_07_EVIDENCE.md`.

## Windows Restricted

`scripts/run-task04.cmd --use-docker-catalog` запускает Python stdlib launcher
без `.ps1` и без изменения Windows execution policy. Необходимы Docker
Desktop, Git, Python 3 в PATH. Для собственного каталога данных:

```cmd
scripts\run-task04.cmd --use-docker-catalog --data-dir C:\path\to\geofabrik-worker-data
```

Launcher собирает образ с commit version, проверяет и переносит host SQLite
в Docker volume при первом запуске, выполняет строгий pipeline, сверяет
`current_run_id`, `integrity_check` и SHA-256 native-volume SQLite с копией,
затем атомарно заменяет `pipeline/volume-backup.sqlite`. При неверном хэше
предыдущая резервная копия сохраняется. Локальный тест проверяет эти
сценарии. CI запускает `.cmd --help` на Windows runner без PowerShell-скрипта.
Сквозной запуск на Windows PC и восстановление из backup ещё
требуют доступ к этому ПК и его существующим volume; из Work-среды они
не подтверждены.

## Росстат

ОКТМО и официальная таблица перекодировки теперь загружаются одновременно
через две отдельные HTTP-сессии. Каждый запуск продолжает получать текущие
паспорт и CSV, проверять структуру и сохранять raw snapshots. В отчёт
добавлено `rosstat_parallel_fetch_parse_duration_seconds`, индивидуальные
длительности сохранены. Условный GET не используется: сервер ранее вернул
HTTP 200 при `If-Modified-Since`. Локальный тест с барьером подтверждает
одновременность, полный suite — 56/56 PASS. Прямой запрос с этой Work-среды
вернул HTTP 502 за 7,57 с, поэтому локальный live speedup не измерен.
GitHub Actions `rosstat-parallel-probe.yml` выполнил live-проверку на
коммите `07cee29`: [workflow run](https://github.com/emanymedih/zemlya/actions/runs/36390238972),
[machine report](https://github.com/emanymedih/zemlya/actions/runs/36390238972/artifacts/10956167216).
Версии обоих наборов `data-20260901T1609`; 186 533 строк ОКТМО,
3 283 строки Калужской области, 81 364 строки таблицы перекодировки;
все четыре raw ответа получили SHA-256. Загрузка и разбор ОКТМО заняли
8,187 с, перекодировочной таблицы 3,558 с, общий параллельный этап
8,189 с. Это один сетевой замер на GitHub runner, сравнение с прежними
31 секундами на другом ПК не является равным benchmark. Docker unit suite
того же коммита прошёл: [CI](https://github.com/emanymedih/zemlya/actions/runs/36390239019).
Полный строгий pipeline с текущим Geofabrik PBF и повтором требует среду
с доступом к PBF и Docker; live probe проверил только Росстат.

## Сквозной gate на GitHub runner

`pipeline-live-repeat.yml` скачивает publisher-current PBF, выполняет
строгий pipeline и повтор через launcher с Docker volume, проверяет
стабильность domain counts и экспортированную SQLite. Первый запуск
[run 36390703826](https://github.com/emanymedih/zemlya/actions/runs/36390703826)
показал успешный расчёт первого pipeline (91 512 дорог, 3 281 связь
иерархии, 3 007 прямых замен), затем выявил право `0600` у атомарно
записанного JSON-отчёта на Linux bind mount. Launcher после успешного
запуска теперь открывает отчёт для чтения хостом через Docker `chmod 0644`;
Windows путь не меняется. Gate требуется повторить на этом исправлении.

Повторный [run 36391518413](https://github.com/emanymedih/zemlya/actions/runs/36391518413)
прошёл два строгих pipeline и проверку backup: выпуск Geofabrik
`36d270c5b4b6`, 97 809 records, 101 067 entities, 104 374 relations
в каждом bundle; суммарный параллельный этап Росстата 8,914 с и 7,766 с.
[Отчёты запусков](https://github.com/emanymedih/zemlya/actions/runs/36391518413/artifacts/10955664684).
Выявлен дефект test harness: промежуточный отчёт в корне checkout пометил
повторный код как `-dirty`, хотя исполняемый код не менялся. Отчёты перенесены
в игнорируемый каталог данных; gate теперь проверяет одинаковый `code_version`.
Для этого уточнения выполнен следующий финальный прогон.

Финальный [strict live repeat](https://github.com/emanymedih/zemlya/actions/runs/36392349832)
на `2d3f0b5` завершился успешно. Выпуск Geofabrik `36d270c5b4b6`
подтверждён как publisher-current в обоих запусках. Первый run
`1f506faf-944f-4bf8-9d4d-f93c1490fc93`, повтор
`f0e63d8f-3d6a-412d-a55e-e26d97ac3be3`. В каждом bundle: 5 raw
artifacts, 97 809 normalized records, 101 067 entities, 104 374 relations.
Оба отчёта фиксируют одинаковый чистый `code_version=git:2d3f0b5...`.
Параллельный этап Росстата: 6,947 с и 6,895 с; отдельно ОКТМО
6,945 с и 6,893 с, таблица перекодировки 4,004 с и 3,539 с.
Проверены стабильность domain counts, SQLite `integrity_check=ok`,
указатель повтора в экспортированном backup и counts его таблиц.
[Machine reports](https://github.com/emanymedih/zemlya/actions/runs/36392349832/artifacts/10957050812).
[Docker и Windows CMD CI](https://github.com/emanymedih/zemlya/actions/runs/36392349845)
того же коммита успешны. Сквозной запуск на конкретном Windows ПК и
восстановление его существующего каталога остаются отдельным местным gate.

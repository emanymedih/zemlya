# Task 5 — Geofabrik RoadFeature extraction

Статус: **DONE_WITH_WARNINGS** (2026-09-27 performance follow-up; initial live extraction 2026-09-24).

## Цель

Из проверенного Geofabrik PBF получать воспроизводимый слой дорожных
объектов OSM в общий pipeline с исходной геометрией, тегами и provenance.
Этот слой станет пространственной основой для связи с Parcel после Task 13.

## Текущий факт и архитектурная граница

Task 4 хранит Geofabrik release и перечень GDAL layers, но не извлекает
дорожные features. Доступны raw PBF, release hash/manifest и GDAL OSM reader.
Реестр участков в контуре отсутствует. Поэтому до Task 13 нельзя считать
relation вида parcel-near-road или parcel-access подтверждённой.

## План работ

1. Зафиксировать схему road feature и natural key: OSM type + OSM id.
2. Читать только объекты линий, подтверждённые тегом highway, из проверенного
   текущего PBF; не использовать Overpass как массовую замену Geofabrik.
   Область выборки задавать геометрией OSM admin_level=4 «Калужская область»
   из того же PBF; provenance границы сохранять и маркировать её как
   картографический OSM AOI, не как юридически удостоверенную границу.
3. Хранить исходные теги, геометрию, CRS, PBF artifact/release, snapshot hash,
   время репликации PBF и время извлечения. Отдельным проходом по PBF
   сохранять osm_version и osm_timestamp каждого выбранного way; покрытие
   проверять по каждому объекту и не подменять время объекта временем snapshot.
4. Проверять CRS, допустимый тип/валидность/непустоту геометрии, OSM IDs,
   дубли natural key, counts и стабильность повторного прогона.
5. Публиковать RoadFeature и отчёт извлечения в рамках того же pipeline run.
6. Сверить ограниченную выборку с чтением GDAL и проверить live-run в Docker.
7. Сохранить evidence и повторно запустить pipeline для проверки идемпотентности.

## Приёмка

- Никакая road entity/record не остаётся без PBF snapshot provenance.
- Пропуск обязательных идентификаторов, ошибочный CRS, пустая или невалидная
  геометрия переводят run в failed; недопустимые features не проходят молча.
- Теги highway сохраняются без преобразования, меняющего source meaning.
- OSM version/timestamp берутся из объектной метаинформации PBF; если дата
  отсутствует, её покрытие явно показывается, а отсутствующий way завершает run ошибкой.
- Идентификаторы детерминированы; обновлённый PBF создаёт новое наблюдение,
  сохраняя прежнее.
- Перезапуск на том же PBF не дублирует каталог и воспроизводит counts/hashes.
- Docker tests, PBF fixture tests, live-run, повторный run и отчёт PASS/warnings.
- Пространственная relation с участком добавляется после Task 13, при наличии
  официальной геометрии; OSM не служит доказательством юридического доступа.

## Производительность и эксплуатационный gate (2026-09-27)

- Для cold PBF scan использовать Docker named volume `/fast` с
  `LANDRADAR_PBF_WORK_DIR`, `TMPDIR`, `CPL_TMPDIR`. Пробный scan
  того же release занял 106.65 с вместо 1,981.59 с через `/tmp`.
- Кэш привязан к SHA-256 PBF, региону, коду адаптера, версиям reader
  dependencies и OSM driver config. После изменения адаптера кэш
  перестраивается; повторный scan слоя — 1.02 с.
- Для SQLite доступен `scripts/run-task04.ps1 -UseDockerCatalog`.
  До первого запуска проверяется и копируется прежний host catalog;
  после успешного run host backup экспортируется через Docker copy
  с проверкой SHA-256 и atomic replace. Режим opt-in, старый каталог
  не удаляется. Диагностические full runs: 126.31 с cold и 21.33 с warm.
- Свежий PBF и strict live-run с повторным run пройдены 2026-09-27
  на отдельном Docker volume. Перед переключением основного контура остаются
  end-to-end запуск PowerShell launcher и тест восстановления host backup.
  На проверенном ПК .ps1 блокируется политикой Restricted; Docker-компоненты
  проверены отдельно, политика не менялась.

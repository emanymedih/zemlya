# Task 3 evidence — execution environment

- Проверено: 2026-09-23; статус: **DONE**.
- Docker: client/server 29.8.0, context `desktop-linux`.
- Диск C: свободно 744044933120 из 999008440320 байт; обязательный минимум 2000000000 байт.
- Windows Schannel: Geofabrik, Rosstat и GitHub вернули HTTP 200.
- Прямой container HTTPS: Geofabrik, Rosstat и GitHub вернули HTTP 200.
- TLS verification включена; `verify=False`, `-k` и отключение hostname-check не используются.
- Причина исходного сбоя: `rosstat.gov.ru` отдавал leaf без intermediate `Russian Trusted Sub CA`.
- Runtime использует app-local bundle `/opt/zemlya/certs/ca-bundle.pem` поверх Debian CA.
- DER SHA-256 root: `d26d2d0231b7c39f92cc738512ba54103519e4405d68b5bd703e9788ca8ecf31`.
- DER SHA-256 intermediate: `2155785036c900dbb5f1bb2a1569c80c55595bd6bf94867a29bbddbc7d88a3f2`.
- Docker build сверяет оба pin и выполняет `openssl verify` для intermediate через root.
- Исправленный preflight выполнен дважды на test tag и повторён на рабочем `task01`; класс результатов совпал.
- Прямой `rosstat-health`: 186533 строк всего, 3283 строки с официальным кодом субъекта `29`.
- Полный `rosstat-oktmo` из рабочего контейнера: 3283 записи; text-filter больше не является default.
- CSV snapshot: 20125498 байт; SHA-256 `c91a45c85d25c881b9a87cd9973a663e004b5d1b0e83d335778fcd4965ff558f`.
- Task 1 `verify-current`: PASS для release `8f7ab17b3321`, 877774222 байта, оба checksum и 5 GDAL-слоёв подтверждены.
- Тесты кода, встроенного в image: 10/10 PASS.
- Machine reports: `geofabrik-worker-data/task03/task03-preflight-first.json` и `task03-preflight-report.json`.

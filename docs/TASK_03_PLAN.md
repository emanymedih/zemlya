# Task 3 — рабочая execution-среда

## Основание

Пункт 3 в составе Key Block 01: «Рабочая execution-среда
с outbound DNS/HTTPS». Задача нужна для повторяемого запуска
источников 1–2 и следующих production-ingestion блоков.

## Цель

Подтвердить, что PC и Docker могут выполнять source-пайплайны,
сохранять данные, обращаться к внешним источникам и диагностировать
TLS/DNS ограничения без отключения проверки сертификатов.

## План

1. Проверить Docker Engine и активный контекст.
2. Проверить свободное место рабочего диска.
3. Проверить host DNS и HTTPS для Geofabrik, Росстата и GitHub.
4. Проверить container DNS/HTTPS для Geofabrik.
5. Проверить container TLS для Росстата и зафиксировать причину,
   если цепочка сертификатов контейнера не доверяет endpoint.
6. Подтвердить host-TLS fallback для Росстата.
7. Повторить preflight без изменения результатов.
8. Сохранить machine-readable report и evidence.
9. Обновить README/CHANGELOG и сделать commit/push.

## Критерии DONE

- Docker API отвечает;
- свободного места достаточно для текущего контура;
- host DNS/HTTPS проверен по всем активным источникам;
- container network проверен;
- TLS-ограничение либо устранено, либо оформлено как явный
  source-aware transport fallback;
- повторный preflight даёт тот же класс результатов;
- report содержит timestamp, URL, статус, transport и ошибку;
- evidence опубликован в Git.

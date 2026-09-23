# Дополнительная CA-цепочка runtime

Rosstat на `rosstat.gov.ru` отдаёт только leaf-сертификат, поэтому OpenSSL в
контейнере не может самостоятельно построить цепочку. Эти публичные CA-сертификаты
экспортированы 2026-09-23 из цепочки, которую Windows Schannel успешно построил
на устройстве PC. Проверка hostname и сертификата остаётся включённой.

## Закреплённые сертификаты

- `russian-trusted-root-ca.cer`: Russian Trusted Root CA; SHA-1 thumbprint
  `8FF915CCAB7BC16F8C5C8099D53E0E115B3AEC2F`; DER SHA-256
  `d26d2d0231b7c39f92cc738512ba54103519e4405d68b5bd703e9788ca8ecf31`;
  срок действия 2022-03-02 — 2032-02-28.
- `russian-trusted-sub-ca-2024.cer`: Russian Trusted Sub CA; SHA-1 thumbprint
  `6741AB02CF6598C09652DC34D2DC095904E32B52`; DER SHA-256
  `2155785036c900dbb5f1bb2a1569c80c55595bd6bf94867a29bbddbc7d88a3f2`;
  срок действия 2024-07-15 — 2029-07-19.

Docker build сверяет оба SHA-256, проверяет intermediate через root и создаёт
локальный bundle поверх стандартного Debian CA bundle. Любое изменение файлов
ломает сборку. При смене цепочки Rosstat сертификаты и pins обновляются только
после повторной проверки через Windows X509Chain и OpenSSL.

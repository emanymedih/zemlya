FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# PyOsmium's wheel links against the system Expat runtime.
RUN apt-get update \
    && apt-get install --no-install-recommends -y libexpat1 \
    && rm -rf /var/lib/apt/lists/*

# Rosstat serves only its leaf certificate. Vendor the exact chain trusted by
# the Windows host, pin the exported DER files, and build an app-local bundle.
COPY deploy/geofabrik-worker/certs/*.cer /tmp/zemlya-certs/
RUN printf '%s  %s\n' \
      'd26d2d0231b7c39f92cc738512ba54103519e4405d68b5bd703e9788ca8ecf31' '/tmp/zemlya-certs/russian-trusted-root-ca.cer' \
      '2155785036c900dbb5f1bb2a1569c80c55595bd6bf94867a29bbddbc7d88a3f2' '/tmp/zemlya-certs/russian-trusted-sub-ca-2024.cer' \
      | sha256sum -c - \
    && mkdir -p /opt/zemlya/certs \
    && openssl x509 -inform DER -in /tmp/zemlya-certs/russian-trusted-root-ca.cer -out /opt/zemlya/certs/russian-trusted-root-ca.pem \
    && openssl x509 -inform DER -in /tmp/zemlya-certs/russian-trusted-sub-ca-2024.cer -out /opt/zemlya/certs/russian-trusted-sub-ca-2024.pem \
    && openssl verify -CAfile /opt/zemlya/certs/russian-trusted-root-ca.pem /opt/zemlya/certs/russian-trusted-sub-ca-2024.pem \
    && cat /etc/ssl/certs/ca-certificates.crt \
           /opt/zemlya/certs/russian-trusted-root-ca.pem \
           /opt/zemlya/certs/russian-trusted-sub-ca-2024.pem \
           > /opt/zemlya/certs/ca-bundle.pem \
    && rm -rf /tmp/zemlya-certs

ENV REQUESTS_CA_BUNDLE=/opt/zemlya/certs/ca-bundle.pem \
    SSL_CERT_FILE=/opt/zemlya/certs/ca-bundle.pem

COPY deploy/geofabrik-worker/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY landradar /app/landradar
COPY deploy/geofabrik-worker/run.sh /app/run.sh
RUN chmod 0755 /app/run.sh \
    && python -c "import pyogrio; assert pyogrio.list_drivers().get('OSM') == 'r', pyogrio.list_drivers().get('OSM')"

ARG LANDRADAR_CODE_VERSION=unknown
ENV LANDRADAR_CODE_VERSION=${LANDRADAR_CODE_VERSION}

VOLUME ["/data"]
ENTRYPOINT ["/app/run.sh"]

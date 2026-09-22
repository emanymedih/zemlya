FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app
COPY deploy/geofabrik-worker/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY landradar /app/landradar
COPY deploy/geofabrik-worker/run.sh /app/run.sh
RUN chmod 0755 /app/run.sh \
    && python -c "import pyogrio; assert pyogrio.list_drivers().get('OSM') == 'r', pyogrio.list_drivers().get('OSM')"

VOLUME ["/data"]
ENTRYPOINT ["/app/run.sh"]

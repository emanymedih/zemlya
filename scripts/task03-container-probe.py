import json
import socket
import ssl
import urllib.request
from urllib.parse import urlparse
from datetime import datetime, timezone

urls = [
    ("geofabrik", "https://download.geofabrik.de/index-v1-nogeom.json"),
    ("rosstat", "https://rosstat.gov.ru/opendata/7708234640-oktmo"),
    ("github", "https://github.com/emanymedih/zemlya"),
]
out = {"checked_at": datetime.now(timezone.utc).isoformat(), "checks": []}
for name, url in urls:
    row = {"name": name, "url": url, "transport": "container_https"}
    try:
        host = urlparse(url).hostname
        row["dns"] = socket.gethostbyname_ex(host)[2]
        req = urllib.request.Request(url, headers={"User-Agent": "ZemlyaRadar/0.5"})
        with urllib.request.urlopen(req, timeout=20) as response:
            row["status"] = response.status
            row["ok"] = 200 <= response.status < 400
    except Exception as exc:
        row["ok"] = False
        row["error_type"] = type(exc).__name__
        row["error"] = str(exc)
    out["checks"].append(row)
print(json.dumps(out, ensure_ascii=False, indent=2))

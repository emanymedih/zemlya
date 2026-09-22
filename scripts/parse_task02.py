from pathlib import Path
import json
from landradar.sources.rosstat import RosstatOpenDataAdapter

raw = Path("/data/task02-host/raw")
csv_path = sorted(raw.glob("rosstat-oktmo_*.csv"))[-1]
rows = RosstatOpenDataAdapter.parse_csv(csv_path.read_bytes())
kaluga = [row for row in rows if row.get("subject_code") == "29"]
meta = json.loads((raw / "fetch-meta.json").read_text(encoding="utf-8-sig"))
out = {
    "source": "rosstat_opendata",
    "dataset_id": "7708234640-oktmo",
    "passport_url": meta["passport_url"],
    "data_url": meta["data_url"],
    "filter": {"subject_code": "29", "subject_name": "Калужская область"},
    "records": kaluga,
    "all_records_count": len(rows),
    "raw_snapshots": meta["snapshots"],
}
if not kaluga:
    raise SystemExit("No Kaluga rows found")
Path("/data/task02-host/rosstat_oktmo_kaluga.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps({"ok": True, "records": len(rows), "kaluga_matches": len(kaluga)}, ensure_ascii=False))

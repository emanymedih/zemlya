"""Live Rosstat fetch probe without Geofabrik or a production catalog."""

from __future__ import annotations

import json
from pathlib import Path
import sys

from landradar.pipeline.runner import UnifiedPipelineRunner


def main() -> None:
    raw_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/rosstat-probe")
    raw_dir.mkdir(parents=True, exist_ok=True)
    runner = UnifiedPipelineRunner(
        geofabrik_root=raw_dir, rosstat_raw_dir=raw_dir / "raw",
        database_path=raw_dir / "unused.sqlite",
    )
    oktmo, oktmo_snapshots, coding, coding_snapshots, durations = (
        runner._fetch_rosstat_datasets()
    )
    selected = sum(row["subject_code"] == "29" for row in oktmo.rows)
    if selected == 0 or not coding.rows or len(oktmo_snapshots) != 2 or len(coding_snapshots) != 2:
        raise RuntimeError("Rosstat probe returned incomplete source evidence")
    report = {
        "oktmo_data_url": oktmo.data_url,
        "oktmo_rows": len(oktmo.rows),
        "kaluga_rows": selected,
        "coding_data_url": coding.data_url,
        "coding_rows": len(coding.rows),
        "durations": durations,
        "snapshots": [
            {"source_key": snapshot.source_key, "sha256": snapshot.sha256,
             "byte_count": snapshot.byte_count, "request_url": snapshot.request_url}
            for snapshot in (*oktmo_snapshots, *coding_snapshots)
        ],
    }
    output = raw_dir / "probe-report.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

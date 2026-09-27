"""Read-only catalog counts and current run for repeatability checks."""

import argparse
import json
from pathlib import Path
import sqlite3

parser = argparse.ArgumentParser()
parser.add_argument("database")
args = parser.parse_args()
database = Path(args.database).resolve()
with sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True) as connection:
    tables = (
        "pipeline_runs", "raw_artifacts", "normalized_records",
        "entities", "entity_observations", "relations",
        "run_artifacts", "run_records", "run_entities", "run_relations",
    )
    counts = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in tables
    }
    counts["road_v2_records"] = connection.execute(
        "SELECT COUNT(*) FROM normalized_records WHERE schema_version='osm-road-feature/v2'"
    ).fetchone()[0]
    counts["current_run_id"] = connection.execute(
        "SELECT current_run_id FROM pipeline_state WHERE singleton=1"
    ).fetchone()[0]
    counts["integrity"] = connection.execute("PRAGMA integrity_check").fetchone()[0]
print(json.dumps(counts, ensure_ascii=False))

from __future__ import annotations

from pathlib import Path
import json
import sqlite3

from .contracts import PipelineBundle, PipelineRun, canonical_json, stable_id, utc_now


_SCHEMA = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
  run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('success','failed')),
  code_version TEXT NOT NULL, source_keys_json TEXT NOT NULL,
  summary_json TEXT NOT NULL, error TEXT
);
CREATE TABLE IF NOT EXISTS raw_artifacts (
  artifact_id TEXT PRIMARY KEY, source_key TEXT NOT NULL, dataset_id TEXT NOT NULL,
  url TEXT NOT NULL, fetched_at TEXT NOT NULL, status_code INTEGER NOT NULL,
  byte_count INTEGER NOT NULL, sha256 TEXT NOT NULL, local_path TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS normalized_records (
  record_id TEXT PRIMARY KEY, source_key TEXT NOT NULL, dataset_id TEXT NOT NULL,
  schema_version TEXT NOT NULL, record_key TEXT NOT NULL,
  artifact_id TEXT NOT NULL REFERENCES raw_artifacts(artifact_id),
  payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entities (
  entity_id TEXT PRIMARY KEY, entity_type TEXT NOT NULL, canonical_key TEXT NOT NULL,
  UNIQUE(entity_type, canonical_key)
);
CREATE TABLE IF NOT EXISTS entity_observations (
  observation_id TEXT PRIMARY KEY, entity_id TEXT NOT NULL REFERENCES entities(entity_id),
  artifact_id TEXT NOT NULL REFERENCES raw_artifacts(artifact_id),
  record_id TEXT REFERENCES normalized_records(record_id),
  attributes_json TEXT NOT NULL, observed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS relations (
  relation_id TEXT PRIMARY KEY, relation_type TEXT NOT NULL,
  subject_id TEXT NOT NULL REFERENCES entities(entity_id),
  object_id TEXT NOT NULL REFERENCES entities(entity_id),
  evidence_artifact_id TEXT NOT NULL REFERENCES raw_artifacts(artifact_id)
);
CREATE TABLE IF NOT EXISTS run_artifacts (
  run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id),
  artifact_id TEXT NOT NULL REFERENCES raw_artifacts(artifact_id),
  PRIMARY KEY(run_id, artifact_id)
);
CREATE TABLE IF NOT EXISTS run_records (
  run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id),
  record_id TEXT NOT NULL REFERENCES normalized_records(record_id),
  PRIMARY KEY(run_id, record_id)
);
CREATE TABLE IF NOT EXISTS run_entities (
  run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id),
  entity_id TEXT NOT NULL REFERENCES entities(entity_id),
  PRIMARY KEY(run_id, entity_id)
);
CREATE TABLE IF NOT EXISTS run_relations (
  run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id),
  relation_id TEXT NOT NULL REFERENCES relations(relation_id),
  PRIMARY KEY(run_id, relation_id)
);
CREATE TABLE IF NOT EXISTS pipeline_state (
  singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
  current_run_id TEXT REFERENCES pipeline_runs(run_id)
);
PRAGMA user_version = 1;
"""


class PipelineStore:
    """SQLite catalog for immutable artifacts and deterministic domain IDs."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA foreign_keys = ON")
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            raise RuntimeError(f"Unsupported pipeline database schema version: {version}")
        self.connection.executescript(_SCHEMA)
    def close(self) -> None:
        self.connection.close()

    def current_run_id(self) -> str | None:
        row = self.connection.execute(
            "SELECT current_run_id FROM pipeline_state WHERE singleton = 1"
        ).fetchone()
        return row[0] if row else None

    def commit_bundle(self, bundle: PipelineBundle) -> dict:
        bundle.validate()
        run = bundle.run
        finished = utc_now()
        summary = bundle.report()
        summary["run"]["status"] = "success"
        summary["run"]["finished_at"] = finished
        with self.connection:
            self.connection.execute(
                "INSERT INTO pipeline_runs VALUES(?,?,?,?,?,?,?,NULL)",
                (run.run_id, run.started_at, finished, "success", run.code_version,
                 canonical_json(sorted(set(run.source_keys))), canonical_json(summary)),
            )
            for item in bundle.artifacts:
                self.connection.execute(
                    "INSERT OR IGNORE INTO raw_artifacts VALUES(?,?,?,?,?,?,?,?,?)",
                    (item.artifact_id, item.source_key, item.dataset_id, item.url,
                     item.fetched_at, item.status_code, item.byte_count, item.sha256,
                     item.local_path),
                )
                self.connection.execute(
                    "INSERT INTO run_artifacts VALUES(?,?)", (run.run_id, item.artifact_id)
                )
            for item in bundle.records:
                self.connection.execute(
                    "INSERT OR IGNORE INTO normalized_records VALUES(?,?,?,?,?,?,?)",
                    (item.record_id, item.source_key, item.dataset_id,
                     item.schema_version, item.record_key, item.artifact_id,
                     canonical_json(item.payload)),
                )
                self.connection.execute(
                    "INSERT INTO run_records VALUES(?,?)", (run.run_id, item.record_id)
                )
            artifact_by_id = {a.artifact_id: a for a in bundle.artifacts}
            for item in bundle.entities:
                self.connection.execute(
                    "INSERT OR IGNORE INTO entities VALUES(?,?,?)",
                    (item.entity_id, item.entity_type, item.canonical_key),
                )
                observation_id = stable_id(
                    "observation", item.entity_id, item.artifact_id, item.record_id,
                    item.attributes,
                )
                self.connection.execute(
                    "INSERT OR IGNORE INTO entity_observations VALUES(?,?,?,?,?,?)",
                    (observation_id, item.entity_id, item.artifact_id, item.record_id,
                     canonical_json(item.attributes), artifact_by_id[item.artifact_id].fetched_at),
                )
                self.connection.execute(
                    "INSERT INTO run_entities VALUES(?,?)", (run.run_id, item.entity_id)
                )
            for item in bundle.relations:
                self.connection.execute(
                    "INSERT OR IGNORE INTO relations VALUES(?,?,?,?,?)",
                    (item.relation_id, item.relation_type, item.subject_id,
                     item.object_id, item.evidence_artifact_id),
                )
                self.connection.execute(
                    "INSERT INTO run_relations VALUES(?,?)", (run.run_id, item.relation_id)
                )
            self.connection.execute(
                "INSERT INTO pipeline_state VALUES(1,?) "
                "ON CONFLICT(singleton) DO UPDATE SET current_run_id=excluded.current_run_id",
                (run.run_id,),
            )
        return summary
    def record_failure(self, run: PipelineRun, error: Exception) -> None:
        finished = utc_now()
        summary = {
            "run_id": run.run_id, "status": "failed",
            "error_type": type(error).__name__, "error": str(error),
        }
        with self.connection:
            self.connection.execute(
                "INSERT INTO pipeline_runs VALUES(?,?,?,?,?,?,?,?)",
                (run.run_id, run.started_at, finished, "failed", run.code_version,
                 canonical_json(sorted(set(run.source_keys))), canonical_json(summary),
                 f"{type(error).__name__}: {error}"),
            )

    def counts(self) -> dict[str, int]:
        return {
            name: self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for name, table in (
                ("runs", "pipeline_runs"), ("raw_artifacts", "raw_artifacts"),
                ("normalized_records", "normalized_records"), ("entities", "entities"),
                ("relations", "relations"),
            )
        }

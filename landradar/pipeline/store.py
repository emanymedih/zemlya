from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json
import sqlite3

from .contracts import PipelineBundle, PipelineRun, RawArtifact, canonical_json, stable_id, utc_now


_SCHEMA_V1 = """
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

_V1_TABLES = {
    "pipeline_runs", "raw_artifacts", "normalized_records", "entities",
    "entity_observations", "relations", "run_artifacts", "run_records",
    "run_entities", "run_relations", "pipeline_state",
}

_MIGRATION_V2 = (
    """CREATE TABLE run_artifact_observations (
      observation_id TEXT PRIMARY KEY,
      run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id),
      artifact_id TEXT NOT NULL REFERENCES raw_artifacts(artifact_id),
      source_key TEXT NOT NULL, dataset_id TEXT NOT NULL, url TEXT NOT NULL,
      fetched_at TEXT NOT NULL, recorded_at TEXT NOT NULL,
      capture_kind TEXT NOT NULL CHECK(capture_kind IN ('download','verified_local')),
      status_code INTEGER NOT NULL, byte_count INTEGER NOT NULL,
      sha256 TEXT NOT NULL, local_path TEXT NOT NULL,
      UNIQUE(run_id, artifact_id)
    )""",
    "CREATE INDEX ix_artifact_observations_artifact ON run_artifact_observations(artifact_id)",
    """CREATE TABLE run_entity_observations (
      run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id),
      observation_id TEXT NOT NULL REFERENCES entity_observations(observation_id),
      PRIMARY KEY(run_id, observation_id)
    )""",
    """CREATE TABLE run_relation_evidence (
      run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id),
      relation_id TEXT NOT NULL REFERENCES relations(relation_id),
      record_id TEXT NOT NULL REFERENCES normalized_records(record_id),
      PRIMARY KEY(run_id, relation_id, record_id)
    )""",
    "CREATE INDEX ix_entity_observations_entity ON entity_observations(entity_id)",
    "CREATE INDEX ix_relations_subject ON relations(subject_id)",
    "CREATE INDEX ix_relations_object ON relations(object_id)",
    "PRAGMA user_version = 2",
)


class PipelineStore:
    """SQLite catalog for immutable artifacts and deterministic domain IDs."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA foreign_keys = ON")
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1, 2):
            raise RuntimeError(f"Unsupported pipeline database schema version: {version}")
        tables = {
            row[0] for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        if version == 0:
            if tables:
                raise RuntimeError("Unversioned catalog already contains tables; refusing to guess its schema")
            self.connection.executescript("BEGIN;\n" + _SCHEMA_V1 + "\nCOMMIT;")
            version = 1
            tables = set(_V1_TABLES)
        if not _V1_TABLES.issubset(tables):
            raise RuntimeError(f"Pipeline catalog is missing tables: {sorted(_V1_TABLES - tables)}")
        if version == 1:
            with self.connection:
                for statement in _MIGRATION_V2:
                    self.connection.execute(statement)
        elif not {
            "run_artifact_observations", "run_entity_observations", "run_relation_evidence",
        }.issubset(tables):
            raise RuntimeError("Version 2 catalog is missing evidence tables")
    def close(self) -> None:
        self.connection.close()

    def current_run_id(self) -> str | None:
        row = self.connection.execute(
            "SELECT current_run_id FROM pipeline_state WHERE singleton = 1"
        ).fetchone()
        return row[0] if row else None

    def _insert_immutable(self, table: str, key: str, values: tuple,
                          *, stable_columns: int | None = None) -> None:
        """Reuse an existing identity only when its immutable data matches."""
        placeholders = ",".join("?" for _ in values)
        cursor = self.connection.execute(
            f"INSERT OR IGNORE INTO {table} VALUES({placeholders})", values,
        )
        if cursor.rowcount:
            return
        stored = self.connection.execute(
            f"SELECT * FROM {table} WHERE {key}=?", (values[0],),
        ).fetchone()
        if stored is None or stored[:stable_columns] != values[:stable_columns]:
            raise ValueError(f"Immutable {table} identity has conflicting data: {values[0]}")

    def _record_artifact(self, run_id: str, item: RawArtifact) -> None:
        self._insert_immutable(
            "raw_artifacts", "artifact_id",
            (item.artifact_id, item.source_key, item.dataset_id, item.url,
             item.fetched_at, item.status_code, item.byte_count, item.sha256,
             item.local_path),
            # The artifact is content-addressed; retrieval URL/time/path belong
            # to the separate per-run observation and may change on a repeat.
            stable_columns=3,
        )
        stored = self.connection.execute(
            "SELECT source_key,dataset_id,byte_count,sha256 FROM raw_artifacts WHERE artifact_id=?",
            (item.artifact_id,),
        ).fetchone()
        if stored != (item.source_key, item.dataset_id, item.byte_count, item.sha256):
            raise ValueError(f"Immutable raw_artifacts identity has conflicting bytes: {item.artifact_id}")
        self.connection.execute(
            "INSERT INTO run_artifacts VALUES(?,?)", (run_id, item.artifact_id),
        )
        capture_kind = "verified_local" if item.source_key == "geofabrik_pbf" else "download"
        self.connection.execute(
            "INSERT INTO run_artifact_observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (stable_id("artifact-observation", run_id, item.artifact_id),
             run_id, item.artifact_id, item.source_key, item.dataset_id, item.url,
             item.fetched_at, utc_now(), capture_kind, item.status_code,
             item.byte_count, item.sha256, item.local_path),
        )

    def _record_entity_observation(self, run_id: str, entity_id: str,
                                   artifact_id: str, record_id: str | None,
                                   attributes: dict, fetched_at: str) -> None:
        observation_id = stable_id(
            "observation", entity_id, artifact_id, record_id, attributes,
        )
        self._insert_immutable(
            "entity_observations", "observation_id",
            (observation_id, entity_id, artifact_id, record_id,
             canonical_json(attributes), fetched_at),
            stable_columns=5,
        )
        self.connection.execute(
            "INSERT OR IGNORE INTO run_entity_observations VALUES(?,?)",
            (run_id, observation_id),
        )

    def commit_bundle(self, bundle: PipelineBundle) -> dict:
        bundle.validate()
        run = bundle.run
        finished = utc_now()
        summary = bundle.report()
        summary["run"]["status"] = "success"
        summary["run"]["finished_at"] = finished
        with self.connection:
            current = self.connection.execute(
                "SELECT r.started_at FROM pipeline_runs r JOIN pipeline_state p "
                "ON p.current_run_id=r.run_id WHERE p.singleton=1"
            ).fetchone()
            if current is not None and datetime.fromisoformat(run.started_at) <= datetime.fromisoformat(current[0]):
                raise RuntimeError(
                    "A later or simultaneous run is already current; refusing to move "
                    "the catalog pointer backwards"
                )
            self.connection.execute(
                "INSERT INTO pipeline_runs VALUES(?,?,?,?,?,?,?,NULL)",
                (run.run_id, run.started_at, finished, "success", run.code_version,
                 canonical_json(sorted(set(run.source_keys))), canonical_json(summary)),
            )
            for item in bundle.artifacts:
                self._record_artifact(run.run_id, item)
            for item in bundle.records:
                self._insert_immutable(
                    "normalized_records", "record_id",
                    (item.record_id, item.source_key, item.dataset_id,
                     item.schema_version, item.record_key, item.artifact_id,
                     canonical_json(item.payload)),
                )
                self.connection.execute(
                    "INSERT INTO run_records VALUES(?,?)", (run.run_id, item.record_id)
                )
            artifact_by_id = {a.artifact_id: a for a in bundle.artifacts}
            for item in bundle.entities:
                self._insert_immutable(
                    "entities", "entity_id",
                    (item.entity_id, item.entity_type, item.canonical_key),
                )
                self._record_entity_observation(
                    run.run_id, item.entity_id, item.artifact_id, item.record_id,
                    item.attributes, artifact_by_id[item.artifact_id].fetched_at,
                )
                self.connection.execute(
                    "INSERT INTO run_entities VALUES(?,?)", (run.run_id, item.entity_id)
                )
            for item in bundle.extra_entity_evidence:
                self._record_entity_observation(
                    run.run_id, item.entity_id, item.artifact_id, item.record_id,
                    item.attributes, artifact_by_id[item.artifact_id].fetched_at,
                )
            for item in bundle.relations:
                self._insert_immutable(
                    "relations", "relation_id",
                    (item.relation_id, item.relation_type, item.subject_id,
                     item.object_id, item.evidence_artifact_id),
                )
                self.connection.execute(
                    "INSERT INTO run_relations VALUES(?,?)", (run.run_id, item.relation_id)
                )
                if item.evidence_record_id is not None:
                    self.connection.execute(
                        "INSERT INTO run_relation_evidence VALUES(?,?,?)",
                        (run.run_id, item.relation_id, item.evidence_record_id),
                    )
            integrity = self.connection.execute("PRAGMA integrity_check").fetchone()[0]
            foreign_key_issue = self.connection.execute("PRAGMA foreign_key_check").fetchone()
            if integrity != "ok" or foreign_key_issue is not None:
                raise RuntimeError(
                    f"Catalog quality checks failed: integrity={integrity}, "
                    f"foreign_key_issue={foreign_key_issue}"
                )
            summary["catalog_checks"] = {
                "integrity_check": integrity, "foreign_key_issues": 0,
                "schema_version": self.connection.execute("PRAGMA user_version").fetchone()[0],
            }
            self.connection.execute(
                "UPDATE pipeline_runs SET summary_json=? WHERE run_id=?",
                (canonical_json(summary), run.run_id),
            )
            self.connection.execute(
                "INSERT INTO pipeline_state VALUES(1,?) "
                "ON CONFLICT(singleton) DO UPDATE SET current_run_id=excluded.current_run_id",
                (run.run_id,),
            )
        return summary
    def record_failure(self, run: PipelineRun, error: Exception,
                       artifacts: list[RawArtifact] | None = None) -> None:
        finished = utc_now()
        summary = {
            "run_id": run.run_id, "status": "failed",
            "error_type": type(error).__name__, "error": str(error),
            "source_summary": run.summary,
            "input_artifact_ids": sorted({item.artifact_id for item in (artifacts or [])}),
        }
        with self.connection:
            self.connection.execute(
                "INSERT INTO pipeline_runs VALUES(?,?,?,?,?,?,?,?)",
                (run.run_id, run.started_at, finished, "failed", run.code_version,
                 canonical_json(sorted(set(run.source_keys))), canonical_json(summary),
                 f"{type(error).__name__}: {error}"),
            )
            for item in artifacts or []:
                self._record_artifact(run.run_id, item)

    def counts(self) -> dict[str, int]:
        return {
            name: self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for name, table in (
                ("runs", "pipeline_runs"), ("raw_artifacts", "raw_artifacts"),
                ("normalized_records", "normalized_records"), ("entities", "entities"),
                ("relations", "relations"),
            )
        }

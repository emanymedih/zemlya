from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
import json
import uuid


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_id(namespace: str, *parts: Any) -> str:
    digest = sha256(canonical_json(parts).encode("utf-8")).hexdigest()
    return f"{namespace}:{digest[:32]}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class RawArtifact:
    artifact_id: str
    source_key: str
    dataset_id: str
    url: str
    fetched_at: str
    status_code: int
    byte_count: int
    sha256: str
    local_path: str

    @classmethod
    def create(cls, **values: Any) -> "RawArtifact":
        values["artifact_id"] = stable_id(
            "artifact", values["source_key"], values["sha256"]
        )
        return cls(**values)


@dataclass(frozen=True)
class NormalizedRecord:
    record_id: str
    source_key: str
    dataset_id: str
    schema_version: str
    record_key: str
    artifact_id: str
    payload: dict[str, Any]

    @classmethod
    def create(cls, *, source_key: str, dataset_id: str,
               schema_version: str, record_key: str,
               artifact_id: str, payload: dict[str, Any]) -> "NormalizedRecord":
        identity = stable_id(
            "record", artifact_id, schema_version, record_key
        )
        return cls(identity, source_key, dataset_id, schema_version,
                   record_key, artifact_id, payload)
@dataclass(frozen=True)
class Entity:
    entity_id: str
    entity_type: str
    canonical_key: str
    artifact_id: str
    attributes: dict[str, Any]
    record_id: str | None = None

    @classmethod
    def create(cls, *, entity_type: str, canonical_key: str,
               artifact_id: str, attributes: dict[str, Any],
               record_id: str | None = None) -> "Entity":
        identity = stable_id("entity", entity_type, canonical_key)
        return cls(identity, entity_type, canonical_key, artifact_id,
                   attributes, record_id)


@dataclass(frozen=True)
class Relation:
    relation_id: str
    relation_type: str
    subject_id: str
    object_id: str
    evidence_artifact_id: str

    @classmethod
    def create(cls, *, relation_type: str, subject_id: str,
               object_id: str, evidence_artifact_id: str) -> "Relation":
        identity = stable_id(
            "relation", relation_type, subject_id, object_id,
            evidence_artifact_id
        )
        return cls(identity, relation_type, subject_id, object_id,
                   evidence_artifact_id)


@dataclass
class PipelineRun:
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: str = field(default_factory=utc_now)
    finished_at: str | None = None
    status: str = "running"
    code_version: str = "task04-v1"
    source_keys: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineBundle:
    run: PipelineRun
    artifacts: list[RawArtifact]
    records: list[NormalizedRecord]
    entities: list[Entity]
    relations: list[Relation]

    def validate(self) -> None:
        artifact_ids = {item.artifact_id for item in self.artifacts}
        record_ids = {item.record_id for item in self.records}
        entity_ids = {item.entity_id for item in self.entities}
        if len(artifact_ids) != len(self.artifacts):
            raise ValueError("Duplicate artifact_id in pipeline bundle")
        if len(record_ids) != len(self.records):
            raise ValueError("Duplicate record_id in pipeline bundle")
        relation_ids = {item.relation_id for item in self.relations}
        if len(entity_ids) != len(self.entities):
            raise ValueError("Duplicate entity_id in pipeline bundle")
        if len(relation_ids) != len(self.relations):
            raise ValueError("Duplicate relation_id in pipeline bundle")
        for artifact in self.artifacts:
            if artifact.status_code < 200 or artifact.status_code >= 300:
                raise ValueError(f"Artifact is not successful: {artifact.source_key}")
            digest_valid = (
                len(artifact.sha256) == 64
                and all(char in "0123456789abcdef" for char in artifact.sha256)
            )
            if artifact.byte_count < 0 or not digest_valid:
                raise ValueError(f"Invalid artifact integrity metadata: {artifact.artifact_id}")
            if artifact.artifact_id != stable_id("artifact", artifact.source_key, artifact.sha256):
                raise ValueError(f"Artifact ID does not match identity: {artifact.artifact_id}")
        for record in self.records:
            if record.artifact_id not in artifact_ids:
                raise ValueError(f"Record has no raw artifact: {record.record_id}")
            if not record.record_key or not record.schema_version:
                raise ValueError(f"Record needs key and schema version: {record.record_id}")
            expected = stable_id(
                "record", record.artifact_id, record.schema_version, record.record_key
            )
            if record.record_id != expected:
                raise ValueError(f"Record ID does not match identity: {record.record_id}")
        for entity in self.entities:
            if entity.artifact_id not in artifact_ids:
                raise ValueError(f"Entity has no evidence artifact: {entity.entity_id}")
            if entity.record_id is not None and entity.record_id not in record_ids:
                raise ValueError(f"Entity has no normalized record: {entity.entity_id}")
            expected = stable_id("entity", entity.entity_type, entity.canonical_key)
            if entity.entity_id != expected:
                raise ValueError(f"Entity ID does not match identity: {entity.entity_id}")
        for relation in self.relations:
            if relation.subject_id not in entity_ids or relation.object_id not in entity_ids:
                raise ValueError(f"Relation has an unknown endpoint: {relation.relation_id}")
            if relation.evidence_artifact_id not in artifact_ids:
                raise ValueError(f"Relation has no evidence artifact: {relation.relation_id}")
            expected = stable_id(
                "relation", relation.relation_type, relation.subject_id,
                relation.object_id, relation.evidence_artifact_id,
            )
            if relation.relation_id != expected:
                raise ValueError(f"Relation ID does not match identity: {relation.relation_id}")
    def report(self) -> dict[str, Any]:
        return {
            "run": asdict(self.run),
            "counts": {
                "raw_artifacts": len(self.artifacts),
                "normalized_records": len(self.records),
                "entities": len(self.entities),
                "relations": len(self.relations),
            },
            "source_keys": sorted(set(self.run.source_keys)),
            "artifact_sha256": {
                item.source_key: item.sha256 for item in self.artifacts
            },
        }

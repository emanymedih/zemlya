from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
import json
import os
import uuid


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_id(namespace: str, *parts: Any) -> str:
    digest = sha256(canonical_json(parts).encode("utf-8")).hexdigest()
    return f"{namespace}:{digest[:32]}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


RELATION_RULES = {
    "contains_layer": ("osm_release", "osm_layer", "geofabrik_pbf"),
    "intersects_osm_aoi": ("road_feature", "osm_admin_boundary", "geofabrik_pbf"),
    "has_oktmo_code": (
        "oktmo_entry", "oktmo_code", "rosstat_opendata_7708234640-oktmo_data",
    ),
    "within_subject": (
        "oktmo_entry", "oktmo_subject", "rosstat_opendata_7708234640-oktmo_data",
    ),
    "oktmo_parent_code": (
        "oktmo_entry", "oktmo_entry", "rosstat_opendata_7708234640-oktmo_data",
    ),
    "oktmo_replaced_by": (
        "oktmo_code", "oktmo_code", "rosstat_opendata_7708234640-codingtable_data",
    ),
}


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
class EntityEvidence:
    entity_id: str
    artifact_id: str
    record_id: str
    attributes: dict[str, Any]


@dataclass(frozen=True)
class Relation:
    relation_id: str
    relation_type: str
    subject_id: str
    object_id: str
    evidence_artifact_id: str
    evidence_record_id: str | None = None

    @classmethod
    def create(cls, *, relation_type: str, subject_id: str,
               object_id: str, evidence_artifact_id: str,
               evidence_record_id: str | None = None) -> "Relation":
        identity = stable_id(
            "relation", relation_type, subject_id, object_id,
            evidence_artifact_id
        )
        return cls(identity, relation_type, subject_id, object_id,
                   evidence_artifact_id, evidence_record_id)


@dataclass
class PipelineRun:
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: str = field(default_factory=utc_now)
    finished_at: str | None = None
    status: str = "running"
    code_version: str = field(
        default_factory=lambda: os.environ.get("LANDRADAR_CODE_VERSION", "unknown")
    )
    source_keys: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineBundle:
    run: PipelineRun
    artifacts: list[RawArtifact]
    records: list[NormalizedRecord]
    entities: list[Entity]
    relations: list[Relation]
    extra_entity_evidence: list[EntityEvidence] = field(default_factory=list)

    def validate(self) -> None:
        artifacts = {item.artifact_id: item for item in self.artifacts}
        records = {item.record_id: item for item in self.records}
        entities = {item.entity_id: item for item in self.entities}
        artifact_ids = set(artifacts)
        record_ids = set(records)
        entity_ids = set(entities)
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
            artifact = artifacts[record.artifact_id]
            source_matches = record.source_key == artifact.source_key or (
                record.source_key == "rosstat_opendata"
                and artifact.source_key == f"rosstat_opendata_{record.dataset_id}_data"
            )
            if not source_matches or record.dataset_id != artifact.dataset_id:
                raise ValueError(f"Record source/dataset differs from artifact: {record.record_id}")
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
            if entity.record_id is not None and records[entity.record_id].artifact_id != entity.artifact_id:
                raise ValueError(f"Entity record and artifact disagree: {entity.entity_id}")
            expected = stable_id("entity", entity.entity_type, entity.canonical_key)
            if entity.entity_id != expected:
                raise ValueError(f"Entity ID does not match identity: {entity.entity_id}")
        for evidence in self.extra_entity_evidence:
            if evidence.entity_id not in entity_ids:
                raise ValueError(f"Entity evidence has no entity: {evidence.entity_id}")
            if evidence.record_id not in record_ids:
                raise ValueError(f"Entity evidence has no normalized record: {evidence.record_id}")
            if records[evidence.record_id].artifact_id != evidence.artifact_id:
                raise ValueError(f"Entity evidence record and artifact disagree: {evidence.record_id}")
        for relation in self.relations:
            if relation.subject_id not in entity_ids or relation.object_id not in entity_ids:
                raise ValueError(f"Relation has an unknown endpoint: {relation.relation_id}")
            if relation.evidence_artifact_id not in artifact_ids:
                raise ValueError(f"Relation has no evidence artifact: {relation.relation_id}")
            if relation.evidence_record_id is not None:
                record = records.get(relation.evidence_record_id)
                if record is None or record.artifact_id != relation.evidence_artifact_id:
                    raise ValueError(f"Relation record evidence disagrees: {relation.relation_id}")
            rule = RELATION_RULES.get(relation.relation_type)
            if rule is None and {"geofabrik_pbf", "rosstat_opendata"}.intersection(self.run.source_keys):
                raise ValueError(f"Unknown relation type in production bundle: {relation.relation_type}")
            if rule is not None:
                if relation.evidence_record_id is None:
                    raise ValueError(f"Production relation lacks record evidence: {relation.relation_id}")
                subject = entities[relation.subject_id]
                target = entities[relation.object_id]
                evidence = artifacts[relation.evidence_artifact_id]
                if (subject.entity_type, target.entity_type, evidence.source_key) != rule:
                    raise ValueError(f"Relation types or evidence source disagree: {relation.relation_id}")
                if relation.relation_type != "oktmo_replaced_by" and subject.artifact_id != evidence.artifact_id:
                    raise ValueError(f"Relation subject is not supported by evidence: {relation.relation_id}")
                if relation.relation_type in {"contains_layer", "within_subject", "oktmo_parent_code"} and target.artifact_id != evidence.artifact_id:
                    raise ValueError(f"Relation target is not supported by evidence: {relation.relation_id}")
                row = records[relation.evidence_record_id]
                if relation.relation_type == "oktmo_replaced_by":
                    if (row.payload.get("cancelled_code"), row.payload.get("valid_code")) != (
                        subject.canonical_key, target.canonical_key,
                    ):
                        raise ValueError(f"Replacement row does not name its endpoints: {relation.relation_id}")
                elif subject.record_id != row.record_id:
                    raise ValueError(f"Relation row does not support its subject: {relation.relation_id}")
                if relation.relation_type == "has_oktmo_code" and row.payload.get("oktmo_code") != target.canonical_key:
                    raise ValueError(f"OKTMO row does not name its code: {relation.relation_id}")
                if relation.relation_type == "within_subject" and row.payload.get("subject_code") != target.canonical_key:
                    raise ValueError(f"OKTMO row does not name its subject: {relation.relation_id}")
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
                "entity_evidence_observations": len(self.entities) + len(self.extra_entity_evidence),
                "relation_record_evidence": sum(
                    item.evidence_record_id is not None for item in self.relations
                ),
            },
            "source_keys": sorted(set(self.run.source_keys)),
            "artifact_sha256": {
                item.source_key: item.sha256 for item in self.artifacts
            },
            "artifact_captures": [
                {
                    "artifact_id": item.artifact_id,
                    "source_key": item.source_key,
                    "sha256": item.sha256,
                    "fetched_at": item.fetched_at,
                    "local_path": item.local_path,
                    "capture_kind": "verified_local" if item.source_key == "geofabrik_pbf" else "download",
                }
                for item in self.artifacts
            ],
        }

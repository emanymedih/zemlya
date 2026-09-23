import tempfile
import unittest
from pathlib import Path

from landradar.pipeline.contracts import (
    Entity, NormalizedRecord, PipelineBundle, PipelineRun, RawArtifact, Relation,
)
from landradar.pipeline.store import PipelineStore


def make_bundle(run_id: str) -> PipelineBundle:
    artifact = RawArtifact.create(
        source_key="fixture", dataset_id="fixture-v1",
        url="https://example.test/data", fetched_at="2026-01-01T00:00:00Z",
        status_code=200, byte_count=4, sha256="a" * 64,
        local_path="fixtures/data.bin",
    )
    record = NormalizedRecord.create(
        source_key="fixture", dataset_id="fixture-v1",
        schema_version="fixture/v1", record_key="record-1",
        artifact_id=artifact.artifact_id, payload={"value": 1},
    )
    entity = Entity.create(
        entity_type="fixture_entity", canonical_key="entity-1",
        artifact_id=artifact.artifact_id, record_id=record.record_id,
        attributes={"value": 1},
    )
    related = Entity.create(
        entity_type="fixture_entity", canonical_key="entity-2",
        artifact_id=artifact.artifact_id, record_id=record.record_id,
        attributes={"value": 2},
    )
    relation = Relation.create(
        relation_type="supported_by", subject_id=entity.entity_id,
        object_id=related.entity_id, evidence_artifact_id=artifact.artifact_id,
    )
    run = PipelineRun(run_id=run_id, source_keys=["fixture"])
    return PipelineBundle(
        run=run, artifacts=[artifact], records=[record],
        entities=[entity, related], relations=[relation],
    )


class PipelineStoreTests(unittest.TestCase):
    def test_stable_ids_and_repeat_run_do_not_duplicate_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PipelineStore(Path(directory) / "pipeline.sqlite")
            try:
                first = store.commit_bundle(make_bundle("run-1"))
                second = store.commit_bundle(make_bundle("run-2"))
                self.assertEqual(first["counts"], second["counts"])
                self.assertEqual(store.current_run_id(), "run-2")
                self.assertEqual(store.counts(), {
                    "runs": 2, "raw_artifacts": 1, "normalized_records": 1,
                    "entities": 2, "relations": 1,
                })
                links = store.connection.execute(
                    "SELECT COUNT(*) FROM run_entities"
                ).fetchone()[0]
                self.assertEqual(links, 4)
            finally:
                store.close()

    def test_invalid_relation_has_no_publishable_bundle(self):
        bundle = make_bundle("invalid-run")
        bundle.relations[0] = Relation.create(
            relation_type="unsupported",
            subject_id=bundle.entities[0].entity_id,
            object_id="missing-entity",
            evidence_artifact_id=bundle.artifacts[0].artifact_id,
        )
        with self.assertRaisesRegex(ValueError, "unknown endpoint"):
            bundle.validate()

    def test_failed_run_preserves_current_pointer(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PipelineStore(Path(directory) / "pipeline.sqlite")
            try:
                store.commit_bundle(make_bundle("good-run"))
                store.record_failure(PipelineRun(run_id="bad-run"), ValueError("forced"))
                self.assertEqual(store.current_run_id(), "good-run")
                self.assertEqual(store.counts()["runs"], 2)
                status = store.connection.execute(
                    "SELECT status FROM pipeline_runs WHERE run_id='bad-run'"
                ).fetchone()[0]
                self.assertEqual(status, "failed")
            finally:
                store.close()

    def test_sql_failure_rolls_back_new_run_and_keeps_previous(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PipelineStore(Path(directory) / "pipeline.sqlite")
            try:
                store.commit_bundle(make_bundle("good-run"))
                bundle = make_bundle("bad-run")
                conflicting = Entity(
                    entity_id="different-id", entity_type="fixture_entity",
                    canonical_key="entity-1",
                    artifact_id=bundle.artifacts[0].artifact_id,
                    attributes={"value": 99},
                )
                bundle.entities[0] = conflicting
                with self.assertRaises(Exception):
                    store.commit_bundle(bundle)
                self.assertEqual(store.current_run_id(), "good-run")
                self.assertEqual(store.counts()["runs"], 1)
                self.assertEqual(store.counts()["entities"], 2)
                store.record_failure(bundle.run, RuntimeError("transaction rolled back"))
                self.assertEqual(store.current_run_id(), "good-run")
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()

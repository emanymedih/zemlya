import sqlite3
import json
import tempfile
import threading
import unittest
from unittest.mock import patch
from pathlib import Path

from landradar.pipeline.contracts import (
    Entity, EntityEvidence, NormalizedRecord, PipelineBundle, PipelineRun,
    RawArtifact, Relation,
)
from landradar.pipeline.catalog_migrate import seed_catalog
from landradar.pipeline.store import PipelineStore, _SCHEMA_V1
from landradar.pipeline.runner import (
    UnifiedPipelineRunner, assess_geofabrik_freshness,
)


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
    def test_v1_catalog_migrates_without_inventing_historical_fetches(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.sqlite"
            with sqlite3.connect(path) as legacy:
                legacy.executescript(_SCHEMA_V1)
                legacy.execute(
                    "INSERT INTO pipeline_runs VALUES(?,?,?,?,?,?,?,?)",
                    ("historic-run", "2026-01-01T00:00:00+00:00",
                     "2026-01-01T00:01:00+00:00", "success", "git:historic",
                     '["fixture"]', "{}", None),
                )
                legacy.execute("INSERT INTO pipeline_state VALUES(1,?)", ("historic-run",))
            store = PipelineStore(path)
            try:
                self.assertEqual(store.connection.execute("PRAGMA user_version").fetchone()[0], 2)
                self.assertEqual(store.current_run_id(), "historic-run")
                self.assertEqual(store.connection.execute(
                    "SELECT COUNT(*) FROM run_artifact_observations"
                ).fetchone()[0], 0)
                store.commit_bundle(make_bundle("new-run"))
                self.assertEqual(store.connection.execute(
                    "SELECT COUNT(*) FROM run_artifact_observations"
                ).fetchone()[0], 1)
            finally:
                store.close()

    def test_parser_failure_keeps_current_and_captured_raw_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.sqlite"
            store = PipelineStore(path)
            store.commit_bundle(make_bundle("good-run"))
            store.close()
            runner = UnifiedPipelineRunner(
                geofabrik_root=directory, rosstat_raw_dir=directory,
                database_path=path,
            )

            def fail_parse(run):
                run.source_keys.append("fixture")
                runner._captured_artifacts.append(make_bundle("input").artifacts[0])
                raise ValueError("invalid publisher CSV")

            with patch.object(runner, "_build_bundle", side_effect=fail_parse):
                with self.assertRaisesRegex(ValueError, "invalid publisher CSV"):
                    runner.run()
            with sqlite3.connect(path) as catalog:
                self.assertEqual(catalog.execute(
                    "SELECT current_run_id FROM pipeline_state"
                ).fetchone()[0], "good-run")
                failure_id = catalog.execute(
                    "SELECT run_id FROM pipeline_runs WHERE status='failed'"
                ).fetchone()[0]
                self.assertEqual(catalog.execute(
                    "SELECT COUNT(*) FROM run_artifact_observations WHERE run_id=?",
                    (failure_id,),
                ).fetchone()[0], 1)

    def test_same_bytes_keep_per_run_download_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PipelineStore(Path(directory) / "pipeline.sqlite")
            try:
                first = make_bundle("run-1")
                store.commit_bundle(first)
                second = make_bundle("run-2")
                second.artifacts[0] = RawArtifact.create(
                    source_key="fixture", dataset_id="fixture-v1",
                    url="https://example.test/new-url", fetched_at="2026-01-02T00:00:00Z",
                    status_code=200, byte_count=4, sha256="a" * 64,
                    local_path="fixtures/second-download.bin",
                )
                report = store.commit_bundle(second)
                self.assertEqual(report["artifact_captures"][0]["local_path"],
                                 "fixtures/second-download.bin")
                observations = store.connection.execute(
                    "SELECT run_id,fetched_at,local_path FROM run_artifact_observations ORDER BY fetched_at"
                ).fetchall()
                self.assertEqual(observations, [
                    ("run-1", "2026-01-01T00:00:00Z", "fixtures/data.bin"),
                    ("run-2", "2026-01-02T00:00:00Z", "fixtures/second-download.bin"),
                ])
                self.assertEqual(store.counts()["raw_artifacts"], 1)
                self.assertEqual(store.connection.execute(
                    "SELECT fetched_at FROM raw_artifacts"
                ).fetchone()[0], "2026-01-01T00:00:00Z")
            finally:
                store.close()

    def test_same_record_id_with_changed_payload_aborts_and_preserves_pointer(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PipelineStore(Path(directory) / "pipeline.sqlite")
            try:
                store.commit_bundle(make_bundle("good-run"))
                changed = make_bundle("bad-run")
                original = changed.records[0]
                changed.records[0] = NormalizedRecord.create(
                    source_key=original.source_key, dataset_id=original.dataset_id,
                    schema_version=original.schema_version, record_key=original.record_key,
                    artifact_id=original.artifact_id, payload={"value": 999},
                )
                with self.assertRaisesRegex(ValueError, "Immutable normalized_records"):
                    store.commit_bundle(changed)
                self.assertEqual(store.current_run_id(), "good-run")
                self.assertEqual(store.counts()["runs"], 1)
                self.assertEqual(json.loads(store.connection.execute(
                    "SELECT payload_json FROM normalized_records"
                ).fetchone()[0]), {"value": 1})
            finally:
                store.close()

    def test_late_commit_from_older_run_does_not_replace_current(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PipelineStore(Path(directory) / "pipeline.sqlite")
            try:
                newer = make_bundle("newer")
                newer.run.started_at = "2026-09-28T12:00:01+00:00"
                older = make_bundle("older")
                older.run.started_at = "2026-09-28T12:00:00+00:00"
                store.commit_bundle(newer)
                with self.assertRaisesRegex(RuntimeError, "pointer backwards"):
                    store.commit_bundle(older)
                self.assertEqual(store.current_run_id(), "newer")
                self.assertEqual(store.counts()["runs"], 1)
            finally:
                store.close()

    def test_relation_source_and_record_artifact_alignment_are_required(self):
        bundle = make_bundle("invalid-alignment")
        artifact = RawArtifact.create(
            source_key="other", dataset_id="other", url="https://example.test/other",
            fetched_at="2026-01-01T00:00:00Z", status_code=200,
            byte_count=3, sha256="b" * 64, local_path="fixtures/other.bin",
        )
        bundle.artifacts.append(artifact)
        bundle.entities[0] = Entity.create(
            entity_type=bundle.entities[0].entity_type,
            canonical_key=bundle.entities[0].canonical_key,
            artifact_id=artifact.artifact_id,
            record_id=bundle.records[0].record_id,
            attributes=bundle.entities[0].attributes,
        )
        with self.assertRaisesRegex(ValueError, "record and artifact disagree"):
            bundle.validate()

        valid = make_bundle("wrong-endpoints")
        valid.run.source_keys.append("geofabrik_pbf")
        old = valid.relations[0]
        valid.relations[0] = Relation.create(
            relation_type="contains_layer", subject_id=old.subject_id,
            object_id=old.object_id, evidence_artifact_id=old.evidence_artifact_id,
            evidence_record_id=valid.records[0].record_id,
        )
        with self.assertRaisesRegex(ValueError, "types or evidence source"):
            valid.validate()

    def test_production_relation_and_extra_entity_evidence_are_row_linked(self):
        artifact = RawArtifact.create(
            source_key="geofabrik_pbf", dataset_id="central-fed-district",
            url="https://example.test/source.osm.pbf", fetched_at="2026-01-01T00:00:00Z",
            status_code=200, byte_count=4, sha256="c" * 64,
            local_path="fixtures/source.osm.pbf",
        )
        record = NormalizedRecord.create(
            source_key="geofabrik_pbf", dataset_id="central-fed-district",
            schema_version="fixture/v1", record_key="release",
            artifact_id=artifact.artifact_id, payload={"release": "a"},
        )
        release = Entity.create(
            entity_type="osm_release", canonical_key="release",
            artifact_id=artifact.artifact_id, record_id=record.record_id,
            attributes={"name": "release"},
        )
        layer = Entity.create(
            entity_type="osm_layer", canonical_key="release:lines",
            artifact_id=artifact.artifact_id, record_id=record.record_id,
            attributes={"name": "lines"},
        )
        relation = Relation.create(
            relation_type="contains_layer", subject_id=release.entity_id,
            object_id=layer.entity_id, evidence_artifact_id=artifact.artifact_id,
            evidence_record_id=record.record_id,
        )
        bundle = PipelineBundle(
            run=PipelineRun(run_id="row-evidence", source_keys=["geofabrik_pbf"]),
            artifacts=[artifact], records=[record], entities=[release, layer],
            relations=[relation],
            extra_entity_evidence=[EntityEvidence(
                layer.entity_id, artifact.artifact_id, record.record_id,
                {"source_role": "row-level"},
            )],
        )
        with tempfile.TemporaryDirectory() as directory:
            store = PipelineStore(Path(directory) / "catalog.sqlite")
            try:
                store.commit_bundle(bundle)
                self.assertEqual(store.connection.execute(
                    "SELECT record_id FROM run_relation_evidence"
                ).fetchone()[0], record.record_id)
                self.assertEqual(store.connection.execute(
                    "SELECT COUNT(*) FROM run_entity_observations"
                ).fetchone()[0], 3)
                self.assertEqual(store.connection.execute(
                    "SELECT COUNT(*) FROM pragma_foreign_key_check"
                ).fetchone()[0], 0)
            finally:
                store.close()

        bundle.relations[0] = Relation.create(
            relation_type="contains_layer", subject_id=release.entity_id,
            object_id=layer.entity_id, evidence_artifact_id=artifact.artifact_id,
        )
        with self.assertRaisesRegex(ValueError, "lacks record evidence"):
            bundle.validate()

    def test_existing_catalog_rejects_divergent_host_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "host.sqlite"
            target = Path(directory) / "volume.sqlite"
            for path, run_id in ((source, "host-only"), (target, "volume-only")):
                store = PipelineStore(path)
                store.commit_bundle(make_bundle(run_id))
                store.close()
            with self.assertRaisesRegex(RuntimeError, "diverged"):
                seed_catalog(source, target)

    def test_rosstat_datasets_fetch_concurrently_with_independent_adapters(self):
        barrier = threading.Barrier(2, timeout=2)
        instances = []

        class FakeAdapter:
            def __init__(self):
                instances.append(self)

            def fetch_oktmo(self, *, raw_dir, on_snapshot):
                barrier.wait()
                on_snapshot(type("Snapshot", (), {
                    "source_key": "rosstat_opendata_7708234640-oktmo_data",
                    "request_url": "https://example.test/oktmo", "fetched_at": "2026-01-01T00:00:00Z",
                    "status_code": 200, "byte_count": 1, "sha256": "a" * 64,
                    "raw_path": raw_dir + "/oktmo.csv",
                })())
                return "oktmo", ["oktmo-snapshot"]

            def fetch_codingtable(self, *, raw_dir, on_snapshot):
                barrier.wait()
                return "coding", ["coding-snapshot"]

        with tempfile.TemporaryDirectory() as directory:
            runner = UnifiedPipelineRunner(
                geofabrik_root=directory, rosstat_raw_dir=directory,
                database_path=Path(directory) / "catalog.sqlite",
            )
            with patch("landradar.pipeline.runner.RosstatOpenDataAdapter", FakeAdapter):
                oktmo, raw_oktmo, coding, raw_coding, timings = runner._fetch_rosstat_datasets()
            self.assertEqual((oktmo, raw_oktmo, coding, raw_coding), (
                "oktmo", ["oktmo-snapshot"], "coding", ["coding-snapshot"],
            ))
            self.assertEqual(len(instances), 2)
            self.assertEqual(len(runner._captured_artifacts), 1)
            self.assertIn("rosstat_parallel_fetch_parse_duration_seconds", timings)

    def test_catalog_seed_preserves_source_and_refuses_to_replace_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "host.sqlite"
            target = Path(directory) / "volume" / "catalog.sqlite"
            store = PipelineStore(source)
            store.commit_bundle(make_bundle("run-1"))
            store.close()
            first = seed_catalog(source, target)
            self.assertEqual(first["status"], "seeded")
            self.assertEqual(first["current_run_id"], "run-1")
            self.assertTrue(source.exists())
            self.assertEqual(seed_catalog(source, target)["status"], "existing")
            with sqlite3.connect(target) as copied:
                self.assertEqual(copied.execute("SELECT COUNT(*) FROM entities").fetchone()[0], 2)

    def test_corrupt_catalog_is_not_seeded(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "corrupt.sqlite"
            target = Path(directory) / "volume" / "catalog.sqlite"
            source.write_bytes(b"not a SQLite database")
            with self.assertRaises(sqlite3.DatabaseError):
                seed_catalog(source, target)
            self.assertFalse(target.exists())

    def test_export_preserves_previous_backup_if_source_is_corrupt(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "volume.sqlite"
            backup = Path(directory) / "host" / "latest.sqlite"
            store = PipelineStore(source)
            store.commit_bundle(make_bundle("run-1"))
            store.close()
            result = seed_catalog(source, backup, replace_existing=True)
            self.assertEqual(result["status"], "backed_up")
            store = PipelineStore(source)
            store.commit_bundle(make_bundle("run-2"))
            store.close()
            updated = seed_catalog(source, backup, replace_existing=True)
            self.assertEqual(updated["current_run_id"], "run-2")
            source.write_bytes(b"not a SQLite database")
            with self.assertRaises(sqlite3.DatabaseError):
                seed_catalog(source, backup, replace_existing=True)
            with sqlite3.connect(backup) as valid:
                pointer = valid.execute(
                    "SELECT current_run_id FROM pipeline_state WHERE singleton = 1"
                ).fetchone()[0]
            self.assertEqual(pointer, "run-2")

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

    def test_dynamic_passport_snapshot_does_not_duplicate_domain_data(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PipelineStore(Path(directory) / "pipeline.sqlite")
            try:
                first = make_bundle("run-1")
                store.commit_bundle(first)

                second = make_bundle("run-2")
                passport = RawArtifact.create(
                    source_key="fixture_passport", dataset_id="fixture-v1",
                    url="https://example.test/passport",
                    fetched_at="2026-01-02T00:00:00Z", status_code=200,
                    byte_count=8, sha256="b" * 64,
                    local_path="fixtures/passport-2.html",
                )
                second.artifacts.append(passport)
                second.run.source_keys.append("fixture_passport")
                second_counts = store.commit_bundle(second)["counts"]
                self.assertEqual(second_counts["raw_artifacts"], 2)
                self.assertEqual(second_counts["normalized_records"], 1)
                self.assertEqual(second_counts["entities"], 2)
                self.assertEqual(second_counts["relations"], 1)

                third = make_bundle("run-3")
                third.artifacts.append(passport)
                third.run.source_keys.append("fixture_passport")
                self.assertEqual(store.commit_bundle(third)["counts"], second_counts)
                self.assertEqual(store.counts()["raw_artifacts"], 2)
            finally:
                store.close()

    def test_geofabrik_freshness_is_checksum_based_and_reports_age(self):
        current = assess_geofabrik_freshness(
            "a" * 32, "a" * 32, "2026-09-23T00:00:00+00:00",
        )
        changed = assess_geofabrik_freshness(
            "a" * 32, "b" * 32, "2026-09-23T00:00:00+00:00",
        )
        self.assertEqual(current["status"], "current")
        self.assertGreaterEqual(current["replication_age_hours"], 0)
        self.assertEqual(changed["status"], "upstream_changed")

    def test_runner_stages_pbf_for_container_local_processing(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.osm.pbf"
            source.write_bytes(b"pbf fixture")
            runner = UnifiedPipelineRunner(
                geofabrik_root=directory,
                rosstat_raw_dir=directory,
                database_path=Path(directory) / "catalog.sqlite",
            )
            work_root = Path(directory) / "dedicated-work-volume"
            with patch.dict("os.environ", {"LANDRADAR_PBF_WORK_DIR": str(work_root)}):
                staged = runner._prepare_pbf_for_run(source)
                try:
                    self.assertEqual(runner._pbf_stage_status, "staged")
                    self.assertNotEqual(staged, source)
                    self.assertEqual(staged.read_bytes(), source.read_bytes())
                    self.assertEqual(staged.parent.parent, work_root)
                finally:
                    runner._pbf_stage_tempdir.cleanup()

    def test_pipeline_run_uses_build_commit_version(self):
        with patch.dict("os.environ", {"LANDRADAR_CODE_VERSION": "git:abc123"}):
            self.assertEqual(PipelineRun().code_version, "git:abc123")

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
                failed_bundle = make_bundle("bad-run")
                failed_run = PipelineRun(run_id="bad-run", source_keys=["fixture"])
                store.record_failure(
                    failed_run, ValueError("forced"), artifacts=failed_bundle.artifacts
                )
                self.assertEqual(store.current_run_id(), "good-run")
                self.assertEqual(store.counts()["runs"], 2)
                status = store.connection.execute(
                    "SELECT status FROM pipeline_runs WHERE run_id='bad-run'"
                ).fetchone()[0]
                self.assertEqual(status, "failed")
                linked_inputs = store.connection.execute(
                    "SELECT COUNT(*) FROM run_artifacts WHERE run_id='bad-run'"
                ).fetchone()[0]
                self.assertEqual(linked_inputs, 1)
                summary = store.connection.execute(
                    "SELECT summary_json FROM pipeline_runs WHERE run_id='bad-run'"
                ).fetchone()[0]
                self.assertIn(failed_bundle.artifacts[0].artifact_id, summary)
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

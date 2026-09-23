from __future__ import annotations

from pathlib import Path
from typing import Any

from ..sources import GeofabrikPbfIngestor, RosstatOpenDataAdapter
from .contracts import (
    Entity, NormalizedRecord, PipelineBundle, PipelineRun, RawArtifact, Relation,
)
from .store import PipelineStore


class UnifiedPipelineRunner:
    """Validate active source snapshots and publish one provenance-linked run."""

    def __init__(self, *, geofabrik_root: str | Path, rosstat_raw_dir: str | Path,
                 database_path: str | Path, subject_code: str = "29"):
        self.geofabrik_root = Path(geofabrik_root)
        self.rosstat_raw_dir = Path(rosstat_raw_dir)
        self.database_path = Path(database_path)
        self.subject_code = subject_code

    def _build_bundle(self, run: PipelineRun) -> PipelineBundle:
        artifacts: list[RawArtifact] = []
        records: list[NormalizedRecord] = []
        entities: list[Entity] = []
        relations: list[Relation] = []
        geofabrik = GeofabrikPbfIngestor(self.geofabrik_root)
        verification = geofabrik.verify_current()
        if not verification.get("ok"):
            raise RuntimeError(f"Geofabrik current release failed: {verification}")
        manifest = geofabrik.current_manifest()
        if manifest is None:
            raise RuntimeError("Geofabrik current manifest is missing")
        pbf = manifest.pbf
        pbf_artifact = RawArtifact.create(
            source_key="geofabrik_pbf",
            dataset_id=manifest.region_id,
            url=pbf.url,
            fetched_at=pbf.fetched_at,
            status_code=pbf.status_code,
            byte_count=pbf.byte_count,
            sha256=pbf.sha256,
            local_path=pbf.path,
        )
        artifacts.append(pbf_artifact)
        run.source_keys.append(pbf_artifact.source_key)
        release_payload: dict[str, Any] = manifest.to_dict()
        release_record = NormalizedRecord.create(
            source_key="geofabrik_pbf", dataset_id=manifest.region_id,
            schema_version="geofabrik-pbf-manifest/v1",
            record_key=manifest.release_id, artifact_id=pbf_artifact.artifact_id,
            payload=release_payload,
        )
        records.append(release_record)
        release_entity = Entity.create(
            entity_type="osm_release",
            canonical_key=manifest.release_id,
            artifact_id=pbf_artifact.artifact_id,
            record_id=release_record.record_id,
            attributes={
                "region_id": manifest.region_id,
                "region_name": manifest.region_name,
                "sha256": verification["sha256"],
                "md5": verification["md5"],
                "byte_count": verification["byte_count"],
                "replication_timestamp": verification.get("replication_timestamp_iso"),
                "gdal_layers": verification["gdal_layers"],
            },
        )
        entities.append(release_entity)
        for layer_name in verification["gdal_layers"]:
            layer_entity = Entity.create(
                entity_type="osm_layer",
                canonical_key=f"{manifest.release_id}:{layer_name}",
                artifact_id=pbf_artifact.artifact_id,
                record_id=release_record.record_id,
                attributes={"layer": layer_name, "release_id": manifest.release_id},
            )
            entities.append(layer_entity)
            relations.append(Relation.create(
                relation_type="contains_layer", subject_id=release_entity.entity_id,
                object_id=layer_entity.entity_id,
                evidence_artifact_id=pbf_artifact.artifact_id,
            ))
        dataset, snapshots = RosstatOpenDataAdapter().fetch_oktmo(
            raw_dir=str(self.rosstat_raw_dir)
        )
        snapshot_artifacts: dict[str, RawArtifact] = {}
        for snapshot in snapshots:
            artifact = RawArtifact.create(
                source_key=snapshot.source_key,
                dataset_id=dataset.dataset_id,
                url=snapshot.request_url,
                fetched_at=snapshot.fetched_at,
                status_code=snapshot.status_code,
                byte_count=snapshot.byte_count,
                sha256=snapshot.sha256,
                local_path=snapshot.raw_path,
            )
            artifacts.append(artifact)
            snapshot_artifacts[snapshot.source_key.rsplit("_", 1)[-1]] = artifact
        run.source_keys.append("rosstat_opendata")
        csv_artifact = snapshot_artifacts["data"]
        selected = [
            row for row in dataset.rows
            if row.get("subject_code") == self.subject_code
        ]
        if not selected:
            raise ValueError(f"Rosstat dataset has no rows for subject code {self.subject_code}")
        subject = Entity.create(
            entity_type="oktmo_subject",
            canonical_key=self.subject_code,
            artifact_id=csv_artifact.artifact_id,
            attributes={"subject_code": self.subject_code},
        )
        entities.append(subject)
        for row in selected:
            code = row["oktmo_code"]
            record_key = ":".join((
                code, row["record_type"], row["valid_from"], row["valid_to"],
            ))
            record = NormalizedRecord.create(
                source_key="rosstat_opendata",
                dataset_id=dataset.dataset_id,
                schema_version="rosstat-oktmo-13col/v1",
                record_key=record_key,
                artifact_id=csv_artifact.artifact_id,
                payload=row,
            )
            records.append(record)
            entity = Entity.create(
                entity_type="oktmo_entry",
                canonical_key=record_key,
                artifact_id=csv_artifact.artifact_id,
                record_id=record.record_id,
                attributes=row,
            )
            entities.append(entity)
            relations.append(Relation.create(
                relation_type="within_subject", subject_id=entity.entity_id,
                object_id=subject.entity_id,
                evidence_artifact_id=csv_artifact.artifact_id,
            ))
        run.summary = {
            "geofabrik_release_id": manifest.release_id,
            "rosstat_dataset_id": dataset.dataset_id,
            "rosstat_total_records": len(dataset.rows),
            "rosstat_selected_records": len(selected),
            "rosstat_unique_oktmo_codes": len({row["oktmo_code"] for row in selected}),
            "subject_code": self.subject_code,
        }
        bundle = PipelineBundle(
            run=run, artifacts=artifacts, records=records,
            entities=entities, relations=relations,
        )
        bundle.validate()
        return bundle

    def run(self) -> dict[str, Any]:
        run = PipelineRun(source_keys=[])
        store = PipelineStore(self.database_path)
        try:
            bundle = self._build_bundle(run)
            report = bundle.report()
            report["source_summary"] = run.summary
            report["run"]["status"] = "success"
            result = store.commit_bundle(bundle)
            result["source_summary"] = run.summary
            result["current_run_id"] = run.run_id
            result["database"] = str(self.database_path)
            return result
        except Exception as exc:
            store.record_failure(run, exc)
            raise
        finally:
            store.close()

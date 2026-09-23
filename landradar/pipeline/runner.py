from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..sources import GeofabrikPbfIngestor, RosstatOpenDataAdapter
from .contracts import (
    Entity, NormalizedRecord, PipelineBundle, PipelineRun, RawArtifact, Relation, utc_now,
)
from .store import PipelineStore


def assess_geofabrik_freshness(
    local_md5: str, latest_md5: str, replication_timestamp: str | None,
) -> dict[str, Any]:
    status = "current" if local_md5.casefold() == latest_md5.casefold() else "upstream_changed"
    age_hours: float | None = None
    if replication_timestamp:
        replicated = datetime.fromisoformat(replication_timestamp.replace("Z", "+00:00"))
        age_hours = max(
            0.0,
            (datetime.now(timezone.utc) - replicated.astimezone(timezone.utc)).total_seconds() / 3600,
        )
    return {
        "status": status,
        "checked_at": utc_now(),
        "local_publisher_md5": local_md5,
        "latest_publisher_md5": latest_md5,
        "replication_timestamp": replication_timestamp,
        "replication_age_hours": round(age_hours, 2) if age_hours is not None else None,
    }


class UnifiedPipelineRunner:
    """Validate active source snapshots and publish one provenance-linked run."""

    def __init__(self, *, geofabrik_root: str | Path, rosstat_raw_dir: str | Path,
                 database_path: str | Path, subject_code: str = "29",
                 require_latest_geofabrik: bool = True):
        self.geofabrik_root = Path(geofabrik_root)
        self.rosstat_raw_dir = Path(rosstat_raw_dir)
        self.database_path = Path(database_path)
        self.subject_code = subject_code
        self.require_latest_geofabrik = require_latest_geofabrik
        self._captured_artifacts: list[RawArtifact] = []

    def _capture_rosstat_snapshot(self, snapshot: Any, dataset_id: str) -> None:
        self._captured_artifacts.append(RawArtifact.create(
            source_key=snapshot.source_key,
            dataset_id=dataset_id,
            url=snapshot.request_url,
            fetched_at=snapshot.fetched_at,
            status_code=snapshot.status_code,
            byte_count=snapshot.byte_count,
            sha256=snapshot.sha256,
            local_path=snapshot.raw_path,
        ))

    def _build_bundle(self, run: PipelineRun) -> PipelineBundle:
        artifacts: list[RawArtifact] = []
        records: list[NormalizedRecord] = []
        entities: list[Entity] = []
        relations: list[Relation] = []
        geofabrik = GeofabrikPbfIngestor(self.geofabrik_root)
        run.source_keys.append("geofabrik_pbf")
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
        self._captured_artifacts.append(pbf_artifact)

        latest = geofabrik.healthcheck(region_id=manifest.region_id)
        if not latest.get("ok"):
            raise RuntimeError(f"Geofabrik freshness check failed: {latest}")
        freshness = assess_geofabrik_freshness(
            manifest.publisher_md5, latest["publisher_md5"],
            verification.get("replication_timestamp_iso"),
        )
        run.summary["geofabrik_freshness"] = freshness
        if self.require_latest_geofabrik and freshness["status"] != "current":
            raise RuntimeError(
                "Current Geofabrik PBF is verified but outdated versus publisher sidecar; "
                f"local={freshness['local_publisher_md5']} "
                f"latest={freshness['latest_publisher_md5']}"
            )
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
        run.source_keys.append("rosstat_opendata")
        dataset_id = "7708234640-oktmo"
        dataset, snapshots = RosstatOpenDataAdapter().fetch_oktmo(
            raw_dir=str(self.rosstat_raw_dir),
            on_snapshot=lambda snapshot: self._capture_rosstat_snapshot(snapshot, dataset_id),
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
        csv_artifact = snapshot_artifacts["data"]
        selected = [
            row for row in dataset.rows
            if row.get("subject_code") == self.subject_code
        ]
        if not selected:
            raise ValueError(f"Rosstat dataset has no rows for subject code {self.subject_code}")
        selected_issues = [row for row in selected if row.get("_source_quality_issues")]
        if selected_issues:
            first = selected_issues[0]
            raise ValueError(
                "Rosstat selected subject contains invalid validity interval: "
                f"row={first['_source_row_number']} code={first['oktmo_code']} "
                f"valid_from={first['valid_from']} valid_to={first['valid_to']}"
            )
        dataset_issues = [row for row in dataset.rows if row.get("_source_quality_issues")]
        publication_date_age_days = None
        if dataset.published_version:
            published_date = datetime.strptime(dataset.published_version[:8], "%Y%m%d").date()
            run_date = datetime.fromisoformat(run.started_at).date()
            publication_date_age_days = (run_date - published_date).days
        csv_snapshot = next(
            snapshot for snapshot in snapshots if snapshot.source_key.endswith("_data")
        )
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
        run.summary.update({
            "geofabrik_release_id": manifest.release_id,
            "rosstat_dataset_id": dataset.dataset_id,
            "rosstat_data_url": dataset.data_url,
            "rosstat_published_version": dataset.published_version,
            "rosstat_publication_date_age_days": publication_date_age_days,
            "rosstat_data_fetched_at": csv_snapshot.fetched_at,
            "rosstat_latest_advertised_file": True,
            "rosstat_total_records": len(dataset.rows),
            "rosstat_selected_records": len(selected),
            "rosstat_source_quality_status": "warnings" if dataset_issues else "clean",
            "rosstat_source_quality_issue_count": len(dataset_issues),
            "rosstat_source_quality_issue_samples": [
                {
                    "source_row": row["_source_row_number"],
                    "oktmo_code": row["oktmo_code"],
                    "issue": row["_source_quality_issues"][0],
                    "valid_from": row["valid_from"],
                    "valid_to": row["valid_to"],
                }
                for row in dataset_issues[:20]
            ],
            "rosstat_unique_oktmo_codes": len({row["oktmo_code"] for row in selected}),
            "subject_code": self.subject_code,
            "rosstat_use_terms": {
                "terms": dataset.use_terms,
                "terms_url": dataset.use_terms_url,
                "source_attribution": dataset.passport_url,
            },
        })
        bundle = PipelineBundle(
            run=run, artifacts=artifacts, records=records,
            entities=entities, relations=relations,
        )
        bundle.validate()
        return bundle

    def run(self) -> dict[str, Any]:
        run = PipelineRun(source_keys=[])
        self._captured_artifacts = []
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
            store.record_failure(run, exc, artifacts=self._captured_artifacts)
            raise
        finally:
            store.close()

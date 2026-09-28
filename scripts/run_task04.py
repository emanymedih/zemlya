"""Cross-platform Docker pipeline launcher; requires only host Python and Docker."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import uuid


REPO = Path(__file__).resolve().parent.parent


def command(*args: str) -> str:
    result = subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE)
    return result.stdout.strip()


def show(*args: str) -> None:
    subprocess.run(args, check=True)


def inspect_backup(path: Path, expected_run_id: str) -> None:
    with sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Copied SQLite catalog failed integrity_check")
        pointer = db.execute(
            "SELECT current_run_id FROM pipeline_state WHERE singleton = 1"
        ).fetchone()
        if pointer is None or pointer[0] != expected_run_id:
            raise RuntimeError("Copied SQLite catalog pointer differs from the pipeline report")


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_catalog(*, data_dir: Path, image: str, volume: str, expected_run_id: str) -> Path:
    mount = f"{volume}:/catalog:ro"
    state = json.loads(command(
        "docker", "run", "--rm", "--entrypoint", "python", "-v", mount,
        image, "-m", "landradar.pipeline.catalog_migrate", "--source",
        "/catalog/landradar.sqlite", "--inspect",
    ))
    if state["current_run_id"] != expected_run_id:
        raise RuntimeError("Native catalog pointer differs from the pipeline report")
    source_hash = command(
        "docker", "run", "--rm", "--entrypoint", "sha256sum", "-v", mount,
        image, "/catalog/landradar.sqlite",
    ).split()[0]
    destination = data_dir / "pipeline" / "volume-backup.sqlite"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f"{destination.name}.{uuid.uuid4().hex}.tmp")
    container = ""
    try:
        container = command("docker", "create", "--entrypoint", "true", "-v", mount, image)
        if not container:
            raise RuntimeError("Docker did not return an export container ID")
        show("docker", "cp", f"{container}:/catalog/landradar.sqlite", str(temporary))
        copied_hash = file_sha256(temporary)
        if copied_hash != source_hash:
            raise RuntimeError("Exported catalog checksum differs from native source")
        inspect_backup(temporary, expected_run_id)
        os.replace(temporary, destination)
        print(f"Catalog backup: {destination} SHA-256={source_hash}")
        return destination
    finally:
        if container:
            show("docker", "rm", container)
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=REPO / "geofabrik-worker-data")
    parser.add_argument("--image", default="zemlya-radar-geofabrik:task04")
    parser.add_argument("--use-docker-catalog", action="store_true")
    args = parser.parse_args(argv)
    data_dir = args.data_dir.resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    code_version = command("git", "-C", str(REPO), "rev-parse", "HEAD")
    if command("git", "-C", str(REPO), "status", "--porcelain"):
        code_version += "-dirty"
    show("docker", "build", "--build-arg", f"LANDRADAR_CODE_VERSION=git:{code_version}",
         "-f", str(REPO / "deploy/geofabrik-worker/Dockerfile"), "-t", args.image, str(REPO))
    data_mount = f"{data_dir}:/data"
    catalog_mount = ["-v", "landradar-catalog:/catalog"] if args.use_docker_catalog else []
    database = "/data/pipeline/landradar.sqlite"
    if args.use_docker_catalog:
        show("docker", "run", "--rm", "--entrypoint", "python", "-v", data_mount,
             *catalog_mount, args.image, "-m", "landradar.pipeline.catalog_migrate",
             "--source", database, "--destination", "/catalog/landradar.sqlite")
        database = "/catalog/landradar.sqlite"
    report = data_dir / "pipeline" / "current-report.json"
    show("docker", "run", "--rm", "--entrypoint", "python",
         "-e", "LANDRADAR_PBF_WORK_DIR=/fast", "-e", "TMPDIR=/fast",
         "-e", "CPL_TMPDIR=/fast", "-v", data_mount, "-v", "landradar-pbf-work:/fast",
         *catalog_mount, args.image, "-m", "landradar.source_cli", "pipeline-run",
         "--geofabrik-root", "/data/geofabrik-pbf", "--raw-dir", "/data/pipeline/raw/rosstat",
         "--database", database, "--subject-code", "29",
         "--report", "/data/pipeline/current-report.json")
    # The container creates atomic reports with mode 0600. On Linux bind mounts
    # the host user needs read access before it can inspect the successful run.
    if os.name != "nt":
        show("docker", "run", "--rm", "--entrypoint", "chmod", "-v", data_mount,
             args.image, "0644", "/data/pipeline/current-report.json")
    if args.use_docker_catalog:
        current_run_id = json.loads(report.read_text(encoding="utf-8"))["current_run_id"]
        export_catalog(data_dir=data_dir, image=args.image, volume="landradar-catalog",
                       expected_run_id=current_run_id)
    print(f"Pipeline completed. Report: {report}")


if __name__ == "__main__":
    main()

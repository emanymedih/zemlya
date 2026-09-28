"""Seed a native Docker-volume catalog from a verified host SQLite snapshot."""

from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile


def _state(connection: sqlite3.Connection) -> dict:
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise ValueError(f"Catalog integrity check failed: {integrity}")
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version not in (1, 2):
        raise ValueError(f"Unsupported catalog schema version: {version}")
    foreign_key_issue = connection.execute("PRAGMA foreign_key_check").fetchone()
    if foreign_key_issue is not None:
        raise ValueError(f"Catalog foreign key check failed: {foreign_key_issue}")
    pointer = connection.execute(
        "SELECT current_run_id FROM pipeline_state WHERE singleton = 1"
    ).fetchone()
    return {
        "schema_version": version,
        "current_run_id": pointer[0] if pointer else None,
        "runs": connection.execute("SELECT COUNT(*) FROM pipeline_runs").fetchone()[0],
        "raw_artifacts": connection.execute("SELECT COUNT(*) FROM raw_artifacts").fetchone()[0],
        "normalized_records": connection.execute("SELECT COUNT(*) FROM normalized_records").fetchone()[0],
        "entities": connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
        "relations": connection.execute("SELECT COUNT(*) FROM relations").fetchone()[0],
    }

def seed_catalog(
    source: str | Path, destination: str | Path, *, replace_existing: bool = False,
) -> dict:
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError("Catalog source and destination must differ")
    if destination.exists() and not replace_existing:
        with closing(sqlite3.connect(f"{destination.resolve().as_uri()}?mode=ro", uri=True)) as current:
            state = _state(current)
            if source.exists():
                with closing(sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)) as original:
                    _state(original)
                    source_runs = {
                        row[0] for row in original.execute("SELECT run_id FROM pipeline_runs")
                    }
                    current_runs = {
                        row[0] for row in current.execute("SELECT run_id FROM pipeline_runs")
                    }
                    missing_runs = source_runs - current_runs
                    if missing_runs:
                        raise RuntimeError(
                            "Host and native catalogs diverged; host has runs missing from "
                            f"the Docker catalog: {sorted(missing_runs)[:5]}"
                        )
            return {"status": "existing", **state}
    if not source.exists():
        if replace_existing:
            raise FileNotFoundError(source)
        return {"status": "empty", "note": "Pipeline will create a new catalog"}
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=destination.name + ".", suffix=".seed", dir=destination.parent,
    )
    os.close(fd)
    try:
        with closing(sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)) as original:
            before = _state(original)
            with closing(sqlite3.connect(temporary)) as replica:
                original.backup(replica)
                replica.commit()
                copied = _state(replica)
            if copied != before or _state(original) != before:
                raise RuntimeError("Catalog changed during backup; retry after writers stop")
        if replace_existing:
            os.replace(temporary, destination)
        else:
            os.link(temporary, destination)
        return {"status": "backed_up" if replace_existing else "seeded", **copied}
    finally:
        Path(temporary).unlink(missing_ok=True)

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--destination")
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--replace-backup", action="store_true")
    args = parser.parse_args()
    if args.inspect:
        with closing(sqlite3.connect(f"{Path(args.source).resolve().as_uri()}?mode=ro", uri=True)) as catalog:
            result = _state(catalog)
    else:
        if not args.destination:
            parser.error("--destination is required unless --inspect is set")
        result = seed_catalog(
            args.source, args.destination, replace_existing=args.replace_backup,
        )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from landradar.pipeline.store import PipelineStore
from test_pipeline import make_bundle
from scripts import run_task04


class DockerLauncherTests(unittest.TestCase):
    def test_inspect_backup_closes_sqlite_handle_before_windows_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.sqlite"
            store = PipelineStore(source)
            store.commit_bundle(make_bundle("run-1"))
            store.close()
            opened = []
            original_connect = sqlite3.connect

            def track_connect(*args, **kwargs):
                db = original_connect(*args, **kwargs)
                opened.append(db)
                return db

            with patch.object(run_task04.sqlite3, "connect", side_effect=track_connect):
                run_task04.inspect_backup(source, "run-1")
            self.assertEqual(len(opened), 1)
            with self.assertRaises(sqlite3.ProgrammingError):
                opened[0].execute("SELECT 1")

    def test_verified_export_replaces_backup_and_keeps_previous_on_checksum_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.sqlite"
            store = PipelineStore(source)
            store.commit_bundle(make_bundle("run-1"))
            store.close()
            source_hash = run_task04.file_sha256(source)
            backup = root / "pipeline" / "volume-backup.sqlite"
            backup.parent.mkdir()
            backup.write_bytes(b"prior backup")
            actual_hash = [source_hash]
            removed = []

            def fake_command(*args):
                if "--inspect" in args:
                    return json.dumps({"current_run_id": "run-1"})
                if "sha256sum" in args:
                    return actual_hash[0] + "  /catalog/landradar.sqlite"
                if "create" in args:
                    return "test-container"
                raise AssertionError(args)

            def fake_show(*args):
                if args[1] == "cp":
                    Path(args[-1]).write_bytes(source.read_bytes())
                elif args[1] == "rm":
                    removed.append(args[-1])
                else:
                    raise AssertionError(args)

            with patch.object(run_task04, "command", side_effect=fake_command), \
                 patch.object(run_task04, "show", side_effect=fake_show):
                actual_hash[0] = "0" * 64
                with self.assertRaisesRegex(RuntimeError, "checksum"):
                    run_task04.export_catalog(data_dir=root, image="fixture", volume="catalog",
                                              expected_run_id="run-1")
                self.assertEqual(backup.read_bytes(), b"prior backup")
                self.assertEqual(len(list(backup.parent.glob("*.tmp"))), 0)
                actual_hash[0] = source_hash
                run_task04.export_catalog(data_dir=root, image="fixture", volume="catalog",
                                          expected_run_id="run-1")
            self.assertEqual(run_task04.file_sha256(backup), source_hash)
            self.assertEqual(removed, ["test-container", "test-container"])


if __name__ == "__main__":
    unittest.main()

"""Selected unmodified physical rows of the official 20260901 Rosstat CSVs."""

import base64
import hashlib
import json
from pathlib import Path
import unittest

from landradar.pipeline.oktmo_recode import build_recode_relations
from landradar.sources.rosstat import RosstatOpenDataAdapter


FIXTURE = Path(__file__).parent / "fixtures" / "rosstat_20260901_samples.json"


class RosstatGoldenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def payload(self, prefix, expected_sha):
        lines = [base64.b64decode(line, validate=True)
                 for line in self.fixture[prefix + "_lines_b64"]]
        self.assertEqual(hashlib.sha256(b"".join(lines)).hexdigest(), expected_sha)
        self.assertEqual(len(lines), len(self.fixture[prefix + "_source_rows"]))
        self.assertTrue(all(line.endswith(b"\r\n") for line in lines))
        return b"".join(lines)

    def test_official_oktmo_section_and_dates(self):
        rows = RosstatOpenDataAdapter.parse_csv(self.payload(
            "oktmo", "fa9cb3e560e47475968f4f95eed8ce339cb7042f77da3874a0d99030264227d7"
        ))
        self.assertEqual([(r["oktmo_code"], r["section"]) for r in rows], [
            ("29000000000", "1"), ("29000000000", "2"),
            ("29502000000", "1"), ("29502000053", "2"),
        ])
        self.assertEqual(rows[2]["acceptance_date"], "16.05.2025")
        self.assertEqual(rows[2]["introduction_date"], "01.01.2026")

    def test_official_codingtable_replacement_and_annulment(self):
        rows = RosstatOpenDataAdapter.parse_codingtable_csv(self.payload(
            "codingtable", "3b462067a98b92d35a64830f27bad67af0de4371db429c3ed1365019b94291de"
        ))
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[1]["cancelled_code"], "29616404116")
        self.assertEqual(rows[1]["valid_code"], "")
        self.assertEqual(rows[2]["valid_code"], "29502000053")
        result = build_recode_relations(rows, "29")
        self.assertEqual(result.summary["status"], "complete")
        self.assertEqual(result.summary["annulled_without_replacement_count"], 1)
        self.assertEqual(result.edges, [
            ("29613404056", "29613404156"),
            ("29602103051", "29502000053"),
            ("29602103106", "29502000103"),
        ])

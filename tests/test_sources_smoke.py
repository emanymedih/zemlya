import json
import struct
import tempfile
import unittest
from pathlib import Path

from landradar.source_cli import parse_args, write_json_atomic
from landradar.sources.rosstat import RosstatDataset
from landradar.sources import (
    BBox, OSMOverpassAdapter, GeofabrikIndexAdapter, RosstatOpenDataAdapter,
    parse_pbf_header,
)


class SourceSmokeTests(unittest.TestCase):
    def test_bbox_rejects_inverted_latitudes(self):
        with self.assertRaises(ValueError):
            BBox(55, 36, 54, 37).validate()

    def test_osm_query_is_bounded(self):
        q = OSMOverpassAdapter.roads_query(BBox(54.4, 36.1, 54.6, 36.3))
        self.assertIn('way["highway"]', q)
        self.assertIn('54.4,36.1,54.6,36.3', q)

    def test_geofabrik_index_parses_central_fd(self):
        payload = json.dumps({
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {
                    "id": "central-fed-district",
                    "parent": "russia",
                    "name": "Central Federal District",
                    "urls": {
                        "pbf": "https://download.geofabrik.de/russia/central-fed-district-latest.osm.pbf"
                    }
                }
            }]
        }).encode()
        rec = GeofabrikIndexAdapter.parse_region(payload)
        self.assertEqual(rec.region_id, "central-fed-district")
        self.assertTrue(rec.md5_url.endswith(".osm.pbf.md5"))

    @staticmethod
    def _varint(n: int) -> bytes:
        out = bytearray()
        while True:
            b = n & 0x7F
            n >>= 7
            out.append(b | (0x80 if n else 0))
            if not n:
                return bytes(out)

    @classmethod
    def _bytes_field(cls, field_no: int, value: bytes) -> bytes:
        return cls._varint((field_no << 3) | 2) + cls._varint(len(value)) + value

    @classmethod
    def _varint_field(cls, field_no: int, value: int) -> bytes:
        return cls._varint((field_no << 3) | 0) + cls._varint(value)

    def test_json_output_is_written_atomically_and_readably(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "report.json"
            write_json_atomic(target, {"status": "ok", "text": "данные"})
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {
                "status": "ok", "text": "данные",
            })
            self.assertEqual(sorted(path.name for path in Path(directory).iterdir()), ["report.json"])

    def test_rosstat_dataset_version_is_extracted_from_advertised_url(self):
        dataset = RosstatDataset(
            "dataset", "https://example.test/passport",
            "https://example.test/data-20260901T1609.csv", [],
        )
        self.assertEqual(dataset.published_version, "20260901T1609")

    def test_rosstat_headerless_oktmo_schema(self):
        payload = (
            '"29";"502";"000";"101";"0";"2";"с Тестовое";;;"814";"3";'
            '16.05.2025;01.01.2026\n'
        ).encode("cp1251")
        rows = RosstatOpenDataAdapter.parse_csv(payload)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["subject_code"], "29")
        self.assertEqual(rows[0]["oktmo_code"], "29502000101")
        self.assertEqual(rows[0]["name"], "с Тестовое")

    def test_rosstat_parser_validates_every_row(self):
        valid = (
            '"29";"502";"000";"101";"0";"2";"с Тестовое";;;"814";"3";'
            "16.05.2025;01.01.2026\n"
        )
        invalid_later_row = valid + valid.replace('"29";"502"', '"x9";"502"')
        with self.assertRaisesRegex(ValueError, "row 2: invalid subject_code"):
            RosstatOpenDataAdapter.parse_csv(invalid_later_row.encode("cp1251"))

    def test_rosstat_parser_rejects_calendar_but_marks_interval_anomaly(self):
        valid = (
            '"29";"502";"000";"101";"0";"2";"с Тестовое";;;"814";"3";'
            "16.05.2025;01.01.2026\n"
        )
        invalid_calendar_date = valid.replace("16.05.2025", "31.02.2025")
        with self.assertRaisesRegex(ValueError, "invalid valid_from"):
            RosstatOpenDataAdapter.parse_csv(invalid_calendar_date.encode("cp1251"))
        reversed_interval = valid.replace(
            "16.05.2025;01.01.2026", "02.01.2026;01.01.2026"
        )
        rows = RosstatOpenDataAdapter.parse_csv(reversed_interval.encode("cp1251"))
        self.assertEqual(rows[0]["_source_quality_issues"], ["valid_from_after_valid_to"])
        self.assertEqual(rows[0]["_source_row_number"], "1")

    def test_rosstat_fetch_reports_raw_snapshots_before_parse_failure(self):
        from landradar.sources.base import HttpResponse

        class FakeTransport:
            def __init__(self):
                self.responses = [
                    HttpResponse(
                        200, "https://example.test/passport",
                        {"content-type": "text/html; charset=utf-8"},
                        b'<a href="data-20260101T0000.csv">CSV</a>',
                    ),
                    HttpResponse(
                        200, "https://example.test/data-20260101T0000.csv",
                        {"content-type": "text/csv"},
                        b'bad;schema\\n',
                    ),
                ]

            def get(self, *args, **kwargs):
                return self.responses.pop(0)

        captured = []
        with tempfile.TemporaryDirectory() as directory:
            adapter = RosstatOpenDataAdapter(transport=FakeTransport())
            with self.assertRaisesRegex(ValueError, "expected 13"):
                adapter.fetch_dataset(
                    dataset_id="fixture", passport_url="https://example.test/passport",
                    raw_dir=directory, on_snapshot=captured.append,
                )
            self.assertEqual(len(captured), 2)
            self.assertTrue(all(Path(snapshot.raw_path).exists() for snapshot in captured))

    def test_rosstat_cli_defaults_to_official_kaluga_subject_code(self):
        default_args = parse_args(["rosstat-oktmo"])
        self.assertEqual(default_args.subject_code, "29")
        self.assertIsNone(default_args.filter)

        diagnostic_args = parse_args(["rosstat-oktmo", "--filter", "Калуж"])
        self.assertIsNone(diagnostic_args.subject_code)
        self.assertEqual(diagnostic_args.filter, "Калуж")

        pipeline_args = parse_args(["pipeline-run"])
        self.assertFalse(pipeline_args.allow_stale_geofabrik)
        pinned_args = parse_args(["pipeline-run", "--allow-stale-geofabrik"])
        self.assertTrue(pinned_args.allow_stale_geofabrik)

    def test_parse_minimal_pbf_header(self):
        header_block = (
            self._bytes_field(4, b"OsmSchema-V0.6")
            + self._bytes_field(4, b"DenseNodes")
            + self._bytes_field(17, b"unit-test")
            + self._varint_field(33, 12345)
        )
        blob = self._bytes_field(1, header_block)
        blob_header = self._bytes_field(1, b"OSMHeader") + self._varint_field(3, len(blob))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.osm.pbf"
            p.write_bytes(struct.pack(">I", len(blob_header)) + blob_header + blob)
            info = parse_pbf_header(p)
            self.assertEqual(info.blob_type, "OSMHeader")
            self.assertIn("OsmSchema-V0.6", info.required_features)
            self.assertEqual(info.replication_sequence_number, 12345)


if __name__ == '__main__':
    unittest.main()

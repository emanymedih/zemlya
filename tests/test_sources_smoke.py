import json
import struct
import tempfile
import unittest
from pathlib import Path

from landradar.source_cli import parse_args
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

    def test_rosstat_cli_defaults_to_official_kaluga_subject_code(self):
        default_args = parse_args(["rosstat-oktmo"])
        self.assertEqual(default_args.subject_code, "29")
        self.assertIsNone(default_args.filter)

        diagnostic_args = parse_args(["rosstat-oktmo", "--filter", "Калуж"])
        self.assertIsNone(diagnostic_args.subject_code)
        self.assertEqual(diagnostic_args.filter, "Калуж")

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

import tempfile
import unittest

from landradar.sources.base import HttpResponse
from landradar.sources.rosstat import RosstatOpenDataAdapter


class RosstatCodingTableTests(unittest.TestCase):
    def test_parser_normalizes_codes_and_keeps_source_row(self):
        payload = (
            "title;;;;;;;;;;\n"
            "Субъект Российской Федерации;Аннулированный код;Действующий код;"
            "Номер изменения;;;;;;;\n"
            "Калужская область;29 602 103 051;29 502 000 053;"
            "814/2025 ОКТМО;;;;;;;\n"
            "Калужская область;29 616 404 116;;609/2023 ОКТМО;;;;;;;\n"
        ).encode("utf-8")
        rows = RosstatOpenDataAdapter.parse_codingtable_csv(payload)
        self.assertEqual(rows[0]["cancelled_code"], "29602103051")
        self.assertEqual(rows[0]["valid_code"], "29502000053")
        self.assertEqual(rows[0]["_source_row_number"], "3")
        self.assertEqual(rows[1]["valid_code"], "")

    def test_parser_supports_official_short_codes_and_continuation_rows(self):
        payload = (
            "title;;;;;;;;;;\n"
            "Субъект Российской Федерации;Аннулированный код;Действующий код;"
            "Номер изменения;;;;;;;\n"
            "Москва;45 942 000;45 963 000;730/2024 ОКТМО;;;;;;;\n"
            ";;45 932 000;;\n"
            "Смоленская область;66 633 465 146;66 533 000 261 *;"
            "741/2024 ОКТМО;;;;;;;\n"
        ).encode("utf-8")
        rows = RosstatOpenDataAdapter.parse_codingtable_csv(payload)
        self.assertEqual(rows[0]["cancelled_code"], "45942000")
        self.assertEqual(rows[1]["cancelled_code"], "45942000")
        self.assertEqual(rows[1]["valid_code"], "45932000")
        self.assertEqual(rows[1]["_source_continuation"], "true")
        self.assertEqual(rows[2]["valid_code"], "66533000261")
        self.assertEqual(rows[2]["valid_code_note"], "*")

    def test_parser_rejects_unexpected_nonempty_trailing_column(self):
        payload = (
            "title;;;;\n"
            "subject;cancel;valid;change;extra\n"
            "Калужская область;29 602 103 051;29 502 000 053;"
            "814/2025 ОКТМО;unexpected\n"
        ).encode("utf-8")
        with self.assertRaisesRegex(ValueError, "unexpected columns"):
            RosstatOpenDataAdapter.parse_codingtable_csv(payload)

    def test_unknown_structure_stops_before_data_download(self):
        class ChangedStructureTransport:
            calls = 0

            def get(self, url, **kwargs):
                self.calls += 1
                return HttpResponse(
                    200,
                    url,
                    {"content-type": "text/html"},
                    (
                        b'<a href="data-20260901T1609-'
                        b'structure-20990101T0000.csv">CSV</a>'
                    ),
                )

        transport = ChangedStructureTransport()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                ValueError, "Unknown Rosstat coding table structure"
            ):
                RosstatOpenDataAdapter(
                    transport=transport
                ).fetch_codingtable(raw_dir=directory)
        self.assertEqual(transport.calls, 1)


if __name__ == "__main__":
    unittest.main()

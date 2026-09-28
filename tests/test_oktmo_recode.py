import unittest

from landradar.pipeline.oktmo_recode import build_recode_relations


def row(cancelled, valid, source_row="3", change="814/2025 ОКТМО"):
    return {
        "subject_name": "Калужская область",
        "cancelled_code": cancelled,
        "valid_code": valid,
        "change_reference": change,
        "_source_row_number": source_row,
    }


class OktmoRecodeTests(unittest.TestCase):
    def test_direct_relations_are_preserved_without_transitive_inference(self):
        rows = [
            row("29602103051", "29502000053"),
            row("29502000053", "29502000101", source_row="4"),
        ]
        result = build_recode_relations(rows, "29")
        self.assertEqual(result.summary["status"], "complete")
        self.assertEqual(result.edges, [
            ("29602103051", "29502000053"),
            ("29502000053", "29502000101"),
        ])
        self.assertEqual(result.summary["direct_chain_link_count"], 1)
        self.assertEqual(result.summary["relation_count"], 2)
    def test_annulment_without_replacement_is_evidence_but_not_relation(self):
        result = build_recode_relations([
            row("29616404116", "", change="609/2023 ОКТМО"),
        ], "29")
        self.assertEqual(result.summary["status"], "complete")
        self.assertEqual(result.edges, [])
        self.assertEqual(result.summary["annulled_without_replacement_count"], 1)

    def test_source_backed_one_to_many_replacement_is_preserved(self):
        result = build_recode_relations([
            row("29602103051", "29502000053"),
            row("29602103051", "29502000101", source_row="4"),
        ], "29")
        self.assertEqual(result.summary["status"], "complete")
        self.assertEqual(len(result.edges), 2)
        self.assertEqual(result.summary["multi_target_source_count"], 1)

    def test_cross_subject_replacement_fails_closed(self):
        result = build_recode_relations([
            row("29602103051", "30502000053"),
        ], "29")
        self.assertEqual(result.summary["status"], "invalid")
        self.assertEqual(
            result.summary["exception_samples"][0]["check"],
            "cross_subject_replacement",
        )
    def test_cycle_fails_closed(self):
        result = build_recode_relations([
            row("29602103051", "29502000053"),
            row("29502000053", "29602103051", source_row="4"),
        ], "29")
        self.assertEqual(result.summary["status"], "invalid")
        self.assertEqual(result.summary["cycle_count"], 2)
        self.assertEqual(result.edges, [])


if __name__ == "__main__":
    unittest.main()

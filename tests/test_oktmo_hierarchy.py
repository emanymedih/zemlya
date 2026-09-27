import unittest

from landradar.pipeline.oktmo_hierarchy import build_hierarchy, cycle_members, entry_key


def row(code, section="1", source_row="1"):
    return {
        "subject_code": code[:2], "municipality_code": code[2:5],
        "territory_code": code[5:8], "locality_code": code[8:11],
        "oktmo_code": code, "section": section,
        "acceptance_date": "16.05.2025", "introduction_date": "01.01.2026",
        "_source_row_number": source_row,
    }


class OktmoHierarchyTests(unittest.TestCase):
    def test_code_levels_build_evidence_ready_parent_edges(self):
        root = row("29000000000")
        municipality = row("29618000000", source_row="2")
        settlement = row("29618408000", source_row="3")
        locality = row("29618408012", section="2", source_row="4")
        result = build_hierarchy([root, municipality, settlement, locality], "29")
        self.assertEqual(result.summary["status"], "complete")
        self.assertEqual(result.summary["level_counts"], {
            "locality": 1, "municipality": 1, "settlement": 1, "subject": 1,
        })
        self.assertEqual(result.edges, [
            (entry_key(municipality), entry_key(root)),
            (entry_key(settlement), entry_key(municipality)),
            (entry_key(locality), entry_key(settlement)),
        ])
        self.assertEqual(result.summary["checks_passed_rows"]["parent_resolution"], 4)

    def test_missing_parent_keeps_source_row_and_fails_closed(self):
        result = build_hierarchy([row("29000000000"),
                                  row("29502000101", section="2", source_row="88")], "29")
        self.assertEqual(result.summary["status"], "invalid")
        self.assertEqual(result.summary["exception_samples"], [{
            "source_row": "88", "oktmo_code": "29502000101",
            "check": "parent_resolution", "parent_code": "29502000000",
            "candidate_count": "0",
        }])
        self.assertEqual(result.edges, [])

    def test_duplicate_parent_is_ambiguous(self):
        root = row("29000000000")
        parent = row("29502000000")
        child = row("29502000101", section="2")
        result = build_hierarchy([root, parent, dict(parent), child], "29")
        self.assertEqual(result.summary["status"], "invalid")
        self.assertEqual(result.summary["exception_count"], 3)
        self.assertEqual(result.summary["exception_samples"][-1]["candidate_count"], "2")

    def test_subject_and_level_errors_are_reported(self):
        wrong = row("30000000000", source_row="7")
        invalid = row("29000100000", source_row="8")
        result = build_hierarchy([wrong, invalid], "29")
        self.assertEqual(result.summary["status"], "invalid")
        self.assertEqual([x["check"] for x in result.summary["exception_samples"]],
                         ["subject_membership", "level_shape"])

    def test_cycle_checker_flags_members(self):
        self.assertEqual(cycle_members([("a", "b"), ("b", "a"), ("c", "a")]),
                         {"a", "b"})


if __name__ == "__main__":
    unittest.main()

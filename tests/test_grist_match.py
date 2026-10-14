import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from grist_match import plan_substitutions, to_date_str

SUBS = [
    {"id": 11, "name": "Alice Dupont", "subject": "Math", "status": "Substitute"},
    {"id": 12, "name": "Bob Martin", "subject": "English", "status": "Substitute"},
    {"id": 13, "name": "David Leroy", "subject": "Physics", "status": "Substitute"},
    {"id": 14, "name": "Fred Girard", "subject": "History", "status": "Substitute"},
]


def absence(aid, teacher_id, subject, date):
    return {"id": aid, "teacher_id": teacher_id, "teacher_subject": subject, "date": date}


class TestToDateStr(unittest.TestCase):
    def test_epoch_seconds(self):
        self.assertEqual(to_date_str(1792368000), "2026-10-19")

    def test_iso_string(self):
        self.assertEqual(to_date_str("2026-10-19"), "2026-10-19")


class TestPlanSubstitutions(unittest.TestCase):
    def test_basic_assignment(self):
        absences = [absence(1, 1, "Math", "2026-10-19")]
        plans, unmatched = plan_substitutions(absences, SUBS, set())
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["substitute_id"], 11)
        self.assertEqual(unmatched, [])

    def test_subject_match_preferred(self):
        absences = [absence(1, 3, "Physics", "2026-10-19")]
        plans, unmatched = plan_substitutions(absences, SUBS, set())
        self.assertEqual(plans[0]["substitute_id"], 13)

    def test_same_day_one_substitute_per_date(self):
        absences = [absence(1, 1, "Math", "2026-10-19"), absence(2, 1, "Math", "2026-10-19")]
        plans, unmatched = plan_substitutions(absences, SUBS, set())
        self.assertEqual(len(plans), 2)
        used = {p["substitute_id"] for p in plans}
        self.assertEqual(len(used), 2)

    def test_already_covered_skipped(self):
        absences = [absence(1, 1, "Math", "2026-10-19")]
        existing = {(1, "2026-10-19")}
        plans, unmatched = plan_substitutions(absences, SUBS, existing)
        self.assertEqual(plans, [])
        self.assertEqual(unmatched, [])

    def test_all_subs_busy_unmatched(self):
        absences = [absence(i, 1, "Math", "2026-10-19") for i in range(1, 6)]
        plans, unmatched = plan_substitutions(absences, SUBS, set())
        self.assertEqual(len(plans), 4)
        self.assertEqual(len(unmatched), 1)

    def test_multiple_dates_independent(self):
        absences = [
            absence(1, 1, "Math", "2026-10-19"),
            absence(2, 1, "Math", "2026-10-20"),
        ]
        plans, unmatched = plan_substitutions(absences, SUBS, set())
        self.assertEqual(len(plans), 2)
        self.assertEqual([p["substitute_id"] for p in plans], [11, 11])


if __name__ == "__main__":
    unittest.main()

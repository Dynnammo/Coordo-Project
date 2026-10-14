import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from grist_match import plan_substitutions, to_date_str

SUBS = [
    {"id": 11, "name": "Alice Dupont", "status": "Substitute"},
    {"id": 12, "name": "Bob Martin", "status": "Substitute"},
    {"id": 13, "name": "David Leroy", "status": "Substitute"},
    {"id": 14, "name": "Fred Girard", "status": "Substitute"},
]


def absence(aid, teacher_id, date, period):
    return {"id": aid, "teacher_id": teacher_id, "date": date, "period": period}


class TestToDateStr(unittest.TestCase):
    def test_epoch_seconds(self):
        self.assertEqual(to_date_str(1792368000), "2026-10-19")

    def test_iso_string(self):
        self.assertEqual(to_date_str("2026-10-19"), "2026-10-19")


class TestPlanSubstitutions(unittest.TestCase):
    def test_stability_same_substitute_keeps_teacher_all_day(self):
        absences = [
            absence(1, 1, "2026-10-19", "Morning"),
            absence(2, 1, "2026-10-19", "Afternoon"),
        ]
        plans, unmatched = plan_substitutions(absences, SUBS, set())
        self.assertEqual(unmatched, [])
        by_period = {p["period"]: p["substitute_id"] for p in plans}
        self.assertEqual(by_period["Morning"], by_period["Afternoon"])

    def test_two_teachers_same_day_get_distinct_subs_per_period(self):
        absences = [
            absence(1, 1, "2026-10-19", "Morning"),
            absence(2, 2, "2026-10-19", "Morning"),
            absence(3, 1, "2026-10-19", "Afternoon"),
            absence(4, 2, "2026-10-19", "Afternoon"),
        ]
        plans, unmatched = plan_substitutions(absences, SUBS, set())
        self.assertEqual(unmatched, [])
        morning_subs = {p["substitute_id"] for p in plans if p["period"] == "Morning"}
        self.assertEqual(len(morning_subs), 2)
        for teacher in (1, 2):
            subs = {p["substitute_id"] for p in plans if p["teacher_id"] == teacher}
            self.assertEqual(len(subs), 1, f"teacher {teacher} should keep one substitute")

    def test_stability_skipped_if_partner_busy(self):
        absences = [
            absence(1, 1, "2026-10-19", "Morning"),
            absence(2, 2, "2026-10-19", "Morning"),
            absence(3, 2, "2026-10-19", "Afternoon"),
            absence(4, 1, "2026-10-19", "Afternoon"),
        ]
        plans, unmatched = plan_substitutions(absences, SUBS, set())
        self.assertEqual(unmatched, [])
        by_key = {(p["teacher_id"], p["period"]): p["substitute_id"] for p in plans}
        self.assertEqual(by_key[(1, "Morning")], 11)
        self.assertEqual(by_key[(2, "Morning")], 12)
        self.assertEqual(by_key[(2, "Afternoon")], 12)
        self.assertEqual(by_key[(1, "Afternoon")], 11)

    def test_morning_processed_before_afternoon(self):
        from grist_match import sort_key
        morning = absence(2, 1, "2026-10-19", "Morning")
        afternoon = absence(1, 1, "2026-10-19", "Afternoon")
        self.assertLess(sort_key(morning), sort_key(afternoon))
        plans, _ = plan_substitutions([afternoon, morning], SUBS, set())
        self.assertEqual(len(plans), 2)
        self.assertEqual(len({p["substitute_id"] for p in plans}), 1)

    def test_one_substitute_per_period_per_day(self):
        absences = [absence(i, i, "2026-10-19", "Morning") for i in range(1, 6)]
        plans, unmatched = plan_substitutions(absences, SUBS, set())
        self.assertEqual(len(plans), 4)
        self.assertEqual(len(unmatched), 1)

    def test_already_covered_skipped(self):
        absences = [absence(1, 1, "2026-10-19", "Morning")]
        existing = {(1, "2026-10-19", "Morning")}
        plans, unmatched = plan_substitutions(absences, SUBS, existing)
        self.assertEqual(plans, [])
        self.assertEqual(unmatched, [])

    def test_multiple_dates_independent(self):
        absences = [
            absence(1, 1, "2026-10-19", "Morning"),
            absence(2, 1, "2026-10-20", "Morning"),
        ]
        plans, unmatched = plan_substitutions(absences, SUBS, set())
        self.assertEqual([p["substitute_id"] for p in plans], [11, 11])


if __name__ == "__main__":
    unittest.main()

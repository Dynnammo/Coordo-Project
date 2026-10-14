import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from grist_match import GristClient, plan_substitutions, to_date_str

SUBS = [
    {"id": 11, "name": "Alice Dupont", "status": "Substitute"},
    {"id": 12, "name": "Bob Martin", "status": "Substitute"},
    {"id": 13, "name": "David Leroy", "status": "Substitute"},
    {"id": 14, "name": "Fred Girard", "status": "Substitute"},
]


def absence(aid, teacher_id, date, period):
    return {"id": aid, "teacher_id": teacher_id, "date": date, "period": period}


class TestListRecordsPagination(unittest.TestCase):
    def test_multi_page_without_total_key(self):
        """The public Grist API returns no 'total': pagination must stop when
        a page returns fewer records than the page size."""
        client = GristClient("https://example", "key", "doc")

        def fake_request(method, path, payload=None):
            offset = int(path.split("offset=")[1])
            if offset == 0:
                return {"records": [{"id": i, "fields": {}} for i in range(100)]}
            return {"records": [{"id": i, "fields": {}} for i in range(100, 142)]}

        client._request = fake_request
        records = client.list_records("Teachers")
        self.assertEqual(len(records), 142)

    def test_single_page(self):
        client = GristClient("https://example", "key", "doc")
        client._request = lambda method, path, payload=None: {"records": [{"id": 1, "fields": {}}]}
        self.assertEqual(len(client.list_records("T")), 1)


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

    def test_come_back_rule_prioritizes_historic_pair(self):
        # Substitute 13 covered teacher 1 before (score 2): preferred over
        # the default lowest-id substitute 11.
        absences = [absence(1, 1, "2026-10-19", "Morning")]
        scores = {(1, 13): 2}
        plans, unmatched = plan_substitutions(absences, SUBS, set(), scores)
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["substitute_id"], 13)

    def test_come_back_rule_highest_score_wins(self):
        scores = {(1, 12): 3, (1, 14): 5}
        absences = [absence(1, 1, "2026-10-19", "Morning")]
        plans, _ = plan_substitutions(absences, SUBS, set(), scores)
        self.assertEqual(plans[0]["substitute_id"], 14)

    def test_come_back_beats_workload(self):
        # Even a heavily loaded substitute wins via a higher pair score.
        scores = {(1, 14): 1}
        absences = [
            absence(1, 2, "2026-10-19", "Morning"),
            absence(2, 1, "2026-10-19", "Morning"),
        ]
        plans, _ = plan_substitutions(absences, SUBS, set(), scores)
        by_teacher = {p["teacher_id"]: p["substitute_id"] for p in plans}
        self.assertEqual(by_teacher[1], 14)

    def test_stability_beats_come_back(self):
        # Substitute 12 covered teacher 1 in the morning (score says 14 is
        # the historic partner); stability keeps 12 for the afternoon.
        scores = {(1, 14): 9}
        absences = [
            absence(1, 1, "2026-10-19", "Morning"),
            absence(2, 1, "2026-10-19", "Afternoon"),
        ]
        plans, _ = plan_substitutions(absences, SUBS, set(), scores)
        subs = {p["period"]: p["substitute_id"] for p in plans}
        self.assertEqual(subs["Morning"], subs["Afternoon"])

    def test_no_score_falls_back_to_workload(self):
        absences = [absence(1, 1, "2026-10-19", "Morning")]
        plans, _ = plan_substitutions(absences, SUBS, set(), {})
        self.assertEqual(plans[0]["substitute_id"], 11)


if __name__ == "__main__":
    unittest.main()

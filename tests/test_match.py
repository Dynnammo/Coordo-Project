import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from match import Absence, Substitute, load_absences, load_substitutes, match

DATA = Path(__file__).resolve().parent.parent / "data"


class TestMatching(unittest.TestCase):
    def setUp(self):
        self.subs = load_substitutes(DATA / "substitutes.csv")
        self.absences = load_absences(DATA / "absences.csv")

    def test_all_sample_absences_have_valid_rows(self):
        self.assertEqual(len(self.absences), 10)
        for a in self.absences:
            self.assertIn(a.day, ("mon", "tue", "wed", "thu", "fri"))
            self.assertTrue(a.periods)

    def test_subject_match_preferred(self):
        math_sub = Substitute("M1", "Math", ["mon"], 1)
        other_sub = Substitute("X1", "History", ["mon"], 1)
        absence = Absence("Smith", "Math", "mon", [1])
        assignments, unmatched = match([absence], [other_sub, math_sub])
        self.assertEqual(assignments[0][1], math_sub)
        self.assertEqual(unmatched, [])

    def test_workload_balancing(self):
        busy = Substitute("Busy", "Math", ["mon"], 5)
        free = Substitute("Free", "Math", ["mon"], 5)
        busy.assignments = [("mon", 1), ("mon", 2)]
        absences = [Absence("A", "Math", "mon", [p]) for p in (3, 4)]
        assignments, unmatched = match(absences, [busy, free])
        self.assertEqual(len(assignments), 2)
        self.assertEqual(unmatched, [])
        self.assertTrue(all(sub is free for _, sub in assignments))

    def test_max_per_day_respected(self):
        limited = Substitute("L", "Math", ["mon"], 1)
        absences = [Absence("A", "Math", "mon", [1]), Absence("B", "Math", "mon", [2])]
        assignments, unmatched = match(absences, [limited])
        self.assertEqual(len(assignments), 1)
        self.assertEqual(len(unmatched), 1)

    def test_day_availability_respected(self):
        sub = Substitute("S", "Math", ["tue"], 5)
        absence = Absence("A", "Math", "mon", [1])
        assignments, unmatched = match([absence], [sub])
        self.assertEqual(assignments, [])
        self.assertEqual(unmatched, [absence])

    def test_sample_data_high_match_rate(self):
        assignments, unmatched = match(self.absences, self.subs)
        self.assertEqual(len(assignments) + len(unmatched), len(self.absences))
        self.assertGreaterEqual(len(assignments), 8)


if __name__ == "__main__":
    unittest.main()

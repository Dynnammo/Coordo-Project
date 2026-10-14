#!/usr/bin/env python3
"""Matching engine: assign the best available substitute to each absence.

Usage:
    python scripts/match.py --absences data/absences.csv --subs data/substitutes.csv
"""

import argparse
import csv
import sys
from pathlib import Path

SUBJECT_WEIGHT = 10
WORKLOAD_WEIGHT = 1
DAY_ORDER = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4}


class Substitute:
    def __init__(self, name, subject, days_available, max_per_day):
        self.name = name
        self.subject = subject
        self.days_available = set(days_available)
        self.max_per_day = max_per_day
        self.assignments = []  # list of (day, period) tuples

    @property
    def daily_load(self):
        load = {}
        for day, _ in self.assignments:
            load[day] = load.get(day, 0) + 1
        return load

    def can_take(self, day):
        if day not in self.days_available:
            return False
        if self.daily_load.get(day, 0) >= self.max_per_day:
            return False
        return True

    def score(self, subject, day):
        s = 0
        if self.subject == subject:
            s += SUBJECT_WEIGHT
        s -= self.daily_load.get(day, 0) * WORKLOAD_WEIGHT
        return s


class Absence:
    def __init__(self, teacher, subject, day, periods):
        self.teacher = teacher
        self.subject = subject
        self.day = day
        self.periods = periods  # list of period numbers (ints)

    @property
    def sort_key(self):
        return (DAY_ORDER.get(self.day, 99), min(self.periods), self.teacher)


def load_substitutes(path):
    subs = []
    with open(path, newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            try:
                subs.append(Substitute(
                    name=row["name"].strip(),
                    subject=row["subject"].strip(),
                    days_available=[d.strip() for d in row["days_available"].split(",") if d.strip()],
                    max_per_day=int(row["max_per_day"]),
                ))
            except (KeyError, ValueError) as e:
                raise ValueError(f"{path}:{i}: invalid substitute row ({e})")
    return subs


def load_absences(path):
    absences = []
    with open(path, newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            try:
                periods = [int(p) for p in row["period"].split(",") if p.strip()]
                if not periods:
                    raise ValueError("no periods given")
                absences.append(Absence(
                    teacher=row["teacher"].strip(),
                    subject=row["subject"].strip(),
                    day=row["day"].strip().lower(),
                    periods=periods,
                ))
            except (KeyError, ValueError) as e:
                raise ValueError(f"{path}:{i}: invalid absence row ({e})")
    return absences


def match(absences, substitutes):
    """Greedy assignment: earliest absences first, best-scored substitute wins."""
    assignments = []
    unmatched = []
    for absence in sorted(absences, key=lambda a: a.sort_key):
        candidates = [s for s in substitutes if s.can_take(absence.day)]
        if not candidates:
            unmatched.append(absence)
            continue
        best = max(candidates, key=lambda s: (s.score(absence.subject, absence.day), s.name))
        best.assignments.extend((absence.day, p) for p in absence.periods)
        assignments.append((absence, best))
    return assignments, unmatched


def main():
    parser = argparse.ArgumentParser(description="Match absent teachers with substitutes.")
    parser.add_argument("--absences", required=True, help="CSV of teacher absences")
    parser.add_argument("--subs", required=True, help="CSV of available substitutes")
    parser.add_argument("--out", help="Optional CSV output path for the plan")
    args = parser.parse_args()

    try:
        substitutes = load_substitutes(args.subs)
        absences = load_absences(args.absences)
    except (OSError, ValueError) as e:
        parser.error(str(e))

    assignments, unmatched = match(absences, substitutes)

    print("\n=== Substitution plan ===")
    for absence, sub in assignments:
        periods = ",".join(str(p) for p in absence.periods)
        print(f"{absence.day:<4} period(s) {periods:<8} {absence.teacher} ({absence.subject}) -> {sub.name}")

    if unmatched:
        print(f"\n=== Unmatched absences ({len(unmatched)}) ===")
        for absence in unmatched:
            periods = ",".join(str(p) for p in absence.periods)
            print(f"{absence.day:<4} period(s) {periods:<8} {absence.teacher} ({absence.subject}) -> NO SUBSTITUTE FOUND")

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["day", "periods", "absent_teacher", "subject", "substitute"])
            for absence, sub in assignments:
                writer.writerow([
                    absence.day,
                    " ".join(str(p) for p in absence.periods),
                    absence.teacher,
                    absence.subject,
                    sub.name,
                ])
        print(f"\nPlan written to {out_path}")

    print(f"\nMatched: {len(assignments)}/{len(absences)} absences.")
    return 0 if not unmatched else 1


if __name__ == "__main__":
    sys.exit(main())

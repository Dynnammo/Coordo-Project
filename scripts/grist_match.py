#!/usr/bin/env python3
"""Match absent teachers with substitutes, with all data living in Grist.

Reads the `Teachers`, `Absences` and `Substitutions` tables from the Grist
document `Coordo-Project`, assigns the best available substitute to every
absence that does not have one yet, and writes the result back to
`Substitutions`.

Each absence covers half a day: `Morning` or `Afternoon`. Substitutes are
assigned for stability: if a substitute covers a teacher in the morning, they
are prioritized to cover the same teacher in the afternoon.

Usage:
    export GRIST_API_KEY=...
    python scripts/grist_match.py --doc mdRfs6ggKhKUkuhqpW1xA6 [--dry-run]

Requires only the Python standard library.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date

DEFAULT_SERVER = "https://docs.getgrist.com"
SCORE_TABLE = "Substitutions_summary_Substitute_Teacher"
PERIOD_ORDER = {"Morning": 0, "Afternoon": 1}


class GristClient:
    def __init__(self, server, api_key, doc_id):
        self.server = server.rstrip("/")
        self.api_key = api_key
        self.doc_id = doc_id

    def _request(self, method, path, payload=None):
        url = f"{self.server}/api/docs/{self.doc_id}/tables/{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.api_key}")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode()
        return json.loads(body) if body else None

    def list_records(self, table_id):
        records = []
        offset = 0
        while True:
            page = self._request("GET", f"{table_id}/records?limit=100&offset={offset}")
            records.extend(page["records"])
            offset += len(page["records"])
            if len(records) >= page["total"]:
                break
        return records

    def add_records(self, table_id, records):
        return self._request("POST", f"{table_id}/records", {"records": records})


def to_date_str(value):
    """Normalize a Grist Date cell (epoch seconds or ISO string) to 'YYYY-MM-DD'."""
    if isinstance(value, (int, float)):
        return date.fromtimestamp(value).isoformat()
    return value[:10]


def sort_key(absence):
    return (absence["date"], PERIOD_ORDER.get(absence["period"], 2), absence["id"])


def plan_substitutions(absences, substitutes, existing_triples, pair_scores=None):
    """Assign a substitute to each half-day absence.

    absences:       list of dicts {id, teacher_id, date, period}
    substitutes:    list of dicts {id, name, status}
    existing_triples: set of (teacher_id, date, period) already covered
    pair_scores:    dict (teacher_id, substitute_id) -> historical score

    Returns (plans, unmatched) where plans is a list of dicts
    {absence_id, teacher_id, substitute_id, date, period}.

    Priority when choosing a substitute for an absence:
    1. Stability: the substitute covering the same teacher the other half of
       the same day keeps the assignment, if free for this period.
    2. Come-back: among free substitutes, the one with the highest historical
       score for this (teacher, substitute) pair is chosen.
    3. Workload: least assignments that day; ties broken by substitute id.

    A substitute can cover at most one absence per (date, period).
    """
    pair_scores = pair_scores or {}
    plans = []
    unmatched = []
    load = {}
    covered_by = {}

    for absence in sorted(absences, key=sort_key):
        triple = (absence["teacher_id"], absence["date"], absence["period"])
        if triple in existing_triples:
            continue

        def busy(sub_id):
            return load.get((sub_id, absence["date"], absence["period"]), 0) > 0

        other = "Afternoon" if absence["period"] == "Morning" else "Morning"

        # 1. Stability: the substitute covering this teacher the other half
        # of the same day keeps the assignment if free.
        partner = covered_by.get((absence["teacher_id"], absence["date"], other))
        if partner is not None and not busy(partner):
            best_id = partner
        else:
            candidates = [
                s for s in substitutes
                if s["status"] == "Substitute"
                and not busy(s["id"])
            ]
            if not candidates:
                unmatched.append(absence)
                continue
            day_load = lambda sid: (
                load.get((sid, absence["date"], other), 0)
                + load.get((sid, absence["date"], absence["period"]), 0)
            )
            best_id = min(
                (s["id"] for s in candidates),
                key=lambda sid: (
                    -pair_scores.get((absence["teacher_id"], sid), 0),
                    day_load(sid),
                    sid,
                ),
            )

        key = (best_id, absence["date"], absence["period"])
        load[key] = load.get(key, 0) + 1
        covered_by[(absence["teacher_id"], absence["date"], absence["period"])] = best_id
        plans.append({
            "absence_id": absence["id"],
            "teacher_id": absence["teacher_id"],
            "substitute_id": best_id,
            "date": absence["date"],
            "period": absence["period"],
        })
    return plans, unmatched


def fetch_state(client):
    teachers = [
        {
            "id": r["id"],
            "name": r["fields"].get("Name"),
            "status": r["fields"].get("Status"),
        }
        for r in client.list_records("Teachers")
    ]

    def norm_date(v):
        return to_date_str(v) if v is not None else None

    absences = []
    for r in client.list_records("Absences"):
        teacher_id = r["fields"].get("Teacher")
        date_val = r["fields"].get("Date")
        period = r["fields"].get("Period")
        if teacher_id is None or date_val is None or not period:
            continue
        teacher = next((t for t in teachers if t["id"] == teacher_id), None)
        if teacher is None:
            continue
        absences.append({
            "id": r["id"],
            "teacher_id": teacher_id,
            "date": norm_date(date_val),
            "period": period,
        })

    existing_triples = set()
    for r in client.list_records("Substitutions"):
        teacher_id = r["fields"].get("Teacher")
        date_val = r["fields"].get("Date")
        period = r["fields"].get("Period")
        if teacher_id is None or date_val is None or not period:
            continue
        existing_triples.add((teacher_id, norm_date(date_val), period))

    pair_scores = {}
    for r in client.list_records(SCORE_TABLE):
        teacher_id = r["fields"].get("Teacher")
        sub_id = r["fields"].get("Substitute")
        score = r["fields"].get("Score")
        if teacher_id is None or sub_id is None or score is None:
            continue
        pair_scores[(teacher_id, sub_id)] = score

    return teachers, absences, existing_triples, pair_scores


def main():
    parser = argparse.ArgumentParser(description="Fill the Grist Substitutions table from Absences.")
    parser.add_argument("--doc", required=True, help="Grist document id")
    parser.add_argument("--server", default=os.environ.get("GRIST_SERVER", DEFAULT_SERVER))
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without writing to Grist")
    args = parser.parse_args()

    api_key = os.environ.get("GRIST_API_KEY")
    if not api_key:
        parser.error("GRIST_API_KEY environment variable is required")

    client = GristClient(args.server, api_key, args.doc)
    try:
        teachers, absences, existing_triples, pair_scores = fetch_state(client)
    except urllib.error.URLError as e:
        print(f"Error contacting Grist: {e}", file=sys.stderr)
        return 2

    substitutes = [t for t in teachers if t["status"] == "Substitute"]
    plans, unmatched = plan_substitutions(absences, substitutes, existing_triples, pair_scores)

    if not plans:
        print("Nothing to do: every absence already has a substitute (or there are no absences).")
        return 0

    name_by_id = {t["id"]: t["name"] for t in teachers}
    print("=== Substitution plan ===")
    for p in sorted(plans, key=lambda p: (p["date"], PERIOD_ORDER.get(p["period"], 2))):
        print(f"{p['date']}  {p['period']:<9}  {name_by_id.get(p['teacher_id'])} -> {name_by_id.get(p['substitute_id'])}")

    if unmatched:
        print(f"\nUnmatched absences ({len(unmatched)}):")
        for a in unmatched:
            print(f"  {a['date']}  {a['period']:<9}  {name_by_id.get(a['teacher_id'])} (no free substitute)")

    if args.dry_run:
        print("\nDry run: nothing written to Grist.")
        return 0

    client.add_records("Substitutions", [
        {
            "fields": {
                "Teacher": p["teacher_id"],
                "Substitute": p["substitute_id"],
                "Date": p["date"],
                "Period": p["period"],
            }
        }
        for p in plans
    ])
    print(f"\nWrote {len(plans)} row(s) to the Substitutions table.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

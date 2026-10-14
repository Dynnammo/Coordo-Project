#!/usr/bin/env python3
"""Match absent teachers with substitutes, with all data living in Grist.

Reads the `Teachers`, `Absences` and `Substitutions` tables from the Grist
document `Coordo-Project`, assigns the best available substitute to every
absence that does not have one yet, and writes the result back to
`Substitutions`.

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
WORKLOAD_WEIGHT = 1


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


def day_of(date_str):
    return date.fromisoformat(date_str).strftime("%a").lower()


def plan_substitutions(absences, substitutes, existing_pairs):
    """Assign a substitute to each absence.

    absences:       list of dicts {id, teacher_id, date}
    substitutes:    list of dicts {id, name, status}
    existing_pairs: set of (teacher_id, date) already covered by Substitutions

    Returns (plans, unmatched) where plans is a list of dicts
    {absence_id, teacher_id, substitute_id, date}.
    """
    plans = []
    unmatched = []
    load = {}

    for absence in sorted(absences, key=lambda a: (a["date"], a["id"])):
        if (absence["teacher_id"], absence["date"]) in existing_pairs:
            continue
        candidates = [
            s for s in substitutes
            if s["status"] == "Substitute"
            and load.get((s["id"], absence["date"]), 0) < 1
        ]
        if not candidates:
            unmatched.append(absence)
            continue

        best = min(
            candidates,
            key=lambda s: (load.get((s["id"], absence["date"]), 0), s["id"]),
        )
        load[(best["id"], absence["date"])] = load.get((best["id"], absence["date"]), 0) + 1
        plans.append({
            "absence_id": absence["id"],
            "teacher_id": absence["teacher_id"],
            "substitute_id": best["id"],
            "date": absence["date"],
        })
    return plans, unmatched


def fetch_state(client):
    teachers = [
        {
            "id": r["id"],
            "name": r["fields"].get("Name"),
            "subject": r["fields"].get("Subject"),
            "status": r["fields"].get("Status"),
        }
        for r in client.list_records("Teachers")
    ]

    absences = []
    for r in client.list_records("Absences"):
        teacher_id = r["fields"].get("Teacher")
        date_val = r["fields"].get("Date")
        if teacher_id is None or date_val is None:
            continue
        date_str = to_date_str(date_val)
        teacher = next((t for t in teachers if t["id"] == teacher_id), None)
        if teacher is None:
            continue
        absences.append({
            "id": r["id"],
            "teacher_id": teacher_id,
            "date": date_str,
        })

    existing_pairs = set()
    for r in client.list_records("Substitutions"):
        teacher_id = r["fields"].get("Teacher")
        date_val = r["fields"].get("Date")
        if teacher_id is None or date_val is None:
            continue
        date_str = to_date_str(date_val)
        existing_pairs.add((teacher_id, date_str))

    return teachers, absences, existing_pairs


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
        teachers, absences, existing_pairs = fetch_state(client)
    except urllib.error.URLError as e:
        print(f"Error contacting Grist: {e}", file=sys.stderr)
        return 2

    substitutes = [t for t in teachers if t["status"] == "Substitute"]
    plans, unmatched = plan_substitutions(absences, substitutes, existing_pairs)

    if not plans:
        print("Nothing to do: every absence already has a substitute (or there are no absences).")
        return 0

    name_by_id = {t["id"]: t["name"] for t in teachers}
    print("=== Substitution plan ===")
    for p in plans:
        print(f"{p['date']}  {name_by_id.get(p['teacher_id'])} -> {name_by_id.get(p['substitute_id'])}")

    if unmatched:
        print(f"\nUnmatched absences ({len(unmatched)}):")
        for a in unmatched:
            print(f"  {a['date']}  {name_by_id.get(a['teacher_id'])} (no free substitute)")

    if args.dry_run:
        print("\nDry run: nothing written to Grist.")
        return 0

    client.add_records("Substitutions", [
        {"fields": {"Teacher": p["teacher_id"], "Substitute": p["substitute_id"], "Date": p["date"]}}
        for p in plans
    ])
    print(f"\nWrote {len(plans)} row(s) to the Substitutions table.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

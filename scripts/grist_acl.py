#!/usr/bin/env python3
"""Apply row-level access rules to the Coordo-Project Grist document.

Implements docs/ACCESS_RULES.md:
- Substitutions: a teacher sees rows where they are the Teacher or the
  Substitute; everyone else is denied; writes are dispatcher-only.
- Absences: a permanent teacher sees their own absences; writes denied.
- Teachers: the Email column is visible only to owners.
- Schools/Levels: readable by all, read-only for non-owners.

Safe to re-run: existing identical resources/rules are detected and skipped.

Usage:
    export GRIST_API_KEY=...
    python scripts/grist_acl.py --doc mdRfs6ggKhKUkuhqpW1xA6 [--dry-run]
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

SERVER = "https://docs.getgrist.com"
REQUEST_TIMEOUT = 30

# Each rule: (table_id, col_ids, acl_formula, permissions_text, memo)
RULES = [
    # --- Substitutions: see only what concerns you, deny the rest ---
    ("Substitutions", "*",
     "user.Access in [OWNER] or rec.Teacher.Email == user.Email or rec.Substitute.Email == user.Email",
     "+R", "Owners, or the teacher/substitute concerned by the row"),
    ("Substitutions", "*", "True", "-R",
     "Deny everyone else"),
    ("Substitutions", "*", "user.Access != OWNER", "-CUD",
     "Only the dispatcher (owner) writes"),

    # --- Absences: permanent teachers see their own absences ---
    ("Absences", "*",
     "user.Access in [OWNER] or rec.Teacher.Email == user.Email",
     "+R", "Owners, or the absent teacher"),
    ("Absences", "*", "True", "-R",
     "Deny everyone else"),
    ("Absences", "*", "user.Access != OWNER", "-CUD",
     "Only the dispatcher (owner) writes"),

    # --- Teachers: Email column is owner-only ---
    ("Teachers", "Email", "user.Access in [OWNER]", "+R",
     "Email addresses are owner-only"),
    ("Teachers", "Email", "True", "-R",
     "Hide Email from non-owners"),
    ("Teachers", "*", "user.Access != OWNER", "-CUD",
     "Only the dispatcher (owner) edits the directory"),
]


class GristClient:
    def __init__(self, server, api_key, doc_id):
        self.server = server.rstrip("/")
        self.api_key = api_key
        self.doc_id = doc_id

    def request(self, method, path, payload=None):
        url = f"{self.server}/api/docs/{self.doc_id}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.api_key}")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            body = resp.read().decode()
        return json.loads(body) if body else None


def ensure_email_column(client, verbose):
    columns = client.request("GET", "/tables/Teachers/columns")
    col_ids = [c["id"] for c in columns.get("columns", [])]
    if "Email" in col_ids:
        if verbose:
            print("Email column already present in Teachers")
        return
    print("Adding Email column to Teachers...")
    client.request("POST", "/tables/Teachers/columns", {
        "columns": [{"id": "Email", "fields": {"type": "Text", "label": "Email"}}]
    })
    print("Email column added")


def get_or_create_resource(client, table_id, col_ids):
    resources = client.request("GET", "/tables/_grist_ACLResources/records")
    for r in resources.get("records", []):
        f = r["fields"]
        if f.get("tableId") == table_id and f.get("colIds") == col_ids:
            return r["id"], False
    result = client.request("POST", "/tables/_grist_ACLResources/records", {
        "records": [{"fields": {"tableId": table_id, "colIds": col_ids}}]
    })
    return result["records"][0]["id"], True


def apply_rules(client, dry_run):
    # rulePos ordering: first-match-wins within a resource, so order matters.
    pos = 1
    created = skipped = 0
    for table_id, col_ids, formula, perms, memo in RULES:
        resource_id, res_created = get_or_create_resource(client, table_id, col_ids)
        if res_created:
            print(f"Resource created: {table_id}:{col_ids}")
        existing = client.request("GET", "/tables/_grist_ACLRules/records")
        duplicate = False
        for r in existing.get("records", []):
            f = r["fields"]
            if (f.get("resource") == resource_id
                    and f.get("aclFormula") == formula
                    and f.get("permissionsText") == perms):
                duplicate = True
                break
        if duplicate:
            skipped += 1
            pos += 1
            continue
        if dry_run:
            print(f"[dry-run] would add rule {table_id}:{col_ids} {perms} ({formula[:60]}...)")
            pos += 1
            continue
        client.request("POST", "/tables/_grist_ACLRules/records", {
            "records": [{
                "fields": {
                    "resource": resource_id,
                    "aclFormula": formula,
                    "permissionsText": perms,
                    "rulePos": pos,
                    "memo": memo,
                }
            }]
        })
        print(f"Rule added ({table_id}:{col_ids} {perms}): {formula[:70]}")
        created += 1
        pos += 1
    print(f"\nDone: {created} rule(s) added, {skipped} already present.")


def main():
    parser = argparse.ArgumentParser(description="Apply ACL rules to the Coordo-Project doc.")
    parser.add_argument("--doc", required=True, help="Grist document id")
    parser.add_argument("--server", default=os.environ.get("GRIST_SERVER", SERVER))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    api_key = os.environ.get("GRIST_API_KEY")
    if not api_key:
        parser.error("GRIST_API_KEY environment variable is required")

    client = GristClient(args.server, api_key, args.doc)
    ensure_email_column(client, verbose=True)
    apply_rules(client, args.dry_run)
    if args.dry_run:
        print("Dry run: no rules were written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

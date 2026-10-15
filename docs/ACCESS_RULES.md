# Access Rules Plan — Coordo-Project Grist doc

Target document: `mdRfs6ggKhKUkuhqpW1xA6` (Coordo-Project)

This is the ready-to-apply specification for row-level security in the Grist
document. It assumes the `Teachers` table has an `Email` column (Text), and
that the doc has been shared with every permanent teacher and substitute as
**viewers** (Grist ACL rules only apply to users who can already open the
document).

## Principles

1. **Owner/dispatcher (Baptiste) keeps full rights everywhere.**
2. **A teacher (permanent or substitute) sees only what concerns them:**
   - In `Substitutions`: rows where they are the `Teacher` or the `Substitute`.
   - In `Absences`: rows where they are the absent `Teacher` (substitutes see
     nothing by default).
3. **`Teachers` is a directory**: names and statuses are readable by all
   users (needed for reference columns to display names), but the `Email`
   column is readable only by owners.
4. **Deny by default** for everything not explicitly granted.

## Prerequisites checklist

- [ ] Add `Email` (Text) column to `Teachers`
- [ ] Fill the email address of every permanent teacher and substitute
- [ ] Share the doc with all of them as viewers (Accounts must exist in
      Grist; invite by email)
- [ ] Apply the rules below (Access Rules panel in Grist UI, or via the API
      — see "Applying via the API")

## Rules table

`user.Email` is the built-in user attribute (the logged-in user's email).
Owner rules are implicit; the rules below add row-level behavior for
non-owners.

### Table: `Substitutions`

| # | Resource | Effect | Formula (Condition) | Notes |
|---|----------|--------|----------------------|-------|
| 1 | `Substitutions` | Allow `View` | `rec.Teacher.Email == user.Email or rec.Substitute.Email == user.Email` | A user sees only rows that concern them |
| 2 | `Substitutions` | Deny `View` | `True` | Catch-all deny for everyone else |
| 3 | `Substitutions` | Deny `Edit`, `Create`, `Delete` | `True` | Only the dispatcher edits; the script writes with an owner API key |

### Table: `Absences`

| # | Resource | Effect | Formula | Notes |
|---|----------|--------|---------|-------|
| 4 | `Absences` | Allow `View` | `rec.Teacher.Email == user.Email` | Permanent teachers see their own absences |
| 5 | `Absences` | Deny `View` | `True` | Substitutes see nothing here (their schedule lives in `Substitutions`) |
| 6 | `Absences` | Deny `Edit`, `Create`, `Delete` | `True` | Only the dispatcher edits |

### Table: `Teachers`

| # | Resource | Effect | Formula | Notes |
|---|----------|--------|---------|-------|
| 7 | `Teachers:Email` | Allow `View` | `user.Access in [OWNER]` | Email addresses are only for owners (syntax verified against grist-core `ACLRuleCollection.ts`) |
| 8 | `Teachers:Email` | Deny `View` | `True` | Hide from non-owners |
| 9 | `Teachers` (other columns) | Allow `View` | `True` | Names/statuses stay readable so Ref columns display |
| 10 | `Teachers` | Deny `Edit`, `Create`, `Delete` | `True` | |

### Table: `Schools`, `Levels`, Score summary

| # | Resource | Effect | Formula | Notes |
|---|----------|--------|---------|-------|
| 11 | `Schools`, `Levels` | Allow `View` | `True` | Reference data, harmless |
| 12 | `Schools`, `Levels` | Deny write | `True` | |

The Score summary table (`Substitutions_summary_Substitute_Teacher`) inherits
visibility from `Substitutions` group-by rules; if it needs its own rules,
mirror rows 1–3 with `rec.Teacher.Email == user.Email or rec.Substitute.Email == user.Email`.

## Grist Access Rules panel equivalent

If entering via the UI (Gear menu → Access Rules), create these rules:

```
Substitutions:
  View:   rec.Teacher.Email == user.Email or rec.Substitute.Email == user.Email
  View:   True        (Deny)  — add after the Allow rule, marked as Deny
  Edit/Create/Delete: True (Deny)

Absences:
  View:   rec.Teacher.Email == user.Email
  View:   True        (Deny)
  Edit/Create/Delete: True (Deny)

Teachers:
  Email column:
    View: True (Deny)   — non-owners
  Table:
    View: True (Allow)  — other columns stay visible
    Edit/Create/Delete: True (Deny)
```

## Applying via the API

The rules above are stored in the `_grist_ACLRules` / `_grist_ACLResources`
meta-tables. They can be applied programmatically:

```bash
# Read current rules
curl -H "Authorization: Bearer $GRIST_API_KEY" \
  "https://docs.getgrist.com/api/docs/mdRfs6ggKhKUkuhqpW1xA6/tables/_grist_ACLRules/records"

# Add/modify rules via POST/PATCH on _grist_ACLRules records.
```

`scripts/grist_match.py` is unaffected: the API key used belongs to an owner,
so owner access bypasses all deny rules.

## Caveats

- Grist ACL "Deny" rules take precedence over "Allow"; order matters within
  the same table resource.
- `user.Email` matching is case-sensitive in some Grist versions; enter
  emails in `Teachers` exactly as the Grist account email.
- If a teacher has no Grist account matching the email, they simply get the
  deny behavior — sharing the doc with them is what creates the account.
- Sharing the doc as viewer is required: ACL rules filter rows, they do not
  grant document access.

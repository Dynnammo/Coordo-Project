# Coordo-Project

Teacher dispatcher: match absent teachers with the best available substitutes.

Two workflows are supported:

- **Grist (recommended)** — all data lives in the Grist document
  [Coordo-Project](https://docs.getgrist.com/mdRfs6ggKhKU/Coordo-Project).
  Run `scripts/grist_match.py` to fill the `Substitutions` table automatically.
- **CSV (standalone)** — `scripts/match.py` works on local CSV files.

## Grist workflow

The document contains three tables:

| table | columns | role |
|---|---|---|
| `Teachers` | `Name`, `Status` (Permanent/Substitute) | everyone, permanent and substitutes |
| `Schools` | `Name` | schools permanent teachers belong to |
| `Levels` | `Number` | levels 1–10 for permanent teachers |
| `Absences` | `Teacher` (Ref), `Date`, `Period` (Morning/Afternoon) | input: who is absent, when, which half-day |
| `Substitutions` | `Teacher` (Ref), `Substitute` (Ref), `Date`, `Period` | output: who covers whom |
| `Score` (summary of `Substitutions` grouped by Teacher+Substitute) | `Score` (count of periods covered) | historical pairs used by the come-back rule |

### Run the matcher

```bash
export GRIST_API_KEY="your-api-key"   # Grist: Account Settings > API
python scripts/grist_match.py --doc mdRfs6ggKhKUkuhqpW1xA6
```

Add `--dry-run` to print the plan without writing to Grist. Use `--server` or
`GRIST_SERVER` for a self-hosted instance.

Note: the Grist REST API has no offset-based pagination — `limit` only
truncates to the first N records. The client therefore fetches each table in
a single unbounded request, so tables of any size work.

### Matching rules

- Every absence covers one half-day: `Morning` or `Afternoon`.
- Every absence with no existing `Substitutions` row (same teacher, date,
  period) is processed — earliest date first, morning before afternoon.
- Any substitute can replace any absent teacher: subjects are not a constraint.
- A substitute can cover at most one absence per (date, period).
- **Stability first**: if a substitute covers teacher T on date D in one half,
  they are prioritized to cover T in the other half of D too.
- **Come-back rule**: next, substitutes are chosen by their historical score
  with the absent teacher (from the `Score` summary table — the more periods
  a pair has covered together, the more likely the substitute returns).
- Otherwise, among free substitutes, the least busy that day is chosen
  (workload balancing).
- Absences with no free substitute are reported as unmatched; fix by adding
  substitutes or adjusting dates, then rerun.

## CSV workflow (standalone)

```bash
python scripts/match.py --absences data/absences.csv --subs data/substitutes.csv
```

## How it works

The matching engine assigns one substitute to each absence using a score:

1. **Availability filter** — a substitute is only eligible for an absence they
   are available on (same day, and they don't already have an assignment that
   day if `max_per_day` is reached).
2. **Scoring** — any substitute can replace any teacher (no subject
   constraint); among eligible substitutes, the least busy that day wins.
3. **Greedy assignment** — absences are processed in order (earliest first),
   and each absence takes the highest-scoring free substitute.
4. **Reporting** — unmatched absences are reported clearly so the dispatcher
   can handle them manually.

## Data format

### `substitutes.csv`

| column | description |
|---|---|
| `name` | Substitute's name (unique) |
| `days_available` | Comma-separated days they can work, e.g. `mon,tue,wed` |
| `max_per_day` | Max number of periods they can cover per day |

### `absences.csv`

| column | description |
|---|---|
| `teacher` | Name of the absent teacher |
| `day` | Day of the absence, e.g. `mon` |
| `period` | Period number(s) needing coverage, e.g. `1` or `1,2,3` |

## Project structure

```
Coordo-Project/
├── README.md
├── data/                      # sample data for the CSV workflow
├── scripts/
│   ├── grist_match.py         # Grist pipeline (recommended)
│   └── match.py               # standalone CSV matcher
└── tests/
    ├── test_grist_match.py
    └── test_match.py
```

## Tests

```bash
python -m unittest discover tests -v
```

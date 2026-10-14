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
| `Teachers` | `Name`, `Status` (Permanent/Substitute), `Subject` | everyone, permanent and substitutes |
| `Absences` | `Teacher` (Ref), `Date` | input: who is absent, when |
| `Substitutions` | `Teacher` (Ref), `Substitute` (Ref), `Date` | output: who covers whom |

### Run the matcher

```bash
export GRIST_API_KEY="your-api-key"   # Grist: Account Settings > API
python scripts/grist_match.py --doc mdRfs6ggKhKUkuhqpW1xA6
```

Add `--dry-run` to print the plan without writing to Grist. Use `--server` or
`GRIST_SERVER` for a self-hosted instance.

### Matching rules

- Every absence with no existing `Substitutions` row is processed (earliest date first).
- A substitute can cover at most one absence per date.
- Candidates are scored: subject match with the absent teacher (+10), minus
  current workload that day (-1 per assignment) — same subject and least-busy win.
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
2. **Scoring** — eligible substitutes are ranked by:
   - `subject_match` (highest weight): does the substitute teach the same
     subject as the absent teacher?
   - `availability` (lowest weight): a small penalty for substitutes who are
     already covering many periods that day (workload balancing).
3. **Greedy assignment** — absences are processed in order (earliest first),
   and each absence takes the highest-scoring free substitute.
4. **Reporting** — unmatched absences are reported clearly so the dispatcher
   can handle them manually.

## Data format

### `substitutes.csv`

| column | description |
|---|---|
| `name` | Substitute's name (unique) |
| `subject` | Primary subject taught (e.g., `Math`, `English`) |
| `days_available` | Comma-separated days they can work, e.g. `mon,tue,wed` |
| `max_per_day` | Max number of periods they can cover per day |

### `absences.csv`

| column | description |
|---|---|
| `teacher` | Name of the absent teacher |
| `subject` | Subject of the class needing coverage |
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

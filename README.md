# Coordo-Project

Teacher dispatcher: match absent teachers with the best available substitutes.

## Quick start

```bash
python scripts/match.py --absences data/absences.csv --subs data/substitutes.csv
```

Or use the sample data bundled in `data/`.

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
├── data/
│   ├── substitutes.csv
│   └── absences.csv
├── scripts/
│   └── match.py
└── tests/
    └── test_match.py
```

## Tests

```bash
python -m unittest discover tests -v
```

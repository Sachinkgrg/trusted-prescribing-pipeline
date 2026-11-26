# Trusted Prescribing Pipeline

An end to end data solution on NHS open prescribing data: engineering, testing
and insight in one project.

**Question:** how are antibiotics prescribed across GP practices in Newcastle
Gateshead, and can every number be traced back to its source and trusted?

**Status:** bronze and silver layers complete, with 12 automated data quality
checks. Gold layer, test pack and dashboard are in progress (see the roadmap).

## What it does today

```
NHSBSA Open Data API -> data/landing/*.csv -> bronze.epd_raw   -> silver.prescribing
                                              bronze.load_log     silver.dq_results
```

- **Config driven.** The dataset, months and filter live in
  [`config/sources.yml`](config/sources.yml). Adding a source or changing the
  slice needs no Python changes.
- **Reconciled.** Before loading, the pipeline asks the API how many rows match.
  After loading, it compares. A mismatch is a `FAIL`, never a silent gap.
- **Re-runnable.** Loading a month twice replaces it. It does not duplicate it.
- **Audited.** Every load attempt is written to `bronze.load_log`, pass or fail.
- **Cleaned.** The silver layer converts text to dates, whole numbers, money and
  true/false. Values that cannot be converted are kept and flagged, never dropped.
- **Quality checked.** 12 data quality checks (completeness, validity,
  consistency, plausibility, uniqueness) live in
  [`config/checks.yml`](config/checks.yml). Each is a SQL query that counts the
  rows breaking a rule. Results are stored in `silver.dq_results` on every run.
- **Tested.** 32 automated tests run offline against a stand-in for the API.

## Run it

```
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

pytest                       # run the tests
python -m pipeline.discover  # check what the portal holds
python -m pipeline.ingest    # load every configured month
python -m pipeline.silver    # clean, run quality checks, show monthly totals
python -m pipeline.peek      # look at the result
```

Full Windows setup steps are in [SETUP.md](SETUP.md).

## Project layout

| Path | Purpose |
|---|---|
| `config/sources.yml` | What to load: dataset, months, filter |
| `config/checks.yml` | Data quality checks, one SQL rule each |
| `sql/silver/` | Cleaning SQL: bronze to silver |
| `pipeline/silver.py` | Builds silver and runs the quality checks |
| `pipeline/api.py` | Client for the NHSBSA Open Data Portal API |
| `pipeline/bronze.py` | Bronze layer rules: raw text, lineage, idempotent loads, load log |
| `pipeline/ingest.py` | Runs the load and reconciles row counts |
| `pipeline/discover.py` | Explore the portal before loading |
| `pipeline/peek.py` | Quick look at the warehouse |
| `tests/` | Automated tests |
| `docs/01-requirements.md` | Requirements and acceptance criteria |

## Roadmap

- [x] Requirements and acceptance criteria
- [x] Config driven ingestion to bronze, with reconciliation and load log
- [x] Silver layer: typed, cleaned, validated tables in SQL, with 12 quality checks
- [ ] Gold layer: dimensional model for reporting
- [ ] Test pack: test plan, test cases, data quality tests, defect reports
- [ ] CI: tests run automatically on every push (GitHub Actions)
- [ ] Power BI dashboard and a one page findings note

## Data source and licence

English Prescribing Dataset (EPD) with SNOMED code, NHS Business Services
Authority Open Data Portal. Contains public sector information licensed under
the Open Government Licence v3.0.

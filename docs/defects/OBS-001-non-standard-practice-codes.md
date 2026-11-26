# OBS-001: Prescribers with non-standard practice codes

| Field | Value |
|---|---|
| **ID** | OBS-001 |
| **Type** | Observation (data quality warning, not a pipeline defect) |
| **Severity** | Low: data is usable; affects how prescribers are grouped |
| **Found by** | Data quality check `practice_code_format` (severity `warn`) |
| **Status** | Open: under investigation |

## What the check found

On the run of 26 November 2026, **67 rows** had a `practice_code` that is not one
letter followed by five digits, the usual format for GP practice codes.

The full list of affected prescribers, with names and volumes, is generated on
every run in [`reports/findings.md`](../../reports/findings.md).

## Why it matters

If these codes belong to services that are not GP practices (for example
walk-in centres, out-of-hours or community services), mixing them with GP
practices would distort any practice-level comparison.

## Next steps

1. Review the names of the affected prescribers in `reports/findings.md`.
2. Check the codes against the NHS Organisation Data Service (ODS).
3. Decide with the stakeholder whether to report them separately.
4. If they are a known category, add a `prescriber_type` column in silver and
   narrow the check so it only flags genuinely unexpected codes.

## Rows are not deleted

In line with the silver layer rules, these rows are kept and flagged. Totals
for the area include them.

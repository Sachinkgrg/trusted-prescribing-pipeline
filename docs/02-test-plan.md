# Test plan (v1.0)

## 1. Purpose

Show that the pipeline delivers prescribing data that a non-technical
stakeholder can trust: complete, correct, consistent and traceable to source.

## 2. Scope

| In scope | Out of scope |
|---|---|
| Ingestion from the NHSBSA API to bronze | Performance testing at national scale |
| Cleaning and typing from bronze to silver | Security testing of the public API |
| Reporting tables in gold and the findings report | Dashboard usability (to follow with Power BI) |
| Configuration files (`sources.yml`, `checks.yml`) | |

## 3. Approach: three levels of testing

| Level | What it tests | How | When it runs |
|---|---|---|---|
| **Unit and component tests** | Each piece of code behaves as designed, including failure cases | `pytest`, 37 tests, offline, using a stand-in for the API and realistic sample rows | Every change, locally and on every push (GitHub Actions) |
| **Pipeline reconciliation** | Nothing is lost or invented between layers | Source API count = bronze rows (per month); bronze = silver rows; gold totals = silver totals | Every pipeline run |
| **Data quality checks** | The real data obeys business rules | 12 SQL checks in `config/checks.yml`, results stored in `silver.dq_results` | Every pipeline run |

## 4. Test cases

| ID | Test case | Expected result | Covered by | Traces to |
|---|---|---|---|---|
| TC-01 | Load a month whose API count matches the rows received | Status PASS, logged | `test_all_rows_land_in_bronze_and_pass` | AC1, AC4 |
| TC-02 | API count disagrees with rows received | Status FAIL with both counts in the message | `test_count_mismatch_is_reported_as_fail` | AC1 |
| TC-03 | Load the same month twice | No duplicates | `test_running_twice_does_not_duplicate` | AC2 |
| TC-04 | Every bronze row carries its source file and load time | No nulls in lineage columns | `test_bronze_columns_are_lower_case_text_with_lineage` | AC3 |
| TC-05 | A configured month is missing from the source | Status MISSING, run continues | `test_missing_month_is_logged_not_crashed` | AC5 |
| TC-06 | One month errors (e.g. timeout) | That month ERROR, others still load | `test_one_broken_month_does_not_stop_the_others` | AC4 |
| TC-07 | The source adds a new column | Column added, older rows NULL, no failure | `test_a_new_source_column_is_added_not_rejected` | AC1 |
| TC-08 | API rejects a request | The portal's own reason is shown; no pointless retries | `test_rejected_request_shows_the_portals_reason_and_is_not_retried` | DEF-001 |
| TC-09 | Clean data through silver | All 12 checks PASS | `test_clean_data_passes_every_check` | AC6 |
| TC-10 | Text converts to correct types and values | DATE, BIGINT, DOUBLE, BOOLEAN with correct values | `test_types_are_converted`, `test_values_are_converted_correctly` | AC6 |
| TC-11 | Bad rows (blank code, negative cost, 1.5 items, bad date, wrong area, bad flag) | Each caught by the right check; rows flagged, not deleted | `test_bad_rows_are_flagged_not_deleted` | AC6 |
| TC-12 | A row sits in the wrong monthly file | `month_matches_source_file` FAIL, 1 row | `test_row_in_the_wrong_monthly_file_is_caught` | AC6 |
| TC-13 | Duplicate row | `no_duplicate_rows` WARN | `test_duplicate_rows_are_warned` | AC6 |
| TC-14 | Gold totals equal silver totals | Reconciles | `test_gold_adds_back_up_to_silver` | AC7 |
| TC-15 | Gold is altered so money no longer adds up | Reconciliation error | `test_reconciliation_catches_lost_money` | AC7 |
| TC-16 | Findings, charts and README section are generated from data | Files exist; README section replaced | `test_findings_charts_and_readme` | AC7 |

## 5. Entry and exit criteria

**Entry:** requirements and acceptance criteria agreed (`docs/01-requirements.md`); configuration reviewed.

**Exit:** all automated tests pass; 12 of 12 loads PASS; no data quality check at
`error` severity FAILs; every `warn` result is logged as a defect or observation
with an owner and next step.

## 6. Defect management

Defects and observations are recorded in [`docs/defects/`](defects/) with an ID,
severity, steps to reproduce, expected and actual results, root cause, fix and
retest result.

| ID | Title | Severity | Status |
|---|---|---|---|
| [DEF-001](defects/DEF-001-wrong-column-name.md) | Source filter used a column name that does not exist | High | Closed |
| [OBS-001](defects/OBS-001-non-standard-practice-codes.md) | Prescribers with non-standard practice codes | Low | Open |

## 7. Results (latest run)

See [`reports/findings.md`](../reports/findings.md) and the Key findings section of the README.

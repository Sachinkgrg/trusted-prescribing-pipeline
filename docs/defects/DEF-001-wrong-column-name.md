# DEF-001: Source filter used a column name that does not exist

| Field | Value |
|---|---|
| **ID** | DEF-001 |
| **Severity** | High: no data could be loaded |
| **Priority** | P1 |
| **Found in** | First run against the live NHSBSA API (`python -m pipeline.discover`) |
| **Component** | `config/sources.yml` (source filter) and `pipeline/api.py` (error reporting) |
| **Status** | Closed |

## Summary

The configured filter referred to a column called `bnf_code`. The English
Prescribing Dataset with SNOMED code has no such column; the medicine code
column is `BNF_PRESENTATION_CODE`. Every filtered request was rejected.

## Steps to reproduce

1. Set `where` in `config/sources.yml` to `pco_code = '13T00' AND bnf_code LIKE '0501%'`.
2. Run `python -m pipeline.discover`.

## Expected result

A sample row, the dataset's column names and a count of matching rows.

## Actual result

`400 Client Error: BAD REQUEST`. The pipeline retried three times and showed no
reason, so the cause could not be diagnosed.

## Root cause

1. **Assumption not verified against the source.** The filter was written from
   documentation for an older version of the dataset instead of the live schema.
2. **Error reporting hid the cause.** The client discarded the portal's error
   message and retried a request that could never succeed.

## Fix

1. `pipeline/api.py`: a rejected request (4xx) is no longer retried and the
   portal's own message is shown. Server errors (5xx) are still retried.
2. `pipeline/discover.py`: reads one unfiltered row first, so the real column
   names are always visible, then tests the configured filter separately.
3. With the real message visible (`Unrecognized name: bnf_code`), the filter was
   corrected in configuration only: `bnf_presentation_code LIKE '0501%'`.

## Retest

| Check | Result |
|---|---|
| `python -m pipeline.discover` | 5,087 matching rows in EPD_SNOMED_202608 |
| `python -m pipeline.ingest` | 12 of 12 months PASS, 65,299 rows reconciled to the API |
| New automated tests | `test_rejected_request_shows_the_portals_reason_and_is_not_retried`, `test_server_error_is_retried_then_succeeds` |

## Lesson

Discover the live schema before writing filters, and never hide an upstream
system's error message: it is the fastest route to the root cause.

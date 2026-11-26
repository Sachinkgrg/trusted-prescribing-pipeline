# Requirements (v0.1, draft)

This is a self-set brief, written the way I would capture requirements from a
client before building anything. There is no real client. Edit this file as the
project develops and keep the version number honest.

## Background

Antibiotic prescribing by GP practices is monitored across the NHS as part of
antimicrobial stewardship. The NHS Business Services Authority (NHSBSA)
publishes every prescription item dispensed in the community as open data,
month by month.

## The imagined stakeholder

A medicines optimisation lead for the Newcastle Gateshead area. They are not
technical. They want answers they can trust, and they want to know when a
number cannot be trusted.

## Questions the solution must answer

1. How many antibacterial items are prescribed each month, and what do they cost?
2. Is there a seasonal pattern across the last 12 months?
3. Which practices prescribe the most, and which have changed the most?
4. Which antibacterial drugs make up most of the volume?

## Scope

| In scope | Out of scope |
|---|---|
| BNF section 5.1 (antibacterial drugs) | Other BNF sections |
| Practices in sub-ICB location 13T00 | The rest of England |
| September 2025 to August 2026 | Earlier history |
| Monthly refresh | Real-time data |

## Source

English Prescribing Dataset (EPD) with SNOMED code, NHSBSA Open Data Portal,
Open Government Licence v3.0. Accessed through the portal's API.

## Acceptance criteria

Each one is written so that a test can prove it.

| ID | Criterion | Layer |
|---|---|---|
| AC1 | Every month loaded matches the row count reported by the source API | Bronze |
| AC2 | Loading the same month twice does not create duplicates | Bronze |
| AC3 | Every row records its source file and load time | Bronze |
| AC4 | Every load attempt is logged with a status, including failures | Bronze |
| AC5 | A month missing from the source is reported, not silently skipped | Bronze |
| AC6 | Silver keeps every bronze row; values are typed; rows that break a rule are flagged by a check, never deleted | Silver |
| AC7 | To be written with the gold layer (totals reconcile back to bronze) | Gold |

## Assumptions and risks

- The source publishes monthly, a few months in arrears. The latest month may not exist yet.
- The source changed ICB naming from the February 2026 files. The solution must
  not treat a renamed area as a new one. To be tested in the silver layer.
- Practice list sizes are not in this dataset, so volumes are not per patient.
  Any practice comparison must say so.

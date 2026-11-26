-- Gold layer: silver.prescribing -> tables shaped for reporting.
--
-- Rules for gold:
--   1. Built only from silver, never from bronze.
--   2. Every total here must add back up to silver (checked by pipeline/report.py).
--   3. Names are written for the reader of a dashboard, not the engineer.

CREATE SCHEMA IF NOT EXISTS gold;

-- One row per month
CREATE OR REPLACE TABLE gold.monthly_summary AS
SELECT
    month_start,
    COUNT(DISTINCT practice_code)                     AS practices,
    COUNT(*)                                          AS prescription_lines,
    SUM(items)                                        AS items,
    ROUND(SUM(actual_cost_gbp), 2)                    AS cost_gbp,
    ROUND(SUM(actual_cost_gbp) / NULLIF(SUM(items), 0), 2) AS cost_per_item_gbp
FROM silver.prescribing
GROUP BY month_start
ORDER BY month_start;

-- One row per antibiotic (chemical substance), across the whole period
CREATE OR REPLACE TABLE gold.substance_summary AS
SELECT
    bnf_chemical_substance                            AS antibiotic,
    SUM(items)                                        AS items,
    ROUND(SUM(actual_cost_gbp), 2)                    AS cost_gbp,
    ROUND(100.0 * SUM(items) / SUM(SUM(items)) OVER (), 1) AS share_of_items_pct,
    ROUND(SUM(actual_cost_gbp) / NULLIF(SUM(items), 0), 2) AS cost_per_item_gbp
FROM silver.prescribing
GROUP BY bnf_chemical_substance
ORDER BY items DESC;

-- One row per prescriber (practice or other service), across the whole period.
-- No patient list sizes are in this dataset, so these are volumes, not rates.
CREATE OR REPLACE TABLE gold.practice_summary AS
SELECT
    practice_code,
    ANY_VALUE(practice_name)                          AS practice_name,
    regexp_full_match(practice_code, '[A-Z][0-9]{5}') AS standard_code_format,
    COUNT(DISTINCT month_start)                       AS months_active,
    SUM(items)                                        AS items,
    ROUND(SUM(actual_cost_gbp), 2)                    AS cost_gbp
FROM silver.prescribing
GROUP BY practice_code
ORDER BY items DESC;

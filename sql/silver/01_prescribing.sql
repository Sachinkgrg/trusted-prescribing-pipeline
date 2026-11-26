-- Silver layer: bronze.epd_raw -> silver.prescribing
--
-- Rules for silver:
--   1. Every bronze row appears here once. Nothing is dropped or deleted.
--   2. Text becomes the right type: dates, whole numbers, money, true/false.
--   3. If a value cannot be converted, the typed column is NULL and the raw
--      value is kept beside it, so a data quality check can flag the row.
--   4. Codes are trimmed and upper case, so joins and filters behave.

CREATE SCHEMA IF NOT EXISTS silver;

CREATE OR REPLACE TABLE silver.prescribing AS
WITH src AS (
    SELECT
        *,
        NULLIF(TRIM(year_month), '')    AS ym,
        TRY_CAST(items AS DOUBLE)       AS items_number
    FROM bronze.epd_raw
)
SELECT
    -- When
    COALESCE(
        TRY_STRPTIME(ym, '%Y-%m'),
        TRY_STRPTIME(ym, '%Y%m')
    )::DATE                                              AS month_start,
    TRY_STRPTIME(RIGHT(_source_resource, 6), '%Y%m')::DATE AS source_month_start,

    -- Where
    UPPER(TRIM(regional_office_code))                    AS regional_office_code,
    TRIM(regional_office_name)                           AS regional_office_name,
    UPPER(TRIM(icb_code))                                AS icb_code,
    TRIM(icb_name)                                       AS icb_name,
    UPPER(TRIM(pco_code))                                AS pco_code,
    TRIM(pco_name)                                       AS pco_name,
    UPPER(NULLIF(TRIM(practice_code), ''))               AS practice_code,
    TRIM(practice_name)                                  AS practice_name,
    UPPER(TRIM(postcode))                                AS postcode,

    -- What
    UPPER(NULLIF(TRIM(bnf_presentation_code), ''))       AS bnf_presentation_code,
    TRIM(bnf_presentation_name)                          AS bnf_presentation_name,
    UPPER(TRIM(bnf_chemical_substance_code))             AS bnf_chemical_substance_code,
    TRIM(bnf_chemical_substance)                         AS bnf_chemical_substance,
    TRIM(bnf_chapter_plus_code)                          AS bnf_chapter_plus_code,
    TRIM(snomed_code)                                    AS snomed_code,

    -- How much
    CASE WHEN items_number = FLOOR(items_number)
         THEN items_number::BIGINT END                   AS items,
    TRY_CAST(quantity AS DOUBLE)                         AS quantity,
    TRY_CAST(total_quantity AS DOUBLE)                   AS total_quantity,
    TRY_CAST(adq_usage AS DOUBLE)                        AS adq_usage,
    TRY_CAST(nic AS DOUBLE)                              AS nic_gbp,
    TRY_CAST(actual_cost AS DOUBLE)                      AS actual_cost_gbp,
    CASE UPPER(TRIM(unidentified))
         WHEN 'Y' THEN TRUE
         WHEN 'N' THEN FALSE
    END                                                  AS is_unidentified,

    -- Raw values kept for anything we converted, so failures can be checked
    year_month                                           AS raw_year_month,
    items                                                AS raw_items,
    quantity                                             AS raw_quantity,
    nic                                                  AS raw_nic,
    actual_cost                                          AS raw_actual_cost,
    unidentified                                         AS raw_unidentified,

    -- Lineage
    _source_resource                                     AS source_resource,
    _ingested_at                                         AS ingested_at
FROM src;

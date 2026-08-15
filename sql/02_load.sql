-- 02_load.sql
-- Load the CSVs into the tables.
--
-- Two ways to get the files onto the stage:
--
-- A) SnowSQL / Python connector (automated, see sql/load_data.py):
--      PUT file://data/breeds.csv @dog_stage AUTO_COMPRESS=TRUE OVERWRITE=TRUE;
--      PUT file://data/conditions.csv @dog_stage AUTO_COMPRESS=TRUE OVERWRITE=TRUE;
--      PUT file://data/breed_condition_risk.csv @dog_stage AUTO_COMPRESS=TRUE OVERWRITE=TRUE;
--
-- B) Snowflake web UI: open the DOG_COSTS.PUBLIC.dog_stage stage and upload the
--    three CSVs from the data/ folder, then run the COPY statements below.

USE SCHEMA DOG_COSTS.PUBLIC;

COPY INTO breeds
    FROM @dog_stage/breeds.csv
    FILE_FORMAT = (TYPE = CSV SKIP_HEADER = 1 FIELD_OPTIONALLY_ENCLOSED_BY = '"')
    ON_ERROR = ABORT_STATEMENT;

COPY INTO conditions
    FROM @dog_stage/conditions.csv
    FILE_FORMAT = (TYPE = CSV SKIP_HEADER = 1 FIELD_OPTIONALLY_ENCLOSED_BY = '"')
    ON_ERROR = ABORT_STATEMENT;

COPY INTO breed_condition_risk
    FROM @dog_stage/breed_condition_risk.csv
    FILE_FORMAT = (TYPE = CSV SKIP_HEADER = 1 FIELD_OPTIONALLY_ENCLOSED_BY = '"')
    ON_ERROR = ABORT_STATEMENT;

-- Sanity checks
SELECT 'breeds' AS tbl, COUNT(*) AS n_rows FROM breeds
UNION ALL SELECT 'conditions', COUNT(*) FROM conditions
UNION ALL SELECT 'breed_condition_risk', COUNT(*) FROM breed_condition_risk;

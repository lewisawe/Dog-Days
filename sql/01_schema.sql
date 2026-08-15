-- 01_schema.sql
-- "What This Dog Actually Costs" — schema.
-- Run order: 01_schema.sql -> 02_load.sql -> 03_simulation.sql
-- Works in a Snowflake worksheet or via SnowSQL / the Python connector.

CREATE DATABASE IF NOT EXISTS DOG_COSTS;
CREATE SCHEMA IF NOT EXISTS DOG_COSTS.PUBLIC;
USE SCHEMA DOG_COSTS.PUBLIC;

-- Compute. New trial accounts may not have a warehouse selected, so create a
-- small one. CREATE WAREHOUSE does not itself require a running warehouse.
CREATE WAREHOUSE IF NOT EXISTS DOG_WH
    WAREHOUSE_SIZE = XSMALL
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = FALSE;
USE WAREHOUSE DOG_WH;

-- Breed reference: lifespan (median + spread for the simulation), size-band
-- baseline annual costs, one-time setup, and typical acquisition price.
CREATE OR REPLACE TABLE breeds (
    breed_name           STRING,
    size                 STRING,
    lifespan_median      FLOAT,
    lifespan_sd          FLOAT,
    purchase_price       NUMBER,
    annual_food          NUMBER,
    annual_routine_vet   NUMBER,
    annual_preventatives NUMBER,
    annual_insurance     NUMBER,
    puppy_setup          NUMBER,
    lifespan_source      STRING
);

-- Health conditions. mode = 'onetime' (single treatment event) or 'recurring'
-- (one-time diagnosis cost + annual cost from onset to end of life).
CREATE OR REPLACE TABLE conditions (
    condition_name  STRING,
    mode            STRING,
    avg_cost        NUMBER,   -- onetime: treatment cost. recurring: diagnosis cost.
    cost_sd         NUMBER,   -- spread on the one-time cost draw
    annual_cost     NUMBER,   -- recurring only: cost per year from onset
    onset_age       NUMBER,   -- typical age of onset in years
    description     STRING
);

-- Breed-specific elevated predispositions (lifetime probability).
CREATE OR REPLACE TABLE breed_condition_risk (
    breed_name     STRING,
    condition_name STRING,
    lifetime_prob  FLOAT
);

-- Internal stage for loading the CSVs.
CREATE OR REPLACE STAGE dog_stage
    FILE_FORMAT = (TYPE = CSV SKIP_HEADER = 1 FIELD_OPTIONALLY_ENCLOSED_BY = '"' EMPTY_FIELD_AS_NULL = TRUE);

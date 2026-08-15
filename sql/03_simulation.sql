-- 03_simulation.sql
-- The Monte Carlo lifetime-cost simulation. This is the engine of the project.
--
-- We simulate N whole dog-lifetimes per breed entirely in Snowflake SQL. Each
-- simulated dog draws its own lifespan, accrues year-by-year baseline care costs,
-- and rolls the dice on every health condition its breed is predisposed to. The
-- result is not a single number but a full cost DISTRIBUTION per breed: median,
-- best case, and the expensive tail nobody budgets for.
--
-- Run after 01_schema.sql and 02_load.sql.

USE SCHEMA DOG_COSTS.PUBLIC;

-- Number of simulated dogs per breed. GENERATOR needs a constant literal, so to
-- change this, edit the ROWCOUNT in the sim_dogs build below as well.
-- (kept at 10000: 30 breeds x 10000 = 300k simulated dog-lives.)

-- ---------------------------------------------------------------------------
-- Effective risk: breed-specific predispositions, plus whole-population
-- background risk for Cancer and Osteoarthritis applied to EVERY breed. A
-- breed-specific entry overrides the background value.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW effective_risk AS
WITH background AS (
    SELECT b.breed_name,
           bg.condition_name,
           bg.prob AS lifetime_prob
    FROM breeds b
    CROSS JOIN (
        SELECT 'Cancer' AS condition_name, 0.20 AS prob
        UNION ALL SELECT 'Osteoarthritis', 0.25
    ) bg
    WHERE NOT EXISTS (
        SELECT 1 FROM breed_condition_risk r
        WHERE r.breed_name = b.breed_name
          AND r.condition_name = bg.condition_name
    )
)
SELECT breed_name, condition_name, lifetime_prob FROM breed_condition_risk
UNION ALL
SELECT breed_name, condition_name, lifetime_prob FROM background;

-- ---------------------------------------------------------------------------
-- Step 1: one row per simulated dog. Draw a lifespan from a normal distribution
-- around the breed median, clamped to 1..20 years and rounded to whole years.
-- Materialized as a table so the random draws are fixed for the join in step 2.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE sim_dogs AS
SELECT
    b.breed_name,
    ROW_NUMBER() OVER (PARTITION BY b.breed_name ORDER BY RANDOM()) AS sim_id,
    GREATEST(1, LEAST(20, ROUND(b.lifespan_median + b.lifespan_sd * NORMAL(0, 1, RANDOM())))) AS lifespan_years,
    (b.annual_food + b.annual_routine_vet + b.annual_preventatives + b.annual_insurance) AS annual_baseline,
    b.puppy_setup,
    b.purchase_price
FROM breeds b
CROSS JOIN TABLE(GENERATOR(ROWCOUNT => 10000)) g;

-- ---------------------------------------------------------------------------
-- Step 2: for each simulated dog, roll every condition its breed is at risk of.
-- A condition is incurred if a uniform draw lands under the lifetime probability
-- AND the dog lives to the condition's onset age.
--   onetime  -> a treatment cost sampled around the average (never negative)
--   recurring-> a one-time diagnosis cost + annual cost for each year from onset to death
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE sim_condition_costs AS
WITH rolled AS (
    SELECT
        d.breed_name,
        d.sim_id,
        d.lifespan_years,
        r.condition_name,
        c.mode,
        c.avg_cost,
        c.cost_sd,
        c.annual_cost,
        c.onset_age,
        CASE
            WHEN UNIFORM(0::FLOAT, 1::FLOAT, RANDOM()) < r.lifetime_prob
                 AND d.lifespan_years >= c.onset_age
            THEN 1 ELSE 0
        END AS incurred
    FROM sim_dogs d
    JOIN effective_risk r ON r.breed_name = d.breed_name
    JOIN conditions c      ON c.condition_name = r.condition_name
)
SELECT
    breed_name,
    sim_id,
    condition_name,
    incurred,
    CASE
        WHEN incurred = 0 THEN 0
        WHEN mode = 'onetime'
            THEN GREATEST(0, ROUND(avg_cost + cost_sd * NORMAL(0, 1, RANDOM())))
        WHEN mode = 'recurring'
            THEN avg_cost + annual_cost * GREATEST(0, lifespan_years - onset_age)
        ELSE 0
    END AS cost
FROM rolled;

-- ---------------------------------------------------------------------------
-- Step 3: total lifetime cost per simulated dog = baseline over its lifespan +
-- setup + acquisition + summed health costs.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE sim_results AS
WITH health AS (
    SELECT breed_name, sim_id, SUM(cost) AS health_cost
    FROM sim_condition_costs
    GROUP BY breed_name, sim_id
)
SELECT
    d.breed_name,
    d.sim_id,
    d.lifespan_years,
    d.annual_baseline * d.lifespan_years + d.puppy_setup + d.purchase_price AS baseline_cost,
    COALESCE(h.health_cost, 0) AS health_cost,
    (d.annual_baseline * d.lifespan_years + d.puppy_setup + d.purchase_price)
        + COALESCE(h.health_cost, 0) AS lifetime_cost
FROM sim_dogs d
LEFT JOIN health h ON h.breed_name = d.breed_name AND h.sim_id = d.sim_id;

-- ---------------------------------------------------------------------------
-- Summary view: the headline numbers per breed. Median, best/worst deciles,
-- mean, max, expected annual cost, and the tail probability of a very expensive
-- dog (> $40k lifetime).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW breed_cost_summary AS
SELECT
    breed_name,
    COUNT(*)                                                        AS n_sims,
    ROUND(AVG(lifespan_years), 1)                                   AS avg_lifespan,
    ROUND(MEDIAN(lifetime_cost))                                    AS median_cost,
    ROUND(PERCENTILE_CONT(0.10) WITHIN GROUP (ORDER BY lifetime_cost)) AS p10_cost,
    ROUND(PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY lifetime_cost)) AS p90_cost,
    ROUND(AVG(lifetime_cost))                                       AS mean_cost,
    ROUND(MAX(lifetime_cost))                                       AS max_cost,
    ROUND(MEDIAN(lifetime_cost) / NULLIF(AVG(lifespan_years), 0))   AS median_cost_per_year,
    ROUND(AVG(CASE WHEN lifetime_cost > 40000 THEN 1 ELSE 0 END), 3) AS prob_over_40k
FROM sim_results
GROUP BY breed_name;

-- ---------------------------------------------------------------------------
-- Condition drivers: for each breed, how often each condition hits and how much
-- it contributes. avg_cost_all_dogs is the expected cost spread across every dog
-- (the true budget impact). avg_cost_when_affected is the bill if it happens.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW breed_condition_drivers AS
SELECT
    breed_name,
    condition_name,
    ROUND(AVG(incurred), 3)                                    AS pct_affected,
    ROUND(AVG(cost))                                           AS avg_cost_all_dogs,
    ROUND(AVG(CASE WHEN incurred = 1 THEN cost END))           AS avg_cost_when_affected
FROM sim_condition_costs
GROUP BY breed_name, condition_name;

-- Quick look
SELECT * FROM breed_cost_summary ORDER BY median_cost DESC;

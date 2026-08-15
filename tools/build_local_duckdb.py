"""
build_local_duckdb.py
Builds a local DuckDB mirror (local.duckdb) of the Snowflake Monte Carlo so the
Streamlit app can be run and verified BEFORE a Snowflake account exists.

This mirrors sql/03_simulation.sql in DuckDB-compatible SQL. DuckDB has no NORMAL()
generator, so we draw normals with the Box-Muller transform from two uniforms.
DuckDB is a dev convenience only. The submission engine is Snowflake.

Usage:
    pip install duckdb
    python tools/build_local_duckdb.py
"""
import os
import duckdb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
DB_PATH = os.path.join(ROOT, "local.duckdb")
N = 10000

if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

con = duckdb.connect(DB_PATH)

# ---- load CSVs -------------------------------------------------------------
con.execute(f"CREATE TABLE breeds AS SELECT * FROM read_csv_auto('{DATA}/breeds.csv', header=true)")
con.execute(f"CREATE TABLE conditions AS SELECT * FROM read_csv_auto('{DATA}/conditions.csv', header=true)")
con.execute(f"CREATE TABLE breed_condition_risk AS SELECT * FROM read_csv_auto('{DATA}/breed_condition_risk.csv', header=true)")

# ---- effective risk (breed-specific + background applied to all) -----------
con.execute("""
CREATE VIEW effective_risk AS
WITH background AS (
    SELECT b.breed_name, bg.condition_name, bg.prob AS lifetime_prob
    FROM breeds b
    CROSS JOIN (SELECT 'Cancer' AS condition_name, 0.20 AS prob
                UNION ALL SELECT 'Osteoarthritis', 0.25) bg
    WHERE NOT EXISTS (
        SELECT 1 FROM breed_condition_risk r
        WHERE r.breed_name = b.breed_name AND r.condition_name = bg.condition_name)
)
SELECT breed_name, condition_name, lifetime_prob FROM breed_condition_risk
UNION ALL
SELECT breed_name, condition_name, lifetime_prob FROM background
""")

# Box-Muller normal: sqrt(-2 ln u1) * cos(2 pi u2)
NORMAL = "(sqrt(-2*ln(random()+1e-12))*cos(2*pi()*random()))"

# ---- sim_dogs: one row per simulated dog -----------------------------------
con.execute(f"""
CREATE TABLE sim_dogs AS
SELECT
    b.breed_name,
    row_number() OVER (PARTITION BY b.breed_name ORDER BY random()) AS sim_id,
    greatest(1, least(20, round(b.lifespan_median + b.lifespan_sd * {NORMAL}))) AS lifespan_years,
    (b.annual_food + b.annual_routine_vet + b.annual_preventatives + b.annual_insurance) AS annual_baseline,
    b.puppy_setup, b.purchase_price
FROM breeds b
CROSS JOIN range({N}) g
""")

# ---- sim_condition_costs ---------------------------------------------------
con.execute(f"""
CREATE TABLE sim_condition_costs AS
WITH rolled AS (
    SELECT d.breed_name, d.sim_id, d.lifespan_years, r.condition_name,
           c.mode, c.avg_cost, c.cost_sd, c.annual_cost, c.onset_age,
           CASE WHEN random() < r.lifetime_prob AND d.lifespan_years >= c.onset_age
                THEN 1 ELSE 0 END AS incurred
    FROM sim_dogs d
    JOIN effective_risk r ON r.breed_name = d.breed_name
    JOIN conditions c ON c.condition_name = r.condition_name
)
SELECT breed_name, sim_id, condition_name, incurred,
    CASE
        WHEN incurred = 0 THEN 0
        WHEN mode = 'onetime' THEN greatest(0, round(avg_cost + cost_sd * {NORMAL}))
        WHEN mode = 'recurring' THEN avg_cost + annual_cost * greatest(0, lifespan_years - onset_age)
        ELSE 0
    END AS cost
FROM rolled
""")

# ---- sim_results -----------------------------------------------------------
con.execute("""
CREATE TABLE sim_results AS
WITH health AS (
    SELECT breed_name, sim_id, SUM(cost) AS health_cost
    FROM sim_condition_costs GROUP BY breed_name, sim_id
)
SELECT d.breed_name, d.sim_id, d.lifespan_years,
    d.annual_baseline * d.lifespan_years + d.puppy_setup + d.purchase_price AS baseline_cost,
    COALESCE(h.health_cost, 0) AS health_cost,
    d.annual_baseline * d.lifespan_years + d.puppy_setup + d.purchase_price + COALESCE(h.health_cost, 0) AS lifetime_cost
FROM sim_dogs d
LEFT JOIN health h ON h.breed_name = d.breed_name AND h.sim_id = d.sim_id
""")

# ---- summary + drivers views ----------------------------------------------
con.execute("""
CREATE VIEW breed_cost_summary AS
SELECT breed_name,
    count(*) AS n_sims,
    round(avg(lifespan_years), 1) AS avg_lifespan,
    round(median(lifetime_cost)) AS median_cost,
    round(quantile_cont(lifetime_cost, 0.10)) AS p10_cost,
    round(quantile_cont(lifetime_cost, 0.90)) AS p90_cost,
    round(avg(lifetime_cost)) AS mean_cost,
    round(max(lifetime_cost)) AS max_cost,
    round(median(lifetime_cost) / nullif(avg(lifespan_years), 0)) AS median_cost_per_year,
    round(avg(CASE WHEN lifetime_cost > 40000 THEN 1 ELSE 0 END), 3) AS prob_over_40k
FROM sim_results GROUP BY breed_name
""")

con.execute("""
CREATE VIEW breed_condition_drivers AS
SELECT breed_name, condition_name,
    round(avg(incurred), 3) AS pct_affected,
    round(avg(cost)) AS avg_cost_all_dogs,
    round(avg(CASE WHEN incurred = 1 THEN cost END)) AS avg_cost_when_affected
FROM sim_condition_costs GROUP BY breed_name, condition_name
""")

print("built", DB_PATH)
top = con.execute("""
    SELECT breed_name, median_cost, p90_cost, prob_over_40k
    FROM breed_cost_summary ORDER BY median_cost DESC LIMIT 6
""").fetchall()
for r in top:
    print(f"  {r[0]:<28} median ${r[1]:>8,.0f}  p90 ${r[2]:>8,.0f}  P(>40k) {r[3]}")
con.close()

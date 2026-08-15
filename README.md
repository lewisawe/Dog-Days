# What This Dog Actually Costs

Estimate the lifetime cost of owning a dog by breed, shown as a probability
distribution instead of a single number. The estimates come from a Monte Carlo
simulation of thousands of dog-lifetimes run in Snowflake SQL.

Built for the DEV Weekend Challenge: Dog Days Edition.

## How it works

1. Three input tables (breeds, health conditions, breed-condition risk) are loaded
   into Snowflake from CSV.
2. `sql/03_simulation.sql` simulates 10,000 dog-lifetimes per breed. Each simulated
   dog draws its own lifespan, accrues care costs each year (senior years weighted
   higher), and rolls the dice on the health conditions its breed is prone to.
3. The Streamlit app reads the result tables and shows the cost distribution, the
   headline numbers, and the top cost drivers per breed.

## Project layout

```
data/                 input data + methodology
  generate_data.py    builds the three CSVs from documented assumptions
  breeds.csv, conditions.csv, breed_condition_risk.csv
  SOURCES.md          data sources and model methodology
sql/
  01_schema.sql       database, warehouse, tables, stage
  02_load.sql         COPY the CSVs into the tables
  03_simulation.sql   the Monte Carlo simulation (the engine)
  load_data.py        one-shot: schema + upload + load + simulate
streamlit_app.py      the app (runs in Streamlit-in-Snowflake or locally)
tools/
  verify_model.py         pure-Python check of the model numbers
  build_local_duckdb.py   local DuckDB mirror for offline development
requirements.txt      local dependencies (also used by Streamlit Community Cloud)
```

## How the repo fits together

The data flows in one direction: **data → Snowflake → app.**

- **`data/`** holds the inputs. `generate_data.py` turns documented assumptions into three
  CSVs (breeds, conditions, and the per-breed risk of each condition). `SOURCES.md` records
  where every number comes from and what the model simplifies.
- **`sql/`** is where the work happens. `load_data.py` runs the three SQL files in order:
  create the schema, load the CSVs, then run the simulation. `03_simulation.sql` is the
  engine: it fans each breed into 10,000 simulated dogs, draws each dog's lifespan, accrues
  age-weighted care costs, rolls its breed's health conditions, and rolls everything up into
  the `sim_results` table and the `breed_cost_summary` / `breed_condition_drivers` views.
- **`streamlit_app.py`** only reads those Snowflake tables and views. It never does the
  modeling itself. It picks its backend automatically (active Snowpark session inside
  Snowflake, the Python connector locally or on Streamlit Cloud), and the insurance and
  affordability panels fire small parameterized queries so Snowflake recomputes on the fly.
- **`tools/`** exists to trust the SQL. `verify_model.py` reimplements the same model in plain
  Python and `build_local_duckdb.py` reimplements it in DuckDB. When all three land on the
  same medians, the Snowflake simulation is sound. The DuckDB mirror also lets you run the app
  offline during development.

### Against your Snowflake account (local)

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
2. Put your connection details in a `.env` file in the project root:
   ```
   export SNOWFLAKE_ACCOUNT="ORG-ACCOUNT"
   export SNOWFLAKE_USER="you"
   export SNOWFLAKE_PASSWORD="..."
   export SNOWFLAKE_ROLE="ACCOUNTADMIN"
   ```
   The setup creates its own warehouse (`DOG_WH`), so a warehouse is optional.
3. Build everything in Snowflake:
   ```
   python sql/load_data.py
   ```
4. Run the app (it reads `.env` automatically):
   ```
   streamlit run streamlit_app.py
   ```

### As a Streamlit-in-Snowflake app (recommended for the demo)

1. Run `python sql/load_data.py` once to build the data and simulation.
2. In Snowsight: Projects → Streamlit → New. Set the database/schema to
   `DOG_COSTS.PUBLIC`.
3. Paste `streamlit_app.py`, add the `altair` package from the package picker, and
   run. The app uses the active session, so no credentials are needed.

### Offline (no Snowflake)

For UI development without an account, build a local DuckDB mirror. This is a
convenience only; the real engine is Snowflake.
```
python tools/build_local_duckdb.py
streamlit run streamlit_app.py
```

## A note on the numbers

Every figure is a modeled planning estimate in USD, shown as an **uninsured,
pay-as-you-go** cost. Insurance is not baked into the headline (that would double-count
premiums against out-of-pocket bills); it is modeled separately in the app's scenario
tab. Routine care is age-weighted, with senior years costing more. Lifespans lean on the
RVC VetCompass 2024 life tables; costs use US insurer and veterinary ranges. See
`data/SOURCES.md`. This is decision support, not a quote.

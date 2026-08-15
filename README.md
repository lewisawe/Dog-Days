# What This Dog Actually Costs

Estimate the lifetime cost of owning a dog by breed, shown as a probability
distribution rather than a single number. The estimates come from a Monte Carlo
simulation of thousands of dog-lifetimes run in Snowflake SQL.

Built for the DEV Weekend Challenge: Dog Days Edition.

## How it works

1. Three input tables (breeds, health conditions, breed-condition risk) are loaded
   into Snowflake from CSV.
2. `sql/03_simulation.sql` simulates 10,000 dog-lifetimes per breed. Each simulated
   dog draws its own lifespan, accrues year-by-year care costs, and rolls the dice on
   the health conditions its breed is prone to.
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

## Run it

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

Every figure is a modeled planning estimate in USD, gross of insurance
reimbursement. Lifespans lean on the RVC VetCompass 2024 life tables; costs use US
insurer and veterinary ranges. See `data/SOURCES.md`. This is decision support, not a
quote.

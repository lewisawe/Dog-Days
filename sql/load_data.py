"""
load_data.py
One-shot setup for a Snowflake account: runs the schema, uploads the CSVs to the
internal stage, loads them, and builds the Monte Carlo simulation tables/views.

Usage:
    pip install "snowflake-connector-python[pandas]"
    Set connection via environment variables (or edit connect() below):
        SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD,
        SNOWFLAKE_WAREHOUSE (optional), SNOWFLAKE_ROLE (optional)
    python sql/load_data.py

This is the automated path. You can also run the .sql files by hand in a Snowflake
worksheet (upload the CSVs to the DOG_COSTS.PUBLIC.dog_stage stage via the UI first).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
CSVS = ["breeds.csv", "conditions.csv", "breed_condition_risk.csv"]

PLACEHOLDERS = {"", "<none selected>", "none", "null", "xxxxxxxxxxxxxxxxxx"}


def load_dotenv():
    """
    Load key/value pairs from a .env (or connections.toml-style) file into a dict.
    Tolerant of both `KEY=value` and `key = "value"`, ignores comments and
    `[section]` headers. Searches project root and current dir.
    """
    found = {}
    for path in (os.path.join(ROOT, ".env"), os.path.join(os.getcwd(), ".env"),
                 os.path.join(ROOT, "connections.toml")):
        if not os.path.isfile(path):
            continue
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("["):
                    continue
                if line.lower().startswith("export "):
                    line = line[7:]
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.strip()
                # If quoted, take exactly the quoted content and ignore any
                # trailing inline comment. Preserves '#' inside a quoted value.
                if v and v[0] in "\"'":
                    quote = v[0]
                    end = v.find(quote, 1)
                    v = v[1:end] if end != -1 else v[1:]
                else:
                    # unquoted: a ' #' begins an inline comment
                    if " #" in v:
                        v = v.split(" #", 1)[0].strip()
                found[k.strip()] = v
    return found


def resolve():
    """
    Build a Snowflake connect() param dict. Precedence per field:
      1. SNOWFLAKE_<FIELD> from the real OS environment
      2. SNOWFLAKE_<FIELD> from the .env file
      3. bare <field> from the .env file (connections.toml style)
    Bare names are never read from the OS environment (avoids collisions like $USER).
    """
    dot = load_dotenv()

    def ok(v):
        return v is not None and v.strip().lower() not in PLACEHOLDERS and v.strip() != ""

    def pick(field):
        F = field.upper()
        env_val = os.environ.get(f"SNOWFLAKE_{F}")
        if ok(env_val):
            return env_val.strip()
        for key in (f"SNOWFLAKE_{F}", f"snowflake_{field.lower()}"):
            if key in dot and ok(dot[key]):
                return dot[key].strip()
        for key in (field, field.upper(), field.lower()):
            if key in dot and ok(dot[key]):
                return dot[key].strip()
        return None

    params = {}
    for field in ("account", "user", "password", "role", "warehouse", "database", "schema"):
        val = pick(field)
        if val is not None:
            params[field] = val
    return params


def connect():
    import snowflake.connector
    params = resolve()
    for req in ("account", "user", "password"):
        if not params.get(req):
            raise SystemExit(
                f"Missing '{req}'. Put it in a .env file (KEY=value) in the project root "
                f"or export SNOWFLAKE_{req.upper()}. Found keys: {sorted(params)}"
            )
    shown = {k: (v if k != "password" else "***") for k, v in params.items()}
    print("connecting with:", shown)
    return snowflake.connector.connect(**params)


def run_sql_file(cur, path):
    with open(path) as f:
        raw = f.read()
    # Strip '--' line comments first (so a ';' inside a comment can't split a
    # statement), then split on ';'. Our SQL has no '--' inside string literals.
    no_comments = "\n".join(line.split("--", 1)[0] for line in raw.splitlines())
    for chunk in no_comments.split(";"):
        stmt = chunk.strip()
        if stmt:
            cur.execute(stmt)


def main():
    conn = connect()
    cur = conn.cursor()
    try:
        print("1/4 schema...")
        run_sql_file(cur, os.path.join(HERE, "01_schema.sql"))

        print("2/4 uploading CSVs to stage...")
        cur.execute("USE SCHEMA DOG_COSTS.PUBLIC")
        for name in CSVS:
            local = os.path.join(DATA, name).replace("\\", "/")
            cur.execute(f"PUT 'file://{local}' @dog_stage AUTO_COMPRESS=TRUE OVERWRITE=TRUE")

        print("3/4 loading tables...")
        run_sql_file(cur, os.path.join(HERE, "02_load.sql"))

        print("4/4 building simulation (this runs the Monte Carlo in Snowflake)...")
        run_sql_file(cur, os.path.join(HERE, "03_simulation.sql"))

        cur.execute("SELECT breed_name, median_cost, p90_cost, prob_over_40k FROM breed_cost_summary ORDER BY median_cost DESC LIMIT 5")
        print("\nTop 5 by median lifetime cost:")
        for row in cur.fetchall():
            print(f"  {row[0]:<28} median ${row[1]:>7,}  p90 ${row[2]:>7,}  P(>$40k) {row[3]}")
        print("\nDone. Tables and views live in DOG_COSTS.PUBLIC.")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()

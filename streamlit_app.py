"""
streamlit_app.py — "What This Dog Actually Costs"

Reads the Monte Carlo results produced in Snowflake (sql/03_simulation.sql) and
shows lifetime dog-ownership cost as a distribution per breed, plus a live
parameterized scenario lab (insurance and adoption) and a breed leaderboard.

Runs in two environments with no code changes:
  - Streamlit-in-Snowflake: uses the active Snowpark session.
  - Local:   uses snowflake-connector-python with credentials from env vars
             (SNOWFLAKE_ACCOUNT / USER / PASSWORD / [WAREHOUSE] / [ROLE]).
"""
import os
import altair as alt
import pandas as pd
import streamlit as st

DB = "DOG_COSTS.PUBLIC"
TAIL = 40000  # the "expensive dog" threshold used throughout
ADOPT_FEE = 200  # typical adoption fee used by the adopt-vs-buy scenario

st.set_page_config(page_title="What This Dog Actually Costs", page_icon="🐕", layout="wide")


def _load_env_file():
    """Populate os.environ from a local .env (KEY=value, tolerant of `export` and
    quotes) so `streamlit run` works without manually sourcing. Existing OS env
    vars win. Ignored inside Streamlit-in-Snowflake, which has no .env."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.isfile(path):
        return
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.lower().startswith("export "):
            line = line[7:]
        k, v = line.split("=", 1)
        v = v.strip()
        if v and v[0] in "\"'":
            end = v.find(v[0], 1)
            v = v[1:end] if end != -1 else v[1:]
        elif " #" in v:
            v = v.split(" #", 1)[0].strip()
        os.environ.setdefault(k.strip(), v)


_load_env_file()


def _load_st_secrets():
    """Bridge Streamlit secrets into os.environ so the connector path works on
    Streamlit Community Cloud, where credentials come from st.secrets (not env
    vars). Accepts a nested [snowflake] section or flat SNOWFLAKE_* keys. No-ops
    locally when no secrets file exists, and in Streamlit-in-Snowflake."""
    try:
        secrets = st.secrets
    except Exception:
        return
    try:
        if "snowflake" in secrets:
            for k, v in secrets["snowflake"].items():
                os.environ.setdefault(f"SNOWFLAKE_{k.upper()}", str(v))
    except Exception:
        pass
    try:
        for k in secrets:
            if str(k).upper().startswith("SNOWFLAKE_"):
                os.environ.setdefault(str(k).upper(), str(secrets[k]))
    except Exception:
        pass


_load_st_secrets()


# ---------------------------------------------------------------------------
# Data access: one helper that works in Snowflake-in-Streamlit and locally.
# ---------------------------------------------------------------------------
@st.cache_resource
def get_conn():
    """
    Pick a backend, in priority order:
      1. Snowflake-in-Streamlit active Snowpark session (production / SiS).
      2. Snowflake connector via SNOWFLAKE_* env vars (local against your account).
      3. Local DuckDB mirror file (dev-only, built by tools/build_local_duckdb.py).
    """
    try:
        from snowflake.snowpark.context import get_active_session
        return ("snowpark", get_active_session())
    except Exception:
        pass

    if os.environ.get("SNOWFLAKE_ACCOUNT"):
        import snowflake.connector
        params = dict(
            account=os.environ["SNOWFLAKE_ACCOUNT"],
            user=os.environ["SNOWFLAKE_USER"],
            password=os.environ["SNOWFLAKE_PASSWORD"],
        )
        if os.environ.get("SNOWFLAKE_WAREHOUSE"):
            params["warehouse"] = os.environ["SNOWFLAKE_WAREHOUSE"]
        if os.environ.get("SNOWFLAKE_ROLE"):
            params["role"] = os.environ["SNOWFLAKE_ROLE"]
        conn = snowflake.connector.connect(**params)
        cur = conn.cursor()
        try:
            cur.execute("USE WAREHOUSE DOG_WH")  # created by the setup; guaranteed to exist
        except Exception:
            pass
        cur.execute(f"USE SCHEMA {DB}")
        return ("connector", conn)

    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local.duckdb")
    if os.path.exists(local):
        import duckdb
        return ("duckdb", duckdb.connect(local, read_only=True))

    raise RuntimeError("No Snowflake session, no SNOWFLAKE_* env vars, and no local.duckdb mirror.")


@st.cache_data(ttl=600)
def q(sql: str) -> pd.DataFrame:
    kind, handle = get_conn()
    if kind == "snowpark":
        df = handle.sql(sql).to_pandas()
    elif kind == "connector":
        cur = handle.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        df = pd.DataFrame(cur.fetchall(), columns=cols)
    else:  # duckdb dev mirror: objects are unqualified, so drop the DB prefix
        df = handle.execute(sql.replace(f"{DB}.", "")).fetch_df()
    df.columns = [c.lower() for c in df.columns]
    # Snowflake returns numeric columns as Decimal/object; coerce to float so
    # pandas arithmetic and Altair work. Only convert when coercion adds no NaNs.
    for c in df.columns:
        if df[c].dtype == object:
            conv = pd.to_numeric(df[c], errors="coerce")
            if (conv.isna() == df[c].isna()).all():
                df[c] = conv
    return df


def money(x) -> str:
    return f"${x:,.0f}"


def sql_str(s) -> str:
    return "'" + str(s).replace("'", "''") + "'"


# ---------------------------------------------------------------------------
# Theme / CSS (scoped classes, robust across Streamlit versions incl. SiS).
# ---------------------------------------------------------------------------
INK = "#22303C"
MUTED = "#63737F"
SAFE = "#2A9D8F"
AMBER = "#E9A23B"
DANGER = "#E05A47"

st.markdown(
    f"""
    <style>
      .wtdac-hero {{ background: linear-gradient(135deg, #2A9D8F 0%, #22303C 100%);
        border-radius: 18px; padding: 30px 34px; margin: 4px 0 18px 0; color:#fff; }}
      .wtdac-hero h1 {{ margin:0; font-size:2.05rem; font-weight:800; letter-spacing:-0.5px; }}
      .wtdac-hero p {{ margin:10px 0 0 0; font-size:1.05rem; opacity:.93; max-width:760px; }}
      .wtdac-pill {{ display:inline-block; background:rgba(255,255,255,.16); color:#fff;
        padding:4px 12px; border-radius:999px; font-size:.78rem; font-weight:600;
        letter-spacing:.4px; text-transform:uppercase; margin-bottom:14px; }}
      .wtdac-card {{ background:#fff; border:1px solid #ECE7DF; border-radius:14px;
        padding:16px 18px; box-shadow:0 1px 3px rgba(34,48,60,.06); height:100%; }}
      .wtdac-label {{ color:{MUTED}; font-size:.78rem; font-weight:600; text-transform:uppercase;
        letter-spacing:.5px; margin:0 0 6px 0; }}
      .wtdac-value {{ color:{INK}; font-size:1.7rem; font-weight:800; line-height:1.1; margin:0; }}
      .wtdac-sub {{ color:{MUTED}; font-size:.82rem; margin:6px 0 0 0; }}
      .wtdac-meter {{ height:8px; border-radius:99px; background:#EEE9E2; margin-top:12px; overflow:hidden; }}
      .wtdac-meter > span {{ display:block; height:100%; border-radius:99px; }}
      .wtdac-story {{ background:#fff; border:1px solid #ECE7DF; border-left:5px solid {SAFE};
        border-radius:12px; padding:18px 22px; box-shadow:0 1px 3px rgba(34,48,60,.06); }}
      .wtdac-story h4 {{ margin:0 0 4px 0; color:{INK}; font-size:1.12rem; }}
      .wtdac-ev {{ padding:7px 0; border-bottom:1px dashed #EEE9E2; color:{INK}; font-size:.96rem; }}
      .wtdac-ev:last-child {{ border-bottom:none; }}
      .wtdac-ev .age {{ display:inline-block; min-width:78px; color:{MUTED}; font-weight:700; }}
      .wtdac-ev .amt {{ float:right; font-weight:700; color:{DANGER}; }}
      .wtdac-total {{ margin-top:12px; font-size:1.05rem; font-weight:700; color:{INK}; }}
      .wtdac-verdict {{ background:#fff; border:1px solid #ECE7DF; border-radius:12px;
        padding:16px 20px; box-shadow:0 1px 3px rgba(34,48,60,.06); }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Load reference data.
# ---------------------------------------------------------------------------
try:
    with st.spinner("Warming up the Snowflake warehouse and loading breeds…"):
        breeds_df = q(f"SELECT breed_name, size, lifespan_median FROM {DB}.breeds ORDER BY breed_name")
        summary_all = q(f"SELECT * FROM {DB}.breed_cost_summary")
except Exception as e:
    st.title("🐕 What This Dog Actually Costs")
    st.error(
        "Could not reach the Snowflake tables. Run the SQL in `sql/` first "
        "(01_schema → 02_load → 03_simulation), or set the SNOWFLAKE_* env vars locally."
    )
    st.exception(e)
    st.stop()

breed_names = breeds_df["breed_name"].tolist()
SIZE_EMOJI = {"small": "🐕", "medium": "🐕", "large": "🦮", "giant": "🐕‍🦺"}


# ---------------------------------------------------------------------------
# Helpers used across tabs.
# ---------------------------------------------------------------------------
def card(label, value, sub, accent=INK):
    return (
        f'<div class="wtdac-card"><p class="wtdac-label">{label}</p>'
        f'<p class="wtdac-value" style="color:{accent}">{value}</p>'
        f'<p class="wtdac-sub">{sub}</p></div>'
    )


@st.cache_data(ttl=600)
def histogram(breeds):
    in_list = ", ".join(sql_str(b) for b in breeds)
    h = q(f"""
        SELECT breed_name,
               CAST(FLOOR(lifetime_cost / 2000) AS INT) AS bucket,
               COUNT(*) AS n
        FROM {DB}.sim_results
        WHERE breed_name IN ({in_list})
        GROUP BY breed_name, bucket
    """)
    h["cost0"] = h["bucket"] * 2000
    h["cost1"] = h["cost0"] + 2000
    h["cost"] = h["cost0"] + 1000
    h["share"] = h.groupby("breed_name")["n"].transform(lambda s: s / s.sum())
    return h


@st.cache_data(ttl=300)
def scenario_data(breed, adopt, deductible, coins):
    """Live parameterized query: per-sim cost under Uninsured vs With-insurance,
    with an optional adoption acquisition swap. Returns (histogram_df, summary_df).

    Baseline (routine care + setup + acquisition, insurance NOT included) comes from
    sim_results. Uninsured = baseline + full treatment. Insured = baseline + premiums
    + deductible + coinsurance of the rest.
    """
    b = sql_str(breed)
    acq = f"({ADOPT_FEE} - bd.purchase_price)" if adopt else "0"
    scen_cte = f"""
        WITH scen AS (
            SELECT
                sr.baseline_cost + sr.health_cost + {acq} AS uninsured,
                sr.baseline_cost
                    + bd.annual_insurance * sr.lifespan_years
                    + LEAST(sr.health_cost, {deductible})
                    + {coins} * GREATEST(0, sr.health_cost - {deductible})
                    + {acq} AS insured
            FROM {DB}.sim_results sr
            JOIN {DB}.breeds bd ON bd.breed_name = sr.breed_name
            WHERE sr.breed_name = {b}
        )
    """
    hist = q(scen_cte + """
        SELECT scenario, bucket, COUNT(*) AS n FROM (
            SELECT 'Uninsured' AS scenario, CAST(FLOOR(uninsured / 2000) AS INT) AS bucket FROM scen
            UNION ALL
            SELECT 'With insurance', CAST(FLOOR(insured / 2000) AS INT) FROM scen
        ) GROUP BY scenario, bucket
    """)
    hist["cost"] = hist["bucket"] * 2000 + 1000
    hist["share"] = hist.groupby("scenario")["n"].transform(lambda s: s / s.sum())
    summ = q(scen_cte + f"""
        SELECT MEDIAN(uninsured) AS med_unins, MEDIAN(insured) AS med_ins,
               AVG(CASE WHEN uninsured > {TAIL} THEN 1 ELSE 0 END) AS tail_unins,
               AVG(CASE WHEN insured   > {TAIL} THEN 1 ELSE 0 END) AS tail_ins,
               MAX(uninsured) AS max_unins, MAX(insured) AS max_ins
        FROM scen
    """)
    return hist, summ.iloc[0]


# ---------------------------------------------------------------------------
# Hero
# ---------------------------------------------------------------------------
st.markdown(
    """
    <div class="wtdac-hero">
      <div class="wtdac-pill">🐾 powered by a Monte Carlo simulation in Snowflake</div>
      <h1>What This Dog Actually Costs</h1>
      <p>The lifetime cost of a dog is not one number. It is a gamble, and the odds are
      different for every breed. Pick one to see the real range, drawn from 10,000
      simulated dog-lifetimes.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Controls (global)
# ---------------------------------------------------------------------------
left, right = st.columns([1, 1])
with left:
    default_ix = breed_names.index("French Bulldog") if "French Bulldog" in breed_names else 0
    primary = st.selectbox("Choose a breed", breed_names, index=default_ix,
                           help="Each breed is backed by 10,000 dog-lifetimes simulated in Snowflake.")
with right:
    compare_defaults = [b for b in ["Border Collie", "Great Dane"] if b in breed_names and b != primary]
    compare = st.multiselect("Compare with (optional)",
                             [b for b in breed_names if b != primary], default=compare_defaults,
                             help="Overlay other breeds to compare their cost distributions.")

selected = [primary] + compare
row = summary_all[summary_all["breed_name"] == primary].iloc[0]
psize = breeds_df[breeds_df["breed_name"] == primary].iloc[0]["size"]
emoji = SIZE_EMOJI.get(psize, "🐶")

# Verdict badge
tail_pct = float(row["prob_over_40k"])
_pyr = float(row["median_cost_per_year"])
_pyr_hi = float(summary_all["median_cost_per_year"].quantile(0.66))
_tail_hi = float(summary_all["prob_over_40k"].quantile(0.75))
_tail_lo = float(summary_all["prob_over_40k"].quantile(0.33))
if tail_pct >= _tail_hi:
    _label, _color, _why = "High-risk tail", DANGER, "a real chance of a very expensive dog"
elif _pyr >= _pyr_hi:
    _label, _color, _why = "Expensive to run", AMBER, "high steady year-to-year cost"
elif tail_pct <= _tail_lo:
    _label, _color, _why = "Predictable", SAFE, "tight range, low chance of a shock bill"
else:
    _label, _color, _why = "Middle of the pack", INK, "average cost and average risk"
st.markdown(
    f'<div style="margin:2px 0 12px 0"><span style="background:{_color};color:#fff;'
    f'padding:6px 14px;border-radius:999px;font-weight:700;font-size:.9rem">'
    f'{emoji} {primary}: {_label}</span> '
    f'<span style="color:{MUTED};font-size:.92rem">&nbsp;{_why}.</span></div>',
    unsafe_allow_html=True,
)

tab_overview, tab_scenario, tab_board = st.tabs(["📊 Overview", "🛡️ Insurance & adoption", "🏆 Leaderboard"])

# ===========================================================================
# TAB 1 — OVERVIEW
# ===========================================================================
with tab_overview:
    tail_color = SAFE if tail_pct < 0.10 else (AMBER if tail_pct < 0.25 else DANGER)
    meter_w = min(100, tail_pct / 0.50 * 100)
    tail_card = (
        f'<div class="wtdac-card"><p class="wtdac-label">Chance it tops {money(TAIL)}</p>'
        f'<p class="wtdac-value" style="color:{tail_color}">{tail_pct*100:.0f}%</p>'
        f'<div class="wtdac-meter"><span style="width:{meter_w:.0f}%;background:{tail_color}"></span></div></div>'
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(card(f"{emoji} Median lifetime cost", money(row["median_cost"]),
                     f"about {money(row['median_cost_per_year'])} per year"), unsafe_allow_html=True)
    c2.markdown(card("Typical range", money(row["p10_cost"]),
                     f"to {money(row['p90_cost'])} (middle 80%)", accent=SAFE), unsafe_allow_html=True)
    c3.markdown(card("Expected lifespan", f"{row['avg_lifespan']:.0f} yrs",
                     "median for this breed"), unsafe_allow_html=True)
    c4.markdown(tail_card, unsafe_allow_html=True)
    st.write("")

    # Distribution with the danger zone highlighted
    st.subheader("The distribution, not just the average")
    hp = histogram([primary])
    bars = (
        alt.Chart(hp).mark_bar().encode(
            x=alt.X("cost0:Q", title="Lifetime cost (USD)", axis=alt.Axis(format="$,.0f")),
            x2="cost1:Q",
            y=alt.Y("share:Q", title="Share of simulated dogs", axis=alt.Axis(format=".0%")),
            color=alt.condition(f"datum.cost >= {TAIL}", alt.value(DANGER), alt.value(SAFE)),
            tooltip=[alt.Tooltip("cost:Q", title="Cost", format="$,.0f"),
                     alt.Tooltip("share:Q", title="Share", format=".1%")],
        ).properties(height=340)
    )
    median_rule = (alt.Chart(pd.DataFrame({"m": [row["median_cost"]]}))
                   .mark_rule(color=INK, size=2, strokeDash=[5, 4]).encode(x="m:Q"))
    tail_rule = (alt.Chart(pd.DataFrame({"t": [TAIL]}))
                 .mark_rule(color=DANGER, size=1).encode(x="t:Q"))
    st.altair_chart(bars + median_rule + tail_rule, use_container_width=True)
    st.markdown(
        (f"Dashed line marks the median ({money(row['median_cost'])}). "
         f"Everything in :red[**red**] is the tail past {money(TAIL)}: "
         f"**{tail_pct * 100:.0f}% of {primary}s land there.**").replace("$", "\\$")
    )
    st.divider()

    # ---- shared helper: render one simulated life as a timeline card ----
    def life_card(life_df, heading, tier_label="", show_verdict=False):
        head = life_df.iloc[0]
        years = int(head["lifespan_years"])
        total = float(head["lifetime_cost"])
        health = float(head["health_cost"])
        events = life_df.dropna(subset=["condition_name"])
        if events.empty:
            rows_html = (f'<div class="wtdac-ev"><span class="age">Age 0–{years}</span> '
                         f'No major health problems. Just food, checkups, and love.</div>')
        else:
            rows_html = ""
            for _, e in events.iterrows():
                onset = int(e["onset_age"])
                when = f"from age {onset}" if e["mode"] == "recurring" else f"age {onset}"
                rows_html += (f'<div class="wtdac-ev"><span class="age">{when}</span> '
                              f'{e["condition_name"]}<span class="amt">{money(e["event_cost"])}</span></div>')
        accent = DANGER if total > float(row["p90_cost"]) else (SAFE if total < float(row["p10_cost"]) else INK)
        tier_html = f'<div class="wtdac-label" style="margin-bottom:2px">{tier_label}</div>' if tier_label else ""
        vhtml = ""
        if show_verdict:
            diff = total - float(row["median_cost"])
            vcolor = DANGER if diff > 0 else SAFE
            vtxt = (f"{money(abs(diff))} above median" if diff > 0 else f"{money(abs(diff))} below median")
            vhtml = f'&nbsp;<span style="color:{vcolor};font-weight:700">({vtxt})</span>'
        return (
            f'<div class="wtdac-story" style="border-left-color:{accent}">{tier_html}'
            f'<h4>{heading}</h4>'
            f'<div class="wtdac-sub">Health costs: {money(health)} of the total.</div>'
            f'<div style="margin-top:10px">{rows_html}</div>'
            f'<div class="wtdac-total">Total: {money(total)}{vhtml}</div></div>'
        )

    # ---- Three lives: lucky (p5), median (p50), nightmare (p95) ----
    st.divider()
    st.subheader("Three lives: the lucky, the median, the nightmare")
    st.caption("Three real simulated dogs of this breed, at the 5th, 50th, and 95th percentile of lifetime cost. "
               "Same breed, wildly different bills, and the actual life that produced each one.")

    @st.cache_data(ttl=600)
    def three_lives(breed):
        b = sql_str(breed)
        ids = q(f"""
            WITH ranked AS (
                SELECT sim_id, lifetime_cost,
                       ROW_NUMBER() OVER (ORDER BY lifetime_cost) AS rn,
                       COUNT(*) OVER () AS n
                FROM {DB}.sim_results WHERE breed_name = {b})
            SELECT 'Lucky · p5' AS tier, 1 AS ord, sim_id FROM ranked WHERE rn = CAST(0.05 * n AS INT)
            UNION ALL SELECT 'Median · p50', 2, sim_id FROM ranked WHERE rn = CAST(0.50 * n AS INT)
            UNION ALL SELECT 'Nightmare · p95', 3, sim_id FROM ranked WHERE rn = CAST(0.95 * n AS INT)
        """).sort_values("ord")
        id_list = ", ".join(str(int(s)) for s in ids["sim_id"])
        tl = q(f"""
            SELECT sr.sim_id, sr.lifespan_years, sr.baseline_cost, sr.health_cost, sr.lifetime_cost,
                   scc.condition_name, scc.cost AS event_cost, c.onset_age, c.mode
            FROM {DB}.sim_results sr
            LEFT JOIN {DB}.sim_condition_costs scc
                   ON scc.sim_id = sr.sim_id AND scc.breed_name = sr.breed_name AND scc.incurred = 1
            LEFT JOIN {DB}.conditions c ON c.condition_name = scc.condition_name
            WHERE sr.breed_name = {b} AND sr.sim_id IN ({id_list})
            ORDER BY sr.sim_id, c.onset_age NULLS LAST
        """)
        return ids, tl

    with st.spinner("Pulling three lives from Snowflake…"):
        ids3, tl3 = three_lives(primary)
    cols3 = st.columns(3)
    for colx, (_, r3) in zip(cols3, ids3.iterrows()):
        sid = int(r3["sim_id"])
        life_df = tl3[tl3["sim_id"] == sid]
        yrs = int(life_df.iloc[0]["lifespan_years"])
        colx.markdown(life_card(life_df, f"{emoji} Lived {yrs} years", tier_label=r3["tier"]),
                      unsafe_allow_html=True)

    # ---- Can you afford this dog? A budget stress test ----
    st.divider()
    st.subheader("Can you actually afford this dog?")
    st.caption("Enter your budget and Snowflake stress-tests it against every simulated life's worst year.")
    ac1, ac2 = st.columns(2)
    monthly = int(ac1.number_input("Set aside per month ($)", min_value=0, max_value=1000, value=75, step=25,
                                   help="How much you can save toward the dog each month."))
    efund = int(ac2.number_input("Emergency fund on hand ($)", min_value=0, max_value=20000, value=1500, step=500,
                                 help="Cash you could put toward a surprise vet bill today."))

    @st.cache_data(ttl=300)
    def affordability(breed, monthly, efund):
        b = sql_str(breed)
        cushion = efund + monthly * 12
        r = q(f"""
            WITH per_sim AS (
                SELECT d.sim_id, d.annual_baseline,
                       MAX(CASE WHEN c.mode = 'onetime'  AND cc.incurred = 1 THEN cc.cost ELSE 0 END) AS max_onetime,
                       SUM(CASE WHEN c.mode = 'recurring' AND cc.incurred = 1 THEN c.annual_cost ELSE 0 END) AS recurring_annual
                FROM {DB}.sim_dogs d
                LEFT JOIN {DB}.sim_condition_costs cc ON cc.sim_id = d.sim_id AND cc.breed_name = d.breed_name
                LEFT JOIN {DB}.conditions c ON c.condition_name = cc.condition_name
                WHERE d.breed_name = {b}
                GROUP BY d.sim_id, d.annual_baseline
            )
            SELECT AVG(CASE WHEN annual_baseline + max_onetime + recurring_annual > {cushion} THEN 1 ELSE 0 END) AS p_over,
                   MEDIAN(annual_baseline + max_onetime + recurring_annual) AS median_worst,
                   MAX(annual_baseline + max_onetime + recurring_annual)    AS max_worst
            FROM per_sim
        """)
        return r.iloc[0]

    with st.spinner("Stress-testing your budget across 10,000 lives in Snowflake…"):
        aff = affordability(primary, monthly, efund)
    p_over = float(aff["p_over"])
    cushion = efund + monthly * 12
    pct_color = "green" if p_over < 0.10 else ("orange" if p_over < 0.25 else "red")
    st.markdown(f"### :{pct_color}[{p_over * 100:.0f}%] chance of a year you can't cover")
    st.markdown(
        (f"With **{money(monthly)}/month** saved and a **{money(efund)}** emergency fund "
         f"(a **{money(cushion)}** cushion for one bad year), there is a **{p_over * 100:.0f}%** chance "
         f"a {primary} hands you a year whose bills you cannot cover. Its median worst year is "
         f"**{money(aff['median_worst'])}**, and the worst simulated year reached **{money(aff['max_worst'])}**.")
        .replace("$", "\\$")
    )
    st.caption("Worst-year outlay = that year's routine care + the single biggest one-time bill + ongoing condition "
               "costs. Conservative by design: it assumes the big bill and the chronic costs can land in the same year.")

    # ---- Roll a life (random) ----
    st.divider()
    st.subheader("🎲 Roll a life")
    st.caption("Or pull one random simulated dog from the 10,000 in Snowflake.")
    if "roll" not in st.session_state:
        st.session_state.roll = 0
    if st.button(f"Roll a random {primary} life", type="primary"):
        st.session_state.roll += 1

    @st.cache_data(ttl=120)
    def roll_life(breed, nonce):
        b = sql_str(breed)
        return q(f"""
            WITH pick AS (
                SELECT sim_id FROM {DB}.sim_results WHERE breed_name = {b}
                ORDER BY RANDOM() LIMIT 1  -- roll {nonce}
            )
            SELECT sr.lifespan_years, sr.baseline_cost, sr.health_cost, sr.lifetime_cost,
                   scc.condition_name, scc.cost AS event_cost, c.onset_age, c.mode
            FROM {DB}.sim_results sr
            JOIN pick p ON p.sim_id = sr.sim_id
            LEFT JOIN {DB}.sim_condition_costs scc
                   ON scc.sim_id = sr.sim_id AND scc.breed_name = sr.breed_name AND scc.incurred = 1
            LEFT JOIN {DB}.conditions c ON c.condition_name = scc.condition_name
            WHERE sr.breed_name = {b}
            ORDER BY c.onset_age NULLS LAST
        """)

    if st.session_state.roll > 0:
        with st.spinner("Pulling a random dog from Snowflake…"):
            life = roll_life(primary, st.session_state.roll)
        yrs = int(life.iloc[0]["lifespan_years"])
        st.markdown(life_card(life, f"{emoji} This {primary} lived {yrs} years.", show_verdict=True),
                    unsafe_allow_html=True)
    else:
        st.info("Hit the button to meet a dog.")

    # Comparison
    if len(selected) > 1:
        st.divider()
        st.subheader("Side by side")
        hc = histogram(selected)
        overlay = (
            alt.Chart(hc).mark_area(opacity=0.4, interpolate="monotone").encode(
                x=alt.X("cost:Q", title="Lifetime cost (USD)", axis=alt.Axis(format="$,.0f")),
                y=alt.Y("share:Q", title="Share of simulated dogs", axis=alt.Axis(format=".0%"), stack=None),
                color=alt.Color("breed_name:N", title="Breed", scale=alt.Scale(scheme="tableau10")),
                tooltip=[alt.Tooltip("breed_name:N", title="Breed"),
                         alt.Tooltip("cost:Q", title="Cost", format="$,.0f"),
                         alt.Tooltip("share:Q", title="Share", format=".1%")],
            ).properties(height=300)
        )
        med = summary_all[summary_all["breed_name"].isin(selected)][["breed_name", "median_cost"]]
        med_rules = (alt.Chart(med).mark_rule(strokeDash=[5, 4], size=2)
                     .encode(x="median_cost:Q", color=alt.Color("breed_name:N", legend=None)))
        st.altair_chart(overlay + med_rules, use_container_width=True)

        comp = summary_all[summary_all["breed_name"].isin(selected)].copy()
        comp = comp.set_index("breed_name").loc[selected].reset_index()
        for col in ["median_cost", "p10_cost", "p90_cost", "median_cost_per_year"]:
            comp[col] = comp[col].apply(money)
        comp["prob_over_40k"] = (comp["prob_over_40k"] * 100).round(0).astype(int).astype(str) + "%"
        comp = comp.rename(columns={
            "breed_name": "Breed", "avg_lifespan": "Lifespan (yrs)", "median_cost": "Median",
            "p10_cost": "Best case", "p90_cost": "Rough case", "median_cost_per_year": "Per year",
            "prob_over_40k": f"Chance > {money(TAIL)}"})
        st.dataframe(comp[["Breed", "Lifespan (yrs)", "Median", "Best case", "Rough case",
                           "Per year", f"Chance > {money(TAIL)}"]],
                     hide_index=True, use_container_width=True)

    # Cost drivers
    st.divider()
    st.subheader(f"What drives the cost for a {primary}")
    drivers = q(f"""
        SELECT condition_name, pct_affected, avg_cost_all_dogs, avg_cost_when_affected
        FROM {DB}.breed_condition_drivers
        WHERE breed_name = {sql_str(primary)} AND avg_cost_all_dogs > 0
        ORDER BY avg_cost_all_dogs DESC
    """)
    if not drivers.empty:
        dc1, dc2 = st.columns([3, 2])
        with dc1:
            bar = (
                alt.Chart(drivers).mark_bar(cornerRadiusEnd=4).encode(
                    x=alt.X("avg_cost_all_dogs:Q", title="Expected cost per dog (USD)", axis=alt.Axis(format="$,.0f")),
                    y=alt.Y("condition_name:N", sort="-x", title=None),
                    color=alt.Color("pct_affected:Q", title="Share affected",
                                    scale=alt.Scale(scheme="orangered"), legend=alt.Legend(format=".0%")),
                    tooltip=[alt.Tooltip("condition_name:N", title="Condition"),
                             alt.Tooltip("pct_affected:Q", title="Share affected", format=".0%"),
                             alt.Tooltip("avg_cost_when_affected:Q", title="Bill when it happens", format="$,.0f"),
                             alt.Tooltip("avg_cost_all_dogs:Q", title="Expected per dog", format="$,.0f")],
                ).properties(height=320)
            )
            st.altair_chart(bar, use_container_width=True)
        with dc2:
            show = drivers.copy()
            show["pct_affected"] = (show["pct_affected"] * 100).round(0).astype(int).astype(str) + "%"
            show["avg_cost_when_affected"] = show["avg_cost_when_affected"].apply(money)
            show = show.rename(columns={"condition_name": "Condition", "pct_affected": "% of dogs",
                                        "avg_cost_when_affected": "Bill if it happens"})
            st.dataframe(show[["Condition", "% of dogs", "Bill if it happens"]],
                         hide_index=True, use_container_width=True)
    else:
        st.info("No elevated health-cost drivers modeled for this breed beyond background risk.")

# ===========================================================================
# TAB 2 — INSURANCE & ADOPTION (live parameterized Snowflake queries)
# ===========================================================================
with tab_scenario:
    st.subheader(f"Is insurance worth it for a {primary}?")
    st.caption("Move the sliders and Snowflake re-runs the numbers across all 10,000 simulated lives.")

    sc1, sc2, sc3 = st.columns(3)
    acq = sc1.radio("Acquisition", ["Buy (breed price)", "Adopt (~$200)"], horizontal=False,
                    help="Adopt swaps the breed's purchase price for a flat ~$200 fee.")
    adopt = acq.startswith("Adopt")
    deductible = sc2.slider("Annual deductible you cover", 0, 1000, 250, 50,
                            help="What you pay out of pocket each year before insurance starts covering.")
    coins = sc3.slider("Coinsurance you pay after that (%)", 0, 50, 20, 5,
                       help="Your share of the remaining bill after the deductible.") / 100.0

    with st.spinner("Re-running 10,000 simulated lives in Snowflake…"):
        hist, s = scenario_data(primary, adopt, deductible, coins)
    med_u, med_i = float(s["med_unins"]), float(s["med_ins"])
    tail_u, tail_i = float(s["tail_unins"]), float(s["tail_ins"])

    m1, m2, m3 = st.columns(3)
    m1.markdown(card("Median if uninsured", money(med_u),
                     "no premiums, you pay every bill", accent=INK), unsafe_allow_html=True)
    m2.markdown(card("Median with insurance", money(med_i),
                     "premiums + deductible + coinsurance", accent=SAFE), unsafe_allow_html=True)
    dd = tail_u - tail_i
    dd_color = SAFE if dd > 0 else MUTED
    m3.markdown(card(f"Chance of a {money(TAIL)}+ life",
                     f"{tail_u*100:.0f}% → {tail_i*100:.0f}%",
                     "uninsured vs insured", accent=dd_color), unsafe_allow_html=True)
    st.write("")

    overlay = (
        alt.Chart(hist).mark_area(opacity=0.45, interpolate="monotone").encode(
            x=alt.X("cost:Q", title="Lifetime cost (USD)", axis=alt.Axis(format="$,.0f")),
            y=alt.Y("share:Q", title="Share of simulated dogs", axis=alt.Axis(format=".0%"), stack=None),
            color=alt.Color("scenario:N", title=None,
                            scale=alt.Scale(domain=["Uninsured", "With insurance"], range=[DANGER, SAFE])),
            tooltip=[alt.Tooltip("scenario:N", title="Scenario"),
                     alt.Tooltip("cost:Q", title="Cost", format="$,.0f"),
                     alt.Tooltip("share:Q", title="Share", format=".1%")],
        ).properties(height=320)
    )
    rules = (
        alt.Chart(pd.DataFrame({"scenario": ["Uninsured", "With insurance"], "m": [med_u, med_i]}))
        .mark_rule(size=2, strokeDash=[5, 4])
        .encode(x="m:Q", color=alt.Color("scenario:N", legend=None,
                scale=alt.Scale(domain=["Uninsured", "With insurance"], range=[DANGER, SAFE])))
    )
    st.altair_chart(overlay + rules, use_container_width=True)

    # Data-driven verdict
    med_delta = med_i - med_u
    if med_i < med_u:
        vtxt = (f"**Insurance is a clear win here.** At this deductible and coinsurance, it lowers "
                f"the *median* cost by {money(abs(med_delta))} and cuts the chance of a {money(TAIL)}+ "
                f"life from {tail_u*100:.0f}% to {tail_i*100:.0f}%. This breed's health risk is high "
                f"enough that reimbursement beats the premiums.")
        vc = SAFE
    elif dd >= 0.08:
        vtxt = (f"**Worth it for the disaster protection.** Insurance costs about "
                f"{money(med_delta)} more on the median, but it cuts the chance of a {money(TAIL)}+ "
                f"life from {tail_u*100:.0f}% to {tail_i*100:.0f}%. You are buying a smaller tail.")
        vc = AMBER
    else:
        vtxt = (f"**Probably skip it, on these numbers.** Insurance adds about {money(med_delta)} to the "
                f"median and only trims the {money(TAIL)}+ risk from {tail_u*100:.0f}% to "
                f"{tail_i*100:.0f}%. For this breed the premiums outrun the payouts.")
        vc = MUTED
    if adopt:
        vtxt += " Acquisition is set to **adopt**, so the breed purchase price is swapped for a ~$200 fee."
    # Native colored callout (renders markdown reliably; escape $ so it isn't read as LaTeX).
    {SAFE: st.success, AMBER: st.warning, MUTED: st.info}.get(vc, st.info)(vtxt.replace("$", "\\$"))
    st.caption("A simplified insurance model: flat premium already in the baseline, a yearly deductible, "
               "then coinsurance on the rest. Real policies vary. This is for comparison, not a quote.")

# ===========================================================================
# TAB 3 — LEADERBOARD
# ===========================================================================
with tab_board:
    st.subheader("Every breed, ranked")
    metric_label = st.selectbox("Rank by", ["Median lifetime cost", f"Chance it tops {money(TAIL)}", "Cost per year"])
    col = {"Median lifetime cost": "median_cost",
           f"Chance it tops {money(TAIL)}": "prob_over_40k",
           "Cost per year": "median_cost_per_year"}[metric_label]
    is_pct = col == "prob_over_40k"

    lb = summary_all[["breed_name", col]].copy().sort_values(col, ascending=False)
    fmt = ".0%" if is_pct else "$,.0f"
    board = (
        alt.Chart(lb).mark_bar(cornerRadiusEnd=4).encode(
            x=alt.X(f"{col}:Q", title=metric_label, axis=alt.Axis(format=fmt)),
            y=alt.Y("breed_name:N", sort="-x", title=None),
            color=alt.condition(f"datum.breed_name === {sql_str(primary)}",
                                alt.value(DANGER), alt.value(SAFE)),
            tooltip=[alt.Tooltip("breed_name:N", title="Breed"),
                     alt.Tooltip(f"{col}:Q", title=metric_label, format=fmt)],
        ).properties(height=640)
    )
    st.altair_chart(board, use_container_width=True)
    st.caption(f"Your pick, **{primary}**, is highlighted. Values are simulated medians and probabilities.")

# ---------------------------------------------------------------------------
# The Snowflake reveal + footer
# ---------------------------------------------------------------------------
with st.expander("How this works: the Monte Carlo runs in Snowflake"):
    st.markdown(
        "Every breed is backed by **10,000 simulated dog-lifetimes** generated in "
        "Snowflake SQL. Each simulated dog draws its own lifespan, accrues year-by-year "
        "care costs, and rolls the dice on the health conditions its breed is prone to. "
        "The scenario lab re-runs parameterized queries live. Core of the simulation:"
    )
    st.code(
        "-- one row per simulated dog: draw a lifespan around the breed median\n"
        "CREATE OR REPLACE TABLE sim_dogs AS\n"
        "SELECT b.breed_name,\n"
        "       ROW_NUMBER() OVER (PARTITION BY b.breed_name ORDER BY RANDOM()) AS sim_id,\n"
        "       GREATEST(1, LEAST(20, ROUND(b.lifespan_median + b.lifespan_sd * NORMAL(0,1,RANDOM())))) AS lifespan_years,\n"
        "       ...\n"
        "FROM breeds b\n"
        "CROSS JOIN TABLE(GENERATOR(ROWCOUNT => 10000)) g;\n\n"
        "-- roll each breed-specific condition against its lifetime probability\n"
        "... UNIFORM(0::FLOAT, 1::FLOAT, RANDOM()) < r.lifetime_prob ...",
        language="sql",
    )
    st.caption("Full SQL in sql/03_simulation.sql. Data sources and method in data/SOURCES.md.")

with st.expander("About the model and its limits"):
    st.markdown(
        "- **Lifespans** use the Royal Veterinary College VetCompass 2024 medians where a breed "
        "is covered, and commonly published breed figures otherwise.\n"
        "- **Costs** are US planning estimates from insurer claims data and vet guides, drawn around "
        "documented averages.\n"
        "- **Condition risk** per breed comes from published predisposition data, rounded to "
        "planning-grade probabilities.\n"
        "- **Simplifications, on purpose:** routine care is age-weighted (the last up to 3 senior "
        "years cost ~40% more), but within a stage it is flat; each condition is rolled "
        "independently; and a dog's lifespan is drawn independently of the illnesses it develops.\n"
        "- **The headline is uninsured, pay-as-you-go.** Insurance is modeled only in the scenario "
        "tab so you can weigh it. The affordability worst-year figure conservatively assumes a big "
        "one-time bill and chronic costs can land in the same year. None of this is a quote.\n\n"
        "The goal is honest decision support: see the range and the tail, not a false precise number."
    )

st.caption(
    "Modeled planning estimates in USD. Lifespans lean on the RVC VetCompass 2024 life "
    "tables. Not a quote. Adopt with your eyes open."
)

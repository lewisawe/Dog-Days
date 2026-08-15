"""
verify_model.py
A pure-Python mirror of the Snowflake Monte Carlo in sql/03_simulation.sql, used
ONLY to sanity-check the model numbers locally (no Snowflake or third-party deps).
It reads the same CSVs and applies the identical cost logic, so if these numbers
look sane, the SQL model is sound. The Snowflake SQL remains the real engine.
"""
import csv, os, random, statistics

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
N = 10000
BACKGROUND = {"Cancer": 0.20, "Osteoarthritis": 0.25}


def load():
    def rows(name):
        with open(os.path.join(DATA, name)) as f:
            return list(csv.DictReader(f))
    breeds = {r["breed_name"]: r for r in rows("breeds.csv")}
    conditions = {r["condition_name"]: r for r in rows("conditions.csv")}
    risk = {}
    for r in rows("breed_condition_risk.csv"):
        risk.setdefault(r["breed_name"], {})[r["condition_name"]] = float(r["lifetime_prob"])
    return breeds, conditions, risk


def effective_risk(breed, risk):
    eff = dict(risk.get(breed, {}))
    for cond, p in BACKGROUND.items():
        eff.setdefault(cond, p)  # breed-specific overrides background
    return eff


def simulate(breed, breeds, conditions, risk):
    b = breeds[breed]
    median = float(b["lifespan_median"]); sd = float(b["lifespan_sd"])
    annual = sum(int(b[k]) for k in ("annual_food","annual_routine_vet","annual_preventatives","annual_insurance"))
    setup = int(b["puppy_setup"]); price = int(b["purchase_price"])
    eff = effective_risk(breed, risk)
    totals, drivers = [], {c: [0, 0.0] for c in eff}  # cond -> [hits, cost_sum]
    for _ in range(N):
        life = max(1, min(20, round(random.gauss(median, sd))))
        cost = annual * life + setup + price
        for cond, prob in eff.items():
            c = conditions[cond]
            onset = int(c["onset_age"])
            if random.random() < prob and life >= onset:
                if c["mode"] == "onetime":
                    add = max(0, round(random.gauss(int(c["avg_cost"]), int(c["cost_sd"]))))
                else:
                    add = int(c["avg_cost"]) + int(c["annual_cost"]) * max(0, life - onset)
                cost += add
                drivers[cond][0] += 1; drivers[cond][1] += add
        totals.append(cost)
    totals.sort()
    pct = lambda p: totals[min(len(totals)-1, int(p*len(totals)))]
    top = sorted(((c, v[0]/N, (v[1]/v[0] if v[0] else 0)) for c, v in drivers.items()),
                 key=lambda x: -(x[1]*x[2]))[:4]
    return {
        "avg_life": round(statistics.mean(max(1,min(20,round(random.gauss(median,sd)))) for _ in range(2000)),1),
        "median": round(statistics.median(totals)),
        "p10": pct(0.10), "p90": pct(0.90), "max": totals[-1],
        "prob_over_40k": round(sum(1 for t in totals if t > 40000)/N, 3),
        "top": top,
    }


def main():
    breeds, conditions, risk = load()
    for breed in ["Labrador Retriever","French Bulldog","Great Dane","Border Collie",
                  "Bernese Mountain Dog","Cavalier King Charles Spaniel","Chihuahua"]:
        r = simulate(breed, breeds, conditions, risk)
        print(f"\n{breed}  (median lifespan {breeds[breed]['lifespan_median']}y)")
        print(f"  median ${r['median']:,}   p10 ${r['p10']:,}   p90 ${r['p90']:,}   max ${r['max']:,}")
        print(f"  P(lifetime > $40k) = {r['prob_over_40k']*100:.1f}%")
        for cond, pct, avg in r["top"]:
            print(f"    - {cond}: {pct*100:.0f}% of dogs, ${avg:,.0f} when it happens")


if __name__ == "__main__":
    random.seed(42)
    main()

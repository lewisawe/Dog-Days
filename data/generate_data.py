"""
generate_data.py
Emits the input tables for "What This Dog Actually Costs".

This script only produces STATIC INPUT DATA (breeds, conditions, breed-condition
risks). The actual lifetime-cost Monte Carlo simulation runs in Snowflake SQL, not
here. See sql/03_simulation.sql.

Every number here is a documented modeled estimate. Sources and assumptions are in
data/SOURCES.md. Lifespans lean on the RVC VetCompass 2024 life-table study where a
breed is covered; other lifespans use commonly published breed figures. Treatment
and care costs use US ranges from insurer claims data and vet cost guides (2024-2026).
These are planning estimates, not quotes.
"""

import csv
import os

OUT = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Baseline annual care cost by size band (US dollars, modeled).
# food + routine vet (exam/vaccines) + preventatives (flea/tick/heartworm) + insurance.
# ---------------------------------------------------------------------------
SIZE_BASELINE = {
    # size:      food, routine_vet, preventatives, insurance
    "small":  {"food": 420, "routine_vet": 350, "preventatives": 300, "insurance": 480},
    "medium": {"food": 620, "routine_vet": 400, "preventatives": 360, "insurance": 600},
    "large":  {"food": 900, "routine_vet": 460, "preventatives": 440, "insurance": 760},
    "giant":  {"food": 1300, "routine_vet": 520, "preventatives": 540, "insurance": 900},
}

# One-time first-year setup cost added to every dog (supplies, spay/neuter,
# initial vaccine series, microchip). Modeled US estimate.
PUPPY_SETUP = 550

# ---------------------------------------------------------------------------
# Breeds. lifespan_median from RVC 2024 study where marked (src="rvc2024"),
# otherwise commonly published breed lifespan (src="published").
# lifespan_sd drives per-dog variation in the simulation.
# purchase_price: typical US acquisition cost (modeled midpoint).
# ---------------------------------------------------------------------------
# columns: name, size, lifespan_median, lifespan_sd, purchase_price, lifespan_src
BREEDS = [
    ("Labrador Retriever",        "large",  13.1, 2.2, 1200, "rvc2024"),
    ("French Bulldog",            "small",   9.8, 2.4, 3500, "rvc2024"),
    ("Golden Retriever",          "large",  12.5, 2.3, 1500, "published"),
    ("German Shepherd",           "large",  11.3, 2.4, 1500, "published"),
    ("Standard Poodle",           "large",  12.9, 2.2, 1800, "published"),
    ("English Bulldog",           "medium",  9.8, 2.3, 2800, "rvc2024"),
    ("Beagle",                    "small",  12.7, 2.0, 900,  "published"),
    ("Rottweiler",                "large",  10.0, 2.3, 1600, "published"),
    ("Dachshund",                 "small",  12.2, 2.1, 1200, "rvc2024"),
    ("German Shorthaired Pointer","large",  12.5, 2.1, 1200, "published"),
    ("Pembroke Welsh Corgi",      "medium", 12.3, 2.0, 1800, "published"),
    ("Australian Shepherd",       "medium", 13.0, 2.0, 1200, "published"),
    ("Yorkshire Terrier",         "small",  12.6, 2.1, 1500, "published"),
    ("Boxer",                     "large",  10.4, 2.3, 1400, "published"),
    ("Cavalier King Charles Spaniel","small",11.3,2.3, 2500, "published"),
    ("Great Dane",                "giant",   9.0, 2.0, 1800, "rvc2024"),
    ("Doberman Pinscher",         "large",  10.5, 2.2, 1800, "published"),
    ("Shih Tzu",                  "small",  12.8, 2.1, 1000, "published"),
    ("Border Collie",             "medium", 13.1, 2.0, 1000, "rvc2024"),
    ("Siberian Husky",            "medium", 12.6, 2.0, 1200, "published"),
    ("Bernese Mountain Dog",      "giant",   8.4, 1.9, 2000, "published"),
    ("Chihuahua",                 "small",  13.5, 2.2, 800,  "published"),
    ("Pug",                       "small",  11.6, 2.3, 1800, "rvc2024"),
    ("Cocker Spaniel",            "medium", 11.3, 2.2, 1200, "published"),
    ("Miniature Schnauzer",       "small",  12.8, 2.0, 1500, "published"),
    ("Pomeranian",                "small",  12.4, 2.1, 1400, "published"),
    ("Boston Terrier",            "small",  11.7, 2.2, 1200, "published"),
    ("Shiba Inu",                 "small",  13.0, 2.0, 1800, "published"),
    ("Mastiff",                   "giant",   9.0, 1.9, 1800, "rvc2024"),
    ("Jack Russell Terrier",      "small",  12.7, 2.0, 900,  "rvc2024"),
]

# ---------------------------------------------------------------------------
# Conditions. mode "onetime" = single treatment event; "recurring" = annual
# ongoing cost from onset to end of life.
# For onetime: avg_cost / cost_sd is the treatment cost.
# For recurring: dx_cost is a one-time diagnosis cost, annual_cost recurs yearly.
# onset_age = typical age of onset (years). "age_related" onset handled in SQL.
# ---------------------------------------------------------------------------
# columns: name, mode, avg_cost, cost_sd, annual_cost, onset_age, description
CONDITIONS = [
    ("Hip dysplasia",        "onetime",   5200, 1500,    0, 4, "Malformed hip joint; often needs surgery (FHO/THR)."),
    ("Elbow dysplasia",      "onetime",   3000, 1000,    0, 2, "Developmental elbow disease; arthroscopy or surgery."),
    ("Cruciate ligament rupture","onetime",4000, 1200,   0, 6, "CCL tear needing TPLO/TTA surgery."),
    ("Gastric dilatation-volvulus","onetime",5000,1500,  0, 7, "Bloat; emergency surgery, life-threatening."),
    ("Brachycephalic airway (BOAS)","onetime",3500,1000, 0, 2, "Airway surgery for flat-faced breathing problems."),
    ("Intervertebral disc disease","onetime",6000,2000,  0, 5, "IVDD; spinal surgery for disc herniation."),
    ("Dilated cardiomyopathy","recurring",1500, 0,    1200, 6, "Progressive heart muscle disease; lifelong meds."),
    ("Mitral valve disease", "recurring", 1000, 0,     900, 8, "Degenerative heart valve; lifelong management."),
    ("Cancer",               "onetime",   6000, 3000,    0, 6, "Major cancer treatment (surgery/chemo); mostly mid-to-late life."),
    ("Atopic dermatitis",    "recurring",  400, 0,     800, 2, "Chronic allergies; lifelong meds and vet visits."),
    ("Osteoarthritis",       "recurring",  300, 0,     600, 8, "Age-related joint disease; onset late in life."),
    ("Hypothyroidism",       "recurring",  400, 0,     500, 5, "Lifelong thyroid medication."),
    ("Epilepsy",             "recurring",  600, 0,    1200, 3, "Seizure disorder; lifelong medication."),
    ("Eye disease (PRA/cataracts)","onetime",3000,1000, 0, 7, "Cataract surgery or progressive vision loss."),
    ("Patellar luxation",    "onetime",   2500,  800,    0, 3, "Kneecap dislocation; surgical correction."),
    ("Cushing's disease",    "recurring",  600, 0,    1500, 8, "Adrenal disorder; lifelong meds and monitoring."),
]

# ---------------------------------------------------------------------------
# Breed-condition risk. lifetime_prob = probability the dog develops this
# condition over its life (modeled from breed-health literature).
# Only ELEVATED / notable predispositions are listed per breed. Baseline
# whole-population risks (cancer, osteoarthritis) are applied to ALL breeds in
# the SQL so every dog carries some background risk; entries here OVERRIDE the
# baseline for predisposed breeds.
# ---------------------------------------------------------------------------
# dict: breed -> list of (condition, lifetime_prob)
RISK = {
    "Labrador Retriever": [("Hip dysplasia",0.20),("Elbow dysplasia",0.12),("Cruciate ligament rupture",0.15),("Osteoarthritis",0.45),("Cancer",0.31)],
    "French Bulldog": [("Brachycephalic airway (BOAS)",0.45),("Intervertebral disc disease",0.20),("Atopic dermatitis",0.30),("Hip dysplasia",0.14),("Patellar luxation",0.10)],
    "Golden Retriever": [("Cancer",0.38),("Hip dysplasia",0.18),("Elbow dysplasia",0.10),("Atopic dermatitis",0.20),("Osteoarthritis",0.40)],
    "German Shepherd": [("Hip dysplasia",0.19),("Elbow dysplasia",0.12),("Cruciate ligament rupture",0.12),("Osteoarthritis",0.42),("Cancer",0.25)],
    "Standard Poodle": [("Hip dysplasia",0.10),("Cancer",0.24),("Cushing's disease",0.08),("Eye disease (PRA/cataracts)",0.10)],
    "English Bulldog": [("Brachycephalic airway (BOAS)",0.50),("Hip dysplasia",0.30),("Atopic dermatitis",0.35),("Cruciate ligament rupture",0.12)],
    "Beagle": [("Epilepsy",0.10),("Hypothyroidism",0.10),("Atopic dermatitis",0.15),("Osteoarthritis",0.30)],
    "Rottweiler": [("Cruciate ligament rupture",0.18),("Hip dysplasia",0.20),("Cancer",0.35),("Osteoarthritis",0.42)],
    "Dachshund": [("Intervertebral disc disease",0.25),("Patellar luxation",0.08),("Cushing's disease",0.08),("Osteoarthritis",0.35)],
    "German Shorthaired Pointer": [("Hip dysplasia",0.10),("Cancer",0.22),("Gastric dilatation-volvulus",0.10)],
    "Pembroke Welsh Corgi": [("Intervertebral disc disease",0.12),("Hip dysplasia",0.10),("Osteoarthritis",0.38)],
    "Australian Shepherd": [("Eye disease (PRA/cataracts)",0.12),("Epilepsy",0.08),("Hip dysplasia",0.10)],
    "Yorkshire Terrier": [("Patellar luxation",0.15),("Mitral valve disease",0.20),("Eye disease (PRA/cataracts)",0.08)],
    "Boxer": [("Cancer",0.38),("Dilated cardiomyopathy",0.15),("Hip dysplasia",0.12),("Osteoarthritis",0.35)],
    "Cavalier King Charles Spaniel": [("Mitral valve disease",0.50),("Eye disease (PRA/cataracts)",0.10),("Patellar luxation",0.10)],
    "Great Dane": [("Gastric dilatation-volvulus",0.25),("Dilated cardiomyopathy",0.18),("Hip dysplasia",0.15),("Osteoarthritis",0.40)],
    "Doberman Pinscher": [("Dilated cardiomyopathy",0.45),("Cancer",0.25),("Hip dysplasia",0.10)],
    "Shih Tzu": [("Brachycephalic airway (BOAS)",0.25),("Eye disease (PRA/cataracts)",0.15),("Patellar luxation",0.10),("Atopic dermatitis",0.15)],
    "Border Collie": [("Hip dysplasia",0.10),("Epilepsy",0.08),("Eye disease (PRA/cataracts)",0.10),("Osteoarthritis",0.30)],
    "Siberian Husky": [("Eye disease (PRA/cataracts)",0.12),("Hip dysplasia",0.08),("Atopic dermatitis",0.12)],
    "Bernese Mountain Dog": [("Cancer",0.45),("Hip dysplasia",0.20),("Elbow dysplasia",0.15),("Osteoarthritis",0.45)],
    "Chihuahua": [("Patellar luxation",0.18),("Mitral valve disease",0.20),("Eye disease (PRA/cataracts)",0.08)],
    "Pug": [("Brachycephalic airway (BOAS)",0.45),("Eye disease (PRA/cataracts)",0.15),("Atopic dermatitis",0.25),("Hip dysplasia",0.12)],
    "Cocker Spaniel": [("Eye disease (PRA/cataracts)",0.15),("Atopic dermatitis",0.20),("Mitral valve disease",0.15),("Hypothyroidism",0.10)],
    "Miniature Schnauzer": [("Cushing's disease",0.10),("Cancer",0.20),("Eye disease (PRA/cataracts)",0.10)],
    "Pomeranian": [("Patellar luxation",0.15),("Mitral valve disease",0.15),("Eye disease (PRA/cataracts)",0.08)],
    "Boston Terrier": [("Brachycephalic airway (BOAS)",0.30),("Patellar luxation",0.12),("Eye disease (PRA/cataracts)",0.15)],
    "Shiba Inu": [("Patellar luxation",0.10),("Atopic dermatitis",0.20),("Eye disease (PRA/cataracts)",0.08)],
    "Mastiff": [("Hip dysplasia",0.22),("Gastric dilatation-volvulus",0.18),("Cancer",0.30),("Osteoarthritis",0.42)],
    "Jack Russell Terrier": [("Patellar luxation",0.10),("Eye disease (PRA/cataracts)",0.10),("Osteoarthritis",0.28)],
}


def write_csv(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"wrote {path}: {len(rows)} rows")


def main():
    # breeds.csv
    breed_rows = []
    for name, size, life, sd, price, src in BREEDS:
        b = SIZE_BASELINE[size]
        breed_rows.append([
            name, size, life, sd, price,
            b["food"], b["routine_vet"], b["preventatives"], b["insurance"],
            PUPPY_SETUP, src,
        ])
    write_csv(
        os.path.join(OUT, "breeds.csv"),
        ["breed_name","size","lifespan_median","lifespan_sd","purchase_price",
         "annual_food","annual_routine_vet","annual_preventatives","annual_insurance",
         "puppy_setup","lifespan_source"],
        breed_rows,
    )

    # conditions.csv
    cond_rows = [[n, mode, avg, sd, ann, onset, desc]
                 for (n, mode, avg, sd, ann, onset, desc) in CONDITIONS]
    write_csv(
        os.path.join(OUT, "conditions.csv"),
        ["condition_name","mode","avg_cost","cost_sd","annual_cost","onset_age","description"],
        cond_rows,
    )

    # breed_condition_risk.csv
    risk_rows = []
    for breed, items in RISK.items():
        for cond, prob in items:
            risk_rows.append([breed, cond, prob])
    write_csv(
        os.path.join(OUT, "breed_condition_risk.csv"),
        ["breed_name","condition_name","lifetime_prob"],
        risk_rows,
    )

    # sanity checks
    breed_names = {b[0] for b in BREEDS}
    cond_names = {c[0] for c in CONDITIONS}
    for breed, items in RISK.items():
        assert breed in breed_names, f"risk breed not in breeds: {breed}"
        for cond, prob in items:
            assert cond in cond_names, f"risk condition not in conditions: {cond}"
            assert 0 < prob < 1, f"bad prob {prob} for {breed}/{cond}"
    print(f"OK: {len(BREEDS)} breeds, {len(CONDITIONS)} conditions, {len(risk_rows)} risk rows")


if __name__ == "__main__":
    main()

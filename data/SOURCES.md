# Data Sources and Methodology

This project estimates the lifetime cost of owning a dog by breed. Every number is a
**modeled planning estimate**, not a quote or a guarantee. The point is the shape of the
risk, not a precise dollar figure for any individual dog.

## What is real vs modeled

**Lifespans.** Breeds marked `rvc2024` use median life expectancy from the Royal
Veterinary College VetCompass life-table research on UK companion dogs (McMillan et al.,
*Scientific Reports*, 2024, including the April 2024 author correction). Examples: Border
Collie 13.1, Labrador 13.1, French Bulldog 9.8, English Bulldog 9.8, Great Dane 9.0,
Mastiff 9.0, Pug 11.6, Dachshund 12.2, Jack Russell 12.7. Breeds marked `published` use
commonly cited breed lifespans from vet and kennel-club sources.

**Treatment costs.** US dollar ranges from pet-insurer claims data and veterinary cost
guides (2024-2026). Anchors: hip dysplasia diagnosis ~$1,500 and treatment ~$5,200 (Lemonade
claims data); total hip replacement $3,500-7,000 per hip; cruciate (TPLO) surgery
~$3,500-5,000; the widely reported reality that a single unexpected vet bill often lands in
the $3,000-7,000 range.

**Annual care costs.** Modeled by size band: food, routine vet (exam and vaccines),
preventatives (flea/tick/heartworm), and pet insurance. Insurance premiums (~$300-900/yr)
track published US averages that rise with size and breed risk.

**Condition prevalence by breed.** The biggest modeled component. Lifetime probabilities are
drawn from breed-health literature and predisposition data, then rounded to planning-grade
figures. Only elevated, breed-notable predispositions are listed per breed. Whole-population
background risks (cancer, age-related osteoarthritis) are applied to every breed in the
simulation SQL, and a breed-specific entry overrides the background value when present.

## The model

For each breed we run a Monte Carlo simulation **in Snowflake SQL** (`sql/03_simulation.sql`).
Each simulated dog:

1. Draws a lifespan from a normal distribution around the breed median (clamped to a sane range).
2. Accrues baseline annual care costs (food + routine vet + preventatives). Care is age-weighted:
   the last up to three years of life cost 40% more, reflecting higher senior vet and medication
   needs. Insurance is deliberately excluded here so the headline is an uninsured, pay-as-you-go
   figure; insurance is modeled separately in the app's scenario lab.
3. Adds a one-time first-year setup cost and the breed's typical acquisition price.
4. For each condition the breed is at risk of, rolls against the lifetime probability. If it hits:
   - **one-time** conditions add a treatment cost sampled around the average, if the dog lives to the onset age.
   - **recurring** conditions add a one-time diagnosis cost plus an annual cost for every year from onset to death.

Running thousands of simulated dog-lives per breed turns "what does this breed cost" from a
single number into a distribution: a median, a best case, and a tail. The tail is the part
nobody budgets for.

## Honest limitations

- Prevalence figures are planning estimates, not epidemiological point estimates. Real risk
  varies with breeding lines, screening, diet, and luck.
- Costs are US-centric and vary widely by region and clinic.
- We model the common predispositions per breed, not every possible condition.
- The headline cost is uninsured and pay-as-you-go. The scenario lab models insurance as a flat
  premium plus a deductible and coinsurance, a simplified policy for comparison, not a quote.
- Within a life stage, care cost is flat; we approximate the senior increase as a 40% surcharge
  on the last up to three years rather than a smooth per-year curve.
- A dog's lifespan is drawn independently of the conditions it develops; we do not model a fatal
  condition shortening life.

The goal is decision support before adoption: see the range, understand the tail, adopt with
eyes open.

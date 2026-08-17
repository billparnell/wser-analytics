# Pacing Model — Phase 2 of WSER Analytics

*A learning log, not a replication. Started August 2026.*

---

## The thesis

Grade-adjusted pace, as implemented by Strava and most watches, uses one generic
curve for every runner. The interesting work in ultra pacing right now — Joseph
Mestrallet / Enduraw being the visible example — starts by fitting a *personal*
cost curve from an athlete's own GPS data, then layers environmental terms
(temperature, humidity, wind, altitude) on top, then produces segment-by-segment
pace targets.

This project works through that stack from the bottom, using a dataset nobody
else has: my own Western States 100 file, plus Black Canyon and Big Alta.

**The specific question I want to answer:** what did the standard model predict
for me through the WS canyons, what did I actually run, and how much of the gap
does heat explain?

Western States is a good test case precisely because it's the condition European
ultra data handles worst. Canyon temperatures at 2pm are not Chamonix.

---

## Scope

**In scope**
- Fitting a personal grade/cost curve from my own race and training GPS files
- Comparing it against Strava GAP and against the published Minetti curve
- Adding one environmental term (heat) and testing whether it improves fit
- Documenting every step, including the wrong turns

**Out of scope**
- Reverse-engineering Enduraw's proprietary model. Their fatigue term — how the
  cost curve decays over 100 miles — is the actual hard part and is not public.
  This project studies published science; Enduraw is the practitioner I'm
  learning from, and gets cited as such.
- Coaching anyone off these numbers. This is a portfolio and learning artifact.

**Framing note for the writeup:** "documenting my study of published pacing
science" — never "reverse-engineering a competitor." Small field. The generous
version travels better and is also the true one.

---

## Why this sits in the WSER repo

Phase 1 (results explorer) and Phase 2 (pacing model) share infrastructure and
eventually share data:

- Same DuckDB warehouse, same dbt project
- WSER publishes aid station splits — thousands of runners, segment by segment.
  Once a course-level pacing model exists, that's a validation set no other
  hobbyist has assembled.
- "Built by a finisher" carries across both. Place 108, 25:21:50, 2025.

Two finished phases of one project beat two half-finished projects. Phase 1's
staging model gets built first.

---

## Background reading

### Science (all English, all published)

| Source | What it gives me |
|---|---|
| Minetti et al. 2002, *J Appl Physiol* 93(3):1039-46 | The foundational energy-cost-vs-grade curve, treadmill, −45% to +45%. Free article on PubMed. Everything downstream is a fit to this. |
| Saugy et al. 2006 | Eccentric muscle damage markers by slope — the thing the metabolic curve can't see |
| Townshend et al. 2014 | How downhill damage in the first half shows up as late-race pace loss |
| Kipp, Byrnes & Kram 2018 | Gait parameter shifts by slope; why one curve per runner is defensible |
| Blocken et al. (cycling peloton CFD) | Aerodynamics/drafting. Cited directly by Enduraw. Lower priority for a solo 100M. |

### Practitioner (Enduraw / Mestrallet)

- **Transvulcania analysis** (Medium, English) — *read this first.* Fits a
  personal gradient coefficient curve for Petter Engdahl, plots real speed vs.
  Strava GAP vs. custom GAP, shows Strava overestimating downhill speed. This is
  the method, in public.
  `medium.com/@josephmestrallet/nutrition-and-data-analysis-of-petter-engdahl-transvulcania-e03fcf77bdbb`
- **Enduraw Report API** (Medium, English) — the environmental adjustment layer:
  wind direction and speed, temperature, humidity, altitude, pulled per-activity
  from a weather API.
  `medium.com/@josephmestrallet/enduraw-report-api-a-powerful-tool-to-enhance-your-activity-interpretation-with-external-7273edbf9653`
- **NYC Marathon pacing strategy** (Medium, French) — km-by-km plan construction;
  place-vs-time race framing
- **Evokecast #125** (Oct 2025, English, ~71 min) — Scott Johnston interview.
  Best overview of the pacing philosophy.
- Outside.fr and u-Trail interviews (French) — context and claims, not method

Most of the method material is in English. The French is mostly interviews.

### Reaching out

Email Mestrallet. Western States finisher, published in graph theory, specific
technical question. Worst case is silence.

---

## Data

| Source | Status | Notes |
|---|---|---|
| WS100 2025 GPS (mine) | ⬜ export | ~26h at 1s ≈ 90k points |
| Black Canyon 100k 2026 | ⬜ export | 13:45, course PR — good second fit point |
| Big Alta 100k 2026 | ⬜ export | Different terrain profile |
| Training runs, Upper Park / Legacy Trail | ⬜ export | Fresh-legs baseline, no fatigue confound |
| Historical weather, WS course 6/28/2025 | ⬜ | Open-Meteo has a free historical API |
| WSER aid station splits | ⬜ | Phase 3 validation set |

Convert FIT/GPX → Parquet in Python early. Don't make Power Query parse XML.

Fresh-legs training data matters more than it looks: it isolates the grade term
before fatigue contaminates it. Fit the curve on those first, then see how badly
it breaks at mile 80.

---

## Phases

### Phase 0 — finish what's already started
- [ ] Build `stg_wser_results.sql`
- [ ] Mart models: finisher trends, age groups, multi-finish runners, sub-24 rates
- [ ] dbt tests + docs
- [ ] Push Phase 1 to GitHub with a clean README

### Phase 1 — the baseline curve
- [ ] Export and parse GPS files to Parquet
- [ ] Clean: drop GPS dropouts, smooth elevation (raw barometric noise will wreck
      grade calculation), compute grade over a sensible window — 10m or 20m, not
      point-to-point
- [ ] Implement the Minetti polynomial as a reference function
- [ ] Implement Strava's GAP as a second reference
- [ ] Plot my actual speed vs. grade, all files, and look at it before fitting
      anything

### Phase 2 — the personal fit
- [ ] Fit a curve to my own speed-vs-grade data. Start with a polynomial to match
      the literature; try a spline if the tails misbehave
- [ ] Split uphill and downhill fits — asymmetry is the whole point
- [ ] Compare: my curve vs. Minetti vs. Strava. Where do they diverge, and by
      how much over the course of 100 miles?
- [ ] Write up Phase 2 before moving on. The writeup is the deliverable.

### Phase 3 — heat
- [ ] Pull historical hourly weather along the course by timestamp and lat/lon
- [ ] Add a temperature term. Simplest defensible version first: a multiplier on
      cost as a function of temperature (and probably wet-bulb, not dry-bulb)
- [ ] Test whether it improves fit on the WS file specifically, in the canyons
- [ ] Be honest in the writeup if it doesn't

### Phase 4 — front ends
- [ ] **Plotly** — full-resolution interactive explorer. Stacked subplots with a
      shared x-axis: elevation profile / pace traces / residual, all scrubbing
      together. Export standalone HTML to the repo.
- [ ] **Power BI** — segment-level report on binned data. See constraint below.
- [ ] **matplotlib** — static figures for the writeup

### Phase 5 — validation (stretch)
- [ ] WSER aid station splits as a multi-runner test set
- [ ] Does the model's segment prediction hold across ~thousands of finishers?

---

## Modeling notes

**Minetti polynomial (verify coefficients against the paper before trusting):**

```
C(i) = 155.4i⁵ − 30.4i⁴ − 43.3i³ + 46.3i² + 19.5i + 3.6
```

Cost in J·kg⁻¹·m⁻¹, `i` = gradient as a fraction, valid roughly −0.45 ≤ i ≤ 0.45.
Flat cost ≈ 3.6. This is a fit to lab data on 10 trained subjects at
steady state — it says nothing about hour 20.

**Things that will bite:**

- Grade computed point-to-point from GPS elevation is garbage. Smooth first.
- Hiking and running are different cost functions. Above ~15–20% grade I was
  walking, and that's a regime change, not a curve extension. Minetti measured
  both separately for a reason.
- Aid station stops need to come out of the speed data or they'll read as
  0 mph at whatever grade the aid station sits on.
- Fatigue is confounded with everything late in the race. Don't fit one curve to
  the whole 100 miles and call it personal — fit early-race and late-race
  separately and look at the difference. That difference *is* the interesting
  result, and it's the thing I can honestly say I found rather than borrowed.

---

## Front-end constraint worth knowing up front

**Power BI caps most visuals at 3,500 displayed data points** — total, across all
series — and silently downsamples past that. A 90k-point trace gets decimated
~25×. It will look fine and will not be showing the divergences the model exists
to find.

So the split is:

- **Power BI** works on binned/segment-level data — aid station to aid station,
  or quarter-mile bins. Genuinely more readable at that grain, and it's the
  resume-relevant artifact: star schema, DAX measures, Power Query, publish to
  Service. Use **what-if parameters** for target finish time and expected
  temperature, with DAX recomputing segment targets live — that's the feature
  that makes this look like a product instead of a dashboard.
- **Deneb** (free custom visual, Vega-Lite specs inside Power BI) for anything
  the native visuals can't render. Same point limits, near-total design control.
  Rare enough in a mid-level BI candidate to be worth having touched.
- **Plotly** for the full-resolution version.

Power BI Desktop is free but Windows-only. Publishing to a shared workspace needs
Pro (~$14/user/month) — buy one month when there's something worth linking to.
Until then: `.pbix` in the repo plus a screen-recorded walkthrough.

Same fitted model feeds all three. Building the second and third is nearly free
once the first exists, and "one model, three front ends, here's why I chose each"
is a better interview answer than any one of them.

---

## Open questions

- Polynomial or spline for the personal fit?
- Wet-bulb or dry-bulb for the heat term? (Suspect wet-bulb, given humidity in
  the canyons.)
- How to handle the run/hike transition — one model with a breakpoint, or two?
- Is there enough signal in three race files to say anything, or does this need
  a season of training data behind it?
- Email Mestrallet before or after Phase 2 is written up? (After, probably — a
  specific question about a specific result beats a general one.)

---

## Log

*One entry per session. What I tried, what broke, what I learned. This is the
actual product — the model is the excuse.*

### 2026-08-15 — scoped
Decided the project. Settled scope, reading list, phase order. Key decision:
Phase 0 (finishing the existing dbt work) comes first — one finished project
beats two half-built ones.

### 2026-08-15 — dbt unblocked, warehouse decided
Built `pacing_todo.md` from this doc, checked against the actual repo. Three
things the plan doc had wrong:

- `models/` held nothing but dbt's scaffold examples. Phase 0 was at zero, not
  partly done.
- The GPX already in `data/raw/` is the *course* file (Torsten Heycke, 8,118
  points, aid-station waypoints) — not my 26-hour activity file. All of Phase 1
  still blocks on exporting the real thing.
- dbt couldn't run. I assumed a missing Snowflake adapter; `dbt debug` said
  otherwise — `dbt-snowflake` 1.11.4 was installed and registered fine, and the
  failure was `250001 (08001) Incorrect username or password`. Worth writing
  down: I diagnosed from `requirements.txt` instead of from the error, and got
  the cause wrong. Run the thing first.

**Decision: DuckDB, drop Snowflake.** The dataset is ~11k rows and the whole
pipeline is local; Snowflake was buying a resume line and a credential-rotation
chore, nothing analytical. `profiles.yml` now lives in the repo with a relative
path and no secrets, so the project is clone-and-run. Model SQL stays ANSI-plain
so the profile is the only thing that changes if this ever needs a real
warehouse. Deleted the plaintext Snowflake password from `~/.dbt/profiles.yml`;
the trial account still needs deleting from the console.

`dbt debug` passes, `dbt parse` is clean, `staging/` and `marts/` are configured
and empty. Next: pick the source for `stg_wser_results` — raw Excel, the prep
script's CSVs, or the 11,046-row `main.wser_results` table already in
`data/wser.duckdb`.

### 2026-08-17 — Phase 1: the file, and the first look

Got the WS100 2025 file off the COROS. 86,570 points, 1 Hz, 100.1 mi,
25:24:21 on the watch against 25:21:50 official. Distance, elevation, heart
rate and cadence all present.

**The elevation is quantised to whole metres.** That's the finding that shaped
everything else. At ~2 m of travel per sample, one 1 m step reads as a 50%
grade: 86% of samples show *zero* elevation change and then it jumps a full
metre. Point-to-point grade off this file puts **8.9% of points outside
Minetti's entire valid range**, with a maximum of 1050% and a standard
deviation of 28.6% on a course whose real grades sit inside ±25%. The plan doc
said grade computed point-to-point would be garbage. It's worse than that, and
for a reason the doc didn't anticipate — not GPS noise, watch quantisation.

Curiously, the *aggregate* is fine: raw total gain 18,209 ft against the
course's published ~18,000. The error is entirely local.

**Smoothing window: 75 m, not the 10–20 m I'd guessed.** Swept a
Savitzky-Golay window on a 1 m distance grid and used total climb as the
criterion. 20 m leaves 1,265 ft of phantom gain; 200 m erases 840 ft of real
terrain; 75 m lands within 30 ft of published. Worth being honest that the
published figure is itself a smoothed survey number, so this calibrates the
window rather than validating it. Kept a 20 m grade column alongside so Phase 2
can test how much the choice matters.

Grade must be measured per metre travelled, not per second — speed swings
tenfold between running the flats and hiking a canyon, so a time-indexed series
would weight the slow parts of the course far more heavily.

**Aid-station stops fall out of the GPS on their own.** Sustained sub-0.5 m/s
over 60 s finds 9 stops, and **8 land within half a mile of a real aid
station** — Robinson Flat 11.7 min, Michigan Bluff 10.4, Rucky Chucky 6.5 + 2.3
(the river), Devil's Thumb 3.8. The ninth, 4.9 min at mile 22.1, is nowhere
near a station and must have been mine. Validating this against
`stg_wser_aid_stations` is the first time the two halves of the project have
touched. Total 50 min stopped, 24.56 h moving against 25.41 h elapsed.

Two GPS dropouts, at mile 3.3 and mile 52.9 (El Dorado Creek, the 552 s gap).
Both understate horizontal distance while the real descent continues, which
manufactured grades of +179%. Masked a smoothing window either side rather than
trusting the interpolation. After that, grade runs −43% to +49%, which is
believable for this course, and 98.9% of cells survive for fitting.

#### The first look

| grade | measured | Minetti (constant power) | ratio |
|---|---|---|---|
| −20% | 1.98 m/s | 4.42 | **0.45** |
| −10% | 2.43 | 3.70 | 0.66 |
| −5% | 2.43 | 2.90 | 0.84 |
| 0% | 2.22 | 2.21 | 1.01 |
| +5% | 1.79 | 1.70 | 1.06 |
| +10% | 1.43 | 1.33 | 1.07 |
| +20% | 1.08 | 0.88 | **1.23** |

Anchored at flat, so the divergence away from flat is the whole content.

**Downhill, the textbook curve is wrong by more than a factor of two.** Minetti
predicts peak speed of 4.46 m/s at −18%; I peaked at 2.48 m/s at −8%. The
metabolic curve says descending is cheap, so go fast. Real trail says braking
forces, technical footing and quadriceps that have to survive another 40 miles.
None of that is in a treadmill metabolic cost.

This is the Enduraw Transvulcania finding — Strava overestimating downhill
speed — arrived at independently on my own file. Encouraging, and also a
reminder that I haven't done anything novel yet: I've reproduced the known
result that makes personal curves worth fitting.

**Uphill I'm *faster* than the model**, and increasingly so with steepness
(1.23× at +20%). Suspect that's the run/hike regime change — above ~15% I'm
power-hiking, and hiking is cheaper than the running curve extrapolates. Which
is exactly why Minetti measured walking separately, and an argument for the
breakpoint model over one continuous curve.

**Heart rate is nearly flat across the whole range** — 127–136 bpm whether
descending at 11:26/mi or climbing at 19:49/mi, rising only to 145 on the
steepest pitches. I paced by effort, not by speed. That's worth returning to:
if effort really was near-constant, then a cost curve fitted to this file is
close to an iso-effort curve, which is the assumption the whole constant-power
comparison rests on.

Not fitted anything yet. That was the point of today.

Next: verify the Minetti coefficients against the actual paper before they get
load-bearing, add Strava GAP as a second reference, then split early-race from
late-race and see how much of the downhill gap is fatigue rather than terrain.

# Pacing Project — To Do

Working list derived from `pacing_project.md`, reconciled against what's actually
in the repo as of 2026-08-15. Phase order follows the plan doc: Phase 0 finishes
first.

Status key: `[ ]` not started · `[~]` partly done · `[!]` blocked / needs a decision

---

## Phase 0 — finish the dbt work that's already started

Reality check as of 2026-08-15: `models/` contained only dbt's scaffold
examples, and the dashboard was fed by `scripts/prep_dashboard_data.py`
(pandas → CSVs) bypassing dbt entirely. As of 2026-08-16 the staging and mart
layers exist and `dbt build` runs 54 checks green; the dashboard still reads
the CSVs rather than the dbt models, which is the remaining seam.

### 0.0 Unblock dbt before writing any SQL — **DONE 2026-08-15**
- [x] **Warehouse decided: DuckDB, Snowflake dropped.** The real failure was
      never a missing adapter (`dbt-snowflake` 1.11.4 was installed) — it was
      auth: `250001 (08001) Incorrect username or password`. Rather than chase
      stale trial credentials, the project commits to local DuckDB.
- [x] Project-local `profiles.yml` at the repo root targeting
      `data/wser.duckdb` (dbt reads cwd before `~/.dbt`). No secrets, relative
      path, so the repo is clone-and-run.
- [x] Snowflake output and its plaintext password removed from
      `~/.dbt/profiles.yml`
- [x] Deleted `models/example/` and its `schema.yml`; `dbt_project.yml` now
      configures `staging/` (views) and `marts/` (tables)
- [x] `dbt debug` → all checks passed; `dbt parse` clean
- [ ] **Delete the Snowflake trial account** at `hkbevzo-sub68389` — the
      password was in plaintext on disk and is now unused. Console login needed.
- [x] Removed the stale empty `wser.duckdb` at the repo root (0 tables, 12 KB)
- [x] `.duckdb` gitignored and untracked; `scripts/build_db.py` rebuilds the
      database from the tracked CSVs, verified by delete-and-rebuild
- [x] Removed the empty `scripts/ingest_excel.py`, superseded by `build_db.py`
- [x] **dbt source settled.** `build_db.py` loads all six tables, so dbt reads
      from DuckDB and the ingest question is answered for both streams at once.
      Note the provenance asymmetry: `wser_results` is a *scrape* of wser.org
      (11k rows, 1974–2025), while `runners`/`splits` are parsed from the local
      Excel in `data/raw/` (2017–2025). They are not the same pipeline and
      don't currently reconcile against each other.
- [x] **Reconciled the two streams, and it found a bug.** 2017 disagreed by
      two runners. `prep_dashboard_data.py` inferred finisher status from the
      spreadsheet's Time cell, but the sheet lists all starters in one ordered
      block — finishers ranked from 1, then DNFs continuing the numbering — so
      two genuine 2017 finishers with blank Time cells (Sean Nowak, bib 381,
      26:17:33; Maddy McCarthy, bib 262, 26:40:00) were counted as DNFs.
      Fixed by deriving `finished` from the finisher block, which reproduces
      wser.org's official count for all eight years. Also confirmed Meghan
      Arbogast / Canfield is one runner under two surnames — names are not a
      safe join key across the streams.
- [ ] Consider gitignoring `data/processed/*.csv` too — also derived, and
      regenerable by `prep_dashboard_data.py`. Left tracked for now so the
      offline rebuild doesn't depend on parsing 40 spreadsheets.

### 0.1 Models
- [x] `stg_wser_results.sql` — 11,046 rows, 1974–2025. Surrogate key over
      (year, name, finish_minutes): ties make (year, place) non-unique, and two
      different Paul Schmidts finished in 2000. Adds `finish_seconds` parsed
      from the string (the scrape truncates to the minute), normalised
      `gender` (M/F/NB from five reported spellings), `is_official_finish`
      (false for runners recorded past the 30-hour cutoff) and `is_sub_24`.
- [x] `stg_wser_runners.sql` — 2,928 starters, 2017–2025, with DNFs
- [x] `stg_wser_splits.sql` — 52,131 rows, one per runner-station
- [x] `stg_wser_aid_stations.sql` — 24 stations in course order
- [x] `fct_finisher_trends` — one row per race year; starters, finishers,
      finish rate, gender split, sub-24 rate, fastest/median/slowest
- [x] `fct_age_group_performance` — race year x age group x gender. Bands are
      our own decades, NOT WSER award divisions; 14 finishers with no recorded
      age go to 'Unknown' so bands still sum to the year total.
- [x] `fct_sub_24_rates` — race year x gender. Counts people, not places (see
      the 1983/1984 note below).
- [x] `dim_runner_careers` — one row per runner; multi-finishers are
      `finish_count > 1`. **Identity is name-only, by decision on 2026-08-16.**
      Wrong in both directions: Arbogast/Canfield splits one runner into two
      careers (1 + 12 finishes), the two Paul Schmidts of 2000 merge two people
      into one. `has_identity_conflict` flags careers whose implied birth year
      moves >2 years or that finished twice in one June — 46 of 6,958 careers,
      all multi-finishers, so ~2.5% of multi-finish careers are suspect.
      Exclude flagged rows from any "most finishes" ranking.
- [ ] Spot-check Bill Finkbeiner: the model gives him 17 finishes (1983–2011)
      under a single name spelling. If his real total is higher, the scrape is
      missing years or he appears under another spelling — worth an eyeball
      from someone who knows the history.

### 0.2 Quality + ship
- [x] dbt tests — 54 passing across staging and marts: unique/not_null on
      every grain, range checks on rates,
      `accepted_values` on gender and year, relationship tests splits →
      runners and splits → aid_stations
- [x] Two singular tests carrying the reconciliation:
      `assert_results_and_runners_agree` (cross-source finisher counts must
      match on 2017–2025 — verified it fails on the pre-fix data) and
      `assert_finisher_counts_match_wser_org` (matches wser.org's published
      summary, with 1990 and 2005 pinned as known exceptions)
- [x] Source + model + column descriptions in yml
- [x] README section for the dbt layer
- [x] `dbt docs generate` runs clean (catalog written)
- [ ] Decide whether to publish the docs site anywhere
- [ ] **Unresolved upstream:** two separately scraped wser.org pages disagree.
      1990 results list has 211 official finishers vs 208 in the summary (and
      the list itself is odd — place 21 missing, one place shared); 2005 has a
      clean gapless 1–318 sequence vs 317 in the summary. Both look like
      summary-side errors. Resolving means going back to wser.org.
- [x] **`is_sub_24` counts people, not places** (decided 2026-08-16).
      wser.org's summary appears to count places, so 1983 and 1984 each come
      out one higher here where a tie straddles the 24-hour line. Counting
      humans who broke 24 hours is the defensible reading; documented in
      `fct_sub_24_rates` rather than tuned to match.
- [ ] Point the Streamlit dashboard at the dbt models instead of reading
      `data/processed/*.csv` directly — closes the last bypass
- [ ] Push Phase 1 (results explorer) to GitHub with a clean README
- [ ] Reconcile the phase numbering — the repo section calls the results explorer
      "Phase 1" and the phase list calls the baseline curve "Phase 1." Pick one
      before the writeups start referring to them.

---

## Phase 1 — the baseline curve

### 1.0 Get the data
- [!] **Export WS100 2025 GPS (mine).** The GPX already in `data/raw/` is the
      *course* file (Torsten Heycke, 8,118 points, aid-station waypoints) — not
      the 26-hour activity file. Still need the personal one from Garmin/Strava.
- [ ] Export Black Canyon 100k 2026 (13:45)
- [ ] Export Big Alta 100k 2026
- [ ] Export 3–5 fresh-legs training runs (Upper Park, Legacy Trail)
- [ ] Decide FIT vs GPX at the source. FIT keeps per-second cadence/HR and the
      barometric altimeter field; Strava's GPX export drops some of it.

### 1.1 Parse and clean
- [ ] `scripts/parse_activities.py` — FIT/GPX → Parquet in `data/activities/`,
      one file per activity, columns: timestamp, lat, lon, ele, dist, hr, cadence
- [ ] Add `fitparse` (or `fitdecode`) to `requirements.txt`
- [ ] Drop GPS dropouts — flag gaps > N seconds and implausible speeds rather
      than silently interpolating over them
- [ ] Smooth elevation before touching grade (Savitzky-Golay or a rolling
      median; compare against the course GPX profile as a sanity check)
- [ ] Compute grade over a 10 m and a 20 m window; keep both and compare
- [ ] Detect and strip aid-station stops — otherwise they read as 0 mph at
      whatever grade the aid station sits on
- [ ] Tag each point with elapsed race time and cumulative distance (needed for
      the early/late fatigue split later)

### 1.2 Reference curves
- [ ] Implement the Minetti polynomial, coefficients verified against the 2002
      paper — the version in `pacing_project.md` is transcribed from memory
- [ ] Implement Strava GAP as a second reference
- [ ] Unit-test both against known points (flat cost ≈ 3.6 J·kg⁻¹·m⁻¹)

### 1.3 Look before fitting
- [ ] Scatter actual speed vs. grade, all files, hex-binned
- [ ] Overlay Minetti and Strava GAP on the same axes
- [ ] Write down what you see *before* fitting anything — that observation is
      the first log entry with real content in it

---

## Phase 2 — the personal fit

- [ ] Fit speed-vs-grade on fresh-legs training files first (no fatigue confound)
- [ ] Polynomial first to match the literature; spline if the tails misbehave
- [ ] Split uphill and downhill fits — the asymmetry is the point
- [ ] Handle the run/hike transition explicitly: breakpoint model vs. two
      separate fits above/below ~15–20% grade. Test both, report which won.
- [ ] Fit early-race and late-race separately on the WS file; the *difference*
      is the headline result
- [ ] Compare my curve vs. Minetti vs. Strava — quantify divergence in
      cumulative minutes over the 100-mile course profile, not just in curve space
- [ ] Hold out one race file as a test set so the comparison isn't in-sample
- [ ] **Write up Phase 2.** The writeup is the deliverable.

---

## Phase 3 — heat

- [ ] Pull Open-Meteo historical hourly weather by lat/lon + timestamp along the
      course (6/28/2025); cache the response to Parquet so it's not re-fetched
- [ ] Compute wet-bulb from temp + humidity; keep dry-bulb alongside for comparison
- [ ] Add a temperature multiplier on cost, simplest defensible form first
- [ ] Test on the WS canyons specifically (Deadwood → Michigan Bluff, ~2pm)
- [ ] Compare fit with and without the term on held-out data
- [ ] Say so plainly in the writeup if it doesn't improve fit

---

## Phase 4 — front ends

- [ ] Plotly: stacked subplots, shared x-axis — elevation / pace traces /
      residual, scrubbing together. Standalone HTML into the repo.
- [ ] Power BI: bin to aid-station segments or quarter-mile bins *first*
      (3,500-point visual cap), star schema, DAX measures
- [ ] Power BI what-if parameters: target finish time + expected temperature,
      DAX recomputing segment targets live
- [ ] Deneb / Vega-Lite for anything native visuals can't render
- [ ] matplotlib static figures for the writeup
- [ ] `.pbix` in the repo + screen-recorded walkthrough (defer the Pro license
      until there's something worth linking to)

---

## Phase 5 — validation (stretch)

- [ ] Join the model's segment predictions to `stg_wser_splits`
- [ ] Does segment prediction hold across thousands of finishers?
- [ ] Segment residuals by finish-time bucket — does the model break for the
      back of the pack, the front, or both?

---

## Reading

- [ ] Enduraw Transvulcania analysis (Medium) — **read first**, it's the method
- [ ] Enduraw Report API post (Medium) — the environmental layer
- [ ] Minetti et al. 2002 (PubMed, free) — verify the polynomial coefficients
- [ ] Evokecast #125 — Scott Johnston interview, ~71 min
- [ ] Townshend et al. 2014 — downhill damage → late-race pace loss
- [ ] Kipp, Byrnes & Kram 2018 — gait shifts by slope
- [ ] Saugy et al. 2006 — eccentric damage markers by slope
- [ ] Blocken et al. — aero/drafting, low priority for a solo 100M
- [ ] Email Mestrallet — **after** Phase 2 is written up, with a specific
      question about a specific result

---

## Housekeeping

- [ ] One log entry in `pacing_project.md` per working session
- [ ] Keep the framing: "documenting my study of published pacing science,"
      never "reverse-engineering a competitor"

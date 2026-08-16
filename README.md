# WSER Analytics

Analytics for the Western States 100-Mile Endurance Run.

## Interactive dashboard

Covers 2017-2025, the era with a consistent aid-station layout (no race in 2020).

```bash
source venv/bin/activate
python scripts/prep_dashboard_data.py   # rebuild data/processed/ from data/raw/
streamlit run dashboard/app.py
```

Views (filter by year, gender, cohort; spotlight any finisher):

- **The course, painted by pace** — the official GPX elevation profile with each
  aid-station segment colored by the cohort's median pace (a nod to Kirk
  Goldsberry's court-mapped shot charts).
- **Where the race ends** — the profile as a muted silhouette with a bubble at
  each aid station sized by the number of DNFs whose race ended there.
- **Race flow** — bump chart of the top 10's positions through every aid station.
- **Who fades where** — heatmap of segment pace relative to each runner's own
  average, by finish-time bucket.
- **Finish times** — split violins by gender and year against the 24h
  silver-buckle line.

Data sources: official wser.org splits spreadsheets (`data/raw/wser*.xls*`) and
course GPX with aid-station waypoints (`data/raw/WSER2025welev.gpx`).

### Adding a new year (e.g. 2026)

1. Download the splits spreadsheet from wser.org (Results → Splits) and save it
   as `data/raw/wser2026.xlsx` — the filename pattern `wser<year>.xls*` is what
   the prep script looks for.
2. Add the year to the `YEARS` list near the top of
   `scripts/prep_dashboard_data.py`.
3. Re-run `python scripts/prep_dashboard_data.py`. The console prints
   starter/finisher counts per year — sanity-check them against
   wser.org (or `data/wser_year_summary.csv`).
4. Restart the dashboard (or let Streamlit hot-reload). The new year appears
   in the Year dropdown automatically; nothing in `dashboard/app.py` needs
   to change.

Things that can trip up step 3:

- **Column names must match the `STATIONS` dict** in the prep script. If wser
  renames a station or adds/drops one (like Escarpment in 2022), add or adjust
  the entry there — each maps a spreadsheet column name to its official mile.
  A station missing from the dict is silently ignored; a year missing a
  station in the dict is fine.
- **Header row position varies** (2025 had a title row above the headers);
  the script auto-detects it within the first 3 rows.
- **Split cell formats** (`HH:MM:SS`, `arrival-departure` ranges, `--:--`,
  and Excel time/timedelta types) are all handled by `parse_time_to_minutes` —
  if a new format appears, extend that function.
- **Course changes**: the elevation profile comes from the official GPX. If the
  course or aid-station mileages change materially, download the new GPX from
  wser.org/gps-info, update `GPX_FILE` and the miles in `STATIONS`, and
  reconsider whether the new year still belongs in the same comparable era.

---

## Deploying the dashboard

Railway builds the `Dockerfile`, which bakes `data/processed/*.csv` into the
image — so **the live site serves whatever CSVs were committed at build time**.
After changing the prep script, push and redeploy or the dashboard keeps showing
the old numbers.

A newly connected service reports **"unexposed service"** until it has a public
domain: Settings → Networking → Generate Domain. If the dialog asks for a target
port use `8501`, matching the Dockerfile's `EXPOSE`, and set a `PORT=8501`
service variable so Streamlit binds the port the proxy forwards to.

`railway.toml` points the health check at Streamlit's `/_stcore/health` rather
than `/`, which on a cold start can be slow enough to fail the probe and
restart-loop the service.

## Warehouse and dbt

DuckDB, in a single file at `data/wser.duckdb`. The dataset is ~11k finisher
rows and the whole pipeline is local, so a file-based database keeps the repo
clone-and-run with no credentials to manage. `profiles.yml` lives in the repo
root with a relative path — dbt reads the working directory before `~/.dbt`, so
running dbt from the repo root picks it up automatically. Model SQL is kept
ANSI-plain so the profile is the only thing that changes if this ever needs a
real warehouse.

**The database is derived data and is not committed.** Rebuild it:

```bash
source venv/bin/activate
python scripts/prep_dashboard_data.py   # data/raw/*.xls* -> data/processed/*.csv
python scripts/build_db.py              # CSVs -> data/wser.duckdb
dbt debug                               # confirm the connection
```

Two upstream paths feed the database:

| Table(s) | Source |
|---|---|
| `wser_results`, `wser_year_summary` | scraped from wser.org by `01_scrape_and_explore.ipynb`; its CSV output is committed, so rebuilds run offline |
| `runners`, `splits`, `aid_stations`, `course_profile` | parsed from `data/raw/` by `prep_dashboard_data.py` |

Only the scrape needs the network, and it only needs re-running when a new race
year is published.

### Models

```bash
dbt deps && dbt build     # builds the staging layer and runs every test
```

| Model | Grain | Coverage |
|---|---|---|
| `stg_wser_results` | one finisher per year | 1974–2025, 11,046 rows |
| `stg_wser_runners` | one starter per year, DNFs included | 2017–2025, 2,928 rows |
| `stg_wser_splits` | one runner per aid station reached | 2017–2025, 52,131 rows |
| `stg_wser_aid_stations` | one station | 24 rows |
| `fct_finisher_trends` | one race year | 49 rows |
| `fct_sub_24_rates` | race year × gender | |
| `fct_age_group_performance` | race year × age group × gender | |
| `dim_runner_careers` | one runner, whole history | 6,958 rows |

`stg_wser_results` is the long history; `stg_wser_runners` is richer (bib,
hometown, DNFs, seconds-precision times) but only covers the consistent
aid-station era. They come from different sources, so two singular tests in
`tests/` hold them to each other and to wser.org's own published counts.

Quirks the staging layer handles, all of them real:

- **Ties.** Runners finishing together share a place, so `(year, place)` is not
  unique — it repeats 203 times, heavily in 1981–84. Places then skip, so the
  last place still equals the finisher count.
- **Two Paul Schmidts** both finished in 2000, ages 48 and 42, so `(year, name)`
  is not unique either. The surrogate key adds finish time.
- **Over-cutoff finishers.** A handful of runners are recorded past 30 hours
  with no place; `is_official_finish` flags them.
- **Gender** is reported five ways (`M`, `F`, `NB (M)`, ` NB(F)`, ` M (X)`) and
  is normalised to M/F/NB, with the raw string kept.
- **Name changes.** Meghan Arbogast and Meghan Canfield are one runner. Never
  join the two sources on name.
- **1975, 2008 and 2020 are absent** because no race was held.

### Runner identity

`dim_runner_careers` resolves a runner's identity **on name alone**. That is a
deliberate simplification for this project, and it is wrong in both directions:
a runner who changes surname splits into two careers (Meghan Arbogast and
Meghan Canfield are one person, 1 finish and 12), and two people sharing a name
merge into one (the two Paul Schmidts of 2000, aged 48 and 42).

The model measures the damage instead of hiding it. `has_identity_conflict` is
true where a career's implied birth year — race year minus age — moves by more
than two years, or where a "runner" finished twice in one June, which is proof
rather than suspicion. **46 of 6,958 careers are flagged, all of them
multi-finishers**, so roughly 2.5% of multi-finish careers are suspect. Exclude
flagged rows from any "most finishes" ranking.

Sanity check on the unflagged data: Tim Twietmeyer shows 25 finishes, all 25
under 24 hours, which is his actual record.

### Resources:
- Learn more about dbt [in the docs](https://docs.getdbt.com/docs/introduction)
- Check out [Discourse](https://discourse.getdbt.com/) for commonly asked questions and answers
- Join the [chat](https://community.getdbt.com/) on Slack for live discussions and support
- Find [dbt events](https://events.getdbt.com) near you
- Check out [the blog](https://blog.getdbt.com/) for the latest news on dbt's development and best practices

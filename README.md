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

Welcome to your new dbt project!

### Using the starter project

Try running the following commands:
- dbt run
- dbt test


### Resources:
- Learn more about dbt [in the docs](https://docs.getdbt.com/docs/introduction)
- Check out [Discourse](https://discourse.getdbt.com/) for commonly asked questions and answers
- Join the [chat](https://community.getdbt.com/) on Slack for live discussions and support
- Find [dbt events](https://events.getdbt.com) near you
- Check out [the blog](https://blog.getdbt.com/) for the latest news on dbt's development and best practices

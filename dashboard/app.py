"""WSER 100 interactive analytics dashboard.

Run with:  streamlit run dashboard/app.py

Data comes from the dbt staging models in data/wser.duckdb, which is built by
scripts/build_db.py and `dbt build`. Covers 2017-2025, the era with a consistent
aid-station layout.
"""

import duckdb
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "wser.duckdb"

GOLD = "#C9A227"
DARK = "#2B2118"
# celadon green (fast) -> cream -> burnt orange (slow)
PACE_SCALE = [
    [0.0, "#69A077"],
    [0.3, "#A9C9A4"],
    [0.55, "#EFE6CD"],
    [0.78, "#C97B3D"],
    [1.0, "#8F3E14"],
]

st.set_page_config(page_title="WSER 100 Analytics", page_icon="🏔️", layout="wide")


# ---------------------------------------------------------------- data


@st.cache_data
def load_data():
    """Read the dbt staging models out of DuckDB.

    Columns are aliased back to the names the rest of this module already uses,
    so the dbt layer is the single source of truth without the plotting code
    needing to know about it.
    """
    if not DB.exists():
        st.error(
            f"No database at {DB}. Build it with:\n\n"
            "    python scripts/prep_dashboard_data.py\n"
            "    python scripts/build_db.py\n"
            "    dbt build"
        )
        st.stop()

    con = duckdb.connect(str(DB), read_only=True)
    try:
        profile = con.execute("""
            select mile, elevation_ft, lat, lon
            from stg_wser_course_profile
            order by mile
        """).df()

        stations = con.execute("""
            select
                station_name as station,
                station_mile as mile,
                cutoff_hours,
                elevation_ft
            from stg_wser_aid_stations
            order by station_order
        """).df()

        runners = con.execute("""
            select
                runner_id,
                race_year       as year,
                bib,
                first_name,
                last_name,
                runner_name     as name,
                gender,
                cast(age as bigint)            as age,
                city,
                state,
                country,
                finish_minutes                 as finish_min,
                is_finisher                    as finished,
                -- Cast to double so missing places arrive as NaN rather than
                -- pandas' nullable pd.NA, which does not behave the same in the
                -- numpy comparisons downstream.
                cast(overall_place as double)  as overall_place,
                cast(gender_place as double)   as gender_place
            from stg_wser_runners
        """).df()

        splits = con.execute("""
            select
                runner_id,
                race_year       as year,
                station_name    as station,
                station_mile    as mile,
                elapsed_minutes as elapsed_min
            from stg_wser_splits
        """).df()
    finally:
        con.close()

    return profile, stations, runners, splits


@st.cache_data
def segment_paces(splits: pd.DataFrame, station_miles: tuple) -> pd.DataFrame:
    """Per-runner pace (min/mi) over each canonical mini-segment.

    A runner's pace between their consecutive *recorded* stations is
    projected onto every canonical inter-station segment it spans, so
    sparsely timed stations (No Hands, Cal-1/3) don't punch holes in
    the profile.
    """
    miles = np.array(station_miles)
    s = splits.sort_values(["runner_id", "mile"])
    # prepend a virtual Start (mile 0, elapsed 0) per runner
    starts = s.groupby("runner_id", as_index=False).first()
    starts[["mile", "elapsed_min"]] = 0.0
    s = (pd.concat([s, starts])
           .sort_values(["runner_id", "mile"])
           .drop_duplicates(["runner_id", "mile"]))

    g = s.groupby("runner_id")
    s["prev_mile"] = g["mile"].shift()
    s["prev_elapsed"] = g["elapsed_min"].shift()
    s = s.dropna(subset=["prev_mile"])
    s = s[s["mile"] > s["prev_mile"]]
    s["pace"] = (s["elapsed_min"] - s["prev_elapsed"]) / (s["mile"] - s["prev_mile"])
    s = s[(s["pace"] > 4) & (s["pace"] < 120)]  # drop timing glitches

    rows = []
    seg_start, seg_end = miles[:-1], miles[1:]
    for r in s.itertuples():
        covered = np.where((seg_start >= r.prev_mile - 1e-9)
                           & (seg_end <= r.mile + 1e-9))[0]
        for i in covered:
            rows.append((r.runner_id, r.year, i, r.pace))
    return pd.DataFrame(rows, columns=["runner_id", "year", "seg_idx", "pace"])


@st.cache_data
def segment_cost_factors(profile: pd.DataFrame, station_miles: tuple) -> np.ndarray:
    """Energy cost of each canonical segment relative to flat running.

    Minetti et al. (2002) cost of running at gradient i (J/kg/m), integrated
    over the GPX profile within the segment so rolling terrain costs more
    than its net grade suggests. Factor 1.0 = flat-equivalent.
    """
    def minetti(i):
        return (155.4 * i**5 - 30.4 * i**4 - 43.3 * i**3
                + 46.3 * i**2 + 19.5 * i + 3.6)

    miles = np.array(station_miles)
    p = profile.sort_values("mile")
    x_m = p["mile"].to_numpy() * 1609.34
    e_m = p["elevation_ft"].to_numpy() * 0.3048
    dx, de = np.diff(x_m), np.diff(e_m)
    ok = dx > 1
    grade = np.zeros_like(dx)
    grade[ok] = np.clip(de[ok] / dx[ok], -0.45, 0.45)  # Minetti's tested range
    cost = minetti(grade)
    mid_mile = (p["mile"].to_numpy()[1:] + p["mile"].to_numpy()[:-1]) / 2

    factors = np.ones(len(miles) - 1)
    for i in range(len(miles) - 1):
        m = (mid_mile >= miles[i]) & (mid_mile < miles[i + 1])
        if m.any():
            factors[i] = np.average(cost[m], weights=dx[m]) / minetti(0.0)
    return factors


def fmt_hm(minutes):
    if pd.isna(minutes):
        return "—"
    h, m = divmod(int(round(minutes)), 60)
    return f"{h}:{m:02d}"


profile, stations, runners, splits = load_data()
station_miles = tuple(stations["mile"])
seg_paces = segment_paces(splits, station_miles)

# ---------------------------------------------------------------- sidebar

st.sidebar.title("🏔️ WSER 100")
st.sidebar.caption(
    "Olympic Valley → Auburn · 100.2 miles · 18k ft up, 23k ft down. "
    "Years 2017-2025: the consistent aid-station era."
)

years = sorted(runners["year"].unique())
year_sel = st.sidebar.selectbox("Year", ["All years"] + [str(y) for y in years],
                                index=0)
gender_sel = st.sidebar.radio("Gender", ["All", "Women", "Men"], horizontal=True)
cohort_sel = st.sidebar.selectbox(
    "Cohort",
    ["All finishers", "Silver buckle (sub-24h)", "Bronze buckle (24-30h)",
     "Top 10 overall", "Everyone (incl. DNF)"],
)

mask = pd.Series(True, index=runners.index)
if year_sel != "All years":
    mask &= runners["year"] == int(year_sel)
if gender_sel != "All":
    mask &= runners["gender"] == ("F" if gender_sel == "Women" else "M")
starters_mask = mask.copy()  # year/gender only, for finish-rate denominator
if cohort_sel == "Silver buckle (sub-24h)":
    mask &= runners["finish_min"] < 24 * 60
elif cohort_sel == "Bronze buckle (24-30h)":
    mask &= runners["finish_min"] >= 24 * 60
elif cohort_sel == "Top 10 overall":
    mask &= runners["overall_place"] <= 10
elif cohort_sel != "Everyone (incl. DNF)":
    mask &= runners["finished"]

cohort = runners[mask]
cohort_ids = set(cohort["runner_id"])

spotlight_pool = cohort[cohort["finished"]].sort_values(["year", "overall_place"])
labels = {
    rid: f"{name} · {yr} · P{int(pl)}"
    for rid, name, yr, pl in zip(spotlight_pool["runner_id"], spotlight_pool["name"],
                                 spotlight_pool["year"], spotlight_pool["overall_place"])
}
spot_sel = st.sidebar.selectbox("🔦 Runner spotlight",
                                ["None"] + list(labels.values()))
spot_id = next((rid for rid, lab in labels.items() if lab == spot_sel), None)

st.sidebar.markdown("---")
st.sidebar.caption(
    "Inspired by Kirk Goldsberry's court-mapped shot charts: the race's "
    "key stat (pace) is painted directly onto its geography (the course)."
)

# ---------------------------------------------------------------- header

title_year = year_sel if year_sel != "All years" else "2017–2025"
st.title(f"Western States 100 · {title_year}")

k = st.columns(5)
fin = cohort[cohort["finished"]]
starters = runners[starters_mask]
k[0].metric("Cohort size", len(cohort))
k[1].metric("Finishers / starters",
            f"{int(starters['finished'].sum())} / {len(starters)}")
k[2].metric("Finish rate",
            f"{starters['finished'].sum() / max(len(starters), 1):.0%}")
k[3].metric("Sub-24 (silver)", int((fin["finish_min"] < 1440).sum()))
k[4].metric("Fastest", fmt_hm(fin["finish_min"].min()))

# ---------------------------------------------------------------- 1. course heat map

st.subheader("The course, painted by pace")
st.caption(
    "Median pace of the selected cohort over each aid-station segment, "
    "mapped onto the elevation profile — celadon green is fast, "
    "burnt orange is a grind. Hover the gold diamonds for aid-station detail."
)

seg = (seg_paces[seg_paces["runner_id"].isin(cohort_ids)]
       .groupby("seg_idx")["pace"].median())

fig = go.Figure()
smiles = stations["mile"].to_numpy()
vmin, vmax = seg.quantile(0.05), seg.quantile(0.95)
for i in range(len(smiles) - 1):
    m = (profile["mile"] >= smiles[i]) & (profile["mile"] <= smiles[i + 1])
    chunk = profile[m]
    if chunk.empty:
        continue
    pace = seg.get(i, np.nan)
    if pd.notna(pace):
        frac = float(np.clip((pace - vmin) / max(vmax - vmin, 1e-9), 0, 1))
        color = px.colors.sample_colorscale(PACE_SCALE, [frac])[0]
    else:
        color = "#cccccc"
    fig.add_trace(go.Scatter(
        x=chunk["mile"], y=chunk["elevation_ft"],
        fill="tozeroy", mode="lines",
        line=dict(color=color, width=0.6), fillcolor=color,
        name="", showlegend=False, hoverinfo="skip",
    ))
    mid = chunk.iloc[len(chunk) // 2]
    fig.add_trace(go.Scatter(
        x=[mid["mile"]], y=[mid["elevation_ft"] / 2],
        mode="markers", marker=dict(size=28, opacity=0),
        showlegend=False,
        hovertemplate=(
            f"<b>{stations.iloc[i]['station']} → {stations.iloc[i + 1]['station']}</b>"
            f"<br>miles {smiles[i]:.1f}–{smiles[i + 1]:.1f}"
            f"<br>median pace: {pace:.1f} min/mi<extra></extra>"
            if pd.notna(pace) else "no split data<extra></extra>"
        ),
    ))

# cohort median arrival per station for hover
arr = (splits[splits["runner_id"].isin(cohort_ids)]
       .groupby("station")["elapsed_min"].median())
fig.add_trace(go.Scatter(
    x=stations["mile"], y=stations["elevation_ft"],
    mode="markers+text",
    marker=dict(symbol="diamond", size=9, color=GOLD,
                line=dict(color=DARK, width=1)),
    text=[s if s in ("Escarpment", "Robinson Flat", "Devil's Thumb", "Foresthill",
                     "Rucky Chucky", "Finish") else ""
          for s in stations["station"]],
    textposition="top center", textfont=dict(size=10, color=DARK),
    customdata=np.stack([
        stations["station"],
        stations["elevation_ft"].round(0),
        [fmt_hm(arr.get(s, np.nan)) for s in stations["station"]],
        [f"{c:.1f}h" if pd.notna(c) else "—" for c in stations["cutoff_hours"]],
    ], axis=-1),
    hovertemplate=("<b>%{customdata[0]}</b><br>mile %{x:.1f} · %{customdata[1]} ft"
                   "<br>cohort median arrival: %{customdata[2]}"
                   "<br>cutoff: %{customdata[3]}<extra></extra>"),
    showlegend=False,
))

if spot_id:
    sp = splits[splits["runner_id"] == spot_id].merge(
        stations[["station", "elevation_ft"]], on="station")
    fig.add_trace(go.Scatter(
        x=sp["mile"], y=sp["elevation_ft"] + 400,
        mode="markers", marker=dict(symbol="star", size=11, color="#5B2A86"),
        name=spot_sel.split(" · ")[0],
        customdata=[fmt_hm(t) for t in sp["elapsed_min"]],
        hovertemplate="<b>%{text}</b> %{customdata}<extra></extra>",
        text=sp["station"],
    ))
    fig.update_layout(legend=dict(orientation="h", y=1.08))

fig.update_layout(
    height=420, template="plotly_white",
    margin=dict(l=10, r=10, t=30, b=10),
    xaxis=dict(title="Miles", range=[0, 101], showgrid=False),
    yaxis=dict(title="Elevation (ft)", range=[0, 9500]),
)
st.plotly_chart(fig, width='stretch')

# colorbar legend
lg = go.Figure(go.Scatter(
    x=[None], y=[None], mode="markers",
    marker=dict(colorscale=PACE_SCALE, cmin=vmin, cmax=vmax, color=[vmin],
                colorbar=dict(orientation="h", thickness=10, y=0.5,
                              title="median pace (min/mi)"), size=0.1),
))
lg.update_layout(height=90, template="plotly_white",
                 xaxis=dict(visible=False), yaxis=dict(visible=False),
                 margin=dict(l=80, r=80, t=0, b=0))
st.plotly_chart(lg, width='stretch')

# ---------------------------------------------------------------- 1b. GAP map

st.subheader("Same course, repainted as effort")
st.caption(
    "Grade-adjusted pace: each segment's median pace divided by the energy "
    "cost of its terrain (Minetti et al. 2002 — the published physiology "
    "model that tools like Strava GAP approximate), integrated over the GPX "
    "rather than net grade. Same color scale as above, so segments that stay "
    "burnt orange are slow beyond what the terrain explains — heat, "
    "altitude, and accumulated fatigue. Altitude is not adjusted for."
)

factors = segment_cost_factors(profile, station_miles)
gapfig = go.Figure()
for i in range(len(smiles) - 1):
    m = (profile["mile"] >= smiles[i]) & (profile["mile"] <= smiles[i + 1])
    chunk = profile[m]
    if chunk.empty:
        continue
    raw = seg.get(i, np.nan)
    gap = raw / factors[i] if pd.notna(raw) else np.nan
    if pd.notna(gap):
        frac = float(np.clip((gap - vmin) / max(vmax - vmin, 1e-9), 0, 1))
        color = px.colors.sample_colorscale(PACE_SCALE, [frac])[0]
    else:
        color = "#cccccc"
    gapfig.add_trace(go.Scatter(
        x=chunk["mile"], y=chunk["elevation_ft"],
        fill="tozeroy", mode="lines",
        line=dict(color=color, width=0.6), fillcolor=color,
        name="", showlegend=False, hoverinfo="skip",
    ))
    mid = chunk.iloc[len(chunk) // 2]
    gapfig.add_trace(go.Scatter(
        x=[mid["mile"]], y=[mid["elevation_ft"] / 2],
        mode="markers", marker=dict(size=28, opacity=0),
        showlegend=False,
        hovertemplate=(
            f"<b>{stations.iloc[i]['station']} → {stations.iloc[i + 1]['station']}</b>"
            f"<br>raw pace: {raw:.1f} min/mi"
            f"<br>grade-adjusted: {gap:.1f} min/mi"
            f"<br>terrain cost: {factors[i]:.2f}× flat<extra></extra>"
            if pd.notna(gap) else "no split data<extra></extra>"
        ),
    ))
gapfig.update_layout(
    height=380, template="plotly_white",
    margin=dict(l=10, r=10, t=10, b=10),
    xaxis=dict(title="Miles", range=[0, 101], showgrid=False),
    yaxis=dict(title="Elevation (ft)", range=[0, 9500]),
)
st.plotly_chart(gapfig, width='stretch')

# ---------------------------------------------------------------- 1c. drop map

st.subheader("Where the race ends")
st.caption(
    "Every DNF, placed at the first aid station the runner never reached — "
    "bubble area scales with the number of drops. Filtered by year and "
    "gender (drops are independent of the finish cohort)."
)

dnf = runners[starters_mask & ~runners["finished"]]
dnf_splits = splits[splits["runner_id"].isin(set(dnf["runner_id"]))]
last_mile = dnf_splits.groupby("runner_id")["mile"].max()

# stations actually timed in each year, in course order
timed = (splits[["year", "station", "mile"]].drop_duplicates()
         .sort_values("mile"))
timed_by_year = {y: list(zip(g["mile"], g["station"]))
                 for y, g in timed.groupby("year")}


def first_unreached(rid, year):
    lm = last_mile.get(rid, -1.0)
    for mile, station in timed_by_year[year]:
        if mile > lm:
            return station
    return "Finish"  # split at the line but no official time (over cutoff)


drop_counts = pd.Series(
    [first_unreached(r, y) for r, y in zip(dnf["runner_id"], dnf["year"])]
).value_counts()

drops = stations.merge(drop_counts.rename("drops"), left_on="station",
                       right_index=True)
drops = drops[drops["drops"] > 0]

dropfig = go.Figure()
dropfig.add_trace(go.Scatter(
    x=profile["mile"], y=profile["elevation_ft"],
    fill="tozeroy", mode="lines",
    line=dict(color="#B8B2A2", width=1), fillcolor="#E7E2D4",
    hoverinfo="skip", showlegend=False,
))
dropfig.add_trace(go.Scatter(
    x=drops["mile"], y=drops["elevation_ft"] + 300,
    mode="markers",
    marker=dict(
        size=drops["drops"], sizemode="area",
        sizeref=2.0 * drops["drops"].max() / (46 ** 2), sizemin=4,
        color="#8F3E14", opacity=0.75,
        line=dict(color="#5C2A0E", width=1),
    ),
    customdata=np.stack([
        drops["station"],
        drops["drops"],
        (100 * drops["drops"] / max(len(dnf), 1)).round(1),
    ], axis=-1),
    hovertemplate=("<b>%{customdata[0]}</b> · mile %{x:.1f}"
                   "<br>%{customdata[1]} drops "
                   "(%{customdata[2]}% of all DNFs)<extra></extra>"),
    showlegend=False,
))
dropfig.update_layout(
    height=380, template="plotly_white",
    margin=dict(l=10, r=10, t=10, b=10),
    xaxis=dict(title="Miles", range=[0, 101], showgrid=False),
    yaxis=dict(title="Elevation (ft)", range=[0, 9500]),
)
st.plotly_chart(dropfig, width='stretch')
st.caption(
    f"{len(dnf)} DNFs in the current selection. A drop is charged to the "
    "first timed station after the runner's last recorded split — e.g. a "
    "runner last seen at Last Chance counts at Devil's Thumb, covering the "
    "canyon in between. Runners with no recorded splits count at the first "
    "timed station; a bubble at the Finish means a split at the line but "
    "no official finish (over the 30-hour cutoff)."
)

# ---------------------------------------------------------------- 2 + 3

left, right = st.columns(2)

with left:
    bump_year = int(year_sel) if year_sel != "All years" else years[-1]
    st.subheader(f"Race flow · top 10 of {bump_year}")
    st.caption("Position at each aid station among the year's finishers — "
               "watch moves made in the canyons and on Cal Street.")
    yr_fin = runners[(runners["year"] == bump_year) & runners["finished"]]
    if gender_sel != "All":
        yr_fin = yr_fin[yr_fin["gender"] == ("F" if gender_sel == "Women" else "M")]
    yr_splits = splits[splits["runner_id"].isin(set(yr_fin["runner_id"]))].copy()
    yr_splits["rank"] = yr_splits.groupby("station")["elapsed_min"].rank("min")
    top10 = yr_fin.nsmallest(10, "finish_min")

    bump = go.Figure()
    for _, rr in top10.iterrows():
        d = (yr_splits[yr_splits["runner_id"] == rr["runner_id"]]
             .sort_values("mile"))
        d = d[d["station"] != "No Hands Bridge"]
        bump.add_trace(go.Scatter(
            x=d["mile"], y=d["rank"], mode="lines+markers",
            name=rr["name"], line=dict(width=2), marker=dict(size=5),
            customdata=np.stack([d["station"],
                                 [fmt_hm(t) for t in d["elapsed_min"]]], axis=-1),
            hovertemplate=(f"<b>{rr['name']}</b><br>%{{customdata[0]}}"
                           "<br>position %{y:.0f} · %{customdata[1]}<extra></extra>"),
        ))
    bump.update_layout(
        height=430, template="plotly_white",
        xaxis=dict(title="Miles", range=[0, 101]),
        yaxis=dict(title="Position", autorange="reversed", dtick=2,
                   range=[25, 0.5]),
        legend=dict(font=dict(size=10)),
        margin=dict(l=10, r=10, t=10, b=10),
    )
    st.plotly_chart(bump, width='stretch')

with right:
    st.subheader("Who fades where")
    st.caption("Each runner's segment pace vs their own race average "
               "(cohort medians). Blue = banking time early; "
               "red = the canyons collecting their toll.")
    sp = seg_paces[seg_paces["runner_id"].isin(cohort_ids)].copy()
    avg = sp.groupby("runner_id")["pace"].transform("mean")
    sp["rel"] = sp["pace"] / avg
    fb = runners.set_index("runner_id")["finish_min"]
    sp["bucket"] = pd.cut(sp["runner_id"].map(fb) / 60,
                          bins=[14, 18, 20, 22, 24, 26, 28, 30],
                          labels=["<18h", "18-20", "20-22", "22-24",
                                  "24-26", "26-28", "28-30"])
    hm = sp.pivot_table(index="bucket", columns="seg_idx", values="rel",
                        aggfunc="median", observed=True)
    seg_labels = [f"{stations.iloc[i]['station']}→" for i in hm.columns]
    heat = go.Figure(go.Heatmap(
        z=hm.values, x=seg_labels, y=hm.index.astype(str),
        colorscale="RdBu_r", zmid=1.0, zmin=0.5, zmax=1.5,
        colorbar=dict(title="pace ÷ own avg", thickness=12),
        hovertemplate=("finish %{y}h · %{x}: %{z:.2f}× own average"
                       "<extra></extra>"),
    ))
    heat.update_layout(
        height=430, template="plotly_white",
        xaxis=dict(tickfont=dict(size=8)),
        yaxis=dict(title="Finish time"),
        margin=dict(l=10, r=10, t=10, b=10),
    )
    st.plotly_chart(heat, width='stretch')

# ---------------------------------------------------------------- 4. distributions

st.subheader("Finish times")
st.caption("Every finish in the selected cohort. The dashed line is the "
           "silver-buckle standard (24h); the race closes at 30h.")

dist = go.Figure()
fin_all = runners[mask & runners["finished"]]
colors = {"F": "#D1495B", "M": "#30638E"}
for g, label in [("F", "Women"), ("M", "Men")]:
    d = fin_all[fin_all["gender"] == g]
    if d.empty:
        continue
    dist.add_trace(go.Violin(
        x=d["year"].astype(str), y=d["finish_min"] / 60,
        side="negative" if g == "M" else "positive",
        line_color=colors[g], name=label, points=False,
        spanmode="hard", meanline_visible=True, width=1.6,
    ))
dist.add_hline(y=24, line_dash="dash", line_color=GOLD,
               annotation_text="silver buckle", annotation_font_color=GOLD)
dist.add_hline(y=30, line_color="#999", line_width=1)
dist.update_layout(
    height=380, template="plotly_white", violinmode="overlay",
    yaxis=dict(title="Finish time (hours)", range=[13.5, 31]),
    xaxis=dict(title=""),
    legend=dict(orientation="h", y=1.1),
    margin=dict(l=10, r=10, t=10, b=10),
)
st.plotly_chart(dist, width='stretch')

if spot_id:
    r = runners[runners["runner_id"] == spot_id].iloc[0]
    st.info(f"🔦 **{r['name']}** ({int(r['year'])}) — finished "
            f"**{fmt_hm(r['finish_min'])}**, P{int(r['overall_place'])} overall, "
            f"P{int(r['gender_place'])} {('woman' if r['gender'] == 'F' else 'man')}, "
            f"age {int(r['age'])}, from {r['city']}, {r['state']}.")

st.caption("Data: wser.org official splits 2017-2025 (no race in 2020) and "
           "the official course GPX. Aid-station layout is consistent across "
           "these years; No Hands Bridge is rarely timed and is bridged "
           "through neighboring stations.")

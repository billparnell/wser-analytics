"""Prepare WSER dashboard data.

Reads the official course GPX and the 2017-2025 splits spreadsheets
(the era with a consistent aid-station layout) and writes tidy CSVs to
data/processed/ for the Streamlit/Plotly dashboard.

Usage: python scripts/prep_dashboard_data.py

To add a new year, drop wser<year>.xlsx into data/raw/, add the year to
YEARS below, and re-run. See README "Adding a new year" for details.
"""

import datetime as dt
import re
import warnings
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"

GPX_FILE = RAW / "WSER2025welev.gpx"
YEARS = [2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025]

# Canonical stations: name in splits files -> (official mile, GPX waypoint match)
STATIONS = {
    "Start": (0.0, "Olympic Valley"),
    "Escarpment": (3.5, None),  # no GPX waypoint; elevation read off profile
    "Lyon Ridge": (10.3, "Lyon Ridge"),
    "Red Star Ridge": (15.8, "Red Star"),
    "Duncan Canyon": (24.4, "Duncan Canyon"),
    "Robinson Flat": (30.3, "Robinson Flat"),
    "Miller's Defeat": (34.4, "Miller"),
    "Dusty Corners": (38.0, "Dusty Corners"),
    "Last Chance": (43.3, "Last Chance"),
    "Devil's Thumb": (47.8, "Devil"),
    "El Dorado Creek": (52.9, "El Dorado"),
    "Michigan Bluff": (55.7, "Michigan Bluff"),
    "Foresthill": (62.0, "Foresthill"),
    "Dardanelles (Cal-1)": (65.7, "Dardanelles"),
    "Peachstone (Cal-2)": (70.7, "Peachstone"),
    "Ford's Bar (Cal-3)": (73.0, "Ford"),
    "Rucky Chucky": (78.0, "Rucky Chucky"),
    "Green Gate": (79.8, "Green Gate"),
    "Auburn Lake Trails": (85.2, "Auburn Lake"),
    "Quarry Road": (90.7, "Quarry"),
    "Pointed Rocks": (94.3, "Pointed Rocks"),
    "No Hands Bridge": (96.8, None),  # no GPX waypoint
    "Robie Point": (98.9, "Robie Point"),
    "Finish": (100.2, "Placer HS"),
}

# Official cutoffs as hours elapsed from the 5:00am start (30h race).
CUTOFF_HOURS = {
    "Lyon Ridge": 5.5, "Red Star Ridge": 5.5, "Duncan Canyon": 7.5,
    "Robinson Flat": 9.17, "Miller's Defeat": 10.25, "Dusty Corners": 11.08,
    "Last Chance": 12.42, "Devil's Thumb": 14.17, "El Dorado Creek": 15.67,
    "Michigan Bluff": 16.92, "Foresthill": 18.75, "Dardanelles (Cal-1)": 21.67,
    "Peachstone (Cal-2)": 21.67, "Ford's Bar (Cal-3)": 24.0,
    "Rucky Chucky": 24.0, "Green Gate": 24.83, "Auburn Lake Trails": 26.25,
    "Quarry Road": 27.67, "Pointed Rocks": 28.67, "Robie Point": 30.0,
    "Finish": 30.0,
}

NS = {"gpx": "http://www.topografix.com/GPX/1/1"}


def haversine_miles(lat1, lon1, lat2, lon2):
    r = 3958.8
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    a = (np.sin((lat2 - lat1) / 2) ** 2
         + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2)
    return 2 * r * np.arcsin(np.sqrt(a))


def parse_gpx():
    root = ET.parse(GPX_FILE).getroot()

    pts = root.findall(".//gpx:trkpt", NS)
    lat = np.array([float(p.get("lat")) for p in pts])
    lon = np.array([float(p.get("lon")) for p in pts])
    ele_ft = np.array([float(p.find("gpx:ele", NS).text) for p in pts]) * 3.28084

    dist = np.zeros(len(lat))
    dist[1:] = np.cumsum(haversine_miles(lat[:-1], lon[:-1], lat[1:], lon[1:]))

    # Locate each waypoint's position along the track
    wpt_rows = []
    for w in root.findall("gpx:wpt", NS):
        wlat, wlon = float(w.get("lat")), float(w.get("lon"))
        name = w.find("gpx:name", NS).text
        e = w.find("gpx:ele", NS)
        wele = float(e.text) * 3.28084 if e is not None else np.nan
        i = np.argmin(haversine_miles(lat, lon, wlat, wlon))
        wpt_rows.append({"gpx_name": name, "ele_ft": wele, "track_mile": dist[i]})
    wpts = pd.DataFrame(wpt_rows)

    # Match canonical stations to GPX waypoints
    station_rows = []
    for station, (official_mile, pat) in STATIONS.items():
        row = {"station": station, "mile": official_mile,
               "cutoff_hours": CUTOFF_HOURS.get(station, np.nan)}
        if pat is not None:
            m = wpts[wpts.gpx_name.str.contains(pat, case=False, regex=False)]
            if len(m) == 0:
                raise ValueError(f"No GPX waypoint match for {station} ({pat})")
            m = m.iloc[0]
            row["elevation_ft"] = m.ele_ft
            row["track_mile"] = m.track_mile
        else:
            row["elevation_ft"] = np.nan  # filled from warped profile below
            row["track_mile"] = np.nan
        station_rows.append(row)
    stations = pd.DataFrame(station_rows).sort_values("mile").reset_index(drop=True)

    # Piecewise-linearly warp track distance so each aid station sits at
    # its official mile (GPS track length never matches course markings).
    anchored = stations.dropna(subset=["track_mile"])
    anchors_track = anchored.track_mile.to_numpy()
    anchors_official = anchored.mile.to_numpy()
    if dist[-1] > anchors_track[-1]:
        anchors_track = np.append(anchors_track, dist[-1])
        anchors_official = np.append(anchors_official, anchors_official[-1])
    warped = np.interp(dist, anchors_track, anchors_official)

    profile = pd.DataFrame({"mile": warped, "elevation_ft": ele_ft,
                            "lat": lat, "lon": lon})

    # Stations without a GPX waypoint: read elevation off the warped profile
    missing = stations.elevation_ft.isna()
    stations.loc[missing, "elevation_ft"] = np.interp(
        stations.loc[missing, "mile"], warped, ele_ft)
    # Light downsample to keep the dashboard payload small
    profile = profile.iloc[:: max(1, len(profile) // 2500)].reset_index(drop=True)
    return profile, stations.drop(columns="track_mile")


def parse_time_to_minutes(val):
    """Elapsed minutes from a split cell.

    Cells arrive as datetime.time (<24h), datetime.timedelta (>=24h), or
    strings like '13:48:00', '13:48:00-13:49:00' (in-out: take arrival),
    '--:--' (missing).
    """
    if pd.isna(val):
        return np.nan
    if isinstance(val, dt.timedelta):
        return val.total_seconds() / 60
    if isinstance(val, dt.time):
        return val.hour * 60 + val.minute + val.second / 60
    if isinstance(val, dt.datetime):  # excel sometimes promotes to datetime
        base = dt.datetime(val.year, val.month, val.day)
        days = (base - dt.datetime(1899, 12, 31)).days
        return days * 1440 + val.hour * 60 + val.minute + val.second / 60
    s = str(val).strip()
    if not s or s.startswith("--"):
        return np.nan
    s = s.split("-")[0].strip()  # in-out range: take arrival
    m = re.match(r"^(\d+):(\d{2})(?::(\d{2}))?$", s)
    if not m:
        return np.nan
    h, mi, sec = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    return h * 60 + mi + sec / 60


def find_header_row(path):
    peek = pd.read_excel(path, nrows=3, header=None)
    for i in range(3):
        if any("Name" in str(v) for v in peek.iloc[i]):
            return i
    raise ValueError(f"No header row found in {path}")


def parse_splits():
    runners, splits = [], []
    for year in YEARS:
        path = next(RAW.glob(f"wser{year}.xls*"))
        df = pd.read_excel(path, header=find_header_row(path))

        station_cols = [c for c in df.columns if c in STATIONS and c != "Start"]
        for _, r in df.iterrows():
            rid = f"{year}-{r['Bib']}"
            finish_min = parse_time_to_minutes(r.get("Time"))
            runners.append({
                "runner_id": rid, "year": year, "bib": str(r["Bib"]),
                "first_name": r["First Name"], "last_name": r["Last Name"],
                "name": f"{r['First Name']} {r['Last Name']}",
                "gender": r["Gender"], "age": r.get("Age"),
                "city": r.get("City"), "state": r.get("State"),
                "country": r.get("Country"),
                "finish_min": finish_min,
                "finished": pd.notna(finish_min),
            })
            for st in station_cols:
                t = parse_time_to_minutes(r[st])
                if pd.notna(t):
                    splits.append({"runner_id": rid, "year": year,
                                   "station": st, "mile": STATIONS[st][0],
                                   "elapsed_min": t})

    runners = pd.DataFrame(runners)
    splits = pd.DataFrame(splits)

    # Recompute gender place among finishers
    fin = runners[runners.finished]
    runners["overall_place"] = fin.groupby("year").finish_min.rank("first")
    runners["gender_place"] = fin.groupby(["year", "gender"]).finish_min.rank("first")

    # Sanity: finish split should equal finish time where both exist
    chk = splits[splits.station == "Finish"].merge(
        runners[["runner_id", "finish_min"]], on="runner_id")
    bad = (chk.elapsed_min - chk.finish_min).abs() > 1
    if bad.mean() > 0.01:
        print(f"WARNING: {bad.sum()} finish-split mismatches")

    return runners, splits


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    profile, stations = parse_gpx()
    profile.to_csv(OUT / "course_profile.csv", index=False)
    stations.to_csv(OUT / "aid_stations.csv", index=False)
    print(f"course profile: {len(profile)} pts, "
          f"{profile.mile.max():.1f} mi, "
          f"hi {profile.elevation_ft.max():.0f} ft / lo {profile.elevation_ft.min():.0f} ft")
    print(stations.to_string(index=False))

    runners, splits = parse_splits()
    runners.to_csv(OUT / "runners.csv", index=False)
    splits.to_csv(OUT / "splits.csv", index=False)
    print(f"\nrunners: {len(runners)} ({runners.finished.sum()} finishers), "
          f"splits: {len(splits)} rows, years: {sorted(runners.year.unique())}")


if __name__ == "__main__":
    main()

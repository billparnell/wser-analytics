"""Convert activity GPX files to Parquet.

Parsing only -- this writes what the watch recorded, with no smoothing, no
derived grade and no dropped points. Cleaning belongs downstream, where the
choices are visible and reversible.

Reads  data/activities/raw/*.gpx
Writes data/activities/<name>.parquet

Extension fields are matched on local tag name, so both the COROS `gpxdata:`
namespace and Garmin's `gpxtpx:` TrackPointExtension parse without special
casing. Missing fields come through as null rather than zero.

Usage: python scripts/parse_activities.py
"""

import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "activities" / "raw"
OUT = ROOT / "data" / "activities"

TRKPT = "{http://www.topografix.com/GPX/1/1}trkpt"

# local tag name -> output column. Several vendors, same meaning.
FIELDS = {
    "ele": "elevation_m",
    "time": "time",
    "distance": "distance_m",
    "speed": "speed_mps",
    "cadence": "cadence_spm",
    "cad": "cadence_spm",
    "hr": "heart_rate_bpm",
    "heartrate": "heart_rate_bpm",
    "atemp": "temperature_c",
}

NUMERIC = [
    "elevation_m", "distance_m", "speed_mps",
    "cadence_spm", "heart_rate_bpm", "temperature_c",
]


def local(tag: str) -> str:
    return tag.rpartition("}")[2].lower()


def parse_gpx(path: Path) -> pd.DataFrame:
    rows = []
    # iterparse keeps peak memory flat; a 100-mile file is ~28 MB of XML.
    for _, elem in ET.iterparse(str(path), events=("end",)):
        if elem.tag != TRKPT:
            continue
        row = {"lat": elem.get("lat"), "lon": elem.get("lon")}
        for child in elem.iter():
            name = FIELDS.get(local(child.tag))
            if name and child.text:
                row.setdefault(name, child.text.strip())
        rows.append(row)
        elem.clear()

    df = pd.DataFrame(rows)
    df["lat"] = pd.to_numeric(df["lat"])
    df["lon"] = pd.to_numeric(df["lon"])
    df["time"] = pd.to_datetime(df["time"], utc=True, format="ISO8601")
    for col in NUMERIC:
        df[col] = pd.to_numeric(df[col], errors="coerce") if col in df else pd.NA

    cols = ["time", "lat", "lon"] + NUMERIC
    return df[cols].sort_values("time").reset_index(drop=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted(RAW.glob("*.gpx"))
    if not files:
        raise SystemExit(f"No GPX files in {RAW}")

    for path in files:
        df = parse_gpx(path)
        dest = OUT / f"{path.stem}.parquet"
        df.to_parquet(dest, index=False)

        elapsed = df.time.iloc[-1] - df.time.iloc[0]
        dist_km = df.distance_m.max() / 1000 if df.distance_m.notna().any() else float("nan")
        have = [c for c in NUMERIC if df[c].notna().any()]
        print(
            f"{path.name}\n"
            f"  {len(df):,} points, {elapsed}, {dist_km:.1f} km "
            f"({dist_km * 0.621371:.1f} mi)\n"
            f"  {df.time.iloc[0]:%Y-%m-%d %H:%M:%S} -> {df.time.iloc[-1]:%H:%M:%S} UTC\n"
            f"  fields: {', '.join(have)}\n"
            f"  -> {dest.relative_to(ROOT)} ({dest.stat().st_size / 1e6:.1f} MB)"
        )


if __name__ == "__main__":
    main()

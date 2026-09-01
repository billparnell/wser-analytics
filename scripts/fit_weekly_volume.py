"""
Garmin FIT export -> per-activity and weekly-volume CSVs.

Reads the .fit files straight out of the export .zip (no need to unzip),
pulls the `session` summary message from each one, and writes:

    activities.csv        one row per activity, every session field found
    weekly.csv            one row per week (Mon-start), all sports combined
    weekly_by_sport.csv   one row per week, with hours/miles columns per sport

Setup:
    pip install fitdecode pandas

Usage (Jupyter): set ZIP_PATH below, then run the cell / %run this file.
"""

import io
import os
import zipfile
from collections import defaultdict

import pandas as pd
import fitdecode

# ---------------------------------------------------------------- config ---

# Point this at the export zip, or at a directory of .fit files.
ZIP_PATH = "exportSportData_426607884946653184_20260831.zip"

OUT_DIR = "."

# Week starts on Monday. Use "W-SUN" if you'd rather weeks start Sunday.
WEEK_RULE = "W-MON"

# Drop activities that look like duplicates (same start time + same distance).
DEDUPE = True

# Session fields summed across a week.
SUM_FIELDS = [
    "total_timer_time", "total_elapsed_time", "total_distance",
    "total_ascent", "total_descent", "total_calories", "total_strides",
    "total_work", "total_training_effect", "total_anaerobic_training_effect",
    "training_stress_score",
]

# Session fields averaged across a week, weighted by moving time.
MEAN_FIELDS = [
    "avg_heart_rate", "avg_speed", "enhanced_avg_speed", "avg_cadence",
    "avg_running_cadence", "avg_power", "normalized_power", "avg_temperature",
    "avg_step_length", "avg_stance_time", "avg_vertical_oscillation",
    "avg_vertical_ratio",
]

# Session fields where the weekly value is the max seen.
MAX_FIELDS = [
    "max_heart_rate", "max_speed", "enhanced_max_speed", "max_power",
    "max_cadence", "max_running_cadence",
]

# --------------------------------------------------------------- parsing ---


def _iter_fit_blobs(path):
    """Yield (name, bytes) for each .fit file in a zip or a directory."""
    if os.path.isdir(path):
        for name in sorted(os.listdir(path)):
            if name.lower().endswith(".fit"):
                with open(os.path.join(path, name), "rb") as fh:
                    yield name, fh.read()
    else:
        with zipfile.ZipFile(path) as zf:
            for info in sorted(zf.infolist(), key=lambda i: i.filename):
                if info.filename.lower().endswith(".fit"):
                    yield os.path.basename(info.filename), zf.read(info)


def parse_sessions(blob, name):
    """Extract every `session` message from one FIT file as a dict."""
    rows = []
    with fitdecode.FitReader(io.BytesIO(blob)) as fr:
        for frame in fr:
            if frame.frame_type != fitdecode.FIT_FRAME_DATA:
                continue
            if frame.name != "session":
                continue
            row = {"file": name}
            for fld in frame.fields:
                val = fld.value
                # Skip array-valued fields (HR zone buckets etc.) - they don't
                # fit a flat table and aren't useful for volume totals.
                if isinstance(val, (list, tuple, bytes, bytearray)):
                    continue
                row[fld.name] = val
            rows.append(row)
    return rows


def load_activities(path, verbose=True):
    rows = []
    failures = []
    n = 0
    for name, blob in _iter_fit_blobs(path):
        n += 1
        try:
            rows.extend(parse_sessions(blob, name))
        except Exception as exc:
            failures.append((name, f"{type(exc).__name__}: {exc}"))
        if verbose and n % 100 == 0:
            print(f"  parsed {n} files, {len(rows)} sessions", flush=True)

    if verbose:
        print(f"  done: {n} files, {len(rows)} sessions, {len(failures)} failed")
        for name, err in failures[:10]:
            print(f"    ! {name}: {err}")

    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit("No session messages found - is ZIP_PATH correct?")

    # Timestamps: FIT stores UTC. Convert to naive local-ish for weekly bucketing.
    for col in ("start_time", "timestamp"):
        if col in df:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")

    if "start_time" not in df or df["start_time"].isna().all():
        df["start_time"] = df.get("timestamp")

    df = df.dropna(subset=["start_time"]).sort_values("start_time")

    if DEDUPE:
        before = len(df)
        key = ["start_time"]
        if "total_distance" in df:
            key.append("total_distance")
        df = df.drop_duplicates(subset=key, keep="first")
        if verbose and before != len(df):
            print(f"  dropped {before - len(df)} duplicate sessions")

    # Friendly derived columns.
    df["sport"] = df.get("sport", "unknown").astype(str).fillna("unknown")
    if "sub_sport" in df:
        df["sub_sport"] = df["sub_sport"].astype(str)
    df["date"] = df["start_time"].dt.tz_convert(None).dt.date
    df["moving_hours"] = df.get("total_timer_time", pd.NA) / 3600.0
    df["elapsed_hours"] = df.get("total_elapsed_time", pd.NA) / 3600.0
    df["distance_km"] = df.get("total_distance", pd.NA) / 1000.0
    df["distance_mi"] = df["distance_km"] * 0.621371
    if "total_ascent" in df:
        df["ascent_ft"] = df["total_ascent"] * 3.28084
    if "avg_speed" in df:
        # min/mile and min/km, only where speed is sane.
        spd = df["avg_speed"].where(df["avg_speed"] > 0.1)
        df["pace_min_per_mi"] = (1609.34 / spd) / 60.0
        df["pace_min_per_km"] = (1000.0 / spd) / 60.0

    return df.reset_index(drop=True)


# ----------------------------------------------------------- aggregation ---


def _weighted_mean(sub, col, weight_col="total_timer_time"):
    if col not in sub:
        return pd.NA
    vals = pd.to_numeric(sub[col], errors="coerce")
    wts = pd.to_numeric(sub.get(weight_col, pd.Series(1, index=sub.index)),
                        errors="coerce").fillna(0)
    mask = vals.notna() & (wts > 0)
    if not mask.any():
        return vals.mean() if vals.notna().any() else pd.NA
    return (vals[mask] * wts[mask]).sum() / wts[mask].sum()


def weekly_summary(df):
    """One row per week, all sports pooled."""
    d = df.copy()
    d["week_start"] = (
        d["start_time"].dt.tz_convert(None).dt.to_period(WEEK_RULE[0]).dt.start_time
        if False else
        d["start_time"].dt.tz_convert(None) - pd.to_timedelta(
            d["start_time"].dt.tz_convert(None).dt.weekday, unit="D")
    )
    d["week_start"] = d["week_start"].dt.normalize()

    out = []
    for week, sub in d.groupby("week_start"):
        row = {
            "week_start": week.date(),
            "activities": len(sub),
            "days_active": sub["date"].nunique(),
            "sports": ", ".join(sorted(sub["sport"].unique())),
        }
        row["moving_hours"] = round(sub["moving_hours"].sum(skipna=True), 2)
        row["elapsed_hours"] = round(sub["elapsed_hours"].sum(skipna=True), 2)
        row["distance_mi"] = round(sub["distance_mi"].sum(skipna=True), 2)
        row["distance_km"] = round(sub["distance_km"].sum(skipna=True), 2)
        if "ascent_ft" in sub:
            row["ascent_ft"] = round(sub["ascent_ft"].sum(skipna=True), 0)
        for col in SUM_FIELDS:
            if col in sub:
                row[col] = pd.to_numeric(sub[col], errors="coerce").sum(skipna=True)
        for col in MEAN_FIELDS:
            if col in sub:
                v = _weighted_mean(sub, col)
                row[col] = round(v, 2) if pd.notna(v) else pd.NA
        for col in MAX_FIELDS:
            if col in sub:
                row[col] = pd.to_numeric(sub[col], errors="coerce").max()
        out.append(row)

    weekly = pd.DataFrame(out).set_index("week_start").sort_index()

    # Fill in weeks with zero training so the series is continuous.
    full = pd.date_range(weekly.index.min(), weekly.index.max(), freq="7D").date
    weekly = weekly.reindex(full)
    weekly.index.name = "week_start"
    zero_cols = (["activities", "days_active", "moving_hours", "elapsed_hours",
                  "distance_mi", "distance_km", "ascent_ft"] + SUM_FIELDS)
    for col in zero_cols:
        if col in weekly:
            weekly[col] = weekly[col].fillna(0)
    if "sports" in weekly:
        weekly["sports"] = weekly["sports"].fillna("")
    return weekly.reset_index()


def weekly_by_sport(df):
    """One row per week, with hours/miles/activity-count columns per sport."""
    d = df.copy()
    naive = d["start_time"].dt.tz_convert(None)
    d["week_start"] = (naive - pd.to_timedelta(naive.dt.weekday, unit="D")).dt.normalize()

    piv = d.pivot_table(
        index="week_start", columns="sport",
        values=["moving_hours", "distance_mi"],
        aggfunc="sum", fill_value=0,
    )
    counts = d.pivot_table(index="week_start", columns="sport",
                           values="file", aggfunc="count", fill_value=0)
    counts.columns = pd.MultiIndex.from_product([["activities"], counts.columns])
    piv = pd.concat([piv, counts], axis=1)
    piv.columns = [f"{sport}_{metric}" for metric, sport in piv.columns]
    piv = piv[sorted(piv.columns)].round(2)

    full = pd.date_range(piv.index.min(), piv.index.max(), freq="7D")
    piv = piv.reindex(full).fillna(0)
    piv.index = piv.index.date
    piv.index.name = "week_start"
    return piv.reset_index()


# -------------------------------------------------------------------- run ---

if __name__ == "__main__":
    print(f"Reading {ZIP_PATH} ...")
    acts = load_activities(ZIP_PATH)

    weekly = weekly_summary(acts)
    by_sport = weekly_by_sport(acts)

    paths = {
        "activities.csv": acts,
        "weekly.csv": weekly,
        "weekly_by_sport.csv": by_sport,
    }
    for fname, frame in paths.items():
        dest = os.path.join(OUT_DIR, fname)
        frame.to_csv(dest, index=False)
        print(f"wrote {dest}  ({len(frame)} rows, {len(frame.columns)} cols)")

    print()
    print(f"{len(acts)} activities from "
          f"{acts['start_time'].min().date()} to {acts['start_time'].max().date()}")
    print(acts["sport"].value_counts().to_string())
    print()
    print("Last 8 weeks:")
    cols = [c for c in ["week_start", "activities", "moving_hours",
                        "distance_mi", "ascent_ft"] if c in weekly]
    print(weekly[cols].tail(8).to_string(index=False))

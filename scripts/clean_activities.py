"""Turn parsed activity Parquet into an analysis-ready course profile.

Reads  data/activities/<name>.parquet   (raw, from parse_activities.py)
Writes data/activities/<name>_profile.parquet

The output is indexed by *distance*, not time. Grade has to be measured per
metre travelled, and speed swings roughly tenfold between running the flats and
hiking a canyon wall, so a time-indexed series weights the slow parts of the
course far more heavily than the fast ones.

Two decisions here are empirical rather than conventional, and both are
documented in the Phase 1 log:

SMOOTHING WINDOW (75 m). The COROS records elevation quantised to whole metres
while covering about 2 m per sample, so a single 1 m step reads as a 50% grade
and 8.9% of point-to-point grades land outside Minetti's entire valid range.
Sweeping the Savitzky-Golay window against the course's known ~18,000 ft of
climb: 20 m leaves 1,265 ft of phantom gain, 200 m erases 840 ft of real
terrain, and 75 m lands within 30 ft. Note the published figure is itself a
smoothed survey number, so this calibrates the window, it does not validate it
to the foot.

STOPS (60 s under 0.5 m/s). Aid-station time has to come out or it reads as
zero speed at whatever grade the aid station happens to sit on. Detected from
GPS alone, 8 of the 9 stops land within half a mile of a real aid station,
which is why the threshold is trusted.

Usage: python scripts/clean_activities.py
"""

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter

ROOT = Path(__file__).resolve().parent.parent
ACT = ROOT / "data" / "activities"

GRID_M = 1.0          # uniform distance grid spacing
SMOOTH_M = 75         # elevation smoothing window, see header
ALT_SMOOTH_M = 20     # kept alongside so Phase 2 can test sensitivity
STOP_SPEED = 0.5      # m/s, below this over STOP_WINDOW counts as stopped
STOP_WINDOW = 60      # seconds
GAP_JUMP_M = 10       # a distance jump this large means GPS dropped out
M_PER_MILE = 1609.34


def smooth_grade(elev_grid: np.ndarray, window_m: int):
    """Savitzky-Golay smoothed elevation and its gradient, in percent."""
    n = max(5, int(window_m / GRID_M) | 1)
    n = min(n, len(elev_grid) - 1 | 1)
    smoothed = savgol_filter(elev_grid, n, 2)
    return smoothed, np.gradient(smoothed, GRID_M) * 100


def build_profile(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(subset=["distance_m", "elevation_m", "time"]).copy()
    df = df.sort_values("distance_m")

    dt = df.time.diff().dt.total_seconds().fillna(1.0)
    dd = df.distance_m.diff().fillna(0.0)

    # Sustained near-zero movement, not instantaneous -- GPS jitter alone
    # produces plenty of single samples that look stationary.
    rolling_speed = (dd.rolling(STOP_WINDOW, min_periods=10).sum()
                     / dt.rolling(STOP_WINDOW, min_periods=10).sum())
    stopped = (rolling_speed < STOP_SPEED).fillna(False)

    # Moving time excludes stops, so speed is speed rather than an average
    # diluted by however long the aid station took.
    df["moving_s"] = dt.where(~stopped, 0.0).cumsum()
    df["elapsed_s"] = (df.time - df.time.iloc[0]).dt.total_seconds()
    df["stopped"] = stopped

    # Distance is monotonic by construction; drop the rare backward GPS jump so
    # np.interp stays well defined.
    df = df[df.distance_m.diff().fillna(1) > 0]

    grid = np.arange(df.distance_m.min(), df.distance_m.max(), GRID_M)
    d = df.distance_m.to_numpy()

    def on_grid(col):
        return np.interp(grid, d, df[col].to_numpy())

    elev_raw = on_grid("elevation_m")
    elev, grade = smooth_grade(elev_raw, SMOOTH_M)
    _, grade_alt = smooth_grade(elev_raw, ALT_SMOOTH_M)

    moving_s = on_grid("moving_s")
    # Speed over the same window the grade is measured over, so the two
    # describe the same stretch of trail. A centred difference rather than a
    # smoothed gradient: moving time is non-decreasing but has a step at every
    # stop, and Savitzky-Golay across that step rings negative.
    half = max(2, int(SMOOTH_M / GRID_M) // 2)
    forward = np.concatenate([moving_s[half:], np.full(half, np.nan)])
    backward = np.concatenate([np.full(half, np.nan), moving_s[:-half]])
    elapsed_over_window = forward - backward
    with np.errstate(divide="ignore", invalid="ignore"):
        speed = np.where(elapsed_over_window > 0,
                         (2 * half * GRID_M) / elapsed_over_window,
                         np.nan)

    out = pd.DataFrame({
        "distance_m": grid,
        "mile": grid / M_PER_MILE,
        "elapsed_s": on_grid("elapsed_s"),
        "moving_s": moving_s,
        "elevation_m": elev,
        "elevation_raw_m": elev_raw,
        "grade_pct": grade,
        f"grade_pct_{ALT_SMOOTH_M}m": grade_alt,
        "speed_mps": speed,
        "lat": on_grid("lat"),
        "lon": on_grid("lon"),
        "stopped_frac": on_grid("stopped"),
    })
    for col in ("heart_rate_bpm", "cadence_spm"):
        if col in df and df[col].notna().any():
            out[col] = np.interp(grid, d, df[col].ffill().bfill().to_numpy())

    out["pace_min_mi"] = M_PER_MILE / (out.speed_mps * 60)

    # GPS dropouts understate horizontal distance while the real climb or
    # descent continues, so grade goes vertical on the far side of one. Mask a
    # full smoothing window either side rather than trust the interpolation:
    # this file drops out twice, in the El Dorado Creek canyon (mile 52.9) and
    # at the Rucky Chucky river crossing.
    jumps = df.distance_m[dd.reindex(df.index) > GAP_JUMP_M]
    near_gap = np.zeros(len(grid), dtype=bool)
    for jump_at in jumps:
        near_gap |= np.abs(grid - jump_at) < SMOOTH_M
    out["near_gap"] = near_gap

    # A distance grid compresses stops to almost nothing, but the few cells that
    # straddle one still need excluding from any fit.
    out["is_clean"] = (
        (out.stopped_frac < 0.5)
        & out.speed_mps.between(0.3, 7.0)
        & ~out.near_gap
    )
    return out


def main():
    files = sorted(p for p in ACT.glob("*.parquet") if not p.stem.endswith("_profile"))
    if not files:
        raise SystemExit(f"No parsed activities in {ACT}. Run parse_activities.py first.")

    for path in files:
        prof = build_profile(pd.read_parquet(path))
        dest = ACT / f"{path.stem}_profile.parquet"
        prof.to_parquet(dest, index=False)

        clean = prof[prof.is_clean]
        gain = np.diff(prof.elevation_m)
        print(
            f"{path.stem}\n"
            f"  {len(prof):,} x {GRID_M:g} m cells, {prof.mile.max():.1f} mi\n"
            f"  climb {gain[gain > 0].sum() * 3.28084:,.0f} ft / "
            f"descent {-gain[gain < 0].sum() * 3.28084:,.0f} ft\n"
            f"  grade {clean.grade_pct.min():+.0f}% to {clean.grade_pct.max():+.0f}%, "
            f"sd {clean.grade_pct.std():.1f}\n"
            f"  usable for fitting: {clean.is_clean.sum():,} cells "
            f"({len(clean) / len(prof) * 100:.1f}%)\n"
            f"  -> {dest.relative_to(ROOT)}"
        )


if __name__ == "__main__":
    main()

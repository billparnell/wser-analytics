"""First look: measured speed against grade, with Minetti as a reference.

Deliberately not a fit. Phase 1 is for looking at the data before modelling it,
so this plots what the watch recorded next to what the textbook curve predicts
and leaves the divergence visible.

Minetti et al. 2002 gives the metabolic cost of running as a function of
gradient, in J/kg/m. Turning that into a predicted speed assumes the runner
holds constant metabolic power, so speed goes as 1/cost -- the same assumption
underneath Strava's GAP. The curve is anchored to measured flat speed rather
than fitted, so any divergence away from flat is the interesting part.

CAVEAT: the polynomial coefficients are transcribed from the project notes and
have NOT yet been checked against the paper. See pacing_todo.md.

Usage: python scripts/plot_speed_vs_grade.py
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ACT = ROOT / "data" / "activities"
FIG = ROOT / "figures"

# Minetti et al. 2002, J Appl Physiol 93(3):1039-46. i = gradient as a fraction.
MINETTI = [155.4, -30.4, -43.3, 46.3, 19.5, 3.6]


def minetti_cost(gradient):
    """Metabolic cost of running, J/kg/m. Valid roughly -0.45 <= i <= 0.45."""
    return np.polyval(MINETTI, gradient)


def main():
    FIG.mkdir(exist_ok=True)
    prof = pd.read_parquet(ACT / "bp_states_2025_profile.parquet")
    clean = prof[prof.is_clean]

    grade = clean.grade_pct.to_numpy()
    speed = clean.speed_mps.to_numpy()

    # measured median speed per 1% grade bin
    edges = np.arange(-45, 51, 1.0)
    idx = np.digitize(grade, edges) - 1
    centres, medians, counts = [], [], []
    for b in range(len(edges) - 1):
        sel = speed[idx == b]
        if len(sel) >= 200:                     # >=200 m of trail in the bin
            centres.append((edges[b] + edges[b + 1]) / 2)
            medians.append(np.median(sel))
            counts.append(len(sel))
    centres, medians = np.array(centres), np.array(medians)

    flat_speed = np.median(speed[np.abs(grade) < 2])
    ref_grade = np.linspace(-45, 45, 400)
    predicted = flat_speed * minetti_cost(0) / minetti_cost(ref_grade / 100)

    fig, ax = plt.subplots(figsize=(11, 6.5))
    ax.hexbin(grade, speed, gridsize=70, cmap="Greys", bins="log",
              mincnt=1, linewidths=0)
    ax.plot(ref_grade, predicted, color="#C97B3D", lw=2.2, ls="--",
            label="Minetti 2002, constant power (anchored at flat)")
    ax.plot(centres, medians, color="#2B2118", lw=2.6,
            label="Measured median speed")
    ax.axvline(0, color="#999", lw=0.8, zorder=0)
    ax.axhline(flat_speed, color="#999", lw=0.8, ls=":", zorder=0)

    peak = centres[np.argmax(medians)]
    ax.annotate(f"fastest at {peak:+.0f}% grade",
                xy=(peak, medians.max()), xytext=(peak - 26, medians.max() + 0.55),
                arrowprops=dict(arrowstyle="->", color="#2B2118"), fontsize=10)

    ax.set_xlabel("Grade (%)")
    ax.set_ylabel("Speed (m/s)")
    ax.set_title("Western States 2025 — measured speed vs grade\n"
                 "86,570 GPS points, aid-station stops removed", loc="left")
    ax.set_xlim(-45, 50)
    ax.set_ylim(0, 4.2)
    ax.legend(loc="upper right", frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()

    dest = FIG / "speed_vs_grade_2025.png"
    fig.savefig(dest, dpi=150)
    print(f"wrote {dest.relative_to(ROOT)}")

    # the numbers worth reading without opening the image
    print(f"\nflat speed (|grade|<2%): {flat_speed:.2f} m/s")
    print(f"measured peak: {medians.max():.2f} m/s at {peak:+.0f}%")
    mp = ref_grade[np.argmax(predicted)]
    print(f"Minetti peak:  {predicted.max():.2f} m/s at {mp:+.0f}%")
    print("\ngrade   measured   Minetti   ratio")
    for g in [-30, -20, -10, -5, 0, 5, 10, 20, 30]:
        if g < centres.min() or g > centres.max():
            continue
        m = np.interp(g, centres, medians)
        p = flat_speed * minetti_cost(0) / minetti_cost(g / 100)
        print(f"{g:>+5}%   {m:>7.2f}   {p:>7.2f}   {m / p:>5.2f}")


if __name__ == "__main__":
    main()

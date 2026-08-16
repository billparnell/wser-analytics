"""Rebuild data/wser.duckdb from the tracked CSVs.

The database file is derived data and is not committed — this script
regenerates it. Two upstream paths feed it:

  data/raw/wser<year>.xls*  -> prep_dashboard_data.py -> data/processed/*.csv
  wser.org (scraped)        -> 01_scrape_and_explore  -> data/wser_results_raw.csv

Only the second needs the network, and its output is committed, so this
script runs fully offline.

Usage:
    python scripts/prep_dashboard_data.py   # if data/processed/ is stale
    python scripts/build_db.py
"""

from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DB_PATH = DATA / "wser.duckdb"

# table name -> source CSV, relative to data/
TABLES = {
    "wser_results": "wser_results_raw.csv",
    "wser_year_summary": "wser_year_summary.csv",
    "runners": "processed/runners.csv",
    "splits": "processed/splits.csv",
    "aid_stations": "processed/aid_stations.csv",
    "course_profile": "processed/course_profile.csv",
}

# Sources produced by prep_dashboard_data.py, named in the error if missing
PREPPED = {"runners", "splits", "aid_stations", "course_profile"}


def main():
    missing = {t: p for t, p in TABLES.items() if not (DATA / p).exists()}
    if missing:
        lines = [f"  data/{p}" for p in missing.values()]
        hint = (
            "\n\nRun `python scripts/prep_dashboard_data.py` first."
            if missing.keys() & PREPPED
            else ""
        )
        raise SystemExit("Missing source CSVs:\n" + "\n".join(lines) + hint)

    DB_PATH.unlink(missing_ok=True)
    con = duckdb.connect(str(DB_PATH))
    for table, rel in TABLES.items():
        con.execute(
            f"CREATE TABLE {table} AS SELECT * FROM read_csv_auto(?)",
            [str(DATA / rel)],
        )
        n = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        print(f"{table:<20} {n:>7,} rows   <- data/{rel}")
    con.close()

    size_mb = DB_PATH.stat().st_size / 1024 / 1024
    print(f"\nwrote {DB_PATH.relative_to(ROOT)} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()

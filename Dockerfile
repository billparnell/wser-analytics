# Build stage: raw spreadsheets -> DuckDB with the dbt models built into it.
# Kept separate so dbt and its dependencies never reach the runtime image.
FROM python:3.12-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY dbt_project.yml packages.yml package-lock.yml profiles.yml ./
COPY macros/ macros/
COPY models/ models/
COPY tests/ tests/
COPY scripts/ scripts/
COPY data/raw/ data/raw/
COPY data/wser_results_raw.csv data/wser_year_summary.csv data/

# dbt build runs the tests too, so a data regression fails the image rather
# than shipping a quietly wrong dashboard.
RUN python scripts/prep_dashboard_data.py \
 && python scripts/build_db.py \
 && dbt deps \
 && dbt build

# Runtime stage: Streamlit and the built database, nothing else.
FROM python:3.12-slim

WORKDIR /app

COPY requirements-dashboard.txt .
RUN pip install --no-cache-dir -r requirements-dashboard.txt

COPY dashboard/ dashboard/
COPY --from=builder /build/data/wser.duckdb data/wser.duckdb

EXPOSE 8501

# Railway injects PORT; default to 8501 for local docker runs
CMD streamlit run dashboard/app.py --server.port ${PORT:-8501} --server.address 0.0.0.0 --server.headless true

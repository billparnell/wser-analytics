FROM python:3.12-slim

WORKDIR /app

COPY requirements-dashboard.txt .
RUN pip install --no-cache-dir -r requirements-dashboard.txt

COPY dashboard/ dashboard/
COPY data/processed/ data/processed/

EXPOSE 8501

# Railway injects PORT; default to 8501 for local docker runs
CMD streamlit run dashboard/app.py --server.port ${PORT:-8501} --server.address 0.0.0.0 --server.headless true

FROM python:3.13-slim

WORKDIR /app

# Patch OS packages against known vulnerabilities
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend packages, migrations, datasets, and runtime configs (excludes web/ and node_modules)
COPY ledger/ ./ledger/
COPY ledger_api/ ./ledger_api/
COPY migrations/ ./migrations/
COPY certs/ ./certs/
COPY datasets/ ./datasets/
COPY contract/ ./contract/
COPY runtime-config.json evaluation-budget.json ./

RUN mkdir -p /app/data/blobs

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "ledger_api.main:app", "--host", "0.0.0.0", "--port", "8000"]

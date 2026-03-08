FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Run as non-root user
RUN useradd -m -u 1000 tdo
USER tdo

EXPOSE 8000

# Route to the correct entry point based on JOB_NAME:
#   JOB_NAME=harvest  → run the harvest pipeline job
#   JOB_NAME=embed    → run the embedding backfill job
#   JOB_NAME=migrate  → run alembic migrations
#   anything else     → run the FastAPI server
CMD ["sh", "-c", \
  "if [ \"$JOB_NAME\" = \"harvest\" ]; then \
     exec python -m src.jobs.harvest; \
   elif [ \"$JOB_NAME\" = \"embed\" ]; then \
     exec python -m src.jobs.embed; \
   elif [ \"$JOB_NAME\" = \"migrate\" ]; then \
     exec python -m src.jobs.migrate; \
   else \
     exec uvicorn src.api.main:app --host 0.0.0.0 --port 8000; \
   fi"]

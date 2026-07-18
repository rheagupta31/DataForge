# DataForge — production image
#
# Build:  docker build -t dataforge .
# Run:    docker run -p 5000:5000 --env-file .env dataforge
#
# Serves via gunicorn (not the Flask dev server) with 4 worker processes.
# Configure GROQ_API_KEY / PORT / FLASK_DEBUG through environment variables
# or an --env-file; see .env.example.

FROM python:3.11-slim

WORKDIR /app

# libpq5 is the runtime client library Postgres connections need;
# psycopg2-binary bundles its own copy but this keeps things robust
# across base image variants.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV FLASK_DEBUG=false
ENV PORT=5000
EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "120", "app:app"]

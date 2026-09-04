# The read API. The pipeline is not in this image — it runs on a schedule and
# writes the database; this serves what it produced.
FROM python:3.12-slim

WORKDIR /app

# Only what the API imports: FastAPI, uvicorn, pydantic, and the pipeline
# package for its enums and Store. Not anthropic — nothing here calls a model.
COPY requirements.txt ./
RUN pip install --no-cache-dir fastapi uvicorn[standard] pydantic

COPY tradewatch/ ./tradewatch/
COPY api/ ./api/
COPY scripts/ ./scripts/

# The data ships inside the image. Nothing writes to it at runtime, so it needs
# no volume and survives no redeploy — because it is rebuilt from the repo every
# time. That is what makes a free tier with ephemeral disk a correct host rather
# than a compromise.
COPY data/snapshot.db ./data/snapshot.db

# TRADEWATCH_ALLOWED_ORIGINS must name the deployed frontend, or the browser
# will refuse the response even though the API answered.
ENV TRADEWATCH_DB=/app/data/snapshot.db \
    TRADEWATCH_ALLOWED_ORIGINS=http://localhost:5173 \
    PORT=8000

EXPOSE 8000
CMD ["sh", "-c", "uvicorn api.app:app --host 0.0.0.0 --port ${PORT}"]

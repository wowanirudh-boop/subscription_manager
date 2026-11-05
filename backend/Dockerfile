# Build from the repository root:  docker build -f backend/Dockerfile -t srt-backend .
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app
COPY phase0 /app/phase0
COPY backend /app/backend
RUN pip install --no-cache-dir /app/phase0 "/app/backend[gcp]" \
 && useradd --create-home --uid 10001 app
USER app
CMD exec uvicorn srt_backend.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers

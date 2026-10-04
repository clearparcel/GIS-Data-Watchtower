FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY clearparcel ./clearparcel
COPY config ./config
RUN pip install --no-cache-dir ".[gcs]"
USER 65532:65532
ENTRYPOINT ["watchtower"]
CMD ["--config","config/example_sources.json","cloud-job"]

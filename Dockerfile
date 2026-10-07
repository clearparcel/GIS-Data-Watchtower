# Python 3.13 is the validated container baseline; CI separately verifies package compatibility on 3.12-3.14.
FROM python:3.13-slim@sha256:bf44cdfcb76cd3b41e879bc058fc37ec5872002ccfde7fcb765e218cde0cd79c
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md LICENSE constraints.txt ./
COPY clearparcel ./clearparcel
COPY config ./config
ARG WATCHTOWER_BUILD_REVISION=""
ARG WATCHTOWER_BUILD_ENVIRONMENT="development"
RUN python -c "import json,os,re,pathlib; r=os.environ['WATCHTOWER_BUILD_REVISION']; e=os.environ['WATCHTOWER_BUILD_ENVIRONMENT']; assert not r or re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}',r), 'Invalid source revision'; assert e in ('preview','production','development'), 'Invalid build environment'; pathlib.Path('clearparcel/datawatch/build_info.json').write_text(json.dumps({'revision':r,'environment':e}),encoding='utf-8')"
RUN pip install --no-cache-dir --constraint constraints.txt ".[gcs]"
USER 65532:65532
ENTRYPOINT ["watchtower"]
CMD ["--config","config/example_sources.json","cloud-job"]

# Python 3.13 is the validated container baseline; CI separately verifies package compatibility on 3.12-3.14.
FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md LICENSE constraints.txt ./
COPY clearparcel ./clearparcel
COPY config ./config
ARG WATCHTOWER_BUILD_REVISION=""
ARG WATCHTOWER_BUILD_ENVIRONMENT="development"
# Preview and production images must carry the full source revision.
RUN python -c "import json,os,re,pathlib; r=os.environ['WATCHTOWER_BUILD_REVISION']; e=os.environ['WATCHTOWER_BUILD_ENVIRONMENT']; assert not r or re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}',r), 'Invalid source revision'; assert e in ('preview','production','development'), 'Invalid build environment'; assert r or e == 'development', 'Preview and production builds require WATCHTOWER_BUILD_REVISION'; pathlib.Path('clearparcel/datawatch/build_info.json').write_text(json.dumps({'revision':r,'environment':e}),encoding='utf-8')"
RUN pip install --no-cache-dir --constraint constraints.txt ".[gcs]" \
    && python -m pip uninstall -y pip setuptools
USER 65532:65532
ENTRYPOINT ["watchtower"]
CMD ["--config","config/example_sources.json","cloud-job"]

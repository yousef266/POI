FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md /app/
COPY src /app/src
COPY run.py agent.json sources.json /app/
COPY fixtures /app/fixtures
RUN pip install --no-cache-dir -e ".[postgis]"

ENTRYPOINT ["poi-harvester"]

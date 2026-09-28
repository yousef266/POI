# POI Harvester Agent

Collect POIs from configured sources, validate geometry, normalize Arabic/English attributes, preserve provenance, detect incremental changes, and publish a PostGIS layer with GeoServer styling.

## Start with your coding assistant

Clone this repository, open its folder in Claude, Codex, or another coding assistant, and send:

> This folder contains a POI Harvester agent. Read its setup instructions, install it, and help me configure `.env` for my servers using `.env.example`. Then use this agent to handle my POI collection requests, following its source, geometry validation, and publication rules.

After setup, ask for the category and location you want. Supply the database name, GeoServer workspace, and optional schema for publication.

## Install

Requires Python 3.11+, PostgreSQL with PostGIS, and GeoServer.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[postgis]"
Copy-Item .env.example .env
```

Edit `.env` with your server connections and credentials. It is ignored by Git. Database, workspace, and optional schema are supplied with the request.

Connection settings: `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `GEOSERVER_URL`, `GEOSERVER_USER`, and `GEOSERVER_PASSWORD`. Process environment variables override `.env`; use `--env-file PATH` for another configuration. Optional `GEOSERVER_PGHOST` selects the database address reachable from GeoServer; `PGSSLMODE` selects PostgreSQL TLS mode.

## Collect and publish

Use your area's WGS84 GeoJSON boundary:

```powershell
.\run.ps1 run --polygon area.geojson --category bank --sources openstreetmap --contact YOUR_OPERATOR_EMAIL --use internal --database YOUR_DATABASE --workspace YOUR_WORKSPACE --out output/banks
```

For a natural-language request, use `--intent "banks in Jeddah" --place-catalog places.geojson` instead of the polygon/category arguments. English and Arabic requests are supported. The catalog or an approved place provider supplies the requested boundary.

The place catalog contains named WGS84 GeoJSON polygons or multipolygons. Configure `--place-provider provider.json` for a licensed HTTP resolver. A provider configuration declares `name`, `endpoint`, `license`, `attribution`, `allowed_uses`, `commercial_use`, and `rate_limit_per_second`. Ambiguous results require clarification. A bounding box selects the rectangle itself, not an administrative boundary.

Normal runs publish a database POI layer and a styled GeoServer layer, then verify them. Missing required inputs produce `needs_input`. Use `--no-publish` only for a file-only preview.

The included sources accept older available data with its source date disclosed. Snapshot downgrades remain blocked and live failures do not silently substitute cached data. Select `--freshness-policy strict` for age enforcement or `--snapshot-from PATH` for an explicit integrity-checked historical capture. Workers handling the same source/query should share snapshot state.

Sources are configured in `sources.json`; included OSM sources permit internal use. Commercial use or redistribution requires an operator-reviewed source configuration. Supply a genuine operator contact for live requests; robots checks and configured rate limits are enforced.

## Output

- PostGIS record table and active POI view.
- GeoServer layer with WFS/WMS, styling, metadata, and attribution.
- Integer serial primary key `id` in the published layer.
- Required canonical attributes and populated optional columns.
- GeoJSON, captured source records, provenance, change sets, and review evidence under `output/`.

Internal identities are retained for deterministic updates and replay. Missing source names/coordinates are not invented; generated language values and derived geometry retain explicit flags, confidence, and provenance.

Address-only records can use a licensed `--geocode-catalog` or `--geocode-provider`. `--allow-source-centers` explicitly permits footprint-derived centers. Unresolved or ambiguous coordinates remain in the review queue. Required canonical fields remain even when source values are absent; optional columns appear when at least one record supplies a meaningful value.

## Verify and replay

```powershell
.\run.ps1 verify-local --database YOUR_DATABASE --workspace YOUR_WORKSPACE --layer poi_bank --out output/banks
.\run.ps1 replay output/banks
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\run.ps1 evaluate --ratings fixtures/arabic_name_review_human_ratings.json --out output/evaluation
```

The regression suite has **170 passed, 0 failed, 0 skipped**. Evaluation generates machine-readable results and readiness evidence under `output/`. Local validation, human review evidence, and official certification are recorded separately.

For incremental processing, supply `--previous output/banks/records.json` and a new output directory. Evaluation verifies the seeded 50-addition/50-update/20-removal/30-unchanged change set and deterministic offline replay. Add `--local-services --database DATABASE --schema TEST_SCHEMA --workspace TEST_WORKSPACE` to evaluate PostGIS/GeoServer in isolated test targets.

The existing Arabic sample has 100 human-reviewed and accepted examples, 0 rejected and 0 unreviewed. Exact IDs and decisions are preserved in `fixtures/arabic_name_review_human_ratings.json` and `fixtures/arabic_name_review_manifest.json`. To score those decisions:

```powershell
.\run.ps1 review-names --ratings fixtures/arabic_name_review_human_ratings.json --out output/arabic-review/score.json
```

The 10K fixture uses explicitly invented grid locations for processing/publication load testing. It is not real-POI location or official throughput evidence.

## Container execution

The submission specification requires an equivalent single command against a clean container. With Docker available:

```powershell
.\scripts\run-local-demo.ps1
```

This starts PostGIS/GeoServer and runs the agent with explicitly labeled demo POIs. Generated passwords stay in ignored `.env.container`. Stop the services with `.\scripts\stop-local.ps1`; their data is retained.

For package-only evaluation:

```powershell
docker build -t poi-harvester .
docker run --rm --entrypoint python poi-harvester -m unittest discover -s tests -v
docker run --rm -v "$($PWD.Path)/output:/app/output" poi-harvester evaluate --out output/container-evaluation
```

For native deployment, install or connect to your own PostGIS/GeoServer services and configure `.env`.

## Documentation

- [Design and reproducibility](docs/DESIGN.md)

Tests and fixtures are included for reproducible evaluation. Credentials, local runtimes, live captures, and generated evaluation artifacts are excluded from Git.

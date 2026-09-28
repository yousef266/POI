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

## Collect and publish

Use your area's WGS84 GeoJSON boundary:

```powershell
.\run.ps1 run --polygon area.geojson --category bank --sources openstreetmap --contact YOUR_OPERATOR_EMAIL --use internal --database YOUR_DATABASE --workspace YOUR_WORKSPACE --out output/banks
```

For a natural-language request, use `--intent "banks in Jeddah" --place-catalog places.geojson` instead of the polygon/category arguments. English and Arabic requests are supported. The catalog or an approved place provider supplies the requested boundary.

Normal runs publish a database POI layer and a styled GeoServer layer, then verify them. Missing required inputs produce `needs_input`. Use `--no-publish` only for a file-only preview.

The included sources accept older available data with its source date disclosed. Snapshot downgrades remain blocked and live failures do not silently substitute cached data. Sources are configured in `sources.json`; included OSM sources permit internal use. See the usage guide for source policy and provider configuration.

## Output

- PostGIS record table and active POI view.
- GeoServer layer with WFS/WMS, styling, metadata, and attribution.
- Integer serial primary key `id` in the published layer.
- Required canonical attributes and populated optional columns.
- GeoJSON, captured source records, provenance, change sets, and review evidence under `output/`.

Internal identities are retained for deterministic updates and replay. Missing source names/coordinates are not invented; generated language values and derived geometry retain explicit flags, confidence, and provenance.

## Verify and replay

```powershell
.\run.ps1 verify-local --database YOUR_DATABASE --workspace YOUR_WORKSPACE --layer poi_bank --out output/banks
.\run.ps1 replay output/banks
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\run.ps1 evaluate --ratings fixtures/arabic_name_review_human_ratings.json --out output/evaluation
```

The regression suite has **170 passed, 0 failed, 0 skipped**. Evaluation generates machine-readable results and readiness evidence under `output/`. Local validation, human review evidence, and official certification are recorded separately.

## Documentation

- [Installation and operation](docs/USAGE.md)
- [Design and reproducibility](docs/DESIGN.md)
- [Local validation](docs/VALIDATION.md)
- [Human Arabic review](docs/ARABIC_REVIEW.md)

Tests and fixtures are included for reproducible evaluation. Credentials, local runtimes, live captures, and generated evaluation artifacts are excluded from Git.

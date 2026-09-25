# POI Harvester Agent

An executable starting point for the GURA POI Harvester bounty. It collects from a declared source registry, checks the declared use before any source access, normalizes POIs, merges likely duplicates, preserves field-level provenance, writes an incremental change set, and can publish the spatial layer to PostGIS and GeoServer.

## Run the local fixture

Python 3.11+ is sufficient for the local run; no API key, database, or installed Python package is needed.

```powershell
python run.py run --bbox 24.70 46.66 24.73 46.69 --category pharmacy --sources demo,demo_alt --out output/demo
python run.py replay output/demo
python -m unittest discover -s tests -v
```

The first command writes `poi.geojson`, `records.json`, `raw.json`, `sources_snapshot.json`, `changes.json`, `metadata.json`, and `review_queue.json`. The replay command reconstructs the same merged records from captured raw data, without network access or an LLM.

The callable `poi_harvester.agent.invoke(payload)` provides the same workflow to a front end, another agent, or a trigger. It asks for a missing area, category, database, or workspace. It publishes by default; pass `"publish": false` for a file-only preview. `agent.json` documents its current inputs and outputs; it is not a substitute for the linked Common Agent Contract.

For a subsequent harvest, pass `--previous output/demo/records.json` and use a new `--out` directory. This emits added, updated, removed, and unchanged IDs with field-level changes.

For an exact WGS84 polygon AOI, use `--polygon fixtures/riyadh_small_aoi.geojson` instead of `--bbox`. The source query uses the polygon's bounds and the agent filters records against the polygon before merging. Polygon holes and multipolygons are supported. Non-WGS84 coordinates are not supported. To resolve an admin boundary or named place, use `--place "Place name" --place-catalog places.geojson`; the catalog must contain a matching named GeoJSON polygon or multipolygon. No general online place resolver is configured.

Address-only source records go to the review queue unless a licensed lookup catalog is supplied with `--geocode-catalog geocodes.json`. The catalog format is `{ "provider": { "name": "...", "license": "...", "attribution": "...", "allowed_uses": ["internal"], "commercial_use": false }, "entries": [{ "id": "...", "address": "...", "lat": 0, "lon": 0, "confidence": 0.5 }] }`. It is an optional pluggable local provider, not an online geocoding service. Matched records are marked `geocode_derived`, with geometry provenance and a confidence ceiling of 0.5. OSM way/relation centers are never silently used as verified POI points.

## Live OpenStreetMap collection

The included registry contains an Overpass adapter driven by the packaged 244-leaf taxonomy. Provide a real operator contact before making a live request:

```powershell
.\run.ps1 run --bbox 24.65 46.62 24.79 46.79 --intent "pharmacies in Riyadh" --sources openstreetmap --contact you@example.com --use internal --out output/riyadh
```

Live requests fail closed when `robots.txt` cannot be reached or disallows the endpoint. An HTTP 4xx for `robots.txt` is treated as unavailable under RFC 9309. Source policies in `sources.json` are **operator declarations**, not a legal determination. Review the ODbL and any source-specific terms before commercial use or redistribution. Both uses are deliberately disabled for the OSM source in the starter registry pending that review. The agent never fabricates a missing translation.

The registry also includes a Swiss OSM Overpass source for a real local test. The 2026-09-25 Zurich run collected 30 pharmacy nodes. The global Overpass endpoint timed out from this PC, so the Swiss test does not verify the Riyadh benchmark.

Natural-language intent can name more than one category. A corrected Zurich run publishes 42 pharmacy/clinic records; a bakery run collected 35 `shop=bakery` POIs. Two same-name clinic nodes with different phone numbers are kept separate. Core Arabic pharmacy, clinic, hospital, and school terms are supported; the other taxonomy leaves currently have English labels only.

```powershell
.\run.ps1 run --bbox 47.37 8.52 47.39 8.55 --category pharmacy --sources osm_swiss --contact you@example.com --out output/zurich-osm-real
.\run.ps1 publish --out output/zurich-osm-real --layer poi_pharmacy --database poi_agent_test --schema osm_live --workspace poi_osm_live
.\run.ps1 verify-local --database poi_agent_test --schema osm_live --workspace poi_osm_live --layer poi_pharmacy --out output/zurich-osm-real
```

Publish an existing harvest with `publish` to avoid a second network request. Use a separate database schema or layer name for each independent dataset; the publisher rejects a workspace that would overwrite another workspace's table.

The shipped taxonomy is [src/poi_harvester/taxonomy.json](src/poi_harvester/taxonomy.json). It has 244 leaves, 249 OSM tag mappings, 62 Google Places type mappings, and 98 Wikidata class mappings. Google mappings use exact type names or explicit overrides; Wikidata class mappings require a P1282 OSM tag statement plus an exact English label match. Other P1282 matches are kept as review candidates. Rebuild the snapshot with `python scripts/build_taxonomy.py --contact you@example.com`.

## PostGIS and GeoServer publication

For the native Windows setup on this PC, see [LOCAL_SETUP.md](LOCAL_SETUP.md). PostgreSQL 17 has PostGIS 3.6.2, and GeoServer 2.28.5 is available locally. The end-to-end test passed for both the default `public` schema and a custom schema.

The agent reads an editable `.env` in the project root automatically, or a different file passed with `--env-file`. Copy `.env.example` for a new server. `.env` is git-ignored, and process environment variables take precedence over file values. The file contains only connection settings: `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `GEOSERVER_URL`, `GEOSERVER_USER`, and `GEOSERVER_PASSWORD`.

For another server, edit those connection values. On each publishing run, give `--database` and `--workspace`. Add `--schema` when the table should be in a schema other than `public`. The layer name defaults to `poi_<category>`; `--layer` can change it. For unusual network setups, optional `GEOSERVER_PGHOST` tells GeoServer which database address to reach, and `PGSSLMODE` sets the agent's PostgreSQL TLS mode.

Run the local test with the included PowerShell launcher. It uses Python available on this PC and loads `.env` automatically:

```powershell
.\scripts\start-native-geoserver.ps1
.\run.ps1 run --bbox 24.70 46.66 24.73 46.69 --category pharmacy --sources 'demo,demo_alt' --out output/local --publish --allow-demo-publish --database poi_agent_test --workspace poi_agent_test
.\run.ps1 verify-local --database poi_agent_test --workspace poi_agent_test --layer poi_pharmacy --out output/local
```

For a different schema, add `--schema your_schema` to both commands. `verify-local` reads the PostGIS view, checks its count, SRID, and provenance, then checks GeoServer's default style, source attribution, and WMS capabilities.

Install the optional driver with `pip install ".[postgis]"` before publishing. The publisher retains source records in a PostGIS table, exposes an active-record view as the layer, registers that view in GeoServer, and applies a simple SLD point style. Each POI attribute and its field provenance has a dedicated PostGIS/GeoServer column; list values use JSON array text in their own columns so WFS can expose them. GeoJSON uses the standard `properties` object to hold its named attributes. Database and GeoServer credentials are read from environment variables and must not be committed.

The publisher has been validated against the local services on this PC. Other servers still need their own connection and permission checks. The GeoServer REST endpoint must be writable by the configured user, and PostGIS must be enabled in the selected database.

A container build is available with `docker build -t poi-harvester .`; run it with a mounted output directory and the CLI arguments above. Docker is not installed in this workspace, so this image has not yet been built here.

For a complete local PostGIS + GeoServer demo on Windows after Docker Desktop is installed and running:

```powershell
.\scripts\run-local-demo.ps1
```

The script creates random local passwords in the git-ignored `.env.container`, starts `postgis/postgis:17-3.5` on host port 5433 and the official GeoServer 2.28.5 image on host port 8080, then runs the agent with `--publish`. The existing Windows PostgreSQL service on port 5432 is left alone. To stop the demo services without deleting their data, run `.\scripts\stop-local.ps1`.

## Current scope and gaps

See [AGENT1_AUDIT.md](AGENT1_AUDIT.md) for a requirement-by-requirement result. This is a **working vertical slice**, not yet a claim that all bounty acceptance criteria are met. Bilingual enrichment remains absent: 0 of 42 records in the corrected live Zurich mixed layer have both Arabic and English names. Named AOIs and geocoding require operator-supplied local catalogs. Gold benchmark conflation/category/coordinate scores, Arabic human quality, full crosswalk review, and production validation of source licenses remain unverified. The live global Overpass test on this PC timed out twice on 2026-09-25; Zurich OSM runs completed and published real source nodes locally. The linked Common Agent Contract is not reproduced in the PDF; its exact interface and repository structure must be checked before submission.

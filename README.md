# POI Harvester Agent

An executable starting point for the GURA POI Harvester bounty. It collects from a declared source registry, checks the declared use before any source access, normalizes POIs, merges likely duplicates, preserves field-level provenance, writes an incremental change set, and can publish the spatial layer to PostGIS and GeoServer.

## Run the local fixture

Python 3.11+ is sufficient for the local run; no API key, database, or installed Python package is needed.

```powershell
python run.py run --bbox 24.70 46.66 24.73 46.69 --category pharmacy --sources demo,demo_alt --out output/demo
python run.py replay output/demo
python -m unittest discover -s tests -v
```

The first command writes `poi.geojson`, `records.json`, `raw.json`, `sources_snapshot.json`, `changes.json`, `metadata.json`, `review_queue.json`, plus `source_capture.json`, `provenance.json` and `timings.json`. The replay command reconstructs the same merged records from captured raw data, without network access or an LLM.

The callable `poi_harvester.agent.invoke(payload)` provides the same workflow to a front end, another agent, or a trigger. It asks for a missing area, category, database, or workspace. It publishes by default; pass `"publish": false` for a file-only preview. `agent.json` documents its current inputs and outputs; it is not a substitute for the linked Common Agent Contract.

For a subsequent harvest, pass `--previous output/demo/records.json` and use a new `--out` directory. This emits added, updated, removed, and unchanged IDs with field-level changes.

For an exact WGS84 polygon AOI, use `--polygon fixtures/riyadh_small_aoi.geojson` instead of `--bbox`. The source query uses the polygon's bounds and the agent filters records against the polygon before merging. Polygon holes and multipolygons are supported. Non-WGS84 coordinates are not supported. To resolve a named AOI, use `--place "Place name"` with either `--place-catalog places.geojson` or an explicit licensed `--place-provider provider.json`. The local catalog contains named GeoJSON polygons or multipolygons; the HTTP adapter accepts Nominatim-compatible search results. An English or Arabic `--intent` can extract a place, category and nearby radius. Ambiguous results ask for a more specific place. Nearby point or road results use a derived bounding box and carry low-confidence area provenance.

Address-only source records go to the review queue unless a licensed lookup catalog is supplied with `--geocode-catalog geocodes.json`. The catalog format is `{ "provider": { "name": "...", "license": "...", "attribution": "...", "allowed_uses": ["internal"], "commercial_use": false }, "entries": [{ "id": "...", "address": "...", "lat": 0, "lon": 0, "confidence": 0.5 }] }`. An explicit `--geocode-provider provider.json` also supports licensed Nominatim-compatible live lookup. Ambiguous results go to review; derived coordinates retain provider attribution and confidence at most 0.5. Matched records are marked `geocode_derived`, with geometry provenance and a confidence ceiling of 0.5. OSM way/relation centers are never silently used as verified POI points.

## Live OpenStreetMap collection

The included registry contains an Overpass adapter driven by the packaged 244-leaf taxonomy. Provide a real operator contact before making a live request:

```powershell
.\run.ps1 run --bbox 24.65 46.62 24.79 46.79 --intent "pharmacies in Riyadh" --sources openstreetmap --contact you@example.com --use internal --out output/riyadh
```

Live requests fail closed when `robots.txt` cannot be reached or disallows the endpoint. An HTTP 4xx for `robots.txt` is treated as unavailable under RFC 9309. Source policies in `sources.json` are **operator declarations**, not a legal determination. Review the ODbL and any source-specific terms before commercial use or redistribution. Both uses are deliberately disabled for the OSM source in the starter registry pending that review. Missing Arabic or English names are filled by a deterministic rule baseline: generic establishment terms are translated and proper names are transliterated. Original names are preserved, generated fields carry method/version/confidence and provenance, and low-confidence names go to review. Human Arabic quality is not certified.

The registry also includes a Swiss OSM Overpass source for a real local test. The 2026-09-25 Zurich run collected 30 pharmacy nodes. The global Overpass endpoint timed out from this PC, so the Swiss test does not verify the Riyadh benchmark.

Natural-language intent can name more than one category. A corrected Zurich run publishes 42 pharmacy/clinic records; a bakery run collected 35 `shop=bakery` POIs. Two same-name clinic nodes with different phone numbers are kept separate. Arabic intent supports common categories including pharmacies, clinics, hospitals, schools, restaurants, hotels, mosques, bakeries, banks, ATMs, cafes and fuel stations. The complete 244-leaf taxonomy has not been manually localized.

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

Run the local test with the included PowerShell launcher. It selects a compatible local Python runtime on this PC and loads `.env` automatically:

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

## Local evaluator and current evidence

Run the one-command offline evaluator, then inspect its machine-readable reports and readiness table:

```powershell
.\run.ps1 evaluate --out output/evaluation --readiness docs/AGENT1_READINESS.md
```

It runs the unit suite, project-authored conflation labels, license and taxonomy reports, a 10, 000-record synthetic throughput probe, exact replay, and bilingual reprocessing of the saved 42-record Zurich capture when present. This is local evidence only; the official gold labels and specified benchmark hardware were not supplied. The evaluator marks unavailable scores `NOT_CERTIFIED`. `docs/AGENT1_READINESS.md` lists A1–A12 separately.

The 42-record Zurich capture can be reprocessed without another source request and published to an isolated schema:

```powershell
.\run.ps1 reprocess --from-run output/zurich-mixed-corrected --out output/zurich-mixed-enriched
.\run.ps1 replay output/zurich-mixed-enriched
.\run.ps1 publish --out output/zurich-mixed-enriched --layer poi_clinic_pharmacy --database poi_agent_test --schema osm_enriched --workspace poi_osm_enriched
.\run.ps1 verify-local --database poi_agent_test --schema osm_enriched --workspace poi_osm_enriched --layer poi_clinic_pharmacy --out output/zurich-mixed-enriched
```

On this PC, the separate `poi_osm_enriched` layer was verified with 42 real-source points and dedicated bilingual provenance columns. The rule baseline filled both language fields for 42/42 records; low-confidence German-name transliterations require human review. The earlier `poi_osm_mixed` layer remains available.

For an explicitly authorized HTTP place resolver or geocoder, create an operator-owned JSON file with at least:

```json
{
  "name": "operator_search",
  "endpoint": "https://your-approved-service.example/search",
  "license": "operator-reviewed license",
  "attribution": "Required attribution",
  "allowed_uses": ["internal"],
  "commercial_use": false,
  "rate_limit_per_second": 1
}
```

Use `--place-provider path.json` or `--geocode-provider path.json`, plus `--contact` for a live request. The public OpenStreetMap Nominatim endpoint is rejected as a generic built-in provider; configure a self-hosted or licensed third-party service under its own terms. No live geocoder or named-place provider was available for this PC's run; their adapters are verified with mocked provider responses.

See [AGENT1_AUDIT.md](AGENT1_AUDIT.md) for the requirement audit and [CONTRACT_BLOCKER.md](CONTRACT_BLOCKER.md) for the missing Common Agent Contract. No official bounty score or contract compliance is claimed.

## Reproduce from a clean clone

On Windows PowerShell with Python 3.12 installed:

```powershell
git clone https://github.com/yousef266/POI.git
cd POI
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[postgis]"
Copy-Item .env.example .env
```

Edit `.env` with your own PostgreSQL and GeoServer connection settings. Give the database name and workspace at run time; schema is optional. Run the offline fixture and evaluator:

```powershell
.\.venv\Scripts\python.exe run.py run --bbox 24.70 46.66 24.73 46.69 --category pharmacy --sources demo,demo_alt --out output/demo
.\.venv\Scripts\python.exe run.py replay output/demo
.\.venv\Scripts\python.exe run.py evaluate --out output/evaluation --readiness docs/AGENT1_READINESS.md
.\.venv\Scripts\python.exe scripts/benchmark_agent1.py
.\.venv\Scripts\python.exe -m unittest tests.test_zurich_regression -v
```

The 10K command is a synthetic local pipeline probe. The Zurich regression fixture reproduces the same-name/different-phone merge pattern with invented records. The original 42-record live capture is stored locally under `output/zurich-mixed-corrected` and is deliberately not committed as redistributed OSM data. On this PC, reprocess and replay it with `.\run.ps1 reprocess --from-run output/zurich-mixed-corrected --out output/zurich-mixed-enriched` followed by `.\run.ps1 replay output/zurich-mixed-enriched`. A fresh live Zurich request can be made with the `osm_swiss` example above, but the live feature count can change.

## Submission verification and Arabic review

Current transformations use enrichment `rules-v2` and conflation version 3; historical conflation versions 1 and 2 remain replayable. Known conflicting phone numbers block new cross-source merges, including a bridge through a record without a phone. Address similarity is diagnostic and cannot override distance/category/phone guards.

HTTP transport is serialized per source endpoint across processes, including robots checks. After each response it waits at least the configured interval plus the measured wall-clock resolution. A 429 Retry-After cooldown is shared across processes. The local concurrent test measures actual loopback HTTP arrivals with a high-resolution clock; no real external source is hammered.

The offline evaluator runs tests, repeated 50/50/20 incremental refresh, two canonical replays with capture-integrity hashes, taxonomy/license reports, the synthetic 10K probe and an unreviewed 100-name Arabic dataset. Include actual PostGIS/GeoServer publication only when services and `.env` are configured:

```powershell
.\run.ps1 evaluate --out output/submission-evaluation --local-services --database poi_agent_test --schema poi_submission_probe --workspace poi_submission_probe
.\run.ps1 benchmark --out output/benchmark-publication --publish --database poi_agent_test --schema poi_submission_probe --workspace poi_submission_probe
```

These explicit publication commands create synthetic test layers in the selected isolated schema/workspace. The evaluator also reads saved publication targets in this PC's existing Zurich captures when they use the same database, and verifies those layers without republishing them.

Review the 100 project-authored generated names yourself:

```powershell
.\run.ps1 review-names --interactive --reviewer "YOUR NAME" --ratings output/arabic-review/ratings.json --out output/arabic-review/score.json
```

A blank review has no score; a partial review does not become an A8 pass. See [docs/ARABIC_REVIEW.md](docs/ARABIC_REVIEW.md) for the accept/reject/skip/resume workflow. Official status stays `NOT_CERTIFIED` even after a local human review.

The benchmark separates harvesting/normalization, conflation/reconciliation, audit/artifact writing, PostGIS, GeoServer, publication target checks and complete pipeline time. It also records process CPU time, peak RSS and host CPU/RAM when available. These are measurements from this PC, not official hardware results.

For a Docker-enabled host:

```powershell
docker build -t poi-harvester .
docker run --rm --entrypoint python poi-harvester -m unittest discover -s tests -v
docker run --rm -v "$($PWD.Path)/output:/app/output" poi-harvester evaluate --out output/container-evaluation
```

The image includes tests, scripts, fixtures and documentation. Docker is not installed on this PC, so the image build/run is `NOT_AVAILABLE` locally; the equivalent native workflow is tested. Secrets and local runtimes are excluded from the build context.

See [docs/DESIGN.md](docs/DESIGN.md), [docs/LOCAL_EVALUATION.json](docs/LOCAL_EVALUATION.json) and [docs/AGENT1_READINESS.md](docs/AGENT1_READINESS.md). Raw live OSM captures and service credentials remain local and are excluded from Git. Fresh run timestamps and measured runtimes can change; captured transformation/replay results remain deterministic.

## Snapshot safety and final blocker verification

The CLI/API reject older snapshots and default to a 24-hour maximum age for live
OSM snapshots. Failures do not silently fall back or publish removals. Equivalent
English/Arabic requests can explicitly use one immutable capture:

```powershell
.\run.ps1 run --intent "I want all pharmacies in Cairo" --place-catalog PATH_TO_CATALOG --snapshot-from PATH_TO_CAPTURE --sources openstreetmap --use internal --out output/cairo-english
.\run.ps1 run --intent "عايز كل الصيدليات في القاهرة" --place-catalog PATH_TO_CATALOG --snapshot-from PATH_TO_CAPTURE --sources openstreetmap --use internal --out output/cairo-arabic
```

These are historical runs with the original source timestamp, not fresh harvests.
The durable latest-version guard still applies. `--allow-source-centers` is an
explicit option for captured OSM footprint centers; these remain derived, with
coordinate confidence capped at 0.35. It is not required for source node points.
Genuinely unnamed POIs remain unnamed and do not count as bilingual.

See [the new verification report](docs/BLOCKER_RESOLUTION.md) and
[snapshot policy](docs/DESIGN.md#snapshot-freshness-and-explicit-historical-processing).
Local evidence remains under `output/blockers-resolution`; runtime data and
credentials are excluded from Git. Official benchmarks and human review are
reported separately from local test results.

## Evidence and completeness

`metadata.json` includes `bilingual_measurements`: the complete record denominator,
valid bilingual names including generated translations, and source-authoritative
bilingual names with field provenance. The stricter authoritative measurement
excludes generated names, empty/malformed strings, missing provenance and wrong
scripts. Script validity does not certify linguistic quality. The legacy
`bilingual_complete_count` and record `language_complete` fields retain their
presentation semantics for compatibility with captured replay.

Snapshot descriptors expose `CURRENT`, `HISTORICAL`, `STALE` or `UNKNOWN`.
Publication rechecks age and version and exposes the state in layer metadata.
An explicit capture pin always reports `HISTORICAL` and retains the original
retrieval timestamp; input-access time is recorded separately. Failed CLI/API
refreshes report `FAILED_REFRESH`, with no automatic stale fallback.

Robots matching supports wildcards, end anchors, combined matching agent groups,
longest-rule precedence, and conservatively honors unrooted provider exclusions.
See [the September 27 evidence investigation](docs/EVIDENCE_INVESTIGATION.md)
for actual results, source restrictions, and the disclosed audit request incident.

## Latest human review and performance correction

Yousef explicitly accepted all 100 existing Arabic review examples. The exact IDs
and input names remain unchanged. Decisions are in
`fixtures/arabic_name_review_human_ratings.json`; the canonical-hash manifest is
`fixtures/arabic_name_review_manifest.json`. Apply them using:

```powershell
.\run.ps1 evaluate --ratings fixtures/arabic_name_review_human_ratings.json --out output/evaluation-reviewed
```

Human review is complete: 100 reviewed, 100 accepted, 0 rejected, 0 unreviewed. The
priority queue has 30 IDs from the 100-example corpus; export with `--ratings` to
show those decisions. The original unrated input fixture is preserved for
reproducible generation/tests. No names or POI data were invented or changed.

The PDF's A7 measures bilingual fields **after enrichment**; generated translations
are permitted. For Cairo the denominator remains 155, including 15 unnamed POIs.
`ceil(0.95 * 155)=148`; current 140/155 means 8 additional legitimately named bilingual
records are needed. The 63/155 source-authoritative metric is diagnostic, not a
separate requirement imposed by the PDF. No unnamed-record exclusion is specified.

The 10K performance grid has invented geometry. It is a synthetic load test only,
not valid evidence for real-POI throughput or location accuracy. A11 is now
NOT_CERTIFIED, with explicit dataset/geometry labels in benchmark output.
See [the corrected final verification](docs/FINAL_VERIFICATION.md).

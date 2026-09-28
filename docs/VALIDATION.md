# Local validation — September 28, 2026

## Regression suite

`python -m unittest discover -s tests -v` completed with **170 passed, 0 failed, 0 skipped**. All previously passing tests are retained. Nine publication-schema tests cover required fields, empty optional fields, populated provenance, numeric public identity, deterministic projection, and GeoServer attribute bindings/cache refresh.

The complete evaluator with local PostGIS/GeoServer also passed all 170 tests. A new Python environment installed the package from scratch and independently passed the same 170 tests. Installation/test logs are under ignored `output/release-clean-*`; evaluator evidence is under `output/schema-final-evaluation/`.

## Database and GeoServer

The real-source layer `poi_jeddah_live:poi_bank` contains **84** records in database `poi_agent_test`, schema `poi_jeddah_live`. Local verification passed PostGIS/WFS/WMS, EPSG:4326, dedicated fields, provenance, styling and attribution checks. All 84 node coordinates match captured source coordinates; this does not measure positional error against independent gold labels.

The published schema changed from 61 to 52 columns. The integer serial primary key is `id`; internal `stable_id` is absent from public WFS attributes. Required canonical fields remain; entirely empty optional fields are omitted. Repeated publication preserves IDs and coordinates. A separate database regression confirmed preserved IDs across updates, unchanged records, removal and reactivation.

Source timestamp: **2026-07-24T11:04:51+00:00**. The run is explicitly disclosed as older available source data. It contains 81 bilingual records and 3 genuinely unnamed records; unresolved-coordinate records are retained in the review evidence, not fabricated into the layer.

Local evidence is saved under ignored `output/jeddah-banks-20260928/` and `output/schema-final-tests.log`. Credentials and runtime files are excluded from Git.

## Human Arabic review

- AI assessed: 100.
- Human reviewed: 100.
- Human accepted: 100.
- Human rejected: 0.
- Unreviewed: 0.

Exact original example IDs and accepted decisions are bound by the tracked review manifest and ratings under `fixtures/`. See [ARABIC_REVIEW.md](ARABIC_REVIEW.md). This is the user's human attestation; no interactive review session or official judge decision is invented.

## Evidence scope

Automated evaluation retains the 50-added/50-updated/20-removed/30-unchanged incremental fixture, offline deterministic replay, bilingual parity, snapshot safety, timeout and geometry regressions.

This evaluator run reproduced **50 additions, 50 updates, 20 removals, and 30 unchanged records**, including field-level differences and identical repeated change sets. Canonical replay and capture-integrity checks passed without network access or an LLM.

The 10,000-record grid is an explicitly synthetic processing/publication load probe. Its invented coordinates do not demonstrate real POI harvesting, real-world location accuracy, or official A11 throughput. Local test results and the completed human sample do not constitute official certification. The evaluator reports the actual evidence status for each criterion; official scores are not manufactured.

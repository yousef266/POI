# Agent 1 audit against the bounty PDF

Date: 2026-09-25. The PDF's Agent 1 requirements are on pages 6–7. This report distinguishes implemented behavior from benchmark certification. No gold labels or Common Agent Contract were available.

## Functional requirements

| PDF item | Result | Evidence / remaining work |
| --- | --- | --- |
| 1. AOI and English/Arabic intent | Partial | Bbox, polygon with holes, multipolygon, and named boundary from an operator-supplied GeoJSON catalog work. English taxonomy labels and four curated Arabic category groups work. No online place resolver or broad Arabic taxonomy intent yet. |
| 2. Source registry | Partial | Declarative source entries include endpoint or local path, license, attribution, allowed uses, commercial flag, rate, coverage, freshness, reliability. Only OSM Overpass and fixture adapters are implemented. |
| 3. License gate and attribution | Implemented locally; full benchmark unverified | Source eligibility is checked before collection. Disallowed sources are excluded with a reason. Attribution is carried into records, metadata, PostGIS fields and GeoServer abstract. Source policy declarations still need legal/operator validation. |
| 4. Rate and etiquette | Partial | Honest contact-bearing User-Agent, robots check, per-process/per-source throttling, configurable lower ceiling, retry/backoff, and conditional requests are implemented. Robots denial, token timing, ceiling and HTTP 304 are tested. A concurrent multi-process load test is still required. |
| 5. Canonical schema | Implemented locally | Dedicated database/WFS columns include IDs, names, category, location, contact, address, hours, timestamp, confidence, geometry and field provenance. |
| 6. Conflation | Implemented; gold accuracy unverified | Spatial/name/category/phone matching, Arabic name comparison, field provenance, stable IDs. A real false merge between two Zurich clinics with the same name but different phones was fixed; current layer has 42 separate points. Historical runs retain exact replay via algorithm versioning. |
| 7. Geocoding fallback | Partial | A licensed operator-supplied address catalog is pluggable. Derived points have a geometry provenance ID and confidence at most 0.5. Tested with an address-only fixture. No live geocoding service configured or tested. |
| 8. Taxonomy | Partial | 244 leaves, 249 OSM tag mappings, 62 Google type mappings, 98 Wikidata class mappings. Crosswalk coverage and classification against gold labels are unverified. |
| 9. Bilingual enrichment | **Missing** | Existing source `name:ar`/`name:en` values are preserved, but missing names are not translated or transliterated. Corrected Zurich mixed run: 0/42 bilingual records. |
| 10. Incremental refresh | Implemented locally | A seeded fixture with 50 adds, 50 phone updates, 20 removals gave exactly those classifications plus 30 unchanged, with field-level diffs and exact replay. Real corrected Zurich rerun: 1 add, 1 update, 40 unchanged. |
| 11. Publication | Implemented locally | Real OSM layers published to PostGIS 17/PostGIS 3.6 and GeoServer 2.28.5. Counts, SRID, source coordinates, provenance, WFS fields, WMS availability, attribution metadata and category style were verified. |

## Acceptance criteria

| Gate | Current evidence | Status |
| --- | --- | --- |
| A1 license 100% | Local license-denial test and CLI commercial-use attempt against `osm_swiss` blocked before collection, with no output directory | Full benchmark and legal correctness unverified |
| A2 robots/rate 0 violations | Unit tests for disallow, timing, ceiling, HTTP 304; live Swiss source access | Load test unverified |
| A3 attribution 100% | Real local DB and GeoServer checks across published runs | Passed on local runs; benchmark unverified |
| A4 conflation precision ≥0.92 | Corrected one real false merge | Gold labels unavailable |
| A5 conflation recall ≥0.85 | OSM ways without verified geometry are reviewed rather than published | Gold labels unavailable; likely coverage risk |
| A6 category accuracy ≥0.88 | Taxonomy and tag query tests | Gold labels unavailable |
| A7 bilingual completeness ≥0.95 | 0/42 bilingual in corrected live mixed run | **Fails local sample** |
| A8 Arabic quality ≥0.90 | No generated Arabic names or human review sample | Unverified |
| A9 median coordinate offset ≤25 m | 42/42 corrected live records match captured OSM node coordinates exactly through PostGIS | Gold source-of-truth unavailable |
| A10 seeded change F1 ≥0.95 | 50/50/20 synthetic run classified all seeded changes correctly | Passed synthetic test; official seed unavailable |
| A11 ≥10k POIs/hour on 4 vCPU/8 GB | Current code harvested 10,000 synthetic POIs in 2.882 seconds with exact replay. A separate local DB/GeoServer publication took 41.756 seconds; all 10,000 were verified | Passed local scale probe; specified hardware/source benchmark unverified |
| A12 exact replay | Demo, three historical live runs, corrected 42-point run and 10,000-point synthetic run replayed identically | Passed tested snapshots; official full benchmark unavailable |

## Local published outputs

- `poi_osm_live:poi_pharmacy`: 30 real OSM node points.
- `poi_osm_mixed:poi_clinic_pharmacy`: 42 real OSM node points after the false merge fix.
- `poi_osm_bakery:poi_bakery`: 35 real OSM node points.
- `poi_benchmark:poi_pharmacy`: 10,000 invented fixture points, explicitly marked demo.
- `poi_agent_test:poi_pharmacy`: 2 invented fixture points, explicitly marked demo.

Each live layer is in the `poi_agent_test` database with its own schema. `output/zurich-mixed-corrected` is the current mixed-layer harvest; `output/zurich-mixed-real` is retained as a historical exact-replay snapshot. The local benchmark is under `output/benchmark-10000`.

## Submission blockers

1. Build and validate bilingual enrichment, especially Arabic proper-name transliteration versus generic-term translation.
2. Obtain the official gold benchmark and measure A1–A12 on its labels and specified hardware. The user has no kickoff benchmark yet.
3. Obtain the linked Common Agent Contract and align the package/interface before submission. The user has no contract file yet.
4. Validate source licenses and commercial/redistribution permissions with the operator. The default OSM registry allows internal use only.
5. Connect and test a real named-place resolver and live geocoding provider if those are required without operator-supplied catalogs.
6. Create the required Git repository/source deliverable; this workspace currently has no Git repository.

# Agent 1 submission readiness

Generated from actual local evidence. Every official status remains NOT_CERTIFIED.

| Criterion | Local status | Official status | Evidence | Remaining blocker |
| --- | --- | --- | --- | --- |
| A1 | PASS | NOT_CERTIFIED | Denied sources are never collected; declarations validated | Official benchmark and operator/legal approval |
| A2 | PASS | NOT_CERTIFIED | Four-process pacing and actual loopback HTTP arrivals; robots, retry/date/backoff, ceiling and 304 tests | Official deployment/source workload |
| A3 | PASS | NOT_CERTIFIED | Fixture provenance/attribution; optional real publication verification | Official benchmark attribution audit |
| A4 | PASS | NOT_CERTIFIED | Project-authored pairwise labels; conflicting-phone and Zurich regressions | Official labelled Riyadh and held-out AOI |
| A5 | PASS | NOT_CERTIFIED | Project-authored pairwise labels | Official labelled Riyadh and held-out AOI |
| A6 | NOT_CERTIFIED | NOT_CERTIFIED | 244-leaf taxonomy validated; unmapped/ambiguous mappings reported | Official category gold labels |
| A7 | PASS | NOT_CERTIFIED | Generated names preserve source values and carry method/version/confidence/provenance | Official corpus bilingual coverage |
| A8 | NOT_CERTIFIED | NOT_CERTIFIED | 100 deterministic generated names with explicit human-rating workflow | Human Arabic review of a representative official sample |
| A9 | NOT_CERTIFIED | NOT_CERTIFIED | Local source-coordinate preservation is separate from real-world accuracy | Gold source-of-truth coordinates |
| A10 | PASS | NOT_CERTIFIED | Repeated fixture classifies 50 adds, 50 updates, 20 removals, 30 unchanged | Official seeded change set |
| A11 | PASS | NOT_CERTIFIED | 10K synthetic probe with separate phases, CPU/memory and optional publication | Official 4-vCPU/8-GB source workload |
| A12 | PASS | NOT_CERTIFIED | Two exact canonical replays; capture integrity and transformation/conflation sidecars | Official full provenance replay corpus |

## Commands and outputs

Each criterion in the machine-readable report includes its command and observed output.
Tests: 110; passed: 110; failed: 0; skipped: 0.
Arabic review: 0/100 reviewed; status NOT_REVIEWED.

## External blockers

- Common Agent Contract and official gold labels are unavailable.
- Source policy declarations require operator/legal approval.
- Human Arabic ratings and official benchmark hardware are unavailable.
- No licensed live place/geocoder provider is configured.

## Cairo blocker-resolution verification (2026-09-27)

See [BLOCKER_RESOLUTION.md](BLOCKER_RESOLUTION.md) and
[BLOCKER_RESOLUTION.json](BLOCKER_RESOLUTION.json) for current source-level
verification and missing official evidence. All 110 tests pass with zero failures
and skips, including all original 80 tests unchanged and 30 added regressions.

The A7 local PASS above is for the evaluator's synthetic fixture. The two Cairo
intents use the same explicitly pinned July 24 capture: 155 POIs, 140 bilingual
and 15 genuinely unnamed (90.32% completeness). The four OSM way centers are
opt-in derived points with confidence 0.35, not verified entrances. The configured
provider cannot currently demonstrate freshness within the default 24-hour live
policy; the public alternative was blocked by robots.txt and was not bypassed.
Stale live/captured publication attempts were rejected without false removals.
Final layer `poi_cairo_final_0926:poi_pharmacy` passed WFS, WMS, geometry, attributes,
CRS, styling, attribution and provenance checks.

AI review: 100 synthetic names assessed, 70 provisionally acceptable, 30 needing
review, zero human reviews. Official statuses remain NOT_CERTIFIED. No optional
provider configuration is needed for the verified captured Cairo AOI flow.

**NOT READY FOR SUBMISSION**: current source access/freshness/names, human review,
official gold, Common Agent Contract, legal/provider approval and official hardware
evidence remain unavailable. No implementation blocker was observed in this pass.

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
Tests: 77; passed: 77; failed: 0; skipped: 0.
Arabic review: 0/100 reviewed; status NOT_REVIEWED.

## External blockers

- Common Agent Contract and official gold labels are unavailable.
- Source policy declarations require operator/legal approval.
- Human Arabic ratings and official benchmark hardware are unavailable.
- No licensed live place/geocoder provider is configured.

## Release package checks

- Installed 0.3.0 wheel in a fresh isolated Python environment: 77/77 tests passed; offline evaluator passed.
- Updated real-source layer `poi_osm_submission_0926:poi_clinic_pharmacy`: 42 points, 42 bilingual, 42 generated Arabic flags and 42 `rules-v2` values verified in PostGIS. WMS PNG, WFS geometry/values, provenance, styling and source-node coordinates passed.
- Existing 30/35/42-point live layers and prior 42-point bilingual layer were checked without republishing them.
- The detailed submission snapshot is `docs/LOCAL_EVALUATION.json`; all official scores remain NOT_CERTIFIED.
- Docker is unavailable on this PC; build/run commands are prepared in README.

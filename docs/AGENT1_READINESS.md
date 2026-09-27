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
Tests: 136; passed: 136; failed: 0; skipped: 0.
Arabic review: 0/100 reviewed; status NOT_REVIEWED.

## External blockers

- Common Agent Contract and official gold labels are unavailable.
- Source policy declarations require operator/legal approval.
- Human Arabic ratings and official benchmark hardware are unavailable.
- No licensed live place/geocoder provider is configured.

## September 27 Cairo and audit qualifications

See [EVIDENCE_INVESTIGATION.md](EVIDENCE_INVESTIGATION.md) for final evidence.
136 tests passed with zero failures/skips; the original 110 assertions remain unchanged.
Cairo uses an explicitly historical July 24 snapshot. Both languages produce 155
records: 63 source-authoritative bilingual names (40.65%), 140 including generated
translations (90.32%), and 15 genuinely unnamed records. Both completeness measures
are below 95%. The A7 PASS above concerns only the evaluator’s fixture mechanics.
A2 regression tests pass, but one unintended disallowed metadata request occurred
during this audit before the wildcard parser fix. Zero violations cannot be claimed
for this audit; official A2 remains NOT_CERTIFIED. Human review remains 0/100.
All official A1–A12 statuses remain NOT_CERTIFIED. Local catalog-based place
resolution works; an optional live geocoder is not required for these Cairo runs.

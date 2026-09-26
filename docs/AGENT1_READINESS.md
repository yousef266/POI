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
Tests: 80; passed: 80; failed: 0; skipped: 0.
Arabic review: 0/100 reviewed; status NOT_REVIEWED.

## External blockers

- Common Agent Contract and official gold labels are unavailable.
- Source policy declarations require operator/legal approval.
- Human Arabic ratings and official benchmark hardware are unavailable.
- No licensed live place/geocoder provider is configured.

## Final real Cairo verification

The table above describes the automated fixture evaluator. The requested real Cairo E2E
does not pass full bilingual completeness: 135/150 English-capture points and 132/147
initial Arabic-capture points have both names. Fifteen unnamed source nodes remain in
the review queue. **Final broader local A7 status: FAIL**; official A7 remains NOT_CERTIFIED.

The initial Arabic source snapshot was older than the English capture and falsely
removed three records. A narrow timestamp freshness guard now rejects such refreshes
before changes/publication. Three regression tests were added without weakening
existing assertions. The newer 150-point Cairo layer was restored and verified.
The actual post-fix Arabic retry timed out externally and wrote no changes.
Identical saved-input Arabic intent produces the same 150 business records, explicitly
an offline parity check.

All 80 tests passed in the final complete regression suite (zero failures/skips).
Human Arabic review is 0/100; the separate AI assessment inspected 100 names and flagged
37 for review. No human score was fabricated. See FINAL_VERIFICATION.json for measured
commands, results, source dates, phase timings, blockers, and the NOT READY FOR SUBMISSION verdict.

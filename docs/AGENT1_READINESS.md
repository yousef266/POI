# Agent 1 submission readiness

Generated from the local offline evaluator. Local fixture results are not official bounty scores.

| Criterion | Local status | Official status | Evidence | Remaining blocker |
| --- | --- | --- | --- | --- |
| A1 | PASS | NOT_CERTIFIED | Source denial tests and declared-policy report; OSM remains internal only | Official benchmark and operator/legal validation |
| A2 | PASS | NOT_CERTIFIED | Four-process local rate test, robots denial, Retry-After, backoff and 304 tests | Official source load test and deployment environment |
| A3 | PASS | NOT_CERTIFIED | Fixture field/metadata attribution tests; local published layers checked separately | Official benchmark attribution audit |
| A4 | PASS | NOT_CERTIFIED | Project fixture pairwise precision 1.0 | Official labelled Riyadh and held-out AOI |
| A5 | PASS | NOT_CERTIFIED | Project fixture pairwise recall 1.0 | Official labelled Riyadh and held-out AOI |
| A6 | NOT_CERTIFIED | NOT_CERTIFIED | Taxonomy/crosswalk coverage reported without gold labels | Official category gold labels |
| A7 | PASS | NOT_CERTIFIED | Fixture 2/2 bilingual; captured Zurich 42/42 | Official corpus and human review of generated names |
| A8 | NOT_CERTIFIED | NOT_CERTIFIED | No 100-name human-rated Arabic sample | Human review sample |
| A9 | NOT_CERTIFIED | NOT_CERTIFIED | Captured OSM coordinates are preserved locally | Gold source-of-truth coordinates |
| A10 | PASS | NOT_CERTIFIED | Unit fixture classified 50 adds, 50 updates, 20 removals and 30 unchanged | Official seeded change set |
| A11 | PASS | NOT_CERTIFIED | Synthetic local rate 11595843 POIs/hour | Official 4-vCPU/8-GB source workload |
| A12 | PASS | NOT_CERTIFIED | Fixture and saved Zurich capture reproduce exact merged output without LLM | Official full provenance replay corpus |

## Additional blockers

- The Common Agent Contract is unavailable; see CONTRACT_BLOCKER.md.
- Source license declarations require operator validation.
- Low-confidence generated Arabic names require human review.
- The official gold labels and specified benchmark hardware are unavailable.

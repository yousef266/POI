> **Superseded by [FINAL_VERIFICATION.md](FINAL_VERIFICATION.md).** This report is a historical record of the preceding pass. Current evidence is 146/146 tests and human-reviewed/accepted 100/100, rejected/unreviewed 0. Human review is no longer a blocker. The PDF allows generated translations in A7 after enrichment; 140/155 is the applicable Cairo measurement. Previous synthetic-grid “POIs/hour” / local A11 PASS claims below are withdrawn as real-POI evidence: this was load testing with invented coordinates, and A11 is NOT_CERTIFIED. Latest refresh failed with read timeouts; the earlier HTTP 504 remains historical evidence. Blanket signed production/acquisition approval is not a universal PDF condition. See the new report for actual remaining requirements.

# Final evidence investigation — September 27, 2026

## Executive summary

**NOT READY FOR SUBMISSION.** All 136 tests passed, with zero failures and zero skips. The existing 110 tests and assertions remain unchanged; 26 regressions were added. Local publication, incremental refresh, and offline replay passed. Current source access, bilingual coverage, human review, and official evidence remain unresolved.

One unintended robots-disallowed metadata request occurred during the audit. It is disclosed below. No bulk extract was downloaded.

[Machine-readable report](EVIDENCE_INVESTIGATION.json). Previous results remain in [BLOCKER_RESOLUTION.md](BLOCKER_RESOLUTION.md).

## Root causes and fixes

1. Available Cairo captures are historical. No other authorized Cairo dataset or provider credentials were found. A guarded live refresh returned HTTP 504, wrote no output, and did not publish.
2. Python's standard robots parser missed wildcard exclusions. The agent now handles wildcards, end anchors, longest-rule priority, merged matching agent groups, and conservative unrooted exclusions. Tests verify denial before data requests.
3. Legacy bilingual flags counted generated translations. New measurements separate valid bilingual presentation fields from source-supplied names with provenance. Malformed primary fields cannot hide valid authoritative alternates. Legacy fields retain their semantics for replay compatibility.
4. Snapshot states are explicit and shown in GeoServer metadata. Pins preserve original retrieval time, while local input access is recorded separately. Failed CLI/API refreshes report FAILED_REFRESH.
5. The 30 uncertain synthetic Arabic examples have a deterministic JSON/Markdown queue integrated with the existing human workflow. It retains the 100-name denominator and creates no human decisions.

## Test results

| Run | Total | Passed | Failed | Skipped |
|---|---:|---:|---:|---:|
| Existing evaluator with local services | 136 | 136 | 0 | 0 |
| Installed package evaluation | 136 | 136 | 0 | 0 |
| Final complete regression | 136 | 136 | 0 | 0 |

The editable base installation in `.venv-final` was refreshed successfully. This was the existing isolated environment, not a newly recreated venv this pass. Its evaluator ran without adding `.local-deps` or PostGIS publication. No existing test file was edited. The new file `tests/test_evidence_integrity.py` has 26 tests covering robots, completeness, alternate names, freshness, retrieval timestamps, refresh failures, and review queues.

Exact evaluator executed:

```powershell
.\run.ps1 evaluate --out output/submission-20260926/final-verification --readiness docs/AGENT1_READINESS.md --local-services --database poi_agent_test --schema poi_final_verification_0926 --workspace poi_final_verification_0926
```

Evidence: `output/submission-20260926/final-verification/report.json`, `output/evidence-investigation/clean-environment/report.json`, and `output/evidence-investigation/final-regression.log`.

## Cairo English and Arabic

Requests: “I want all pharmacies in Cairo” and “عايز كل الصيدليات في القاهرة”. AOI: Cairo Governorate, OSM relation 4103336, not Greater Cairo.

| Measurement | English | Arabic |
|---|---:|---:|
| All POIs / denominator | 155 | 155 |
| Source-authoritative bilingual names | 63 | 63 |
| Source-authoritative completeness | 40.65% | 40.65% |
| Valid bilingual fields including generated names | 140 | 140 |
| Presentation completeness after enrichment | 90.32% | 90.32% |
| Genuinely unnamed source records | 15 | 15 |
| Valid geometries / outside AOI | 155 / 0 | 155 / 0 |

The 95% threshold is unchanged. Generated names are identified and excluded from the stricter source-authoritative numerator. Script checks do not certify linguistic quality or actual business identity.

Provider: OpenStreetMap through `https://overpass.private.coffee/api/interpreter`. Source version: **2026-07-24T11:04:51+00:00**. Original retrieval: **2026-09-26T23:53:51.183901+00:00**. Freshness: **HISTORICAL**, explicitly pinned, never claimed current.

Snapshot ID: `b3ede8d4f251d7d2b595b10a484f8c491bb132b8357fee80e95f96ce9a521d44`.
Dataset SHA256: `fa731fc50468b0ef57d06b4297ae89437436c05faffe9b113e5fab500da23942`.

Both runs used the same AOI, category, snapshot/version, canonical identities, and equivalent business records. Only execution-specific `harvested_at` was excluded from cross-run business comparison. Identity difference: empty. No newer dataset was acquired; comparison with July 24 proves reuse/parity, not that current OSM equals July 24.

Evidence under `output/evidence-investigation`: `cairo-english-final`, `cairo-arabic-final`, `cairo-parity.json`, and `freshness-validation.json`.

## Name and coordinate investigation

All 19 targeted identities were examined against 1,471 local records from real source captures. Available Cairo versions were May 31, July 15, and July 24. The investigation covered all tags, multilingual/alternate names, brand/operator fields, addresses, contacts/websites, metadata, same source IDs, nearby records, and contact-based identity matches. There were zero strong contact matches, zero recovered authoritative names, and zero mapping failures among the 15 unnamed identities. Addresses and proximity were not treated as business names.

The four ways are `way/31265047`, `way/320286872`, `way/767418927`, and `way/1499469160`. Their captures contain footprint centers only. No independently verified entrance point, parsing loss, or CRS conversion error was found. The spec permits a footprint reference and requires derived-coordinate disclosure. These explicitly enabled centers retain source payloads and footprint references; they do not certify A9 accuracy.

Coordinates: **151 source-node points, 4 derived centers, 0 unresolved points in the published selection**. All 155 are valid, inside the AOI, unique, realistic, and preserved from source coordinates. No city-center collapse occurred. All four derived geometry and overall confidence values are capped at 0.35. Source coordinates are not survey-verified gold coordinates.

Evidence: `deep-record-investigation.json`, `geometry-validation.json`, and complete Cairo source captures under `output/evidence-investigation`.

## Arabic review

Unchanged synthetic rules-v3 corpus: 100 previously AI-assessed names, 70 provisionally acceptable, 30 needing human review, **zero human-reviewed**. No human score exists. This corpus is separate from Cairo and is not an official representative sample.

Queue: `output/evidence-investigation/human-review-queue.json` and `.md`. Each item includes ID, current Arabic, source English, normalization-only proposal, reason, confidence, provenance, and a pending decision.

```powershell
.\run.ps1 review-names --queue output/evidence-investigation/human-review-queue.json --interactive --reviewer "Yousef" --ratings output/evidence-investigation/human-ratings.json --out output/evidence-investigation/human-score.json
```

Reviewing this queue remains a partial review of 100. The remaining names also need human decisions. Synthetic review does not substitute for the official representative real-source sample.

## Freshness and provider access

The May 31 snapshot was rejected by the durable version guard before output creation. The live HTTP 504 wrote no output, changes, or publication. No stale fallback or false removals occurred. Existing snapshot/timeout tests and new state tests passed. Historical publication is clearly flagged.

The [Geofabrik Egypt page](https://download.geofabrik.de/africa/egypt.html) advertises extracts, but its [robots.txt](https://download.geofabrik.de/robots.txt) excludes bulk, state, and update paths. No bulk download or connector was added.

**Audit incident:** one GET of `/africa/egypt-updates/state.txt` occurred because the exploratory script used `urllib.robotparser`, which missed wildcard/unrooted exclusions. Further restricted requests stopped. The agent parser was corrected and tested. This metadata was not imported as a current Cairo dataset. **Zero violations cannot be claimed for this audit pass.**

Matching follows the [robots standard](https://www.rfc-editor.org/rfc/rfc9309.html), with conservative handling of nonstandard exclusions. Evidence: `geofabrik-availability.json`, `live-refresh.log`, `stale-rejection.log`, and `freshness-validation.json`.

## GeoServer

Existing layer **poi_cairo_final_0926:poi_pharmacy** was republished with verified historical output. WFS returns 155 records with matching names, category, source IDs, timestamps, confidence, geometry flags, and field provenance. WMS returned a valid PNG, visually inspected with blue pharmacy markers. CRS: EPSG:4326. All geometries are valid/in AOI. `poi_harvester_style` contains the pharmacy rule. OSM attribution, historical state/timestamp, and derived warnings are present. No duplicate layer was created.

Evidence: `output/evidence-investigation/geoserver-validation.json` and `geoserver/wfs.json`, `wms.png`, `featuretype.json`, `layer.json`, and `style.sld`.

## Incremental refresh and replay

**50 additions / 50 updates / 20 removals / 30 unchanged.** Phone-field diffs were verified; repeated execution produced the identical change set. The older-snapshot attempt emitted no change set. English and Arabic outputs each replayed twice with network blocked, no LLM, and identical canonical output. Input integrity passed. Snapshot/version, freshness, and retrieval metadata are bound in provenance.

Evidence: evaluator incremental results and `cairo-offline-replays.json`.

## Local performance

10,000 synthetic POIs: **53.94 seconds**, or **667,392 POIs/hour**, including harvesting, artifacts, PostGIS, and GeoServer publication. Verification separately took 13.08 seconds. Fixture generation/setup, replay, and verification are excluded from pipeline timing; this is not total evaluator wall time. Windows 11, Intel i7-7820HQ, 8 logical CPUs, 34,213,380,096 bytes RAM (about 31.86 GiB). **Official A11: NOT_CERTIFIED**; this is not the required 4-vCPU/8-GB workload.

Evidence: `output/submission-20260926/final-verification/benchmark/report.json`.

## Contract, license, and submission evidence

The repository and local captures were inventoried. The PDF supplies A1–A12 definitions and links to the Common Agent Contract; it does not embed the contract schema. Local Jenkins access failed DNS resolution on September 27. No official gold/held-out data or contract tests were found. `conflation_gold.json` explicitly contains project-authored labels; the Arabic corpus declares synthetic examples.

`sources.json` keeps OSM limited to declared internal use. Commercial or redistribution approval was not added. [OSM license documentation](https://www.openstreetmap.org/copyright), [Psycopg license metadata](https://www.psycopg.org/download/), and [GeoServer license documentation](https://docs.geoserver.org/main/en/user/introduction/license/) are references for review, not legal approval.

Missing: intended deployment/use authorization, provider terms/version evidence, required attribution/database obligations, and complete dependency/service notices for the actual distribution. No project LICENSE file or signed approval was found; the author must decide the repository license. No legal conclusion is asserted. The required clean-container run and unedited submission demo are also unverified/absent. Native Windows services were tested; Docker is unavailable here.

## A1–A12 certification

| Criterion | Local status | Official status | Missing evidence |
|---|---|---|---|
| A1 | PASS | NOT_CERTIFIED | Operator/provider approval for intended commercial/redistribution deployment; verified license obligations and complete dependency/service notices for the actual distribution. Registry declarations are not legal approval. |
| A2 | REGRESSION_PASS; AUDIT_INCIDENT_DISCLOSED | NOT_CERTIFIED | Official deployment load test and provider compliance evidence. One unintended disallowed metadata request occurred during this audit before the wildcard fix; zero violations cannot be claimed for this pass. |
| A3 | PASS | NOT_CERTIFIED | Official contract/benchmark attribution acceptance; current local OSM attribution is present. |
| A4 | PASS | NOT_CERTIFIED | Official labelled Riyadh (~3,000 POIs, three sources) and held-out corpus for precision >=0.92. |
| A5 | PASS | NOT_CERTIFIED | Same official labelled benchmark for recall >=0.85. |
| A6 | NOT_CERTIFIED | NOT_CERTIFIED | Official category gold labels to measure >=0.88 accuracy. |
| A7 | BELOW_95_PERCENT_ON_CAIRO | NOT_CERTIFIED | Current representative official bilingual benchmark; Cairo has 63/155 source-authoritative names (40.65%) and 140/155 including generated names (90.32%); both are below 95%. |
| A8 | AI_ONLY; HUMAN_PENDING | NOT_CERTIFIED | Actual human review of 100 representative names with >=90% acceptable; zero human decisions are available. |
| A9 | SOURCE_PRESERVATION_PASS; GOLD_ACCURACY_NOT_CERTIFIED | NOT_CERTIFIED | Gold source-of-truth coordinates for median offset <=25 m; four centers remain derived, not verified entrances. |
| A10 | PASS | NOT_CERTIFIED | Official seeded benchmark; current 50/50/20/30 is a project-authored deterministic fixture. |
| A11 | PASS | NOT_CERTIFIED | Official source workload on 4 vCPU / 8 GB; current synthetic run uses 8 logical CPUs / about 32 GB. |
| A12 | PASS | NOT_CERTIFIED | Official corpus and Common Agent Contract replay requirements; local source captures replay exactly offline. |

Exact evidence paths are in the machine-readable report. The evaluator’s A7 PASS covers generated-name fixture mechanics, not Cairo’s 95% completeness.

## Files changed

- README.md
- docs/AGENT1_READINESS.md
- docs/ARABIC_REVIEW.md
- docs/EVIDENCE_INVESTIGATION.json
- docs/EVIDENCE_INVESTIGATION.md
- src/poi_harvester/agent.py
- src/poi_harvester/cli.py
- src/poi_harvester/name_review.py
- src/poi_harvester/names.py
- src/poi_harvester/pipeline.py
- src/poi_harvester/publish.py
- src/poi_harvester/robots.py
- src/poi_harvester/snapshots.py
- src/poi_harvester/sources.py
- tests/test_evidence_integrity.py

## Remaining blockers

- No authorized current Cairo POI dataset was acquired: the configured provider returned HTTP 504; alternative public/bulk paths were robots-disallowed. Final data remains July 24 historical.
- Bilingual coverage remains below 95%: 63/155 source-authoritative (40.65%) and 140/155 including generated names (90.32%). Fifteen records have no authoritative names in available evidence.
- Human Arabic quality review remains pending. The 30 uncertain synthetic examples are queued, all 100 remain human-unreviewed, and a representative real-source review sample is still required.
- No authoritative entrance evidence exists locally for four ways. Centers remain derived at 0.35 confidence; gold coordinate accuracy cannot be measured.
- Official contract files, gold/held-out datasets, and required 4 vCPU / 8 GB workload evidence are unavailable. Contract access failed local DNS lookup.
- Production provider/use and distribution-license approvals are unavailable. One audit metadata request violated a robots exclusion because of the now-fixed parser; no zero-violations claim is made.
- Clean-container execution and the required unedited submission demo of at most 10 minutes remain unverified/absent. Docker is unavailable on this PC.

## Repository and final verdict

Generated outputs and credentials remain ignored; no secrets or existing test edits were found in the changed files. See output/evidence-investigation/security-and-test-preservation.json. Final commit and clean working-tree evidence follow after this report is committed.

**NOT READY FOR SUBMISSION.** Local implementation passes; source, quality, certification, approval, and submission evidence blockers remain.

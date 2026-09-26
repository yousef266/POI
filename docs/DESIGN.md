# Agent 1 design and reproducibility

## Flow

1. Normalize English/Arabic intent into existing taxonomy IDs and a supplied or resolved AOI.
2. Validate registry declarations; apply declared-use and coverage gates before collection.
3. For HTTP sources, check robots and serialize transport per endpoint across local processes. Respect the source ceiling, post-response spacing with a measured wall-clock-resolution allowance, shared 429 cooldown, Retry-After, backoff and conditional requests.
4. Save input records before the current run's transformations in `source_capture.json`. Live Overpass records also retain the original element payload and source timestamp/version when supplied by the server.
5. Route unknown categories, ambiguous geometry and missing coordinates to review. Optional licensed geocoding produces an explicitly derived point with confidence at most 0.5.
6. Preserve source names; generate only a missing language. Translate known generic/category/location terms and transliterate proper names. Mixed-script names and numbers are supported; unfamiliar names stay low confidence and require review.
7. Conflate compatible nearby records, select verified language fields before generated fields, reconcile stable IDs, and compute incremental field changes.
8. Write canonical records, GeoJSON, changes, source snapshots, review queue, audit sidecars and timings. Optionally publish dedicated columns to PostGIS and GeoServer.

## Versioned decisions

Conflation versions 1 and 2 remain supported for historical replay. New runs use version 3, which also blocks known conflicting phone numbers across sources and through a phone-less bridge. The Zurich same-source branch guard remains in place. Address similarity is recorded as a diagnostic; it does not override distance, category or phone guards. Precision/recall on official data remain unmeasured.

Generated-name rules are versioned as `rules-v2`. Each generated field has a boolean flag, method, version, confidence and field provenance. Already bilingual records are unchanged. Captured enriched values are replayed without calling a translation service or rerunning mutable language rules.

## Capture and replay

`provenance.json` contains hashes for source captures, raw transformed records, registry, previous records and final records. It records retrieval times, source IDs/version when available, category mapping and taxonomy hash, geometry derivation, enrichment metadata, near-candidate merge/reject decisions and final field selections. Reprocessing preserves captured geocoder attribution and uses a new output directory.

Replay rebuilds normalization, versioned conflation and stable-ID reconciliation from the captured transformed records. It compares parsed record structures and a SHA-256 hash of UTF-8 JSON with sorted keys, compact separators and ordered record lists. New captures also verify every audit hash. Historical captures remain replayable and explicitly report that the new integrity sidecar was not available then.

Retrieved timestamps are captured inputs; they are not regenerated during replay. Timings and hardware measurements live outside the canonical POI records and do not affect the replay hash.

## Performance scope

The 10K dataset is project-authored synthetic data. Reports separate harvesting/normalization, conflation/reconciliation, artifact/audit writing, PostGIS publication, GeoServer registration and verification. CPU time, logical CPU count, available physical RAM and process peak RSS are recorded when supported. Setup and verification are excluded from complete-pipeline time and are identified separately. No official 4-vCPU/8-GB result is claimed.

## External requirements

The Common Agent Contract, official gold labels, operator/legal source approval and a representative human-rated Arabic sample are unavailable. Live place/geocoder adapters are optional; their configured endpoint and policy must be supplied by the operator. Offline tests use project fixtures or loopback HTTP only. Docker is optional and its build must be checked on a host with Docker installed.

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

Generated-name rules are versioned as `rules-v3`. Each generated field has a boolean flag, method, version, confidence and field provenance. Already bilingual records are unchanged. Captured enriched values are replayed without calling a translation service or rerunning mutable language rules.

## Capture and replay

`provenance.json` contains hashes for source captures, raw transformed records, registry, previous records and final records. It records retrieval times, source IDs/version when available, category mapping and taxonomy hash, geometry derivation, enrichment metadata, near-candidate merge/reject decisions and final field selections. Reprocessing preserves captured geocoder attribution and uses a new output directory.

Replay rebuilds normalization, versioned conflation and stable-ID reconciliation from the captured transformed records. It compares parsed record structures and a SHA-256 hash of UTF-8 JSON with sorted keys, compact separators and ordered record lists. New captures also verify every audit hash. Historical captures remain replayable and explicitly report that the new integrity sidecar was not available then.

Retrieved timestamps are captured inputs; they are not regenerated during replay. Timings and hardware measurements live outside the canonical POI records and do not affect the replay hash.

## Performance scope

The 10K dataset is project-authored synthetic data. Reports separate harvesting/normalization, conflation/reconciliation, artifact/audit writing, PostGIS publication, GeoServer registration and verification. CPU time, logical CPU count, available physical RAM and process peak RSS are recorded when supported. Setup and verification are excluded from complete-pipeline time and are identified separately. No official 4-vCPU/8-GB result is claimed.

## External requirements

The Common Agent Contract and official gold labels are unavailable. The existing 100-name Arabic corpus has been explicitly reviewed and accepted by Yousef; its ratings and manifest are stored in fixtures. Actual source-term compliance and deployment license declarations still require evidence. Live place/geocoder adapters are optional; their configured endpoint and policy must be supplied by the operator. Offline tests use project fixtures or loopback HTTP only. Native development can use Windows services. The required clean-container submission run still must be verified on a container-capable host.

## Snapshot freshness and explicit historical processing

The CLI and structured invocation share a durable SQLite latest-snapshot store
(`output/.source-snapshots.sqlite3`). A scope hashes source/endpoint, AOI geometry
and sorted categories, independently of input language. Captures bind the source
timestamp, element identity/version and canonical dataset hash into a snapshot ID.
Older snapshots, missing/malformed timestamps replacing known versions, source
identity mismatches and equal timestamps with different datasets fail before
changes or publication. Repeated identical snapshots are accepted deterministically.
The full source capture, including unresolved and outside-AOI records, is retained;
a conditional response does not reuse only the previously published subset.

Live runs through the CLI/API default to a maximum source snapshot age of 86,400
seconds. Configure `--max-snapshot-age-seconds` or the structured field
`max_snapshot_age_seconds` for an explicit deployment policy. The lower-level
adapter preserves its existing relative-version behavior unless the source declares
`max_snapshot_age_seconds`; callers of `pipeline.run` can pass the same option.
Timestamp ordering alone is not evidence that a source is current. Age validation
also rejects future timestamps beyond five minutes of clock tolerance.

Use `--snapshot-from PATH` / `snapshot_from` to select one integrity-checked capture
for semantically equivalent requests. This is explicit historical processing,
marked `HISTORICAL_CAPTURE_NOT_LIVE`, with its original timestamp and source ID
visible in provenance and GeoServer metadata. It does not claim live freshness.
It still cannot downgrade the latest known dataset for the same scope. Do not reset
the store to bypass a rejection. Share the store between workers using the same
source and query; it is local operational state, excluded from Git.

There is no automatic stale fallback. HTTP retries use socket timeouts, a total
data-request budget, bounded streaming reads and the provider's full Retry-After.
An exhausted budget, cancellation, malformed response or freshness failure is an
error. Source acquisition finishes before writing changes or publishing; failed
acquisition leaves existing output and published records intact. The current
Overpass data-request policy is two attempts, 60-second socket timeouts and a
150-second total budget; robots verification is a separate prerequisite.

## Names and unresolved geometry

OSM multilingual, official, short and alternate name fields are resolved through
the normal adapter. Unicode comparison keys normalize diacritics, tatweel and
Arabic/Persian variants; published source spellings and the original payload remain
available. Empty/malformed values do not satisfy bilingual completeness. Generic
establishment terms are translated; uncertain proper-name transliterations retain
low confidence and review reasons. The versioned synthetic review corpus was
regenerated with the same 100 source examples for rules-v3. Its immutable input
fixture remains unrated; the supplied human ratings overlay records 100 ACCEPT
decisions without altering the examples. Name selection in conflation preserves the selected field's provenance.

Records without source names remain unnamed, with `name_status`, a reason and
field provenance. Nearby records, operator names and brands are not substituted
without evidence that they identify the establishment.

Overpass way/relation centers are footprint-derived coordinates, not verified
entrances. The default behavior still retains them as unresolved review records.
`--allow-source-centers` / `allow_source_centers: true` explicitly permits valid
captured centers. Their original payload, footprint reference, derivation method,
geometry provenance, derived flag and coordinate confidence survive normalization,
conflation and publication; confidence is capped at 0.35. Missing/invalid centers
are not fabricated. Licensed geocoding likewise remains explicitly derived.

Replay uses captured transformed inputs and versioned conflation. It never performs
freshness checks against today's clock, network requests, translation regeneration
or LLM calls; snapshot descriptors are captured provenance verified by integrity
hashes. Cross-request parity compares canonical POI identities and business fields,
excluding the distinct execution timestamps.

## Performance evidence correction

The 10,000-record grid contains invented locations. It remains a processing and
publication load probe, not a valid real-POI harvest/geometry benchmark. The evaluator
now reports A11 as NOT_CERTIFIED even when the grid is processed quickly. Real
source acquisition, correct real-world locations and the required hardware were
not demonstrated by this probe.

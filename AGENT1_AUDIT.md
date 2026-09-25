# Agent 1 audit against the bounty PDF

Date: 2026-09-25. The PDF's Agent 1 requirements are on pages 6–7. See [docs/AGENT1_READINESS.md](docs/AGENT1_READINESS.md) and the machine-readable `output/evaluation-final/report.json` for A1–A12 results. The local evaluator passed 52 tests; no official gold labels or Common Agent Contract were available.

| PDF requirement | Local implementation and evidence | Limit |
| --- | --- | --- |
| AOI and English/Arabic intent | Bbox, polygons with holes, multipolygons, catalog boundaries, explicit HTTP place resolver, common English/Arabic category and nearby phrases. Place provenance is stored. | Live named-place provider was not configured; 244-leaf Arabic intent coverage is not complete. |
| Source registry and license gate | Registry declares endpoint/path, policy, rate, coverage, freshness, reliability. Disallowed uses are excluded before access. Attribution carries through records and GeoServer. | Registry policy is operator declared; legal approval is `NOT_CERTIFIED`. Live adapter is Overpass; other commercial sources require implementation and permission. |
| Etiquette | Honest contact-bearing User-Agent, robots, Retry-After/backoff/304, endpoint-shared SQLite pacing; four-process rate test. | Official concurrent source load benchmark unavailable. |
| Canonical schema and conflation | Dedicated PostGIS/WFS attributes and field provenance. Versioned conflation; same-name, different-phone clinic regression is a project-authored synthetic pattern. Project fixture pairwise precision and recall are both 1.0. | No official Riyadh or held-out gold labels, so A4/A5 are not certified. |
| Geocoding fallback | Local catalog or explicitly configured licensed Nominatim-compatible HTTP adapter. Ambiguous records go to review; derived geometry is tagged and confidence ≤0.5. | HTTP adapter was tested with mocked responses; no live provider was supplied. |
| Taxonomy | 244 leaves; machine-readable OSM, Google and Wikidata crosswalk coverage with unmapped and ambiguous entries reported. Unknown source categories enter review. | Category accuracy against gold labels is `NOT_CERTIFIED`. |
| Bilingual names | Deterministic generic translation plus proper-name transliteration in both directions. Verified source values are preserved; generated values carry method, version, confidence and provenance. Saved 42-record Zurich capture reprocessed to 42/42 bilingual and replayed exactly. | Many German proper names have low-confidence transliteration; human Arabic quality is `NOT_CERTIFIED`. |
| Incremental refresh | Seeded 50 adds, 50 updates, 20 removals, 30 unchanged with field-level diffs. | Official seeded change set unavailable. |
| Publication and replay | Real OSM capture layers in PostGIS/GeoServer; separate 42-point bilingual preview verified in `poi_osm_enriched`, with source coordinates, style, WMS/WFS and provenance. Historical snapshots and 10k synthetic run replay exactly. | Official hardware, gold geometry and Common Agent Contract unavailable. |

The 10,000-record throughput result is a local synthetic pipeline probe, not the official 4-vCPU/8-GB end-to-end benchmark. The existing `poi_osm_mixed`, `poi_osm_live` and `poi_osm_bakery` layers were preserved. The bilingual preview was published separately in `poi_osm_enriched`.

## Remaining submission blockers

1. Obtain the official gold benchmark and report gold-based precision, recall, category accuracy, coordinate offset, Arabic human ratings, seeded changes and throughput on the specified hardware.
2. Obtain the Common Agent Contract and run its required suite; see [CONTRACT_BLOCKER.md](CONTRACT_BLOCKER.md).
3. Obtain operator/legal approval for each intended live source use and configure any licensed live place/geocoder service.
4. Improve and human-rate low-confidence Arabic proper-name transliterations before claiming A8.

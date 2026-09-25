"""Run orchestration and auditable artifact output."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .core import Area, Request, canonicalize, change_set, conflate, feature_collection, reconcile_ids, reproducibility_hash
from .enrichment import VERSION as ENRICHMENT_VERSION, enrich_record
from .sources import collect, covers_area, license_gate, load_registry
from .taxonomy import by_id


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(
    request: Request,
    registry_path: Path,
    output_dir: Path,
    selected_sources: set[str] | None = None,
    previous_path: Path | None = None,
    geocoder: Any | None = None,
    source_records_override: dict[str, list[dict]] | None = None,
) -> dict:
    sources = load_registry(registry_path)
    known = {source["name"] for source in sources}
    if selected_sources is not None and not selected_sources <= known:
        raise ValueError(f"Unknown sources: {sorted(selected_sources - known)}")
    raw, canonical, exclusions, review, failures = [], [], [], [], []
    contributors = []
    previous_cache = {}
    previous_raw: dict[str, list[dict]] = {}
    if previous_path:
        cache_path = previous_path.parent / "http_cache.json"
        raw_path = previous_path.parent / "raw.json"
        if cache_path.exists() and raw_path.exists():
            previous_cache = json.loads(cache_path.read_text(encoding="utf-8"))
            for item in json.loads(raw_path.read_text(encoding="utf-8")):
                previous_raw.setdefault(item["source"], []).append(item["record"])
    current_cache = {}
    geocoder_used = False
    harvested_at = datetime.now(timezone.utc).isoformat()
    for source in sources:
        if selected_sources is not None and source["name"] not in selected_sources:
            continue
        allowed, reason = license_gate(source, request.declared_use)
        if not allowed:
            exclusions.append({"source": source["name"], "reason": reason})
            continue
        if not covers_area(source, request.area.bounds):
            exclusions.append({"source": source["name"], "reason": "AOI outside declared source coverage"})
            continue
        try:
            if source_records_override is not None:
                if source["name"] not in source_records_override:
                    raise ValueError("Captured source records are missing")
                source_records, cache_entry = source_records_override[source["name"]], None
            else:
                source_records, cache_entry = collect(
                    source, request, registry_path, previous_cache.get(source["name"]),
                    previous_raw.get(source["name"]))
            if cache_entry:
                current_cache[source["name"]] = cache_entry
        except Exception as exc:
            failures.append({"source": source["name"], "error": str(exc)})
            continue
        accepted_for_source = 0
        for record in source_records:
            reason = record.get("geometry_review_reason") or record.get("category_review_reason")
            if reason:
                review.append({"source": source["name"], "record": record, "reason": reason})
                continue
            if record.get("lat") is None or record.get("lon") is None:
                found = geocoder.lookup(record["address"]) if geocoder and record.get("address") else None
                if found:
                    record = {**record, "lat": found["lat"], "lon": found["lon"],
                              "geometry_method": "geocode_derived",
                              "geometry_provenance": f"{found['provider']}:{found['reference']}",
                              "geometry_confidence": found["confidence"],
                              "geometry_attribution": found["attribution"],
                              "geometry_license": found["license"]}
                else:
                    review.append({"source": source["name"], "record": record,
                                   "reason": "No verified coordinate or geocoding result"})
                    continue
            try:
                if not request.area.contains(float(record["lat"]), float(record["lon"])):
                    continue
                if record.get("category") not in by_id():
                    review.append({"source": source["name"], "record": record,
                                   "reason": f"Unmapped source category: {record.get('category')!r}"})
                    continue
                if record.get("category") not in request.categories:
                    continue
                record, enrichment_review = enrich_record(record, f"{source['name']}:{record['id']}")
                if enrichment_review:
                    review.append({"source": source["name"], "record": record,
                                   "reason": f"Bilingual enrichment: {enrichment_review}"})
                captured = {**record, "harvested_at": harvested_at}
                normalized = canonicalize(captured, source)
            except (ValueError, KeyError, TypeError) as exc:
                review.append({"source": source["name"], "record": record, "reason": str(exc)})
                continue
            raw.append({"source": source["name"], "record": captured})
            canonical.append(normalized)
            if record.get("geometry_method") == "geocode_derived":
                geocoder_used = True
            accepted_for_source += 1
        if accepted_for_source:
            contributors.append({"source": source["name"], "kind": source["kind"], "license": source["license"], "attribution": source["attribution"]})
    if geocoder_used:
        provider = geocoder.provider
        contributors.append({"source": provider["name"], "kind": "geocoder",
                             "license": provider["license"], "attribution": provider["attribution"]})
    if exclusions and not canonical and not failures:
        raise RuntimeError(f"No permitted sources for declared use: {exclusions}")
    if failures:
        raise RuntimeError(f"Harvest incomplete; no change set or publication written. Source failures: {failures}")
    previous = json.loads(previous_path.read_text(encoding="utf-8")) if previous_path else []
    current = reconcile_ids(previous, conflate(canonical))
    changes = change_set(previous, current)
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "title": f"{' + '.join(by_id()[category]['label_en'] for category in request.categories)} POIs",
        "generated_at": harvested_at,
        "area_bbox": [request.area.bounds.west, request.area.bounds.south, request.area.bounds.east, request.area.bounds.north],
        "categories": list(request.categories),
        "category": request.categories[0] if len(request.categories) == 1 else None,
        "declared_use": request.declared_use,
        "feature_count": len(current),
        "contributors": contributors,
        "demo_data": any(item["kind"] == "fixture" for item in contributors),
        "exclusions": exclusions,
        "source_failures": failures,
        "reproducibility_hash": reproducibility_hash(current),
        "conflation_algorithm_version": 2,
        "enrichment_algorithm_version": ENRICHMENT_VERSION,
        "bilingual_complete_count": sum(bool(row.get("language_complete")) for row in current),
        "generated_name_count": sum(bool(row.get("name_en_method")) + bool(row.get("name_ar_method"))
                                    for row in current),
        "caveats": [
            "Generated translations/transliterations are rule-based and require human quality review.",
            "Source license declarations require operator verification before production use.",
        ],
    }
    if request.area_resolution:
        metadata["area_resolution"] = request.area_resolution
    _write_json(output_dir / "raw.json", raw)
    _write_json(output_dir / "http_cache.json", current_cache)
    _write_json(output_dir / "sources_snapshot.json", sources)
    _write_json(output_dir / "previous_snapshot.json", previous)
    _write_json(output_dir / "records.json", current)
    _write_json(output_dir / "poi.geojson", feature_collection(current))
    _write_json(output_dir / "changes.json", changes)
    _write_json(output_dir / "metadata.json", metadata)
    _write_json(output_dir / "review_queue.json", review)
    return {"status": "completed", "output_dir": str(output_dir), "feature_count": len(current), "metadata": metadata}


def replay(output_dir: Path) -> dict:
    """Rebuild the merged layer from captured raw records without an LLM or network."""
    raw = json.loads((output_dir / "raw.json").read_text(encoding="utf-8"))
    source_list = json.loads((output_dir / "sources_snapshot.json").read_text(encoding="utf-8"))
    sources = {source["name"]: source for source in source_list}
    metadata = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
    version = metadata.get("conflation_algorithm_version", 1)
    rebuilt = conflate([canonicalize(item["record"], sources[item["source"]]) for item in raw], version)
    previous_file = output_dir / "previous_snapshot.json"
    if previous_file.exists():
        previous = json.loads(previous_file.read_text(encoding="utf-8"))
        rebuilt = reconcile_ids(previous, rebuilt)
    expected = json.loads((output_dir / "records.json").read_text(encoding="utf-8"))
    return {
        "identical": rebuilt == expected,
        "reproducibility_hash": reproducibility_hash(rebuilt),
        "feature_count": len(rebuilt),
    }


def reprocess_capture(previous_dir: Path, output_dir: Path) -> dict:
    """Apply current deterministic rules to an immutable, previously accepted capture."""
    previous_dir = previous_dir.resolve()
    output_dir = output_dir.resolve()
    if previous_dir == output_dir:
        raise ValueError("Reprocessing must use a new output directory")
    source_list = json.loads((previous_dir / "sources_snapshot.json").read_text(encoding="utf-8"))
    prior_raw = json.loads((previous_dir / "raw.json").read_text(encoding="utf-8"))
    prior_meta = json.loads((previous_dir / "metadata.json").read_text(encoding="utf-8"))
    by_source: dict[str, list[dict]] = {}
    for item in prior_raw:
        by_source.setdefault(item["source"], []).append(item["record"])
    selected = {item["source"] for item in prior_meta["contributors"] if item["kind"] != "geocoder"}
    if not selected or not selected <= by_source.keys():
        raise ValueError("Capture is missing records for a contributing source")
    west, south, east, north = prior_meta["area_bbox"]
    categories = tuple(prior_meta["categories"])
    request = Request(Area(south, west, north, east),
                      categories[0] if len(categories) == 1 else categories,
                      prior_meta["declared_use"])
    output_dir.mkdir(parents=True, exist_ok=True)
    registry_path = output_dir / "capture_registry.json"
    _write_json(registry_path, {"sources": source_list})
    result = run(request, registry_path, output_dir, selected,
                 previous_dir / "records.json", source_records_override=by_source)
    metadata = result["metadata"]
    metadata["reprocessed_from"] = str(previous_dir)
    metadata["source_scope"] = "previously_accepted_raw_only"
    metadata["caveats"].append("This run reprocessed captured accepted records; it is not a fresh source harvest.")
    _write_json(output_dir / "metadata.json", metadata)
    old_review = json.loads((previous_dir / "review_queue.json").read_text(encoding="utf-8"))
    new_review = json.loads((output_dir / "review_queue.json").read_text(encoding="utf-8"))
    _write_json(output_dir / "review_queue.json", old_review + new_review)
    return result

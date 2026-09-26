"""Capture integrity and transformation/decision provenance outside the public layer."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json

from .taxonomy import catalog


def canonical_hash(value) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode()).hexdigest()


def build_provenance(captures: list[dict], raw: list[dict], sources: list[dict],
                     previous: list[dict], records: list[dict], decisions: list[dict],
                     conflation_version: int) -> dict:
    capture_keys = {capture["source"]: capture["capture_hash"] for capture in captures}
    transformations = []
    taxonomy_hash = canonical_hash(catalog())
    retrieval_times = {capture["source"]: capture["retrieval_timestamp"] for capture in captures}
    for item in raw:
        row = item["record"]
        names = {field: {"generated": bool(row.get(f"{field}_generated") or row.get(f"{field}_method")),
                         "method": row.get(f"{field}_method"), "version": row.get(f"{field}_version"),
                         "confidence": row.get(f"{field}_confidence"),
                         "provenance": row.get(f"provenance_{field}") or f"{item['source']}:{row['id']}"}
                 for field in ("name_en", "name_ar")}
        transformations.append({"source": item["source"], "source_record_id": str(row["id"]),
                                "source_key": f"{item['source']}:{row['id']}",
                                "retrieval_timestamp": retrieval_times[item["source"]],
                                "capture_hash": capture_keys[item["source"]],
                                "source_version": row.get("source_version"),
                                "category_mapping": {"source_category": row.get("source_category"),
                                                     "canonical_category": row["category"],
                                                     "taxonomy_hash": taxonomy_hash},
                                "geometry": {"method": row.get("geometry_method"),
                                             "provenance": row.get("geometry_provenance") or f"{item['source']}:{row['id']}"},
                                "enrichment": names})
    return {"schema_version": 1, "capture_kind": "input_records_before_current_transformation",
            "comparison_representation": "UTF-8 JSON, sorted keys, compact separators, ordered record lists",
            "capture_file_hash": canonical_hash(captures), "raw_file_hash": canonical_hash(raw),
            "source_registry_hash": canonical_hash(sources), "previous_snapshot_hash": canonical_hash(previous),
            "final_records_hash": canonical_hash(records), "taxonomy_hash": taxonomy_hash,
            "conflation_algorithm_version": conflation_version, "transformations": transformations,
            "conflation_candidate_decisions": decisions,
            "conflation_limits": {"maximum_distance_m": 75, "minimum_score": 0.68,
                                  "address_similarity": "diagnostic only; never overrides distance/category/phone guards"},
            "final_field_provenance": [{"stable_id": row["stable_id"], "source_keys": row["source_keys"],
                                        "geometry_provenance": row["geometry_provenance"],
                                        "fields": row["provenance"]} for row in records]}


def verify_capture_integrity(output_dir: Path) -> dict:
    path = output_dir / "provenance.json"
    if not path.exists():
        return {"status": "NOT_AVAILABLE", "reason": "Historical capture predates the provenance sidecar"}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    mapping = {"source_capture.json": "capture_file_hash", "raw.json": "raw_file_hash",
               "sources_snapshot.json": "source_registry_hash", "previous_snapshot.json": "previous_snapshot_hash",
               "records.json": "final_records_hash"}
    checks = {file: canonical_hash(json.loads((output_dir / file).read_text(encoding="utf-8"))) == manifest[field]
              for file, field in mapping.items()}
    metadata = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
    checks["conflation_algorithm_version"] = metadata.get("conflation_algorithm_version") == manifest["conflation_algorithm_version"]
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}

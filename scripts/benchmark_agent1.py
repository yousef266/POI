"""Reproducible synthetic throughput probe; does not substitute for the gold benchmark."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from poi_harvester.core import Area, Request
from poi_harvester.pipeline import replay, run


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "output" / "benchmark-10000"
    root.mkdir(parents=True, exist_ok=True)
    data = [
        {"id": str(index), "lat": 10 + (index // 100) * 0.01,
         "lon": 20 + (index % 100) * 0.01, "name_en": f"Pharmacy {index}",
         "category": "pharmacy", "geometry_method": "fixture_synthetic"}
        for index in range(10_000)
    ]
    (root / "source.json").write_text(json.dumps(data), encoding="utf-8")
    registry = {"sources": [{
        "name": "benchmark_fixture", "kind": "fixture", "path": "source.json",
        "license": "Project-authored synthetic benchmark", "allowed_uses": ["internal"],
        "commercial_use": False, "auth_mode": "none", "coverage_bbox": None,
        "freshness": "synthetic", "attribution": "Project-authored synthetic benchmark",
        "rate_limit_per_second": 1, "reliability_weight": 0.8,
    }]}
    (root / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
    start = perf_counter()
    result = run(Request(Area(9.9, 19.9, 11.1, 21.1), "pharmacy", "internal"),
                 root / "registry.json", root / "harvest", {"benchmark_fixture"})
    seconds = perf_counter() - start
    verification = replay(root / "harvest")
    report = {
        "kind": "synthetic_fixture_pipeline_only",
        "features": result["feature_count"],
        "harvest_seconds": round(seconds, 3),
        "features_per_hour": round(result["feature_count"] * 3600 / seconds),
        "exact_replay": verification["identical"],
        "gold_benchmark": False,
        "four_vcpu_eight_gb_verified": False,
    }
    (root / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

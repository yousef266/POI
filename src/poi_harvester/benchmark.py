"""Local synthetic 10K probe with separately measured publication when explicitly requested."""

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
from time import perf_counter, process_time
import json

from .config import load_env_file, require_publish_env
from .core import Area, Request
from .performance import host_metrics
from .pipeline import replay, run
from .publish import publish, verify_local


def add_benchmark_arguments(parser: ArgumentParser) -> None:
    parser.add_argument("--out", type=Path, default=Path("output/benchmark-10000"))
    parser.add_argument("--publish", action="store_true", help="Explicitly publish synthetic points to an isolated target")
    parser.add_argument("--database")
    parser.add_argument("--schema", default="poi_submission_probe")
    parser.add_argument("--workspace")
    parser.add_argument("--env-file", type=Path)


def benchmark_10000(root: Path, publication_target: dict | None = None,
                    env_file: Path | None = None) -> dict:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    data = [{"id": str(index), "lat": 10 + (index // 100) * 0.01,
             "lon": 20 + (index % 100) * 0.01, "name_en": f"Pharmacy {index}",
             "category": "pharmacy", "geometry_method": "fixture_synthetic"}
            for index in range(10_000)]
    (root / "source.json").write_text(json.dumps(data), encoding="utf-8")
    source = {"name": "benchmark_fixture", "kind": "fixture", "path": "source.json",
              "license": "Project-authored synthetic benchmark", "allowed_uses": ["internal"],
              "commercial_use": False, "auth_mode": "none", "coverage_bbox": None,
              "freshness": "synthetic", "attribution": "Project-authored synthetic benchmark",
              "rate_limit_per_second": 1, "reliability_weight": 0.8}
    registry = root / "registry.json"
    registry.write_text(json.dumps({"sources": [source]}), encoding="utf-8")
    if publication_target:
        if not publication_target.get("database") or not publication_target.get("workspace"):
            raise ValueError("Publication probe requires database and workspace")
        load_env_file(env_file)
        require_publish_env()
    start, cpu_start = perf_counter(), process_time()
    result = run(Request(Area(9.9, 19.9, 11.1, 21.1), "pharmacy", "internal"),
                 registry, root / "harvest", {"benchmark_fixture"})
    harvest_seconds = perf_counter() - start
    publication = {"status": "NOT_AVAILABLE", "reason": "Offline probe; no publication requested"}
    if publication_target:
        publication = publish(root / "harvest", "poi_pharmacy", publication_target["database"],
                              publication_target["workspace"], publication_target["schema"], allow_demo=True)
    complete_seconds = perf_counter() - start
    cpu_seconds = process_time() - cpu_start
    replay_one, replay_two = replay(root / "harvest"), replay(root / "harvest")
    verified = {"status": "NOT_AVAILABLE", "reason": "No publication requested"}
    verification_start = perf_counter()
    if publication_target:
        verified = verify_local("poi_pharmacy", publication_target["database"],
                                publication_target["workspace"], publication_target["schema"], root / "harvest")
    report = {"kind": "synthetic_fixture_with_local_publication" if publication_target else "synthetic_fixture_pipeline_only",
              "features": result["feature_count"], "harvest_seconds": round(harvest_seconds, 6),
              "features_per_hour": round(result["feature_count"] * 3600 / harvest_seconds),
              "complete_pipeline_seconds": round(complete_seconds, 6),
              "complete_features_per_hour": round(result["feature_count"] * 3600 / complete_seconds),
              "process_cpu_seconds": round(cpu_seconds, 6),
              "phase_timings": {**result["timings"], **publication.get("timings", {}),
                                "verification_seconds": perf_counter() - verification_start},
              "hardware": host_metrics(), "publication": publication, "publication_verification": verified,
              "exact_replay": replay_one["identical"] and replay_two["identical"] and
                              replay_one["reproducibility_hash"] == replay_two["reproducibility_hash"],
              "replay_checks": [replay_one, replay_two], "gold_benchmark": False,
              "four_vcpu_eight_gb_verified": False, "official_status": "NOT_CERTIFIED",
              "measurement_scope": "Generation/setup and verification are excluded from complete_pipeline_seconds; artifact writes are included"}
    (root / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description=__doc__)
    add_benchmark_arguments(parser)
    args = parser.parse_args(argv)
    target = {"database": args.database, "schema": args.schema, "workspace": args.workspace} if args.publish else None
    report = benchmark_10000(args.out, target, args.env_file)
    print(json.dumps(report, indent=2))
    return 0 if report["exact_replay"] else 1

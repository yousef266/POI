"""Command-line agent entry point."""

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
import json
import sys

from .core import Area, Request, SUPPORTED_CATEGORIES, area_from_place_catalog, categories_from_text, polygon_from_geojson
from .config import load_env_file, require_publish_env
from .geocode import CatalogGeocoder
from .geocode_http import load_http_geocoder
from .evaluation import evaluate_local
from .benchmark import add_benchmark_arguments, benchmark_10000
from .name_review import review_names, write_review_queue
from .intent import normalize_intent
from .place import CatalogPlaceResolver, choose_unique_place, load_http_place_resolver
from .pipeline import replay, reprocess_capture, run
from .publish import publish, verify_local
from .snapshots import load_pinned
from .sources import load_registry


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="poi-harvester")
    commands = parser.add_subparsers(dest="command", required=True)
    run_cmd = commands.add_parser("run", help="Harvest and generate an auditable POI layer")
    area = run_cmd.add_mutually_exclusive_group()
    area.add_argument("--bbox", nargs=4, type=float, metavar=("SOUTH", "WEST", "NORTH", "EAST"))
    area.add_argument("--polygon", type=Path, help="GeoJSON file containing one WGS84 Polygon")
    area.add_argument("--place", help="Place or admin-boundary name from --place-catalog")
    run_cmd.add_argument("--place-catalog", type=Path, help="Operator-supplied GeoJSON named AOI catalog")
    run_cmd.add_argument("--place-provider", type=Path, help="Explicit licensed Nominatim-compatible resolver config")
    run_cmd.add_argument("--near-radius-m", type=int, help="Radius for named roads/nearby point searches")
    category = run_cmd.add_mutually_exclusive_group(required=True)
    category.add_argument("--category", choices=tuple(SUPPORTED_CATEGORIES))
    category.add_argument("--categories", nargs="+", choices=tuple(SUPPORTED_CATEGORIES))
    category.add_argument("--intent", help="Simple English or Arabic category intent")
    run_cmd.add_argument("--use", choices=("internal", "commercial", "redistribute"), default="internal")
    run_cmd.add_argument("--sources", default="openstreetmap", help="Comma-separated registry source names")
    run_cmd.add_argument("--contact", help="Operator contact email or URL for live source User-Agent")
    run_cmd.add_argument("--max-requests-per-second", type=float,
                         help="Optional lower rate ceiling; cannot raise a source's declared limit")
    run_cmd.add_argument("--registry", type=Path, default=Path("sources.json"))
    run_cmd.add_argument("--geocode-catalog", type=Path,
                         help="Optional licensed local address lookup for source records without coordinates")
    run_cmd.add_argument("--geocode-provider", type=Path,
                         help="Optional licensed Nominatim-compatible address provider config")
    run_cmd.add_argument("--out", type=Path, default=Path("output/demo"))
    run_cmd.add_argument("--max-snapshot-age-seconds", type=float, default=86400, help="Maximum live snapshot age; explicit historical pins are marked separately")
    run_cmd.add_argument("--snapshot-store", type=Path, default=Path("output/.source-snapshots.sqlite3"), help="Durable latest-version guard keyed by semantic AOI/category/source")
    run_cmd.add_argument("--snapshot-from", type=Path, help="Explicit immutable source capture; never presented as a fresh live request")
    run_cmd.add_argument("--allow-source-centers", action="store_true", help="Explicitly use captured footprint centers as low-confidence derived points")
    run_cmd.add_argument("--previous", type=Path, help="Previous records.json for an incremental change set")
    run_cmd.add_argument("--publish", action="store_true", help="Publish to PostGIS and GeoServer")
    run_cmd.add_argument("--allow-demo-publish", action="store_true", help="Explicitly publish invented fixture points for an isolated test")
    run_cmd.add_argument("--layer", help="SQL-safe layer name; defaults to poi_<category>")
    run_cmd.add_argument("--database", help="PostGIS database name; required with --publish")
    run_cmd.add_argument("--schema", default="public", help="PostGIS schema; default: public")
    run_cmd.add_argument("--workspace", help="GeoServer workspace; required with --publish")
    run_cmd.add_argument("--env-file", type=Path, help="Local PostGIS and GeoServer settings; defaults to .env when present")

    benchmark_cmd = commands.add_parser("benchmark", help="Run the synthetic 10K probe with optional isolated publication")
    add_benchmark_arguments(benchmark_cmd)
    review_cmd = commands.add_parser("review-names", help="Prepare/resume human Arabic review and score explicit ratings")
    review_cmd.add_argument("--dataset", type=Path, default=Path("fixtures/arabic_name_review.json"))
    review_cmd.add_argument("--ratings", type=Path, default=Path("output/arabic-review/ratings.json"))
    review_cmd.add_argument("--out", type=Path, default=Path("output/arabic-review/score.json"))
    review_cmd.add_argument("--interactive", action="store_true")
    review_cmd.add_argument("--reviewer")
    review_cmd.add_argument('--queue-out', type=Path, help='Export uncertain examples as JSON and Markdown; no human ratings generated')
    review_cmd.add_argument('--queue', type=Path, help='Review only IDs from a hash-bound queue; retain the full sample denominator')
    replay_cmd = commands.add_parser("replay", help="Rebuild from captured raw input without network or LLM")
    replay_cmd.add_argument("output_dir", type=Path)
    reprocess_cmd = commands.add_parser("reprocess", help="Apply current rules to a saved capture without network")
    reprocess_cmd.add_argument("--from-run", type=Path, required=True)
    reprocess_cmd.add_argument("--out", type=Path, required=True)
    evaluate_cmd = commands.add_parser("evaluate", help="Run local offline A1-A12 evaluation")
    evaluate_cmd.add_argument("--out", type=Path, default=Path("output/evaluation"))
    evaluate_cmd.add_argument("--registry", type=Path, default=Path("sources.json"))
    evaluate_cmd.add_argument("--readiness", type=Path, default=Path("docs/AGENT1_READINESS.md"))
    evaluate_cmd.add_argument("--local-services", action="store_true", help="Also publish/verify 10K synthetic points in an isolated target")
    evaluate_cmd.add_argument("--database")
    evaluate_cmd.add_argument("--schema", default="poi_submission_probe")
    evaluate_cmd.add_argument("--workspace")
    evaluate_cmd.add_argument("--env-file", type=Path)
    evaluate_cmd.add_argument("--ratings", type=Path, help="Optional explicit human ratings for the 100-name dataset")
    publish_cmd = commands.add_parser("publish", help="Publish an existing harvest without requesting the source again")
    publish_cmd.add_argument("--out", type=Path, required=True, help="Existing run output directory")
    publish_cmd.add_argument("--layer", required=True)
    publish_cmd.add_argument("--database", required=True)
    publish_cmd.add_argument("--schema", default="public")
    publish_cmd.add_argument("--workspace", required=True)
    publish_cmd.add_argument("--allow-demo-publish", action="store_true")
    publish_cmd.add_argument("--env-file", type=Path, help="Defaults to .env when present")
    verify_cmd = commands.add_parser("verify-local", help="Check a published layer in real PostGIS and GeoServer")
    verify_cmd.add_argument("--layer", required=True)
    verify_cmd.add_argument("--database", required=True)
    verify_cmd.add_argument("--schema", default="public")
    verify_cmd.add_argument("--workspace", required=True)
    verify_cmd.add_argument("--env-file", type=Path, help="Defaults to .env when present")
    verify_cmd.add_argument("--out", type=Path, help="Run output directory to compare expected count and attribution")
    return parser


def main(argv: list[str] | None = None) -> int:
    # Windows redirected consoles may otherwise reject Arabic output.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        if args.command == "review-names":
            if args.queue_out:
                existing_ratings = json.loads(args.ratings.read_text(encoding='utf-8')) if args.ratings.exists() else None
                write_review_queue(json.loads(args.dataset.read_text(encoding='utf-8')), args.queue_out, existing_ratings)
            print(json.dumps(review_names(args.dataset, args.ratings, args.out, args.interactive, args.reviewer, args.queue), indent=2))
            return 0
        if args.command == "benchmark":
            target = {"database": args.database, "schema": args.schema, "workspace": args.workspace} if args.publish else None
            report = benchmark_10000(args.out, target, args.env_file)
            print(json.dumps(report, indent=2))
            return 0 if report["exact_replay"] else 1
        if args.command == "replay":
            result = replay(args.output_dir)
            print(json.dumps(result, indent=2))
            return 0 if result["identical"] else 1
        if args.command == "reprocess":
            result = reprocess_capture(args.from_run, args.out)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "evaluate":
            target = {"database": args.database, "schema": args.schema, "workspace": args.workspace} if args.local_services else None
            report = evaluate_local(args.out, args.registry, args.readiness, target, args.env_file, args.ratings)
            summary = {"report": str((args.out / "report.json").resolve()),
                       "readiness": str(args.readiness.resolve()),
                       "unit_tests": report["unit_tests"]["status"],
                       "criteria": {key: value["local_status"]
                                    for key, value in report["criteria"].items()}}
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0 if report["unit_tests"]["status"] == "PASS" and all(
                value["local_status"] != "FAIL" for value in report["criteria"].values()) else 1
        load_env_file(args.env_file)
        if args.command == "publish":
            require_publish_env()
            result = publish(args.out, args.layer, args.database, args.workspace, args.schema, args.allow_demo_publish)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "verify-local":
            require_publish_env()
            result = verify_local(args.layer, args.database, args.workspace, args.schema, args.out)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        normalized = normalize_intent(args.intent) if args.intent else None
        categories = tuple(args.categories or ([args.category] if args.category else normalized["categories"]))
        if not categories:
            raise ValueError("Intent has no supported category; specify --category")
        category = categories[0] if len(categories) == 1 else categories
        place = args.place or (normalized["area"] if normalized and not args.bbox and not args.polygon else None)
        area_resolution = None
        if args.bbox:
            selected_area = Area(*args.bbox)
        elif args.polygon:
            selected_area = polygon_from_geojson(json.loads(args.polygon.read_text(encoding="utf-8")))
        elif place:
            if args.place_provider:
                resolver = load_http_place_resolver(
                    args.place_provider, args.use, args.contact or "", args.max_requests_per_second)
            elif args.place_catalog:
                resolver = CatalogPlaceResolver(args.place_catalog, args.use)
            else:
                raise ValueError("Named AOI requires --place-provider or --place-catalog")
            radius = args.near_radius_m or (normalized["constraints"]["radius_m"] if normalized else None)
            resolved = choose_unique_place(resolver, place, radius)
            if resolved["status"] != "resolved":
                raise ValueError(resolved["question"])
            selected_area, area_resolution = resolved["area"], resolved["metadata"]
        else:
            raise ValueError("Provide --bbox, --polygon, --place, or an intent containing a place")
        request = Request(selected_area, category, args.use, args.contact,
                          args.max_requests_per_second, area_resolution, args.allow_source_centers)
        if args.publish:
            if not args.database or not args.workspace:
                raise ValueError("--publish requires --database and --workspace")
            require_publish_env()
        if args.geocode_catalog and args.geocode_provider:
            raise ValueError("Choose either --geocode-catalog or --geocode-provider")
        geocoder = (CatalogGeocoder(args.geocode_catalog, args.use) if args.geocode_catalog else
                    load_http_geocoder(args.geocode_provider, args.use, args.contact or "",
                                       args.max_requests_per_second) if args.geocode_provider else None)
        selected = set(args.sources.split(","))
        registry_sources = load_registry(args.registry)
        for source in registry_sources:
            if source["kind"] == "overpass":
                source["snapshot_store"] = str(args.snapshot_store)
        captured, descriptors = (load_pinned(args.snapshot_from, registry_sources, request, selected)
                                 if args.snapshot_from else (None, None))
        result = run(request, args.registry.resolve(), args.out, selected, args.previous, geocoder,
                     source_records_override=captured, source_snapshots_override=descriptors,
                     snapshot_store_path=args.snapshot_store, max_snapshot_age_seconds=args.max_snapshot_age_seconds)
        if args.publish:
            default_layer = "poi_" + "_".join(categories)
            result["publication"] = publish(args.out, args.layer or default_layer, args.database, args.workspace, args.schema, args.allow_demo_publish)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except KeyboardInterrupt:
        print(json.dumps({"status": "cancelled", "freshness_state": "FAILED_REFRESH", "error": "Refresh cancelled; no stale fallback"}), file=sys.stderr)
        return 130
    except Exception as exc:
        failure = {"status": "failed", "error": str(exc)}
        if args.command == 'run':
            failure['freshness_state'] = 'FAILED_REFRESH'
        print(json.dumps(failure), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

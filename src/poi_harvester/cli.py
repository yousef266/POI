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
from .intent import normalize_intent
from .place import CatalogPlaceResolver, choose_unique_place, load_http_place_resolver
from .pipeline import replay, reprocess_capture, run
from .publish import publish, verify_local


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
    run_cmd.add_argument("--previous", type=Path, help="Previous records.json for an incremental change set")
    run_cmd.add_argument("--publish", action="store_true", help="Publish to PostGIS and GeoServer")
    run_cmd.add_argument("--allow-demo-publish", action="store_true", help="Explicitly publish invented fixture points for an isolated test")
    run_cmd.add_argument("--layer", help="SQL-safe layer name; defaults to poi_<category>")
    run_cmd.add_argument("--database", help="PostGIS database name; required with --publish")
    run_cmd.add_argument("--schema", default="public", help="PostGIS schema; default: public")
    run_cmd.add_argument("--workspace", help="GeoServer workspace; required with --publish")
    run_cmd.add_argument("--env-file", type=Path, help="Local PostGIS and GeoServer settings; defaults to .env when present")

    replay_cmd = commands.add_parser("replay", help="Rebuild from captured raw input without network or LLM")
    replay_cmd.add_argument("output_dir", type=Path)
    reprocess_cmd = commands.add_parser("reprocess", help="Apply current rules to a saved capture without network")
    reprocess_cmd.add_argument("--from-run", type=Path, required=True)
    reprocess_cmd.add_argument("--out", type=Path, required=True)
    evaluate_cmd = commands.add_parser("evaluate", help="Run local offline A1-A12 evaluation")
    evaluate_cmd.add_argument("--out", type=Path, default=Path("output/evaluation"))
    evaluate_cmd.add_argument("--registry", type=Path, default=Path("sources.json"))
    evaluate_cmd.add_argument("--readiness", type=Path, default=Path("docs/AGENT1_READINESS.md"))
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
    args = build_parser().parse_args(argv)
    try:
        if args.command == "replay":
            result = replay(args.output_dir)
            print(json.dumps(result, indent=2))
            return 0 if result["identical"] else 1
        if args.command == "reprocess":
            result = reprocess_capture(args.from_run, args.out)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "evaluate":
            report = evaluate_local(args.out, args.registry, args.readiness)
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
                          args.max_requests_per_second, area_resolution)
        if args.publish:
            if not args.database or not args.workspace:
                raise ValueError("--publish requires --database and --workspace")
            require_publish_env()
        if args.geocode_catalog and args.geocode_provider:
            raise ValueError("Choose either --geocode-catalog or --geocode-provider")
        geocoder = (CatalogGeocoder(args.geocode_catalog, args.use) if args.geocode_catalog else
                    load_http_geocoder(args.geocode_provider, args.use, args.contact or "",
                                       args.max_requests_per_second) if args.geocode_provider else None)
        result = run(request, args.registry.resolve(), args.out, set(args.sources.split(",")), args.previous, geocoder)
        if args.publish:
            default_layer = "poi_" + "_".join(categories)
            result["publication"] = publish(args.out, args.layer or default_layer, args.database, args.workspace, args.schema, args.allow_demo_publish)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

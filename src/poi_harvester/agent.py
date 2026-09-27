"""Provider-neutral structured invocation surface for Agent 1."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .core import Area, Request, categories_from_text, polygon_from_geojson
from .config import load_env_file, require_publish_env
from .geocode import CatalogGeocoder
from .geocode_http import load_http_geocoder
from .intent import normalize_intent
from .pipeline import run
from .place import CatalogPlaceResolver, choose_unique_place, load_http_place_resolver
from .publish import publish
from .snapshots import load_pinned
from .sources import load_registry


def invoke(payload: dict[str, Any]) -> dict[str, Any]:
    """Run a POI harvest from structured input or English/Arabic intent."""
    try:
        normalized = normalize_intent(payload["intent"]) if payload.get("intent") else None
        category = payload.get("categories") or payload.get("category")
        if not category and normalized:
            category = normalized["categories"]
        if not category:
            return {"status": "needs_input", "question": "Provide a supported POI category."}
        if isinstance(category, str):
            category = (category,)
        else:
            category = tuple(category)
        if not category:
            return {"status": "needs_input", "question": "Provide a supported POI category."}

        bbox = payload.get("bbox")
        polygon = payload.get("polygon")
        place = payload.get("place")
        if not place and bbox is None and polygon is None and normalized:
            place = normalized["area"]
        area_resolution = None
        if polygon is not None:
            selected_area = polygon_from_geojson(polygon)
        elif bbox is not None:
            if not isinstance(bbox, list) or len(bbox) != 4:
                return {"status": "needs_input", "question": "Provide bbox [south, west, north, east]."}
            selected_area = Area(*(float(value) for value in bbox))
        elif place:
            declared_use = payload.get("declared_use", "internal")
            if payload.get("place_provider"):
                resolver = load_http_place_resolver(
                    Path(payload["place_provider"]), declared_use, payload.get("contact") or "",
                    payload.get("max_requests_per_second"))
            elif payload.get("place_catalog"):
                resolver = CatalogPlaceResolver(Path(payload["place_catalog"]), declared_use)
            else:
                return {"status": "needs_input", "question":
                        "Provide a configured place provider or reusable place catalog to resolve the named AOI."}
            near_radius = payload.get("near_radius_m")
            if near_radius is None and normalized:
                near_radius = normalized["constraints"]["radius_m"]
            resolved = choose_unique_place(resolver, place, near_radius)
            if resolved["status"] != "resolved":
                return resolved
            selected_area, area_resolution = resolved["area"], resolved["metadata"]
        else:
            return {"status": "needs_input", "question":
                    "Provide bbox, polygon, place, or intent containing a place name."}

        publish_requested = payload.get("publish") is not False
        if publish_requested and (not payload.get("database") or not payload.get("workspace")):
            return {"status": "needs_input", "question":
                    "To publish, provide the database name and GeoServer workspace. Schema is optional."}
        load_env_file(Path(payload["env_file"]) if payload.get("env_file") else None)
        request = Request(
            selected_area, category[0] if len(category) == 1 else category,
            payload.get("declared_use", "internal"), payload.get("contact"),
            payload.get("max_requests_per_second"), area_resolution,
            payload.get("allow_source_centers") is True)
        output_dir = Path(payload.get("output_dir") or "output/agent-run")
        source_names = payload.get("sources", ["openstreetmap"])
        if not isinstance(source_names, list) or not all(isinstance(name, str) for name in source_names):
            raise ValueError("sources must be a list of source names")
        previous = Path(payload["previous_records"]) if payload.get("previous_records") else None
        if payload.get("geocode_catalog") and payload.get("geocode_provider"):
            raise ValueError("Choose either geocode_catalog or geocode_provider")
        geocoder = (CatalogGeocoder(Path(payload["geocode_catalog"]), request.declared_use)
                    if payload.get("geocode_catalog") else
                    load_http_geocoder(Path(payload["geocode_provider"]), request.declared_use,
                                       payload.get("contact") or "", payload.get("max_requests_per_second"))
                    if payload.get("geocode_provider") else None)
        registry = Path(payload.get("registry", "sources.json")).resolve()
        store = Path(payload.get("snapshot_store") or "output/.source-snapshots.sqlite3")
        sources = load_registry(registry)
        for source in sources:
            if source["kind"] == "overpass":
                source["snapshot_store"] = str(store)
        captured, descriptors = (load_pinned(payload["snapshot_from"], sources, request, set(source_names))
                                 if payload.get("snapshot_from") else (None, None))
        result = run(request, registry, output_dir, set(source_names), previous, geocoder,
                     source_records_override=captured, source_snapshots_override=descriptors,
                     snapshot_store_path=store, max_snapshot_age_seconds=payload.get("max_snapshot_age_seconds",86400))
        if normalized:
            result["intent"] = normalized
        if publish_requested:
            require_publish_env()
            layer = payload.get("layer") or "poi_" + "_".join(request.categories)
            result["publication"] = publish(
                output_dir, layer, payload["database"], payload["workspace"],
                payload.get("schema") or "public", payload.get("allow_demo_publish") is True)
        return result
    except Exception as exc:
        return {"status": "failed", "freshness_state": "FAILED_REFRESH", "error": str(exc)}

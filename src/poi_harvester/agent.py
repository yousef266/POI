"""Small provider-neutral invocation surface for UI, workflow, or another agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .core import Area, Request, area_from_place_catalog, categories_from_text, polygon_from_geojson
from .config import load_env_file, require_publish_env
from .geocode import CatalogGeocoder
from .pipeline import run
from .publish import publish


def invoke(payload: dict[str, Any]) -> dict[str, Any]:
    """Invoke the harvester with structured data or a category intent.

    This is deliberately independent of any LLM vendor. An LLM can prepare this
    payload, but the execution, source gating, and replay are deterministic.
    """
    bbox = payload.get("bbox")
    polygon = payload.get("polygon")
    place = payload.get("place")
    if not place and polygon is None and (not isinstance(bbox, list) or len(bbox) != 4):
        return {"status": "needs_input", "question": "Provide bbox, GeoJSON polygon, or a named place with a place catalog."}
    if place and not payload.get("place_catalog"):
        return {"status": "needs_input", "question": "Provide a GeoJSON place catalog to resolve the named AOI."}
    category = payload.get("categories") or payload.get("category")
    if not category and payload.get("intent"):
        try:
            category = categories_from_text(payload["intent"])
        except ValueError:
            return {"status": "needs_input", "question": "Which POI category do you want?"}
    if not category:
        return {"status": "needs_input", "question": "Provide a category or category intent."}
    publish_requested = payload.get("publish") is not False
    if publish_requested and (not payload.get("database") or not payload.get("workspace")):
        return {"status": "needs_input", "question": "To publish, provide the database name and GeoServer workspace. Schema is optional (default: public)."}
    try:
        load_env_file(Path(payload["env_file"]) if payload.get("env_file") else None)
        selected_area = (area_from_place_catalog(Path(payload["place_catalog"]), place) if place else
                         polygon_from_geojson(polygon) if polygon is not None else
                         Area(*(float(value) for value in bbox)))
        request_categories = (category,) if isinstance(category, str) else tuple(category)
        request = Request(selected_area, request_categories[0] if len(request_categories) == 1 else request_categories,
                          payload.get("declared_use", "internal"), payload.get("contact"))
        output_dir = Path(payload.get("output_dir") or "output/agent-run")
        source_names = payload.get("sources", ["openstreetmap"])
        if not isinstance(source_names, list) or not all(isinstance(name, str) for name in source_names):
            raise ValueError("sources must be a list of source names")
        sources = set(source_names)
        previous = Path(payload["previous_records"]) if payload.get("previous_records") else None
        geocoder = (CatalogGeocoder(Path(payload["geocode_catalog"]), request.declared_use)
                    if payload.get("geocode_catalog") else None)
        result = run(request, Path(payload.get("registry", "sources.json")).resolve(),
                     output_dir, sources, previous, geocoder)
        if publish_requested:
            require_publish_env()
            layer = payload.get("layer") or "poi_" + "_".join(request.categories)
            result["publication"] = publish(output_dir, layer, payload["database"], payload["workspace"], payload.get("schema") or "public", payload.get("allow_demo_publish") is True)
        return result
    except Exception as exc:
        return {"status": "failed", "error": str(exc)}

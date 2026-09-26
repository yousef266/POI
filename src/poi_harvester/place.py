"""Pluggable, license-aware named-place AOI resolution."""

from __future__ import annotations

from math import cos, radians
from pathlib import Path
from math import isfinite
from urllib.parse import urlencode, urlparse
import json

from .core import Area, polygon_from_geojson
from .sources import _get_json, _robots_allowed, _source_limiter, license_gate


def _metadata(provider: dict, name: str, source_id: str, confidence: float,
              method: str) -> dict:
    return {"resolved_name": name, "provider": provider["name"],
            "source_id": source_id, "confidence": confidence,
            "method": method, "license": provider["license"],
            "attribution": provider["attribution"]}


class CatalogPlaceResolver:
    """Resolve reusable named boundaries from a local GeoJSON catalog."""

    def __init__(self, path: Path, declared_use: str):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("type") != "FeatureCollection":
            raise ValueError("Place catalog must be a GeoJSON FeatureCollection")
        self.features = data.get("features", [])
        self.provider = data.get("provider")
        if self.provider:
            allowed, reason = license_gate(self.provider, declared_use)
            if not allowed:
                raise PermissionError(reason)
        self.path = path

    def resolve(self, name: str, near_radius_m: int | None = None) -> list[dict]:
        wanted = name.strip().casefold()
        matches = []
        for index, feature in enumerate(self.features):
            properties = feature.get("properties") or {}
            names = [properties.get("name"), *(properties.get("aliases") or [])]
            if wanted not in {value.strip().casefold() for value in names if isinstance(value, str)}:
                continue
            area = polygon_from_geojson(feature)
            provider = self.provider or {"name": "operator_catalog", "license": "NOT_DECLARED",
                                         "attribution": str(self.path)}
            matches.append({"area": area, "metadata": _metadata(
                provider, properties.get("name") or name,
                str(properties.get("id") or index), 1.0, "catalog_boundary")})
        return matches


class HttpPlaceResolver:
    """Nominatim-compatible search against an explicitly configured provider."""

    def __init__(self, provider: dict, declared_use: str, contact: str,
                 max_rate_per_second: float | None = None):
        allowed, reason = license_gate(provider, declared_use)
        if not allowed:
            raise PermissionError(reason)
        for field in ("name", "endpoint", "license", "attribution", "rate_limit_per_second"):
            if not provider.get(field):
                raise ValueError(f"Place provider missing {field}")
        endpoint = provider["endpoint"]
        parsed = urlparse(endpoint)
        if parsed.scheme != "https":
            raise ValueError("Place resolver endpoint must use HTTPS")
        if parsed.hostname == "nominatim.openstreetmap.org":
            raise ValueError("Use an operator-approved self-hosted or third-party search service")
        if not isfinite(provider["rate_limit_per_second"]) or provider["rate_limit_per_second"] <= 0:
            raise ValueError("Provider rate must be finite and positive")
        if not isfinite(provider.get("reliability_weight", 0.5)) or not 0 <= provider.get("reliability_weight", 0.5) <= 1:
            raise ValueError("Provider reliability must be between zero and one")
        if not contact:
            raise ValueError("A contact is required for live place resolution")
        self.provider = provider
        self.contact = contact
        self.max_rate = max_rate_per_second
        self.cache: dict[tuple[str, int | None], list[dict]] = {}

    def resolve(self, name: str, near_radius_m: int | None = None) -> list[dict]:
        if near_radius_m is not None and (not isfinite(near_radius_m) or near_radius_m <= 0):
            raise ValueError("Nearby radius must be finite and positive")
        key = (name.casefold().strip(), near_radius_m)
        if key in self.cache:
            return self.cache[key]
        source = self.provider
        url = source["endpoint"] + "?" + urlencode({
            "q": name, "format": "jsonv2", "polygon_geojson": 1, "limit": 5})
        agent = f"POIHarvesterAgent/0.1 ({self.contact})"
        limiter = _source_limiter(source, self.max_rate)
        if not _robots_allowed(url, agent, limiter):
            raise PermissionError("Place provider robots.txt disallows search endpoint")
        payload, _ = _get_json(url, limiter, agent)
        if not isinstance(payload, list):
            raise ValueError("Place provider returned an invalid search result")
        matches = []
        for candidate in payload:
            geometry = candidate.get("geojson") or {}
            if geometry.get("type") in ("Polygon", "MultiPolygon"):
                area = polygon_from_geojson(geometry)
                method, confidence = "provider_boundary", 0.75
            elif near_radius_m is not None:
                lat, lon = float(candidate["lat"]), float(candidate["lon"])
                delta_lat = near_radius_m / 111_320
                delta_lon = near_radius_m / (111_320 * max(0.01, cos(radians(lat))))
                points = geometry.get("coordinates", []) if geometry.get("type") == "LineString" else [[lon, lat]]
                if geometry.get("type") == "MultiLineString":
                    points = [point for line in geometry.get("coordinates", []) for point in line]
                if not points:
                    points = [[lon, lat]]
                area = Area(min(float(point[1]) for point in points) - delta_lat,
                            min(float(point[0]) for point in points) - delta_lon,
                            max(float(point[1]) for point in points) + delta_lat,
                            max(float(point[0]) for point in points) + delta_lon)
                method, confidence = "derived_nearby_bbox", 0.4
            else:
                continue
            source_id = (f"{candidate['osm_type']}/{candidate['osm_id']}"
                         if candidate.get("osm_type") and candidate.get("osm_id")
                         else str(candidate.get("place_id", "unknown")))
            matches.append({"area": area, "metadata": _metadata(
                source, candidate.get("display_name") or name,
                source_id, confidence, method)})
        self.cache[key] = matches
        return matches


def choose_unique_place(resolver, name: str, near_radius_m: int | None = None) -> dict:
    matches = resolver.resolve(name, near_radius_m)
    if len(matches) != 1:
        return {"status": "needs_input", "question": (
            f"Place {name!r} has {len(matches)} usable matches; provide a more specific name or an explicit AOI."),
            "candidates": [item["metadata"] for item in matches]}
    return {"status": "resolved", **matches[0]}


def load_http_place_resolver(path: Path, declared_use: str, contact: str,
                             max_rate_per_second: float | None = None) -> HttpPlaceResolver:
    return HttpPlaceResolver(json.loads(path.read_text(encoding="utf-8")),
                             declared_use, contact, max_rate_per_second)

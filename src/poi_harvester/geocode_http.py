"""Optional policy-gated, Nominatim-compatible address lookup adapter."""

from __future__ import annotations

from pathlib import Path
from math import isfinite
from urllib.parse import urlencode, urlparse
import json

from .sources import _get_json, _robots_allowed, _source_limiter, license_gate


class HttpGeocoder:
    def __init__(self, provider: dict, declared_use: str, contact: str,
                 max_rate_per_second: float | None = None):
        allowed, reason = license_gate(provider, declared_use)
        if not allowed:
            raise PermissionError(reason)
        for field in ("name", "endpoint", "license", "attribution", "rate_limit_per_second"):
            if not provider.get(field):
                raise ValueError(f"Geocoder provider missing {field}")
        parsed = urlparse(provider["endpoint"])
        if parsed.scheme != "https":
            raise ValueError("Geocoder endpoint must use HTTPS")
        if parsed.hostname == "nominatim.openstreetmap.org":
            raise ValueError("Use an operator-approved self-hosted or third-party geocoding service")
        if not isfinite(provider["rate_limit_per_second"]) or provider["rate_limit_per_second"] <= 0:
            raise ValueError("Provider rate must be finite and positive")
        if not isfinite(provider.get("reliability_weight", 0.5)) or not 0 <= provider.get("reliability_weight", 0.5) <= 1:
            raise ValueError("Provider reliability must be between zero and one")
        if not contact:
            raise ValueError("A contact is required for live geocoding")
        self.provider = provider
        self.contact = contact
        self.max_rate = max_rate_per_second
        self.cache: dict[str, dict | None] = {}

    def lookup(self, address: str) -> dict | None:
        key = address.strip().casefold()
        if key in self.cache:
            return self.cache[key]
        source = self.provider
        url = source["endpoint"] + "?" + urlencode({"q": address, "format": "jsonv2", "limit": 5})
        agent = f"POIHarvesterAgent/0.1 ({self.contact})"
        limiter = _source_limiter(source, self.max_rate)
        if not _robots_allowed(url, agent, limiter):
            raise PermissionError("Geocoder robots.txt disallows search endpoint")
        payload, _ = _get_json(url, limiter, agent)
        if not isinstance(payload, list):
            raise ValueError("Geocoder returned an invalid search result")
        if len(payload) != 1:
            self.cache[key] = None  # Ambiguous/empty matches go to review.
            return None
        candidate = payload[0]
        lat, lon = float(candidate["lat"]), float(candidate["lon"])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Geocoder returned invalid coordinates")
        reference = (f"{candidate['osm_type']}/{candidate['osm_id']}"
                     if candidate.get("osm_type") and candidate.get("osm_id")
                     else str(candidate.get("place_id", "unknown")))
        result = {
            "lat": lat, "lon": lon, "reference": reference,
            "confidence": min(float(source.get("reliability_weight", 0.5)), 0.5),
            "provider": source["name"], "attribution": source["attribution"],
            "license": source["license"],
        }
        self.cache[key] = result
        return result


def load_http_geocoder(path: Path, declared_use: str, contact: str,
                       max_rate_per_second: float | None = None) -> HttpGeocoder:
    return HttpGeocoder(json.loads(path.read_text(encoding="utf-8")),
                        declared_use, contact, max_rate_per_second)

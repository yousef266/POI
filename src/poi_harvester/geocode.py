"""Optional address fallback through a replaceable, licensed lookup provider."""

from __future__ import annotations

from pathlib import Path
from math import isfinite
import json

from .sources import license_gate


class CatalogGeocoder:
    """Exact-address local catalog. Implement ``lookup`` to add another provider."""

    def __init__(self, path: Path, declared_use: str):
        data = json.loads(path.read_text(encoding="utf-8"))
        self.provider = data["provider"]
        allowed, reason = license_gate(self.provider, declared_use)
        if not allowed:
            raise PermissionError(reason)
        for key in ("name", "attribution", "license"):
            if not self.provider.get(key):
                raise ValueError(f"Geocoder provider missing {key}")
        self.entries = {}
        for entry in data["entries"]:
            key = entry["address"].strip().casefold()
            if key in self.entries:
                raise ValueError(f"Duplicate geocoder address: {entry['address']}")
            lat, lon = float(entry["lat"]), float(entry["lon"])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError(f"Invalid geocoder coordinate for {entry['address']}")
            confidence = float(entry.get("confidence", 0.5))
            if not isfinite(confidence) or not 0 <= confidence <= 1:
                raise ValueError("Geocoder confidence must be between zero and one")
            self.entries[key] = {"lat": lat, "lon": lon, "reference": str(entry["id"]),
                                 "confidence": min(float(entry.get("confidence", 0.5)), 0.5)}

    def lookup(self, address: str) -> dict | None:
        result = self.entries.get(address.strip().casefold())
        if result is None:
            return None
        return {
            **result,
            "provider": self.provider["name"],
            "attribution": self.provider["attribution"],
            "license": self.provider["license"],
        }

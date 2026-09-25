"""Deterministic POI normalization, conflation, and change detection."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from hashlib import sha256
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any
import json
import re
import unicodedata

from .taxonomy import by_id


CORE_ALIASES = {
    "pharmacy": ("pharmacy", "صيدلية", "صيدليات", "pharmacies"),
    "clinic": ("clinic", "clinics", "عيادة", "عيادات"),
    "hospital": ("hospital", "hospitals", "مستشفى", "مستشفيات"),
    "school": ("school", "schools", "مدرسة", "مدارس"),
}


def _english_variants(label: str) -> tuple[str, str]:
    singular = label.casefold()
    if singular.endswith("y") and len(singular) > 1 and singular[-2] not in "aeiou":
        plural = singular[:-1] + "ies"
    elif singular.endswith(("s", "x", "ch", "sh")):
        plural = singular + "es"
    else:
        plural = singular + "s"
    return singular, plural


SUPPORTED_CATEGORIES = {
    leaf_id: tuple(dict.fromkeys((*_english_variants(leaf["label_en"]),
                                  leaf_id.replace("_", " "),
                                  *CORE_ALIASES.get(leaf_id, ()),
                                  *("و" + word for word in CORE_ALIASES.get(leaf_id, ())
                                    if re.search(r"[\u0600-\u06ff]", word)))))
    for leaf_id, leaf in by_id().items()
}


@dataclass(frozen=True)
class Area:
    south: float
    west: float
    north: float
    east: float

    def __post_init__(self) -> None:
        if not (-90 <= self.south < self.north <= 90):
            raise ValueError("Invalid latitude bounds")
        if not (-180 <= self.west < self.east <= 180):
            raise ValueError("Invalid longitude bounds")

    def contains(self, lat: float, lon: float) -> bool:
        return self.south <= lat <= self.north and self.west <= lon <= self.east

    @property
    def bounds(self) -> Area:
        return self


@dataclass(frozen=True)
class PolygonArea:
    """WGS84 GeoJSON exterior ring, with coordinates in lon/lat order."""

    ring: tuple[tuple[float, float], ...]
    holes: tuple[tuple[tuple[float, float], ...], ...] = ()

    def __post_init__(self) -> None:
        for ring in (self.ring, *self.holes):
            if len(ring) < 4 or ring[0] != ring[-1]:
                raise ValueError("Polygon rings must be closed and contain at least three vertices")
            for lon, lat in ring:
                if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                    raise ValueError("Polygon coordinates must be WGS84 lon/lat")
        if self.bounds.south == self.bounds.north or self.bounds.west == self.bounds.east:
            raise ValueError("Polygon has no area")

    @property
    def bounds(self) -> Area:
        lon_values = [point[0] for point in self.ring]
        lat_values = [point[1] for point in self.ring]
        return Area(min(lat_values), min(lon_values), max(lat_values), max(lon_values))

    def contains(self, lat: float, lon: float) -> bool:
        if not self.bounds.contains(lat, lon):
            return False
        return _ring_contains(self.ring, lat, lon) and not any(
            _ring_contains(hole, lat, lon) for hole in self.holes)


def _ring_contains(ring: tuple[tuple[float, float], ...], lat: float, lon: float) -> bool:
    inside = False
    for i in range(len(ring) - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        cross = (lon - x1) * (y2 - y1) - (lat - y1) * (x2 - x1)
        if abs(cross) < 1e-12 and min(x1, x2) <= lon <= max(x1, x2) and min(y1, y2) <= lat <= max(y1, y2):
            return True
        if (y1 > lat) != (y2 > lat):
            intersect_lon = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < intersect_lon:
                inside = not inside
    return inside


@dataclass(frozen=True)
class MultiPolygonArea:
    parts: tuple[PolygonArea, ...]

    @property
    def bounds(self) -> Area:
        if not self.parts:
            raise ValueError("AOI MultiPolygon cannot be empty")
        boxes = [part.bounds for part in self.parts]
        return Area(min(box.south for box in boxes), min(box.west for box in boxes),
                    max(box.north for box in boxes), max(box.east for box in boxes))

    def contains(self, lat: float, lon: float) -> bool:
        return any(part.contains(lat, lon) for part in self.parts)


def polygon_from_geojson(value: dict[str, Any]) -> PolygonArea | MultiPolygonArea:
    if value.get("type") == "FeatureCollection":
        features = value.get("features", [])
        if len(features) != 1:
            raise ValueError("Provide exactly one AOI polygon feature")
        value = features[0]
    if value.get("type") == "Feature":
        value = value["geometry"]

    def part(coordinates: list) -> PolygonArea:
        if not coordinates:
            raise ValueError("AOI polygon has no rings")
        rings = tuple(tuple((float(lon), float(lat)) for lon, lat in ring)
                      for ring in coordinates)
        return PolygonArea(rings[0], rings[1:])

    if value.get("type") == "Polygon":
        return part(value["coordinates"])
    if value.get("type") == "MultiPolygon":
        return MultiPolygonArea(tuple(part(coordinates) for coordinates in value["coordinates"]))
    raise ValueError("AOI must be a GeoJSON Polygon or MultiPolygon")


def area_from_place_catalog(path: Path, name: str) -> PolygonArea | MultiPolygonArea:
    """Resolve a named place/admin boundary from an operator-supplied GeoJSON catalog."""
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if catalog.get("type") != "FeatureCollection":
        raise ValueError("Place catalog must be a GeoJSON FeatureCollection")
    wanted = name.strip().casefold()
    matches = []
    for feature in catalog.get("features", []):
        properties = feature.get("properties") or {}
        names = [properties.get("name"), *(properties.get("aliases") or [])]
        if wanted in {value.strip().casefold() for value in names if isinstance(value, str)}:
            matches.append(feature)
    if len(matches) != 1:
        raise ValueError(f"Named AOI {name!r} has {len(matches)} matches; supply one unambiguous boundary")
    return polygon_from_geojson(matches[0])


@dataclass(frozen=True)
class Request:
    area: Area | PolygonArea | MultiPolygonArea
    category: str | tuple[str, ...]
    declared_use: str
    operator_contact: str | None = None
    max_requests_per_second: float | None = None

    def __post_init__(self) -> None:
        if not self.categories or any(category not in SUPPORTED_CATEGORIES for category in self.categories):
            raise ValueError(f"Unsupported category: {self.category}")
        if self.declared_use not in {"internal", "commercial", "redistribute"}:
            raise ValueError(f"Unsupported declared use: {self.declared_use}")
        if self.max_requests_per_second is not None and self.max_requests_per_second <= 0:
            raise ValueError("Request rate must be positive")

    @property
    def categories(self) -> tuple[str, ...]:
        values = (self.category,) if isinstance(self.category, str) else self.category
        return tuple(sorted(set(values)))


def category_from_text(text: str) -> str:
    matches = categories_from_text(text)
    if len(matches) != 1:
        raise ValueError("Category is ambiguous or unsupported; provide an explicit category")
    return matches[0]


def categories_from_text(text: str) -> tuple[str, ...]:
    normalized = text.casefold()
    spans = []
    for category, words in SUPPORTED_CATEGORIES.items():
        for word in words:
            for match in re.finditer(r"(?<!\w)" + re.escape(word) + r"(?!\w)", normalized):
                spans.append((match.start(), match.end(), category))
    selected: list[tuple[int, int, str]] = []
    for start, end, category in sorted(spans, key=lambda item: (-(item[1] - item[0]), item[0], item[2])):
        if not any(start < old_end and end > old_start for old_start, old_end, _ in selected):
            selected.append((start, end, category))
    if not selected:
        raise ValueError("Category is ambiguous or unsupported; provide an explicit category")
    return tuple(sorted({category for _, _, category in selected}))


def _ascii_arabic(text: str) -> str:
    # A comparison key, never used as a published translation.
    mapping = str.maketrans({
        "ا": "a", "أ": "a", "إ": "a", "آ": "a", "ب": "b", "ت": "t", "ث": "th",
        "ج": "j", "ح": "h", "خ": "kh", "د": "d", "ذ": "dh", "ر": "r", "ز": "z",
        "س": "s", "ش": "sh", "ص": "s", "ض": "d", "ط": "t", "ظ": "z", "ع": "a",
        "غ": "gh", "ف": "f", "ق": "q", "ك": "k", "ل": "l", "م": "m", "ن": "n",
        "ه": "h", "ة": "h", "و": "w", "ؤ": "w", "ي": "y", "ى": "a", "ئ": "y",
    })
    return text.translate(mapping)


def name_key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.replace("ـ", "")
    tokens = re.findall(r"[a-z0-9]+|[\u0621-\u064a]+", value)
    generic = {"al", "el", "the", "pharmacy", "clinic", "hospital", "school", "صيدلية", "صيدليه", "عيادة", "مستشفى", "مدرسة"}
    normalized = []
    for token in tokens:
        if token in generic:
            continue
        if re.search(r"[\u0621-\u064a]", token):
            token = re.sub(r"^ال", "", token)
            token = _ascii_arabic(token)
        token = re.sub(r"[aeiouy]", "", token)
        if token:
            normalized.append(token)
    return " ".join(normalized)


def distance_m(a: dict[str, Any], b: dict[str, Any]) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    x = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371008.8 * 2 * asin(min(1.0, sqrt(x)))


def canonicalize(raw: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    lat, lon = float(raw["lat"]), float(raw["lon"])
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f"Invalid coordinate in {source['name']}:{raw.get('id')}")
    category = raw.get("category", "")
    if category not in SUPPORTED_CATEGORIES:
        raise ValueError(f"Unmapped category {category!r}")
    source_key = f"{source['name']}:{raw['id']}"
    fields = {
        "name_en": raw.get("name_en"), "name_ar": raw.get("name_ar"),
        "category": category, "phone": raw.get("phone"), "email": raw.get("email"),
        "address": raw.get("address"), "hours": raw.get("hours"),
        "source_category": raw.get("source_category"),
        "website": raw.get("website"),
        "address_street": raw.get("address_street"),
        "address_city": raw.get("address_city"),
        "address_region": raw.get("address_region"),
        "address_postcode": raw.get("address_postcode"),
        "address_country": raw.get("address_country"),
        "footprint_ref": raw.get("footprint_ref"),
    }
    return {
        "source_key": source_key, "lat": lat, "lon": lon,
        **fields,
        "alternate_names": raw.get("alternate_names") or [],
        "geometry_method": raw.get("geometry_method") or ("fixture_synthetic" if source.get("kind") == "fixture" else "source_point"),
        "harvested_at": str(raw.get("harvested_at") or ""),
        "confidence": min(float(source.get("reliability_weight", 0.5)),
                          float(raw.get("geometry_confidence", 1.0))),
        "attribution": source["attribution"], "license": source["license"],
        "geometry_attribution": raw.get("geometry_attribution"),
        "geometry_license": raw.get("geometry_license"),
        "provenance": {key: source_key for key, val in fields.items() if val is not None},
        "geometry_provenance": raw.get("geometry_provenance") or source_key,
    }


def _match_score(a: dict[str, Any], b: dict[str, Any]) -> float:
    if a["category"] != b["category"]:
        return 0.0
    metres = distance_m(a, b)
    if metres > 75:
        return 0.0
    keys_a = [name_key(a[k]) for k in ("name_en", "name_ar") if a.get(k)]
    keys_b = [name_key(b[k]) for k in ("name_en", "name_ar") if b.get(k)]
    name = max((SequenceMatcher(None, x, y).ratio() for x in keys_a for y in keys_b if x and y), default=0.0)
    phone_a = re.sub(r"\D", "", a.get("phone") or "")
    phone_b = re.sub(r"\D", "", b.get("phone") or "")
    phone_match = bool(phone_a and phone_b and phone_a == phone_b)
    if name < 0.70 and not phone_match:
        return 0.0
    return 0.60 * name + 0.25 * (1 - metres / 75) + 0.15 * int(phone_match)


def conflate(records: list[dict[str, Any]], algorithm_version: int = 2) -> list[dict[str, Any]]:
    if algorithm_version not in (1, 2):
        raise ValueError(f"Unsupported conflation algorithm version: {algorithm_version}")
    records = sorted(records, key=lambda row: row["source_key"])
    parent = list(range(len(records)))
    cluster_phones = [
        {row["source_key"].partition(":")[0]: re.sub(r"\D", "", row.get("phone") or "")}
        for row in records
    ]

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    by_latitude = sorted(range(len(records)), key=lambda index: records[index]["lat"])
    for position, original_index in enumerate(by_latitude):
        first = records[original_index]
        for next_position in range(position + 1, len(by_latitude)):
            other_index = by_latitude[next_position]
            second = records[other_index]
            # 0.0007 degrees of latitude exceeds 75 m at every latitude.
            if second["lat"] - first["lat"] > 0.0007:
                break
            if first["category"] != second["category"] or first["source_key"] == second["source_key"]:
                continue
            i, j = sorted((original_index, other_index))
            if _match_score(records[i], records[j]) >= 0.68:
                left, right = root(i), root(j)
                if left == right:
                    continue
                shared = cluster_phones[left].keys() & cluster_phones[right].keys()
                # Same-source records need stronger evidence than name/distance:
                # identical nonempty phone and a point separation under 15 m.
                if algorithm_version >= 2 and shared and (distance_m(first, second) > 15 or any(
                    not cluster_phones[left][source]
                    or cluster_phones[left][source] != cluster_phones[right][source]
                    for source in shared
                )):
                    continue
                parent[right] = left
                cluster_phones[left].update(cluster_phones[right])

    groups: dict[int, list[dict[str, Any]]] = {}
    for i, record in enumerate(records):
        groups.setdefault(root(i), []).append(record)

    output = []
    for group in groups.values():
        ranked = sorted(group, key=lambda row: (-row["confidence"], row["source_key"]))
        source_keys = sorted(row["source_key"] for row in group)
        merged: dict[str, Any] = {
            "stable_id": sha256("|".join(source_keys).encode()).hexdigest()[:20],
            "source_keys": source_keys,
            "lat": ranked[0]["lat"], "lon": ranked[0]["lon"],
            "geometry_provenance": ranked[0]["geometry_provenance"],
            "geometry_method": ranked[0]["geometry_method"],
            "harvested_at": max(row["harvested_at"] for row in group),
            "confidence": max(row["confidence"] for row in group),
            "attributions": sorted({value for row in group for value in
                                    (row["attribution"], row.get("geometry_attribution")) if value}),
            "licenses": sorted({value for row in group for value in
                                (row["license"], row.get("geometry_license")) if value}),
            "provenance": {},
        }
        for field in ("name_en", "name_ar", "category", "phone", "email", "address", "hours", "source_category", "website", "address_street", "address_city", "address_region", "address_postcode", "address_country", "footprint_ref"):
            chosen = next((row for row in ranked if row.get(field) is not None), None)
            merged[field] = chosen[field] if chosen else None
            if chosen:
                merged["provenance"][field] = chosen["source_key"]
        merged["language_complete"] = bool(merged["name_en"] and merged["name_ar"])
        merged["alternate_names"] = sorted({name for row in group for name in row.get("alternate_names", [])})
        output.append(merged)
    return sorted(output, key=lambda row: row["stable_id"])


def reconcile_ids(previous: list[dict[str, Any]], current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep a POI ID when its contributing source set grows or shrinks."""
    candidates = []
    for current_index, record in enumerate(current):
        current_keys = set(record["source_keys"])
        for old in previous:
            overlap = len(current_keys & set(old.get("source_keys", [])))
            if overlap:
                candidates.append((-overlap, old["stable_id"], current_index))
    used_current, used_old = set(), set()
    for _, old_id, current_index in sorted(candidates):
        if current_index not in used_current and old_id not in used_old:
            current[current_index]["stable_id"] = old_id
            used_current.add(current_index)
            used_old.add(old_id)
    return sorted(current, key=lambda row: row["stable_id"])


def change_set(previous: list[dict[str, Any]], current: list[dict[str, Any]]) -> dict[str, Any]:
    old = {row["stable_id"]: row for row in previous}
    new = {row["stable_id"]: row for row in current}
    updated = []
    for key in sorted(old.keys() & new.keys()):
        fields = sorted(name for name in set(old[key]) | set(new[key]) if name != "harvested_at" and old[key].get(name) != new[key].get(name))
        if fields:
            updated.append({"stable_id": key, "changed_fields": fields})
    return {
        "added": sorted(new.keys() - old.keys()),
        "updated": updated,
        "removed": sorted(old.keys() - new.keys()),
        "unchanged": sorted(key for key in old.keys() & new.keys() if not any(row["stable_id"] == key for row in updated)),
    }


def feature_collection(records: list[dict[str, Any]]) -> dict[str, Any]:
    def attributes(row: dict[str, Any]) -> dict[str, Any]:
        fields = {key: val for key, val in row.items() if key not in {"lat", "lon", "provenance"}}
        fields.update({f"provenance_{key}": value for key, value in row.get("provenance", {}).items()})
        return fields

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature", "id": row["stable_id"],
                "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
                "properties": attributes(row),
            }
            for row in records
        ],
    }


def reproducibility_hash(records: list[dict[str, Any]]) -> str:
    payload = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()

"""Source policy and adapters. No network call precedes the license gate."""

from __future__ import annotations

from pathlib import Path
from os import environ
from threading import Lock
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request as HttpRequest, urlopen
from urllib.robotparser import RobotFileParser
import json
import re

from .core import Area, Request
from .taxonomy import by_id


def load_registry(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    sources = data["sources"]
    names = [source["name"] for source in sources]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate source names")
    for source in sources:
        for field in ("name", "kind", "license", "allowed_uses", "attribution", "rate_limit_per_second", "auth_mode", "freshness", "reliability_weight"):
            if source.get(field) in (None, "", []):
                raise ValueError(f"Source {source.get('name')} missing {field}")
        if source["rate_limit_per_second"] <= 0:
            raise ValueError("Rate limit must be positive")
        if not 0 <= source["reliability_weight"] <= 1:
            raise ValueError("Reliability weight must be between zero and one")
        if not isinstance(source.get("commercial_use"), bool):
            raise ValueError("Source must declare commercial_use as a boolean")
        if source.get("coverage_bbox") is not None and len(source["coverage_bbox"]) != 4:
            raise ValueError("coverage_bbox must have four coordinates")
    return sources


def license_gate(source: dict, declared_use: str) -> tuple[bool, str]:
    if declared_use in {"commercial", "redistribute"} and not source.get("commercial_use", False):
        return False, f"{source['name']} commercial use is not approved: {source['license']}"
    if declared_use not in source["allowed_uses"]:
        return False, f"{source['name']} is not approved for {declared_use}: {source['license']}"
    return True, "allowed by declared source policy"


def covers_area(source: dict, requested: Area) -> bool:
    coverage = source.get("coverage_bbox")
    if coverage is None:
        return True
    west, south, east, north = coverage
    # A partial overlap would silently return an incomplete harvest for the AOI.
    return (west <= requested.west and requested.east <= east
            and south <= requested.south and requested.north <= north)


class TokenBucket:
    def __init__(self, rate_per_second: float):
        self.rate = rate_per_second
        self.next_allowed = 0.0
        self._lock = Lock()

    def wait(self) -> None:
        with self._lock:
            now = monotonic()
            if now < self.next_allowed:
                sleep(self.next_allowed - now)
            self.next_allowed = monotonic() + 1 / self.rate

    def lower_rate(self, rate: float) -> None:
        with self._lock:
            self.rate = min(self.rate, rate)


_LIMITERS: dict[str, TokenBucket] = {}
_LIMITERS_LOCK = Lock()


def _source_limiter(source: dict, requested_ceiling: float | None) -> TokenBucket:
    rate = min(source["rate_limit_per_second"], requested_ceiling or float("inf"))
    key = source["endpoint"]
    with _LIMITERS_LOCK:
        if key not in _LIMITERS:
            _LIMITERS[key] = TokenBucket(rate)
        else:
            # A later invocation can slow a source down, never speed it up.
            _LIMITERS[key].lower_rate(rate)
        return _LIMITERS[key]


def _robots_allowed(endpoint: str, user_agent: str) -> bool:
    parsed = urlparse(endpoint)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        with urlopen(HttpRequest(robots_url, headers={"User-Agent": user_agent}), timeout=10) as response:
            lines = response.read(256_000).decode("utf-8", errors="replace").splitlines()
    except HTTPError as exc:
        if 400 <= exc.code < 500:
            return True  # RFC 9309: an unavailable robots.txt permits access.
        raise RuntimeError(f"Could not verify robots.txt for {endpoint}: {exc}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"Could not verify robots.txt for {endpoint}: {exc}") from exc
    parser = RobotFileParser()
    parser.parse(lines)
    return parser.can_fetch(user_agent, endpoint)


def _get_json(url: str, limiter: TokenBucket, user_agent: str, prior_cache: dict | None = None) -> tuple[dict | None, dict]:
    prior_cache = prior_cache if prior_cache and prior_cache.get("url") == url else None
    for attempt in range(4):
        limiter.wait()
        try:
            headers = {"User-Agent": user_agent, "Accept": "application/json"}
            if prior_cache:
                if prior_cache.get("etag"):
                    headers["If-None-Match"] = prior_cache["etag"]
                if prior_cache.get("last_modified"):
                    headers["If-Modified-Since"] = prior_cache["last_modified"]
            request = HttpRequest(url, headers=headers)
            with urlopen(request, timeout=60) as response:
                payload = response.read()
                try:
                    parsed = json.loads(payload)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise RuntimeError(f"Source returned invalid JSON (HTTP {response.status}, content-type {response.headers.get('Content-Type', 'unknown')})") from exc
                return parsed, {"url": url, "etag": response.headers.get("ETag"),
                                "last_modified": response.headers.get("Last-Modified")}
        except HTTPError as exc:
            if exc.code == 304 and prior_cache:
                return None, prior_cache
            if exc.code not in (429, 502, 503, 504) or attempt == 3:
                raise
            retry_after = exc.headers.get("Retry-After")
            delay = min(30, float(retry_after)) if retry_after and retry_after.isdigit() else 2 ** attempt
            sleep(delay)
        except (URLError, TimeoutError):
            if attempt == 3:
                raise
            sleep(2 ** attempt)
    raise RuntimeError("Request retries exhausted")


def _fixture(source: dict, registry_path: Path) -> list[dict]:
    fixture_path = (registry_path.parent / source["path"]).resolve()
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def _overpass(source: dict, request: Request, prior_cache: dict | None = None,
              prior_records: list[dict] | None = None) -> tuple[list[dict], dict]:
    contact = request.operator_contact or environ.get("POI_CONTACT")
    if not contact:
        raise ValueError("Provide an operator contact before making live source requests")
    user_agent = f"POIHarvesterAgent/0.1 ({contact})"
    endpoint = source["endpoint"]
    if not endpoint.startswith("https://"):
        raise ValueError("Overpass endpoint must use HTTPS")
    if not _robots_allowed(endpoint, user_agent):
        raise PermissionError(f"robots.txt disallows {endpoint}")
    bbox = request.area.bounds
    tags_requested = {
        tag: category
        for category in request.categories
        for tag in by_id()[category]["osm_tags"]
    }
    box = f"{bbox.south},{bbox.west},{bbox.north},{bbox.east}"
    clauses = []
    for tag in sorted(tags_requested):
        key, value = tag.split("=", 1)
        clauses.append(f'nwr["{key}"="{value}"]({box});')
    query = f'[out:json][timeout:60];({"".join(clauses)});out center tags;'
    url = endpoint + "?" + urlencode({"data": query})
    payload, cache = _get_json(url, _source_limiter(source, request.max_requests_per_second), user_agent, prior_cache)
    if payload is None:
        if prior_records is None:
            raise RuntimeError("Source returned 304 but no previous records are available")
        return prior_records, cache
    records = []
    for element in payload.get("elements", []):
        tags = element.get("tags", {})
        matching = [(tag, category) for tag, category in tags_requested.items()
                    if tags.get(tag.split("=", 1)[0]) == tag.split("=", 1)[1]]
        if not matching:
            continue
        categories = {category for _, category in matching}
        if len(categories) != 1:
            records.append({"id": f"{element['type']}/{element['id']}",
                            "category_review_reason": f"Ambiguous OSM tags: {sorted(tag for tag, _ in matching)}"})
            continue
        category = next(iter(categories))
        source_tag = sorted(tag for tag, _ in matching)[0]
        base_name = tags.get("name", "")
        base_is_arabic = bool(re.search(r"[\u0600-\u06ff]", base_name))
        name_en = tags.get("name:en") or (None if base_is_arabic else base_name or None)
        name_ar = tags.get("name:ar") or (base_name if base_is_arabic else None)
        alternate_names = sorted({name.strip() for key in ("alt_name", "official_name", "short_name", "name:en", "name:ar") for name in (tags.get(key) or "").split(";") if name.strip() and name.strip() not in {name_en, name_ar}})
        location = element if element.get("type") == "node" else {}
        if "lat" not in location or "lon" not in location:
            records.append({
                "id": f"{element['type']}/{element['id']}",
                "category": category,
                "name_en": name_en,
                "name_ar": name_ar,
                "source_category": source_tag,
                "address": ", ".join(filter(None, [tags.get("addr:street"), tags.get("addr:city")])),
                "address_street": tags.get("addr:street"),
                "address_city": tags.get("addr:city"),
                "footprint_ref": f"https://www.openstreetmap.org/{element['type']}/{element['id']}",
            })
            continue
        records.append({
            "id": f"{element['type']}/{element['id']}",
            "lat": location["lat"], "lon": location["lon"],
            "name_en": name_en,
            "name_ar": name_ar,
            "alternate_names": alternate_names,
            "category": category,
            "source_category": source_tag,
            "geometry_method": "osm_node",
            "phone": tags.get("phone") or tags.get("contact:phone"),
            "email": tags.get("email") or tags.get("contact:email"),
            "address": ", ".join(filter(None, [tags.get("addr:street"), tags.get("addr:city")])),
            "address_street": tags.get("addr:street"),
            "address_city": tags.get("addr:city"),
            "address_region": tags.get("addr:state"),
            "address_postcode": tags.get("addr:postcode"),
            "address_country": tags.get("addr:country"),
            "website": tags.get("website") or tags.get("contact:website"),
            "hours": tags.get("opening_hours"),
        })
    return records, cache


def collect(source: dict, request: Request, registry_path: Path,
            prior_cache: dict | None = None, prior_records: list[dict] | None = None) -> tuple[list[dict], dict | None]:
    if source["kind"] == "fixture":
        return _fixture(source, registry_path), None
    if source["kind"] == "overpass":
        return _overpass(source, request, prior_cache, prior_records)
    raise ValueError(f"Unknown source adapter: {source['kind']}")

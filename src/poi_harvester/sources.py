"""Source policy and adapters. No network call precedes the license gate."""

from __future__ import annotations

from pathlib import Path
from contextlib import contextmanager, nullcontext, closing
from hashlib import sha256
from os import environ
from threading import Lock
from time import monotonic, sleep, time, get_clock_info, perf_counter
from tempfile import gettempdir
from email.utils import parsedate_to_datetime
from datetime import datetime
from math import isfinite
import sqlite3
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request as HttpRequest, urlopen
import json
import re

from .core import Area, Request
from .taxonomy import by_id
from .names import resolve_osm_names
from .robots import allowed as robots_allowed
from .snapshots import describe, accept_latest, validate_age, query_identity, digest, freshness_state


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
        if not isfinite(source["rate_limit_per_second"]) or source["rate_limit_per_second"] <= 0:
            raise ValueError("Rate limit must be positive")
        if not isfinite(source["reliability_weight"]) or not 0 <= source["reliability_weight"] <= 1:
            raise ValueError("Reliability weight must be between zero and one")
        if not isinstance(source.get("commercial_use"), bool):
            raise ValueError("Source must declare commercial_use as a boolean")
        if "coverage_bbox" not in source:
            raise ValueError("Source must explicitly declare coverage_bbox (null means global)")
        if source.get("coverage_bbox") is not None:
            if len(source["coverage_bbox"]) != 4:
                raise ValueError("coverage_bbox must have four coordinates")
            west, south, east, north = source["coverage_bbox"]
            Area(south, west, north, east)
        field = "path" if source["kind"] == "fixture" else "endpoint"
        if not source.get(field):
            raise ValueError(f"Source {source['name']} missing {field}")
        for field in ("request_timeout_seconds", "total_timeout_seconds", "max_snapshot_age_seconds"):
            if field in source and (not isfinite(source[field]) or source[field] <= 0):
                raise ValueError(f"{field} must be finite and positive")
        if "request_attempts" in source and (not isinstance(source["request_attempts"], int) or not 1 <= source["request_attempts"] <= 4):
            raise ValueError("request_attempts must be between 1 and 4")
        if source["auth_mode"] != "none":
            raise ValueError("Only auth_mode=none is implemented; configure an authentication adapter first")
        if not isinstance(source["allowed_uses"], list) or not set(source["allowed_uses"]) <= {"internal", "commercial", "redistribute"}:
            raise ValueError("Invalid source allowed_uses")
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


def _reserve_shared_request(endpoint: str, rate: float) -> float:
    """Claim an actual dispatch slot; delayed workers never consume stale reservations."""
    state = Path(environ.get("POI_RATE_STATE_PATH") or
                 str(Path(gettempdir()) / "poi_harvester_rate_v1.sqlite3"))
    state.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(state, timeout=30, isolation_level=None) as database:
        database.execute("CREATE TABLE IF NOT EXISTS dispatch_slots_v2 "
                         "(endpoint TEXT PRIMARY KEY, next_at REAL NOT NULL, interval REAL NOT NULL)")
        while True:
            database.execute("BEGIN IMMEDIATE")
            prior = database.execute("SELECT next_at, interval FROM dispatch_slots_v2 WHERE endpoint = ?", (endpoint,)).fetchone()
            now = time()
            interval = max(1 / rate + get_clock_info("time").resolution, prior[1] if prior else 0)
            delay = max(0.0, (prior[0] if prior else now) - now)
            if delay:
                # Share lower ceilings even before this worker wins the next slot.
                database.execute("UPDATE dispatch_slots_v2 SET interval = ? WHERE endpoint = ?", (interval, endpoint))
                database.execute("COMMIT")
                sleep(delay)
                continue
            database.execute("INSERT INTO dispatch_slots_v2(endpoint, next_at, interval) VALUES (?, ?, ?) "
                             "ON CONFLICT(endpoint) DO UPDATE SET next_at=excluded.next_at, interval=excluded.interval",
                             (endpoint, now + interval, interval))
            database.execute("COMMIT")
            return 0.0


class TokenBucket:
    def __init__(self, rate_per_second: float, endpoint: str | None = None):
        if not isfinite(rate_per_second) or rate_per_second <= 0:
            raise ValueError("Request rate must be finite and positive")
        self.rate = rate_per_second
        self.endpoint = endpoint
        self.next_allowed = 0.0
        self._lock = Lock()

    def wait(self) -> None:
        with self._lock:
            if self.endpoint:
                sleep(_reserve_shared_request(self.endpoint, self.rate))
                return
            now = monotonic()
            if now < self.next_allowed:
                sleep(self.next_allowed - now)
            self.next_allowed = monotonic() + 1 / self.rate

    @contextmanager
    def request_slot(self, remaining=None):
        """Serialize actual HTTP transport per endpoint, with shared post-response cooldown."""
        if not self.endpoint:
            self.wait()
            yield
            return
        state = Path(environ.get("POI_RATE_STATE_PATH") or
                     str(Path(gettempdir()) / "poi_harvester_rate_v1.sqlite3"))
        state = state.with_name(state.name + ".request_" + sha256(self.endpoint.encode()).hexdigest()[:16])
        state.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(state, timeout=min(180, remaining()) if remaining else 180, isolation_level=None)) as database:
            database.execute("CREATE TABLE IF NOT EXISTS transport_slot "
                             "(id INTEGER PRIMARY KEY, next_at REAL NOT NULL, interval REAL NOT NULL)")
            database.execute("BEGIN IMMEDIATE")
            prior = database.execute("SELECT next_at, interval FROM transport_slot WHERE id=1").fetchone()
            interval = max(1 / self.rate + get_clock_info("time").resolution, prior[1] if prior else 0)
            if prior:
                delay = max(0.0, prior[0] - time())
                if remaining:
                    if delay >= remaining():
                        raise TimeoutError("Source cooldown exceeds refresh budget; no stale fallback")
                    while delay > 0:
                        remaining()
                        interval_wait = min(delay, 0.25)
                        sleep(interval_wait)
                        delay = max(0.0, prior[0] - time())
                else:
                    sleep(delay)
            cooldown = interval
            try:
                yield
            except HTTPError as exc:
                if exc.code == 429:
                    cooldown = max(cooldown, _retry_after_seconds(exc.headers.get("Retry-After"), 0))
                raise
            finally:
                database.execute("INSERT INTO transport_slot(id,next_at,interval) VALUES(1,?,?) "
                                 "ON CONFLICT(id) DO UPDATE SET next_at=excluded.next_at, interval=excluded.interval",
                                 (time() + cooldown, interval))
                database.execute("COMMIT")

    def lower_rate(self, rate: float) -> None:
        with self._lock:
            self.rate = min(self.rate, rate)


_LIMITERS: dict[str, TokenBucket] = {}
_LIMITERS_LOCK = Lock()


def _source_limiter(source: dict, requested_ceiling: float | None) -> TokenBucket:
    if requested_ceiling is not None and (not isfinite(requested_ceiling) or requested_ceiling <= 0):
        raise ValueError("Request ceiling must be finite and positive")
    rate = min(source["rate_limit_per_second"], requested_ceiling or float("inf"))
    key = source["endpoint"]
    with _LIMITERS_LOCK:
        if key not in _LIMITERS:
            _LIMITERS[key] = TokenBucket(rate, key)
        else:
            # A later invocation can slow a source down, never speed it up.
            _LIMITERS[key].lower_rate(rate)
        return _LIMITERS[key]


def _robots_allowed(endpoint: str, user_agent: str, limiter: TokenBucket | None = None) -> bool:
    parsed = urlparse(endpoint)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        with limiter.request_slot() if limiter else nullcontext():
            with urlopen(HttpRequest(robots_url, headers={"User-Agent": user_agent}), timeout=10) as response:
                body = response.read(512_001)
                if len(body) > 512_000:
                    raise RuntimeError("robots.txt exceeds supported size; refusing unverified access")
                lines = body.decode("utf-8", errors="replace").splitlines()
    except HTTPError as exc:
        if exc.code == 429:
            raise RuntimeError(f"robots.txt rate limited for {endpoint}") from exc
        if 400 <= exc.code < 500:
            return True  # RFC 9309: an unavailable robots.txt permits access.
        raise RuntimeError(f"Could not verify robots.txt for {endpoint}: {exc}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"Could not verify robots.txt for {endpoint}: {exc}") from exc
    return robots_allowed(lines, user_agent, endpoint)


def _retry_after_seconds(value: str | None, attempt: int) -> float:
    if value:
        try:
            delay = float(value)
            if isfinite(delay) and delay >= 0:
                return delay
        except ValueError:
            try:
                return max(0.0, parsedate_to_datetime(value).timestamp() - time())
            except (ValueError, TypeError, OverflowError):
                pass
    return float(2 ** attempt)


def _get_json(url: str, limiter: TokenBucket, user_agent: str, prior_cache: dict | None = None,
              *, timeout_seconds: float = 60, attempts: int = 4,
              total_timeout_seconds: float = 300, cancel_event=None) -> tuple[dict | None, dict]:
    prior_cache = prior_cache if prior_cache and prior_cache.get("url") == url else None
    if not all(isfinite(v) and v > 0 for v in (timeout_seconds, total_timeout_seconds)) or not 1 <= attempts <= 4:
        raise ValueError("Invalid HTTP timeout/retry configuration")
    deadline = perf_counter() + total_timeout_seconds
    def remaining():
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Source refresh cancelled; no stale fallback")
        seconds = deadline - perf_counter()
        if seconds <= 0:
            raise TimeoutError("Source refresh total timeout budget exhausted; no stale fallback")
        return seconds
    for attempt in range(attempts):
        remaining()
        try:
            headers = {"User-Agent": user_agent, "Accept": "application/json"}
            if prior_cache:
                if prior_cache.get("etag"):
                    headers["If-None-Match"] = prior_cache["etag"]
                if prior_cache.get("last_modified"):
                    headers["If-Modified-Since"] = prior_cache["last_modified"]
            request = HttpRequest(url, headers=headers)
            with limiter.request_slot(remaining=remaining):
                remaining()
                with urlopen(request, timeout=min(timeout_seconds, remaining())) as response:
                    chunks = []
                    if hasattr(response, "read1"):
                        while True:
                            budget = min(timeout_seconds, remaining())
                            socket = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
                            if socket is not None:
                                socket.settimeout(budget)
                            chunk = response.read1(65536)
                            remaining()
                            if not chunk:
                                break
                            chunks.append(chunk)
                        payload = b"".join(chunks)
                    else:
                        payload = response.read()
                    remaining()
                    try:
                        parsed = json.loads(payload)
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raise RuntimeError(f"Source returned invalid JSON (HTTP {response.status}, content-type {response.headers.get('Content-Type', 'unknown')})") from exc
                    return parsed, {"url": url, "etag": response.headers.get("ETag"),
                                    "last_modified": response.headers.get("Last-Modified")}
        except HTTPError as exc:
            if exc.code == 304 and prior_cache:
                return None, prior_cache
            if exc.code not in (429, 502, 503, 504) or attempt == attempts - 1:
                raise
            retry_after = exc.headers.get("Retry-After")
            delay = _retry_after_seconds(retry_after, attempt)
            if delay >= remaining():
                raise TimeoutError("Retry-After exceeds refresh budget; no early retry or stale fallback")
            sleep(delay)
        except (URLError, TimeoutError) as exc:
            if attempt == attempts - 1:
                raise TimeoutError(f"Source refresh failed after {attempts} attempts; no stale fallback: {exc}") from exc
            delay = 2 ** attempt
            if delay >= remaining():
                raise TimeoutError("Refresh retry budget exhausted; no stale fallback") from exc
            sleep(delay)
    raise RuntimeError("Request retries exhausted")


def _fixture(source: dict, registry_path: Path) -> list[dict]:
    fixture_path = (registry_path.parent / source["path"]).resolve()
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def _source_snapshot_time(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _overpass(source: dict, request: Request, prior_cache: dict | None = None,
              prior_records: list[dict] | None = None) -> tuple[list[dict], dict]:
    contact = request.operator_contact or environ.get("POI_CONTACT")
    if not contact:
        raise ValueError("Provide an operator contact before making live source requests")
    user_agent = f"POIHarvesterAgent/0.1 ({contact})"
    endpoint = source["endpoint"]
    if not endpoint.startswith("https://"):
        raise ValueError("Overpass endpoint must use HTTPS")
    limiter = _source_limiter(source, request.max_requests_per_second)
    if not _robots_allowed(endpoint, user_agent, limiter):
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
    payload, cache = _get_json(url, limiter, user_agent, prior_cache,
                               timeout_seconds=source.get("request_timeout_seconds", 60),
                               attempts=source.get("request_attempts", 4),
                               total_timeout_seconds=source.get("total_timeout_seconds", 300))
    if payload is None:
        if prior_records is None:
            raise RuntimeError("Source returned 304 but no previous records are available")
        if not cache.get("snapshot") or not all("source_payload" in row for row in prior_records):
            raise RuntimeError("304 lacks verified full snapshot evidence; refusing stale fallback")
        candidate = {**cache["snapshot"], "mode": "live"}
        if candidate["query_hash"] != query_identity(source, request):
            raise ValueError("Conditional response source snapshot scope mismatch")
        elements = sorted((row["source_payload"] for row in prior_records), key=lambda row: (row["type"], row["id"]))
        if digest(elements) != candidate["dataset_hash"]:
            raise ValueError("Conditional response source dataset integrity mismatch")
        validate_age(source, candidate)
        candidate["freshness_decision"] = accept_latest(source, candidate, write=False)
        candidate["freshness"] = "LIVE_AGE_POLICY_VALIDATED" if source.get("max_snapshot_age_seconds") else "TIMESTAMP_VALIDATED"
        candidate['freshness_state'] = freshness_state(source, candidate)
        cache = {**cache, "snapshot": candidate}
        return parse_overpass_payload(source, request, {"elements": elements, "osm3s": {"timestamp_osm_base": candidate["timestamp"]}}), cache
    if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
        raise RuntimeError("Incomplete Overpass response: elements array missing; no changes/publication")
    if payload.get("remark") or payload.get("error"):
        raise RuntimeError("Incomplete Overpass response: " + str(payload.get("remark") or payload.get("error")) + "; no changes/publication")
    snapshot = _source_snapshot_time(payload.get("osm3s", {}).get("timestamp_osm_base"))
    prior_snapshots = [
        stamp for record in (prior_records or [])
        if (stamp := _source_snapshot_time(record.get("source_version"))) is not None
    ]
    if prior_snapshots and snapshot is None:
        raise ValueError("Missing source snapshot timestamp cannot replace previous capture")
    if snapshot is not None and prior_snapshots and snapshot < max(prior_snapshots):
        raise RuntimeError(
            "Source snapshot is older than the previous capture; refusing an incremental refresh "
            f"that could incorrectly remove newer records ({snapshot.isoformat()} < {max(prior_snapshots).isoformat()})")
    descriptor = describe(source, request, payload)
    descriptor["freshness_decision"] = accept_latest(source, descriptor, (prior_cache or {}).get("snapshot"))
    cache = {**cache, "snapshot": descriptor}
    return parse_overpass_payload(source, request, payload), cache


def parse_overpass_payload(source: dict, request: Request, payload: dict) -> list[dict]:
    tags_requested = {tag: category for category in request.categories
                      for tag in by_id()[category]["osm_tags"]}
    records = []
    for element in payload.get("elements", []):
        capture_fields = {"source_payload": element,
                          "source_version": element.get("version") or element.get("timestamp") or
                                            payload.get("osm3s", {}).get("timestamp_osm_base")}
        tags = element.get("tags", {})
        matching = [(tag, category) for tag, category in tags_requested.items()
                    if tags.get(tag.split("=", 1)[0]) == tag.split("=", 1)[1]]
        if not matching:
            continue
        categories = {category for _, category in matching}
        if len(categories) != 1:
            records.append({**capture_fields, "id": f"{element['type']}/{element['id']}",
                            "category_review_reason": f"Ambiguous OSM tags: {sorted(tag for tag, _ in matching)}"})
            continue
        category = next(iter(categories))
        source_tag = sorted(tag for tag, _ in matching)[0]
        source_key = f"{source.get('name', 'openstreetmap')}:{element['type']}/{element['id']}"
        names = resolve_osm_names(tags, source_key)
        name_en, name_ar = names.get("name_en"), names.get("name_ar")
        alternate_names = names["alternate_names"]
        location = element if element.get("type") == "node" else {}
        derived = False
        if element.get("type") != "node" and request.allow_source_centers:
            center = element.get("center") or {}
            try:
                if all(isfinite(float(center[key])) for key in ("lat", "lon")) and -90 <= float(center["lat"]) <= 90 and -180 <= float(center["lon"]) <= 180:
                    location, derived = center, True
            except (KeyError, TypeError, ValueError):
                pass
        if "lat" not in location or "lon" not in location:
            records.append({
                **capture_fields, **names,
                "geometry_status": "unresolved",
                "geometry_unresolved_reason": "No usable source point; footprint center is not an authoritative entrance.",
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
            **capture_fields, **names,
            **({"geometry_derived": True, "geometry_confidence": 0.35,
                "geometry_derivation": "OSM footprint bounding-box center; not a verified pharmacy entrance",
                "geometry_provenance": source_key + ":center",
                "footprint_ref": f"https://www.openstreetmap.org/{element['type']}/{element['id']}"} if derived else {}),
            "id": f"{element['type']}/{element['id']}",
            "lat": location["lat"], "lon": location["lon"],
            "name_en": name_en,
            "name_ar": name_ar,
            "alternate_names": alternate_names,
            "category": category,
            "source_category": source_tag,
            "geometry_method": "source_center_derived" if derived else "osm_node",
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
    return records


def collect(source: dict, request: Request, registry_path: Path,
            prior_cache: dict | None = None, prior_records: list[dict] | None = None) -> tuple[list[dict], dict | None]:
    if source["kind"] == "fixture":
        return _fixture(source, registry_path), None
    if source["kind"] == "overpass":
        return _overpass(source, request, prior_cache, prior_records)
    raise ValueError(f"Unknown source adapter: {source['kind']}")

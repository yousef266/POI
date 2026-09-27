"""Timestamp validation, coherent snapshot IDs and explicit captured-input selection."""

from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import sqlite3


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def timestamp(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Malformed source snapshot timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Malformed source snapshot timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("Source snapshot timestamp requires a timezone")
    return parsed.astimezone(timezone.utc)


def query_identity(source, request):
    return digest({"source": source.get("name", source["endpoint"]), "endpoint": source["endpoint"],
                   "area": asdict(request.area), "categories": sorted(request.categories)})


def validate_age(source, descriptor, now=None):
    """Only live results may claim freshness; historical captures are explicit."""
    limit = source.get("max_snapshot_age_seconds")
    if limit is None or descriptor.get("mode") != "live":
        return
    stamp = timestamp(descriptor.get("timestamp"))
    if stamp is None:
        raise ValueError("Live source is missing its snapshot timestamp; freshness cannot be verified")
    now = now or datetime.now(timezone.utc)
    age = (now - stamp).total_seconds()
    if age < -300:
        raise ValueError("Source snapshot timestamp is in the future")
    if age > limit:
        if source.get('freshness_policy', 'strict') == 'latest_available':
            return
        raise RuntimeError(f"Stale live source snapshot {descriptor['timestamp']}: age {age:.0f}s exceeds {limit}s; no fallback, changes or publication")


def freshness_state(source, descriptor, now=None):
    """Explicit state evaluated at use time; a pin never claims to be current."""
    try:
        stamp = timestamp(descriptor.get('timestamp'))
    except ValueError:
        return 'UNKNOWN'
    if stamp is None:
        return 'UNKNOWN'
    if descriptor.get('mode') != 'live':
        return 'HISTORICAL'
    limit = source.get('max_snapshot_age_seconds', descriptor.get('max_snapshot_age_seconds'))
    if limit is None:
        return 'UNKNOWN'
    age = ((now or datetime.now(timezone.utc)) - stamp).total_seconds()
    return 'UNKNOWN' if age < -300 else 'STALE' if age > limit else 'CURRENT'


def describe(source, request, payload, mode="live", now=None):
    stamp = payload.get("osm3s", {}).get("timestamp_osm_base")
    parsed = timestamp(stamp)
    elements = sorted(payload.get("elements", []), key=lambda row: (row["type"], row["id"]))
    keys = [(row["type"], row["id"]) for row in elements]
    if len(keys) != len(set(keys)):
        raise ValueError("Source snapshot has duplicate record IDs")
    for element in elements:
        if element.get("timestamp") and parsed and timestamp(element["timestamp"]) > parsed:
            raise ValueError("Source feature version is newer than its snapshot")
        if "version" in element and (not isinstance(element["version"], int) or element["version"] <= 0):
            raise ValueError("Malformed source feature version identifier")
    descriptor = {"schema_version": 1, "source": source.get("name", source["endpoint"]),
                  "endpoint": source["endpoint"], "query_hash": query_identity(source, request),
                  "timestamp": parsed.isoformat() if parsed else None, "dataset_hash": digest(elements),
                  "mode": mode, "freshness": "TIMESTAMP_VALIDATED" if parsed else "MISSING_TIMESTAMP_UNVERIFIED"}
    descriptor["snapshot_id"] = digest({k:descriptor[k] for k in ("source", "endpoint", "query_hash", "timestamp", "dataset_hash")})
    validate_age(source, descriptor, now)
    if mode == "live" and source.get("max_snapshot_age_seconds") is not None:
        descriptor["freshness"] = "LIVE_AGE_POLICY_VALIDATED"
        descriptor["max_snapshot_age_seconds"] = source["max_snapshot_age_seconds"]
    elif mode != "live":
        descriptor["freshness"] = "HISTORICAL_CAPTURE_NOT_LIVE"
    descriptor['freshness_state'] = freshness_state(source, descriptor, now)
    if source.get('freshness_policy') == 'latest_available':
        descriptor['freshness_policy'] = 'latest_available'
        descriptor['availability_scope'] = 'Newest response accepted from the selected source; not a claim about all providers.'
        if descriptor['freshness_state'] == 'STALE':
            descriptor['freshness'] = 'OLDER_DATA_ACCEPTED_WITH_DISCLOSURE'
            descriptor['freshness_notice'] = f"Available source data is dated {descriptor['timestamp']}; it is not current."
    return descriptor


def compare(candidate, previous=None):
    current = timestamp(candidate.get("timestamp"))
    if previous:
        for field in ("source", "endpoint", "query_hash"):
            if candidate.get(field) != previous.get(field):
                raise ValueError("Source snapshot identity/version mismatch: " + field)
        prior = timestamp(previous.get("timestamp"))
        if prior and not current:
            raise ValueError("Missing source snapshot timestamp cannot replace a timestamped capture")
        if prior and current < prior:
            raise RuntimeError("Source snapshot is older than the previous capture; refusing false removals/publication")
        if prior and current == prior:
            if previous.get("dataset_hash") and candidate.get("dataset_hash") != previous["dataset_hash"]:
                raise ValueError("Equal source timestamp has inconsistent dataset/version hash")
            return "EQUAL_SNAPSHOT"
    return "NEWER_SNAPSHOT" if current else "UNVERIFIED_TIMESTAMP"


def accept_latest(source, candidate, prior=None, write=True):
    decision = compare(candidate, prior)
    store = source.get("snapshot_store")
    if not store:
        return decision
    path = Path(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=30)) as db:
        db.execute("CREATE TABLE IF NOT EXISTS snapshots(scope TEXT PRIMARY KEY, descriptor TEXT NOT NULL)")
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT descriptor FROM snapshots WHERE scope=?", (candidate["query_hash"],)).fetchone()
        if row:
            decision = compare(candidate, json.loads(row[0]))
        if write and candidate.get("timestamp"):
            db.execute("INSERT INTO snapshots VALUES(?,?) ON CONFLICT(scope) DO UPDATE SET descriptor=excluded.descriptor",
                       (candidate["query_hash"], json.dumps(candidate)))
        db.commit()
    return decision


def load_pinned(directory, sources, request, selected):
    from .audit import verify_capture_integrity, canonical_hash
    from .sources import parse_overpass_payload
    directory = Path(directory)
    if verify_capture_integrity(directory)["status"] == "FAIL":
        raise ValueError("Pinned capture integrity failed")
    meta = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    box = request.area.bounds
    if meta["categories"] != list(request.categories) or meta["area_bbox"] != [box.west, box.south, box.east, box.north]:
        raise ValueError("Pinned capture AOI/category does not match semantic query")
    captured_area = meta.get("area_resolution", {}).get("source_id")
    if captured_area and captured_area != (request.area_resolution or {}).get("source_id"):
        raise ValueError("Pinned named AOI identity does not match")
    captures = {c["source"]:c for c in json.loads((directory / "source_capture.json").read_text(encoding="utf-8"))}
    registry = {s["name"]:s for s in json.loads((directory / "sources_snapshot.json").read_text(encoding="utf-8"))}
    records, descriptors = {}, {}
    for source in sources:
        if source["name"] not in selected:
            continue
        capture = captures[source["name"]]
        if canonical_hash(capture["records"]) != capture["capture_hash"]:
            raise ValueError("Pinned source record hash mismatch")
        if source["endpoint"] != registry[source["name"]]["endpoint"]:
            raise ValueError("Pinned source endpoint/version mismatch")
        saved = capture.get("version", {}).get("snapshot")
        stamps = {r.get("source_snapshot_timestamp", r.get("source_version")) for r in capture["records"]}
        if saved:
            stamp = saved["timestamp"]
        else:
            if len(stamps) != 1:
                raise ValueError("Legacy capture has mixed or unknown source snapshot versions")
            stamp = next(iter(stamps))
        if timestamp(stamp) is None:
            raise ValueError("Pinned OSM capture requires a validated snapshot timestamp")
        payload = {"osm3s":{"timestamp_osm_base":stamp},
                   "elements":[r["source_payload"] for r in capture["records"]]}
        descriptor = describe(source, request, payload, "pinned_capture_not_live")
        if capture.get('retrieval_timestamp'):
            descriptor['original_retrieval_timestamp'] = timestamp(capture['retrieval_timestamp']).isoformat()
        if saved and (saved["query_hash"] != descriptor["query_hash"] or saved["dataset_hash"] != descriptor["dataset_hash"]):
            raise ValueError("Pinned source scope/version mismatch")
        descriptor["freshness_decision"] = accept_latest(source, descriptor, write=False)
        records[source["name"]] = parse_overpass_payload(source, request, payload)
        descriptors[source["name"]] = descriptor
    return records, descriptors

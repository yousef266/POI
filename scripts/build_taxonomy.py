"""Build a traceable POI taxonomy snapshot from public source catalogs.

This is a maintainer command, not part of normal harvesting. It never guesses a
crosswalk: Google matches are exact type-name matches or the explicit overrides
below; Wikidata links come from P1282 statements for the same OSM tag.
"""

from __future__ import annotations

from argparse import ArgumentParser
from datetime import datetime, timezone
from pathlib import Path
from time import sleep
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json
import re


TAGINFO = "https://taginfo.openstreetmap.org/api/4/key/values"
GOOGLE_TYPES = "https://developers.google.com/maps/documentation/places/web-service/place-types"
WIKIDATA = "https://query.wikidata.org/sparql"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
QUOTAS = {
    "amenity": 48, "shop": 65, "tourism": 25, "leisure": 28,
    "healthcare": 20, "craft": 18, "office": 18, "emergency": 10,
    "historic": 12,
}
BLACKLIST = {"yes", "no", "other", "unknown", "fixme", "none", "misc", "miscellaneous"}
CORE_IDS = {
    "amenity=pharmacy": "pharmacy", "amenity=clinic": "clinic",
    "amenity=hospital": "hospital", "amenity=school": "school",
}
GOOGLE_OVERRIDES = {
    "medical_clinic": "clinic",
    "general_hospital": "hospital",
    "primary_school": "school",
    "secondary_school": "school",
}


def get(url: str, user_agent: str) -> bytes:
    with urlopen(Request(url, headers={"User-Agent": user_agent,
                                      "Accept": "application/json, text/html;q=0.8"}), timeout=30) as response:
        return response.read()


def refine_wikidata_labels(leaves: list[dict], user_agent: str) -> None:
    for leaf in leaves:
        leaf["wikidata_p1282_candidates"] = leaf.get("wikidata_p1282_candidates", leaf.get("wikidata_classes", []))
    qids = sorted({qid for leaf in leaves for qid in leaf["wikidata_p1282_candidates"]})
    labels = {}
    for offset in range(0, len(qids), 50):
        url = WIKIDATA_API + "?" + urlencode({
            "action": "wbgetentities", "ids": "|".join(qids[offset:offset + 50]),
            "format": "json", "props": "labels", "languages": "en",
        })
        entities = json.loads(get(url, user_agent))["entities"]
        labels.update({qid: item.get("labels", {}).get("en", {}).get("value", "")
                       for qid, item in entities.items()})
    for leaf in leaves:
        canonical_label = leaf["label_en"].casefold()
        leaf["wikidata_classes"] = sorted({
            qid for qid in leaf["wikidata_p1282_candidates"]
            if labels.get(qid, "").casefold() == canonical_label
        })
        leaf["wikidata_p1282_candidates"] = sorted(set(leaf["wikidata_p1282_candidates"]))


def build(contact: str) -> dict:
    user_agent = f"POIHarvesterTaxonomyBuilder/0.1 ({contact})"
    leaves: list[dict] = []
    by_value: dict[str, dict] = {}
    source_dates: dict[str, str] = {}
    for key, quota in QUOTAS.items():
        url = TAGINFO + "?" + urlencode({"key": key, "filter": "all", "sortname": "count",
                                         "sortorder": "desc", "page": 1, "rp": 250})
        response = json.loads(get(url, user_agent))
        source_dates[key] = response.get("data_until", "")
        selected = 0
        for item in response["data"]:
            value = item["value"]
            if not re.fullmatch(r"[a-z][a-z0-9_]*", value) or value in BLACKLIST:
                continue
            tag = f"{key}={value}"
            if value in by_value:
                by_value[value]["osm_tags"].append(tag)
                continue
            leaf = {
                "id": CORE_IDS.get(tag, f"{key}_{value}"),
                "parent": key,
                "label_en": value.replace("_", " ").title(),
                "osm_tags": [tag],
                "google_types": [],
                "wikidata_classes": [],
                "wikidata_p1282_candidates": [],
                "osm_count_at_snapshot": item.get("count", 0),
            }
            leaves.append(leaf)
            by_value[value] = leaf
            selected += 1
            if selected >= quota:
                break
    if len(leaves) < 200:
        raise RuntimeError(f"Only {len(leaves)} unique taxonomy leaves were found")

    html = get(GOOGLE_TYPES, user_agent).decode("utf-8", errors="replace")
    start, end = html.find('id="table-a"'), html.find('id="table-b"')
    if start < 0 or end <= start:
        raise RuntimeError("Could not locate Google's current Table A place types")
    google_types = set(re.findall(r'<code translate="no" dir="ltr">([a-z_]+)</code>', html[start:end]))
    by_id = {leaf["id"]: leaf for leaf in leaves}
    for place_type in sorted(google_types):
        leaf = by_value.get(place_type) or by_id.get(GOOGLE_OVERRIDES.get(place_type, ""))
        if leaf:
            leaf["google_types"].append(place_type)

    by_tag = {tag: leaf for leaf in leaves for tag in leaf["osm_tags"]}
    tags = sorted(by_tag)
    for offset in range(0, len(tags), 45):
        batch = tags[offset:offset + 45]
        values = " ".join(json.dumps(tag) for tag in batch)
        query = ("SELECT ?item ?tag WHERE { VALUES ?tag { " + values +
                 " } ?item <http://www.wikidata.org/prop/direct/P1282> ?tag. }")
        url = WIKIDATA + "?" + urlencode({"query": query, "format": "json"})
        result = json.loads(get(url, user_agent))
        for binding in result["results"]["bindings"]:
            tag = binding["tag"]["value"]
            qid = binding["item"]["value"].rsplit("/", 1)[-1]
            if tag in by_tag and re.fullmatch(r"Q[0-9]+", qid):
                by_tag[tag]["wikidata_p1282_candidates"].append(qid)
        sleep(1)
    refine_wikidata_labels(leaves, user_agent)
    for leaf in leaves:
        for field in ("osm_tags", "google_types", "wikidata_classes", "wikidata_p1282_candidates"):
            leaf[field] = sorted(set(leaf[field]))
    leaves.sort(key=lambda leaf: leaf["id"])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "leaf_count": len(leaves),
        "source_references": {"osm": TAGINFO, "google": GOOGLE_TYPES,
                              "wikidata": "https://www.wikidata.org/wiki/Property:P1282"},
        "osm_data_until": source_dates,
        "mapping_note": "Google mappings use exact type names or listed overrides. Wikidata classes require a P1282 OSM-tag statement and an exact English label match; other P1282 items remain candidates for manual review.",
        "leaves": leaves,
    }


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--contact", required=True, help="Operator email or URL used only in request User-Agent")
    parser.add_argument("--out", type=Path, default=Path("src/poi_harvester/taxonomy.json"))
    parser.add_argument("--refine-existing", action="store_true", help="Refine a saved P1282 snapshot without refetching source catalogs")
    args = parser.parse_args()
    if args.refine_existing:
        taxonomy = json.loads(args.out.read_text(encoding="utf-8"))
        refine_wikidata_labels(taxonomy["leaves"], f"POIHarvesterTaxonomyBuilder/0.1 ({args.contact})")
        taxonomy["mapping_note"] = ("Google mappings use exact type names or listed overrides. "
                                    "Wikidata classes require a P1282 OSM-tag statement and an exact English label match; "
                                    "other P1282 items remain candidates for manual review.")
    else:
        taxonomy = build(args.contact)
    args.out.write_text(json.dumps(taxonomy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"leaves": taxonomy["leaf_count"],
                      "google_mapped": sum(bool(leaf["google_types"]) for leaf in taxonomy["leaves"]),
                      "wikidata_mapped": sum(bool(leaf["wikidata_classes"]) for leaf in taxonomy["leaves"])}))


if __name__ == "__main__":
    main()

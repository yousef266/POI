"""Project-authored Arabic review corpus and explicit human ratings, never synthetic scores."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json

from .enrichment import VERSION, enrich_record


def build_review_dataset() -> dict:
    proper_names = ("Al Nakheel", "Olympia", "Amavita", "Olaya", "King Fahd",
                    "Riyadh", "Zurich", "Zyrol", "Meridian", "Solara")
    categories = (("pharmacy", "Pharmacy"), ("clinic", "Clinic"),
                  ("hospital", "Hospital"), ("school", "School"),
                  ("amenity_restaurant", "Restaurant"), ("tourism_hotel", "Hotel"),
                  ("amenity_place_of_worship", "Mosque"), ("shop_bakery", "Bakery"),
                  ("amenity_bank", "Bank"), ("amenity_atm", "ATM"))
    entries = []
    for category, generic in categories:
        for proper in proper_names:
            source_name = f"{proper} {generic}"
            record_id = sha256(f"{category}:{source_name}".encode()).hexdigest()[:16]
            generated, reason = enrich_record({"name_en": source_name, "category": category},
                                               f"review_fixture:{record_id}")
            if not generated.get("name_ar"):
                raise ValueError(f"Review example could not be generated: {source_name}")
            entries.append({"id": record_id, "source": "project_authored_review_fixture",
                            "source_name": source_name, "generated_arabic_name": generated["name_ar"],
                            "category": category, "transformation_method": generated["name_ar_method"],
                            "transformation_version": VERSION, "confidence": generated["name_ar_confidence"],
                            "provenance": generated["provenance_name_ar"], "review_reason": reason,
                            "reviewer": None, "review_status": "NOT_REVIEWED", "rating": None})
    return {"dataset_kind": "project_authored_synthetic_review_examples",
            "official_status": "NOT_CERTIFIED", "human_review_status": "NOT_REVIEWED",
            "enrichment_version": VERSION, "count": len(entries), "entries": entries}


def _dataset_hash(dataset: dict) -> str:
    return sha256(json.dumps(dataset, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode()).hexdigest()


def score_reviews(dataset: dict, ratings: dict | None = None) -> dict:
    entries = dataset["entries"]
    identifiers = {entry["id"] for entry in entries}
    if len(identifiers) != len(entries):
        raise ValueError("Review dataset IDs must be unique")
    ratings = ratings or {"dataset_hash": _dataset_hash(dataset), "ratings": []}
    if ratings.get("dataset_hash") != _dataset_hash(dataset):
        raise ValueError("Ratings refer to a different dataset or transformation version")
    decisions = {}
    for item in ratings["ratings"]:
        identifier = item["id"]
        if identifier not in identifiers or identifier in decisions:
            raise ValueError("Unknown or duplicate human rating ID")
        if item.get("rating") not in ("ACCEPT", "REJECT") or not (item.get("reviewer") or "").strip():
            raise ValueError("Every rating needs ACCEPT/REJECT and a human reviewer")
        decisions[identifier] = item
    reviewed = len(decisions)
    accepted = sum(item["rating"] == "ACCEPT" for item in decisions.values())
    complete = reviewed == len(entries) and len(entries) >= 100
    return {"dataset_hash": _dataset_hash(dataset), "total": len(entries), "reviewed": reviewed,
            "accepted": accepted, "rejected": reviewed - accepted,
            "unreviewed": len(entries) - reviewed,
            "status": "REVIEWED" if complete else "PARTIALLY_REVIEWED" if reviewed else "NOT_REVIEWED",
            "human_acceptance_score": round(accepted / reviewed, 6) if reviewed else None,
            "complete_sample_score": round(accepted / len(entries), 6) if complete else None,
            "official_status": "NOT_CERTIFIED",
            "rating_definition": "ACCEPT only if the generic translation and proper-name rendering are both acceptable"}


def review_names(dataset_path: Path, ratings_path: Path, output_path: Path,
                 interactive: bool = False, reviewer: str | None = None) -> dict:
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    ratings = (json.loads(ratings_path.read_text(encoding="utf-8")) if ratings_path.exists() else
               {"dataset_hash": _dataset_hash(dataset), "ratings": []})
    score_reviews(dataset, ratings)  # Validate before prompting or writing.
    if interactive:
        if not reviewer or not reviewer.strip():
            raise ValueError("Interactive review requires --reviewer")
        completed = {item["id"] for item in ratings["ratings"]}
        for index, entry in enumerate(dataset["entries"], 1):
            if entry["id"] in completed:
                continue
            print(f"[{index}/{len(dataset['entries'])}] {entry['source_name']} -> {entry['generated_arabic_name']}")
            print(f"Category: {entry['category']}; confidence: {entry['confidence']}")
            while True:
                choice = input("Accept [a], reject [r], skip [s], quit [q]: ").strip().lower()
                if choice in ("a", "r", "s", "q"):
                    break
            if choice == "q":
                break
            if choice == "s":
                continue
            ratings["ratings"].append({"id": entry["id"], "rating": "ACCEPT" if choice == "a" else "REJECT",
                                       "reviewer": reviewer.strip()})
            ratings_path.parent.mkdir(parents=True, exist_ok=True)
            ratings_path.write_text(json.dumps(ratings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = score_reviews(dataset, ratings)
    ratings_path.parent.mkdir(parents=True, exist_ok=True)
    ratings_path.write_text(json.dumps(ratings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report

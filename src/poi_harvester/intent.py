"""Deterministic English/Arabic POI intent normalization."""

from __future__ import annotations

import re

from .core import categories_from_text


_ARABIC_CATEGORIES = {
    "pharmacy": ("صيدلية", "صيدليات"),
    "clinic": ("عيادة", "عيادات"),
    "hospital": ("مستشفى", "مستشفيات"),
    "school": ("مدرسة", "مدارس"),
    "amenity_restaurant": ("مطعم", "مطاعم", "المطاعم"),
    "tourism_hotel": ("فندق", "فنادق", "الفنادق"),
    "amenity_place_of_worship": ("مسجد", "مساجد", "المساجد"),
    "shop_bakery": ("مخبز", "مخابز", "المخابز"),
    "amenity_bank": ("بنك", "بنوك", "البنوك"),
    "amenity_atm": ("صراف", "الصرافات"),
    "amenity_cafe": ("مقهى", "مقاهي", "المقاهي"),
    "amenity_fuel": ("محطة وقود", "محطات الوقود"),
    "shop_supermarket": ("سوبرماركت", "متاجر السوبرماركت"),
}


def normalize_intent(value: str) -> dict:
    text = value.strip()
    language = "ar" if re.search(r"[\u0600-\u06ff]", text) else "en"
    categories = set()
    try:
        categories.update(categories_from_text(text))
    except ValueError:
        pass
    if language == "ar":
        words = re.findall(r"[\u0621-\u064a]+", text)
        normalized_words = {word.removeprefix("و").removeprefix("ال") for word in words}
        for category, aliases in _ARABIC_CATEGORIES.items():
            if any((alias in normalized_words if " " not in alias else alias in text)
                   for alias in aliases):
                categories.add(category)
    if language == "ar":
        match = re.search(r"(?:القريبة\s+من|بالقرب\s+من|قرب|حول|في)\s+(.+)$", text)
        near = bool(re.search(r"القريبة\s+من|بالقرب\s+من|قرب|حول", text))
    else:
        match = re.search(r"\b(?:near|around|in)\s+(.+)$", text, re.IGNORECASE)
        near = bool(re.search(r"\b(?:near|around)\b", text, re.IGNORECASE))
    place_name = match.group(1).strip(" .،؟") if match else None
    unresolved = []
    if not categories:
        unresolved.append("category")
    if not place_name:
        unresolved.append("area_of_interest")
    return {
        "area": place_name,
        "categories": tuple(sorted(categories)),
        "constraints": {"near": near, "radius_m": 500 if near else None},
        "language": language,
        "confidence": 0.9 if not unresolved else 0.55,
        "unresolved_terms": unresolved,
    }

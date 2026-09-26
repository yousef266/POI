"""Deterministic, conservative bilingual POI-name enrichment.

This is a rule baseline, not a human-quality translation claim. Source names are
never replaced. Generic establishment terms are translated; proper names use a
small curated lexicon or a marked low-confidence transliteration fallback.
"""

from __future__ import annotations

import re
import unicodedata


VERSION = "rules-v2"

# Common establishment words are translated, never phoneticized as brand text.
_GENERICS = {
    "pharmacy": ("صيدلية", "Pharmacy"),
    "pharmacies": ("صيدلية", "Pharmacy"),
    "apotheke": ("صيدلية", "Pharmacy"),
    "clinic": ("عيادة", "Clinic"),
    "clinics": ("عيادة", "Clinic"),
    "hospital": ("مستشفى", "Hospital"),
    "restaurant": ("مطعم", "Restaurant"),
    "restaurants": ("مطعم", "Restaurant"),
    "hotel": ("فندق", "Hotel"),
    "school": ("مدرسة", "School"),
    "schools": ("مدرسة", "School"),
    "mosque": ("مسجد", "Mosque"),
    "church": ("كنيسة", "Church"), "synagogue": ("كنيس", "Synagogue"),
    "bakery": ("مخبز", "Bakery"),
    "backerei": ("مخبز", "Bakery"),
    "bank": ("بنك", "Bank"),
    "atm": ("صراف آلي", "ATM"),
    "fuelstation": ("محطة وقود", "Fuel Station"),
    "cafe": ("مقهى", "Cafe"), "supermarket": ("سوبرماركت", "Supermarket"),
}
_CATEGORY_GENERIC = {
    "pharmacy": ("صيدلية", "Pharmacy"),
    "clinic": ("عيادة", "Clinic"),
    "hospital": ("مستشفى", "Hospital"),
    "school": ("مدرسة", "School"),
    "shop_bakery": ("مخبز", "Bakery"),
    "amenity_restaurant": ("مطعم", "Restaurant"),
    "tourism_hotel": ("فندق", "Hotel"),
    "amenity_place_of_worship": ("دار عبادة", "Place of Worship"),
    "amenity_bank": ("بنك", "Bank"),
    "amenity_atm": ("صراف آلي", "ATM"),
    "amenity_fuel": ("محطة وقود", "Fuel Station"),
    "amenity_cafe": ("مقهى", "Cafe"), "shop_supermarket": ("سوبرماركت", "Supermarket"),
}
_AR_GENERICS = {arabic: english for arabic, english in set(_GENERICS.values())}
_PROPER_EN_AR = {
    "al nakheel": "النخيل", "nakheel": "النخيل", "olympia": "أوليمبيا",
    "central": "المركزية", "olaya": "العليا", "king fahd": "الملك فهد",
    "riyadh": "الرياض", "zurich": "زيورخ", "amavita": "أمافيتا",
}
_PROPER_AR_EN = {value: key.title() for key, value in _PROPER_EN_AR.items()}
_PROPER_AR_EN["النخيل"] = "Al Nakheel"
_LATIN_CLUSTERS = (
    ("sch", "ش"), ("sh", "ش"), ("ch", "تش"), ("kh", "خ"),
    ("gh", "غ"), ("th", "ث"), ("dh", "ذ"), ("ph", "ف"),
    ("ee", "ي"), ("oo", "و"), ("ou", "و"), ("ai", "ي"),
)
_LATIN_LETTERS = {
    "a": "ا", "b": "ب", "c": "ك", "d": "د", "e": "ي", "f": "ف",
    "g": "ج", "h": "ه", "i": "ي", "j": "ج", "k": "ك", "l": "ل",
    "m": "م", "n": "ن", "o": "و", "p": "ب", "q": "ق", "r": "ر",
    "s": "س", "t": "ت", "u": "و", "v": "ف", "w": "و", "x": "كس",
    "y": "ي", "z": "ز",
}
_AR_LETTERS = {
    "ا": "a", "أ": "a", "إ": "i", "آ": "a", "ب": "b", "ت": "t",
    "ث": "th", "ج": "j", "ح": "h", "خ": "kh", "د": "d", "ذ": "dh",
    "ر": "r", "ز": "z", "س": "s", "ش": "sh", "ص": "s", "ض": "d",
    "ط": "t", "ظ": "z", "ع": "a", "غ": "gh", "ف": "f", "ق": "q",
    "ك": "k", "ل": "l", "م": "m", "ن": "n", "ه": "h", "ة": "a",
    "و": "w", "ي": "y", "ى": "a", "ء": "", "ئ": "y", "ؤ": "w",
}


def _ascii(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return "".join(ch for ch in value if not unicodedata.combining(ch))


def _latin_word(word: str) -> tuple[str, bool]:
    folded = _ascii(word)
    if folded in _PROPER_EN_AR:
        return _PROPER_EN_AR[folded], True
    if folded.isdigit():
        return folded, True
    if not re.fullmatch(r"[a-z]+", folded):
        return "", False
    result = []
    index = 0
    while index < len(folded):
        matched = next(((latin, arabic) for latin, arabic in _LATIN_CLUSTERS
                        if folded.startswith(latin, index)), None)
        if matched:
            result.append(matched[1])
            index += len(matched[0])
        else:
            result.append(_LATIN_LETTERS[folded[index]])
            index += 1
    return "".join(result), False


def _arabic_word(word: str) -> tuple[str, bool]:
    if word in _PROPER_AR_EN:
        return _PROPER_AR_EN[word], True
    if not re.fullmatch(r"[\u0621-\u064a]+", word):
        return "", False
    if word.startswith("ال") and len(word) > 3:
        tail, _ = _arabic_word(word[2:])
        return "Al " + tail, False
    return "".join(_AR_LETTERS.get(char, "") for char in word).title(), False


_LOCATION_TERMS = {"street": "شارع", "road": "طريق", "district": "حي", "north": "شمال", "south": "جنوب"}
_LOCATION_AR_EN = {arabic: english.title() for english, arabic in _LOCATION_TERMS.items()}


def _proper_parts(words: list[str], target: str) -> list[tuple[str, bool]]:
    parts = []
    index = 0
    while index < len(words):
        word = words[index]
        if target == "ar":
            found = next(((width, _PROPER_EN_AR[_ascii(" ".join(words[index:index + width]))])
                          for width in range(min(3, len(words) - index), 0, -1)
                          if _ascii(" ".join(words[index:index + width])) in _PROPER_EN_AR), None)
            if found:
                parts.append((found[1], True))
                index += found[0]
                continue
            parts.append((_LOCATION_TERMS[_ascii(word)], True) if _ascii(word) in _LOCATION_TERMS
                         else (word, True) if re.fullmatch(r"[\u0621-\u064a]+", word)
                         else _latin_word(word))
        else:
            parts.append((_LOCATION_AR_EN[word], True) if word in _LOCATION_AR_EN
                         else (word, True) if re.fullmatch(r"[A-Za-z]+|\d+", word)
                         else _arabic_word(word))
        index += 1
    return parts


def _to_arabic(name: str, category: str) -> tuple[str | None, float, str | None]:
    name = re.sub(r"(?i)\b(?:fuel|gas) station\b", "fuelstation", name)
    words = re.findall(r"[A-Za-zÀ-ÿ]+|[\u0621-\u064a]+|\d+", name)
    if not words:
        return None, 0.0, "Empty source name"
    generics = [_GENERICS[_ascii(word)] for word in words if _ascii(word) in _GENERICS]
    generics += [(word, _AR_GENERICS[word]) for word in words if word in _AR_GENERICS]
    if len({item[1] for item in generics}) > 1:
        return None, 0.0, "Conflicting generic establishment terms"
    generic = generics[0] if generics else _CATEGORY_GENERIC.get(category)
    if generic is None:
        return None, 0.0, "No reviewed Arabic generic term for category"
    proper_words = [word for word in words if _ascii(word) not in _GENERICS and word not in _AR_GENERICS]
    if len(proper_words) >= 2 and _ascii(" ".join(proper_words)) in _PROPER_EN_AR:
        proper, reviewed = _PROPER_EN_AR[_ascii(" ".join(proper_words))], True
    else:
        parts = _proper_parts(proper_words, "ar")
        if any(not value for value, _ in parts):
            return None, 0.0, "Proper name cannot be transliterated deterministically"
        proper = " ".join(value for value, _ in parts)
        reviewed = all(known for _, known in parts)
    text = generic[0] + (" " + proper if proper else "")
    return text, (0.82 if reviewed else 0.48), ("generic-only name" if not proper else None)


def _to_english(name: str, category: str) -> tuple[str | None, float, str | None]:
    words = re.findall(r"[A-Za-z]+|[\u0621-\u064a]+|\d+", name.replace("صراف آلي", "صراف").replace("محطة وقود", "محطةوقود"))
    if not words:
        return None, 0.0, "Empty Arabic name"
    arabic_generics = {**_AR_GENERICS, "صراف": "ATM", "محطةوقود": "Fuel Station"}
    generics = [arabic_generics[word] for word in words if word in arabic_generics]
    generics += [_GENERICS[_ascii(word)][1] for word in words if _ascii(word) in _GENERICS]
    if len(set(generics)) > 1:
        return None, 0.0, "Conflicting generic establishment terms"
    generic = generics[0] if generics else (_CATEGORY_GENERIC.get(category) or (None, None))[1]
    if not generic:
        return None, 0.0, "No reviewed English generic term for category"
    proper_words = [word for word in words if word not in arabic_generics and _ascii(word) not in _GENERICS]
    proper_ar = " ".join(proper_words)
    if proper_ar in _PROPER_AR_EN:
        proper, reviewed = _PROPER_AR_EN[proper_ar], True
    else:
        parts = _proper_parts(proper_words, "en")
        if any(not value for value, _ in parts):
            return None, 0.0, "Proper name cannot be transliterated deterministically"
        proper = " ".join(value for value, _ in parts)
        reviewed = all(known for _, known in parts)
    text = (proper + " " if proper else "") + generic
    return text, (0.82 if reviewed else 0.48), ("generic-only name" if not proper else None)


def enrich_record(record: dict, source_key: str) -> tuple[dict, str | None]:
    """Return captured enrichment and an optional review reason."""
    result = dict(record)
    en = (record.get("name_en") or "").strip()
    ar = (record.get("name_ar") or "").strip()
    if en and ar:
        if any(record.get(f"{field}_method") and float(record.get(f"{field}_confidence", 0)) < 0.6
               for field in ("name_en", "name_ar")):
            return result, "Low-confidence proper-name transliteration requires human review"
        return result, None
    if not en and not ar:
        return result, "POI has no source name for bilingual enrichment"
    target = "name_ar" if en else "name_en"
    generated, confidence, review = (_to_arabic(en, record["category"]) if en
                                     else _to_english(ar, record["category"]))
    if not generated:
        return result, review
    result[f"original_{target}"] = record.get(target)
    result[target] = generated
    result[f"{target}_generated"] = True
    result[f"{target}_method"] = "generic_translation+proper_transliteration"
    result[f"{target}_version"] = VERSION
    result[f"{target}_confidence"] = confidence
    result[f"provenance_{target}"] = f"generated:{VERSION}:{source_key}"
    if confidence < 0.6 and review is None:
        review = "Low-confidence proper-name transliteration requires human review"
    return result, review

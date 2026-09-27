"""Conservative source-name resolution; originals remain in the capture."""

import re
import unicodedata

VERSION = "unicode-names-v1"


def clean_name(value):
    if not isinstance(value, str):
        return None
    value = unicodedata.normalize("NFKC", value)
    value = "".join(c for c in value if unicodedata.category(c) != "Cf")
    value = " ".join(value.split()).strip()
    return value or None


def arabic_key(value):
    value = clean_name(value) or ""
    value = "".join(c for c in unicodedata.normalize("NFKD", value)
                    if not unicodedata.combining(c)).replace("ـ", "")
    return value.translate(str.maketrans({"ک": "ك", "ی": "ي"}))


def resolve_osm_names(tags, source_key):
    result = {}
    chosen = {}
    for lang in ("en", "ar"):
        fields = (f"name:{lang}", f"official_name:{lang}", f"short_name:{lang}", f"alt_name:{lang}")
        for field in fields:
            options = [clean_name(part) for part in (tags.get(field) or "").split(";")] if isinstance(tags.get(field), str) else []
            value = next((part for part in options if part), None)
            if value:
                result[f"name_{lang}"] = value
                chosen[lang] = field
                break
    for field in ("name", "official_name", "short_name", "alt_name"):
        value = clean_name(tags.get(field))
        if not value:
            continue
        for part in value.split(";"):
            part = clean_name(part)
            language = "ar" if re.search(r"[\u0600-\u06ff]", part or "") else "en" if re.search(r"[A-Za-z]", part or "") else None
            if language and not result.get(f"name_{language}"):
                result[f"name_{language}"] = part
                chosen[language] = field
    for lang, field in chosen.items():
        result[f"name_{lang}_source_field"] = field
        if field not in ("name", f"name:{lang}"):
            result[f"provenance_name_{lang}"] = f"{source_key}:tags.{field}"
    alternates = {clean_name(part) for field, value in tags.items()
                  if field in ("name", "official_name", "short_name", "alt_name") or field.startswith(("name:", "official_name:", "short_name:", "alt_name:"))
                  if isinstance(value, str) for part in value.split(";")}
    seen = {arabic_key(result.get("name_en")), arabic_key(result.get("name_ar"))}
    result["alternate_names"] = []
    for value in sorted(alternates - {None}, key=lambda text: (arabic_key(text), text)):
        key = arabic_key(value)
        if key not in seen:
            seen.add(key)
            result["alternate_names"].append(value)
    if not result.get("name_en") and not result.get("name_ar"):
        result.update(name_en=None, name_ar=None, name_status="unnamed_source",
                      missing_name_reason="No usable name, multilingual name, official name, short name or alternate name in source tags.",
                      provenance_name_status=f"{source_key}:tags:name_fields_absent_or_empty")
    else:
        result["name_status"] = "source_named"
    return result

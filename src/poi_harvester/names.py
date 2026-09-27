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


def valid_language_name(value, language):
    """Check usable script, not human linguistic quality or verified business truth."""
    if not isinstance(value, str) or any(unicodedata.category(c) == 'Cs' or c == '\ufffd' or
                                        (unicodedata.category(c) == 'Cc' and not c.isspace()) for c in value):
        return False
    value = clean_name(value) or ''
    return any(unicodedata.category(c).startswith('L') and
               ('ARABIC' if language == 'ar' else 'LATIN') in unicodedata.name(c, '') for c in value)


def bilingual_counts(records):
    """Keep the denominator intact and distinguish generated from source names."""
    presentation = authoritative = 0
    for row in records:
        if not all(valid_language_name(row.get('name_' + lang), lang) for lang in ('ar', 'en')):
            continue
        presentation += 1
        provenance = row.get('provenance', {})
        keys = row.get('source_keys', [])
        if all(not row.get(f'name_{lang}_method') and not row.get(f'name_{lang}_generated') and
               any(provenance.get(f'name_{lang}', '') == key or
                   provenance.get(f'name_{lang}', '').startswith(key + ':tags.') for key in keys)
               for lang in ('en', 'ar')):
            authoritative += 1
    total = len(records)
    return {'total': total, 'valid_bilingual_including_generated': presentation,
            'authoritative_bilingual': authoritative,
            'authoritative_bilingual_fraction': authoritative / total if total else None,
            'definition': 'Valid Latin/Arabic letter-bearing source names with field provenance; generated names excluded. Source linguistic quality is not human certified.'}


def resolve_osm_names(tags, source_key):
    result = {}
    chosen = {}
    for lang in ("en", "ar"):
        fields = (f"name:{lang}", f"official_name:{lang}", f"short_name:{lang}", f"alt_name:{lang}")
        for field in fields:
            options = [clean_name(part) for part in (tags.get(field) or "").split(";")] if isinstance(tags.get(field), str) else []
            value = next((part for part in options if valid_language_name(part, lang)), None)
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
            language = "ar" if valid_language_name(part, 'ar') else "en" if valid_language_name(part, 'en') else None
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

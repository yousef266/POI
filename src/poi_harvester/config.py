"""Local environment-file loading without exposing secrets in output."""

from __future__ import annotations

from os import environ
from pathlib import Path


ALLOWED_ENV_KEYS = {
    "PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGSSLMODE",
    "GEOSERVER_URL", "GEOSERVER_USER", "GEOSERVER_PASSWORD",
    "GEOSERVER_PGHOST", "POI_CONTACT",
}


def load_env_file(path: Path | None = None) -> Path | None:
    target = path or Path(".env")
    if not target.exists():
        if path is not None:
            raise FileNotFoundError(f"Environment file not found: {target}")
        return None
    for line_number, raw_line in enumerate(target.read_text(encoding="utf-8-sig").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            raise ValueError(f"Invalid .env line {line_number}; expected KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in ALLOWED_ENV_KEYS:
            raise ValueError(f"Unsupported .env key on line {line_number}: {key}")
        value = value.strip()
        if value.startswith(('"', "'")) and value.endswith(value[:1]):
            value = value[1:-1]
        if value and key not in environ:
            environ[key] = value
    return target


def require_publish_env() -> None:
    required = (
        "PGHOST", "PGUSER", "PGPASSWORD",
        "GEOSERVER_URL", "GEOSERVER_USER", "GEOSERVER_PASSWORD",
    )
    missing = [name for name in required if not environ.get(name)]
    if missing:
        raise ValueError("Missing local service settings: " + ", ".join(missing))

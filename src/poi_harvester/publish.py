"""Optional PostGIS and GeoServer publication adapters."""

from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
from os import environ
from pathlib import Path
from time import sleep, perf_counter
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree
import json
import re


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,40}", value):
        raise ValueError("Layer, store, and workspace names must be lowercase SQL-safe identifiers")
    return value


def _store(database: str, schema: str) -> str:
    """Give each database/schema pair its own stable GeoServer store name."""
    raw = f"{database}\0{schema}"
    stem = re.sub(r"[^a-z0-9_]+", "_", f"{database}_{schema}".lower()).strip("_")
    return _identifier(f"poi_{stem[:24]}_{sha256(raw.encode()).hexdigest()[:8]}")


def _pg_kwargs(database: str) -> dict[str, str]:
    kwargs = {
        "host": environ["PGHOST"], "port": environ.get("PGPORT", "5432"),
        "dbname": database, "user": environ["PGUSER"],
        "password": environ["PGPASSWORD"],
    }
    if environ.get("PGSSLMODE"):
        kwargs["sslmode"] = environ["PGSSLMODE"]
    return kwargs


def publish_postgis(records: list[dict], layer: str, database: str, schema: str = "public", demo_data: bool = False) -> None:
    """Write a versioned active layer, retaining inactive records for audit."""
    try:
        import psycopg
        from psycopg import sql
    except ImportError as exc:
        raise RuntimeError("PostGIS publishing requires: pip install '.[postgis]'") from exc
    layer = _identifier(layer)
    table = _identifier(layer + "_records")
    schema = _identifier(schema)
    column_types = {
        "longitude": "double precision", "latitude": "double precision",
        "primary_source": "text", "primary_source_id": "text", "footprint_ref": "text",
        "name_en": "text", "name_ar": "text", "alternate_names": "text",
        "original_name_en": "text", "original_name_ar": "text",
        "name_en_generated": "boolean", "name_ar_generated": "boolean",
        "name_en_method": "text", "name_en_version": "text", "name_en_confidence": "double precision",
        "name_ar_method": "text", "name_ar_version": "text", "name_ar_confidence": "double precision",
        "category": "text", "source_category": "text", "address": "text",
        "address_street": "text", "address_city": "text", "address_region": "text",
        "address_postcode": "text", "address_country": "text",
        "phone": "text", "email": "text", "website": "text", "hours": "text",
        "harvested_at": "timestamptz", "confidence": "double precision",
        "language_complete": "boolean", "source_keys": "text",
        "attributions": "text", "licenses": "text",
        "geometry_provenance": "text", "geometry_method": "text", "is_demo": "boolean",
        "provenance_name_en": "text", "provenance_name_ar": "text",
        "provenance_category": "text", "provenance_phone": "text",
        "provenance_address": "text", "provenance_hours": "text",
        "provenance_source_category": "text", "provenance_website": "text",
        "provenance_address_street": "text", "provenance_address_city": "text",
        "provenance_address_region": "text", "provenance_address_postcode": "text",
        "provenance_address_country": "text",
        "provenance_email": "text", "provenance_footprint_ref": "text",
    }
    public_columns = ["stable_id", *column_types]
    with psycopg.connect(**_pg_kwargs(database)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT PostGIS_Version()")
            cursor.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
            cursor.execute(sql.SQL("""
                CREATE TABLE IF NOT EXISTS {}.{} (
                    stable_id text PRIMARY KEY,
                    geom geometry(Point,4326) NOT NULL,
                    is_active boolean NOT NULL DEFAULT true
                )
            """).format(sql.Identifier(schema), sql.Identifier(table)))
            cursor.execute(sql.SQL("DROP VIEW IF EXISTS {}.{}").format(sql.Identifier(schema), sql.Identifier(layer)))
            cursor.execute(sql.SQL("ALTER TABLE {}.{} DROP COLUMN IF EXISTS properties").format(
                sql.Identifier(schema), sql.Identifier(table)))
            for name, data_type in column_types.items():
                cursor.execute(sql.SQL("ALTER TABLE {}.{} ADD COLUMN IF NOT EXISTS {} {}").format(
                    sql.Identifier(schema), sql.Identifier(table), sql.Identifier(name), sql.SQL(data_type)))
            for name in ("alternate_names", "source_keys", "attributions", "licenses"):
                cursor.execute("""
                    SELECT data_type FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s AND column_name = %s
                """, (schema, table, name))
                if cursor.fetchone()[0] == "ARRAY":
                    cursor.execute(sql.SQL("ALTER TABLE {}.{} ALTER COLUMN {} TYPE text USING to_json({})::text").format(
                        sql.Identifier(schema), sql.Identifier(table), sql.Identifier(name), sql.Identifier(name)))
            cursor.execute(sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {}.{} USING GIST (geom)").format(
                sql.Identifier(table + "_geom_idx"), sql.Identifier(schema), sql.Identifier(table)))
            cursor.execute(sql.SQL("UPDATE {}.{} SET is_active = false").format(sql.Identifier(schema), sql.Identifier(table)))
            for row in records:
                lon, lat = float(row["lon"]), float(row["lat"])
                provenance = row.get("provenance") or {}
                source_name, _, source_id = ((row.get("source_keys") or [""])[0]).partition(":")
                values = {
                    "longitude": lon, "latitude": lat,
                    "primary_source": source_name or None, "primary_source_id": source_id or None,
                    "footprint_ref": row.get("footprint_ref"),
                    "name_en": row.get("name_en"), "name_ar": row.get("name_ar"),
                    "original_name_en": row.get("original_name_en"),
                    "original_name_ar": row.get("original_name_ar"),
                    "name_en_generated": bool(row.get("name_en_generated") or row.get("name_en_method")),
                    "name_ar_generated": bool(row.get("name_ar_generated") or row.get("name_ar_method")),
                    "name_en_method": row.get("name_en_method"),
                    "name_en_version": row.get("name_en_version"),
                    "name_en_confidence": row.get("name_en_confidence"),
                    "name_ar_method": row.get("name_ar_method"),
                    "name_ar_version": row.get("name_ar_version"),
                    "name_ar_confidence": row.get("name_ar_confidence"),
                    "alternate_names": json.dumps(row.get("alternate_names") or [], ensure_ascii=False),
                    "category": row["category"], "source_category": row.get("source_category"),
                    "address": row.get("address"),
                    "address_street": row.get("address_street"), "address_city": row.get("address_city"),
                    "address_region": row.get("address_region"), "address_postcode": row.get("address_postcode"),
                    "address_country": row.get("address_country"),
                    "phone": row.get("phone"), "email": row.get("email"), "website": row.get("website"), "hours": row.get("hours"),
                    "harvested_at": row.get("harvested_at"), "confidence": row["confidence"],
                    "language_complete": row.get("language_complete"),
                    "source_keys": json.dumps(row.get("source_keys") or [], ensure_ascii=False),
                    "attributions": json.dumps(row.get("attributions") or [], ensure_ascii=False),
                    "licenses": json.dumps(row.get("licenses") or [], ensure_ascii=False),
                    "geometry_provenance": row.get("geometry_provenance"),
                    "geometry_method": row.get("geometry_method") or ("fixture_synthetic" if demo_data else "source_point"),
                    "is_demo": demo_data,
                    "provenance_name_en": provenance.get("name_en"),
                    "provenance_name_ar": provenance.get("name_ar"),
                    "provenance_category": provenance.get("category"),
                    "provenance_phone": provenance.get("phone"),
                    "provenance_address": provenance.get("address"),
                    "provenance_hours": provenance.get("hours"),
                    "provenance_source_category": provenance.get("source_category"),
                    "provenance_website": provenance.get("website"),
                    "provenance_address_street": provenance.get("address_street"),
                    "provenance_address_city": provenance.get("address_city"),
                    "provenance_address_region": provenance.get("address_region"),
                    "provenance_address_postcode": provenance.get("address_postcode"),
                    "provenance_address_country": provenance.get("address_country"),
                    "provenance_email": provenance.get("email"),
                    "provenance_footprint_ref": provenance.get("footprint_ref"),
                }
                names = ["stable_id", *column_types]
                parameters = [row["stable_id"], *(values[name] for name in column_types), lon, lat]
                updates = sql.SQL(", ").join(
                    sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(name), sql.Identifier(name))
                    for name in column_types
                )
                cursor.execute(sql.SQL("""
                    INSERT INTO {}.{} ({}, geom, is_active)
                    VALUES ({}, ST_SetSRID(ST_MakePoint(%s, %s), 4326), true)
                    ON CONFLICT (stable_id) DO UPDATE SET {}, geom = EXCLUDED.geom, is_active = true
                """).format(
                    sql.Identifier(schema), sql.Identifier(table),
                    sql.SQL(", ").join(map(sql.Identifier, names)),
                    sql.SQL(", ").join(sql.Placeholder() for _ in names),
                    updates,
                ), parameters)
            cursor.execute(sql.SQL("""
                CREATE VIEW {}.{} AS SELECT {}, geom::geometry(Point,4326) AS geom
                FROM {}.{} WHERE is_active = true
            """).format(
                sql.Identifier(schema), sql.Identifier(layer),
                sql.SQL(", ").join(map(sql.Identifier, public_columns)),
                sql.Identifier(schema), sql.Identifier(table),
            ))


STYLE_SLD = """<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor version="1.0.0"
 xmlns="http://www.opengis.net/sld"
 xmlns:ogc="http://www.opengis.net/ogc"
 xmlns:xlink="http://www.w3.org/1999/xlink"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
 xsi:schemaLocation="http://www.opengis.net/sld http://schemas.opengis.net/sld/1.0.0/StyledLayerDescriptor.xsd">
  <NamedLayer><Name>poi_harvester_style</Name><UserStyle><Title>POI Harvester categories</Title>
    <FeatureTypeStyle>
      <Rule><Name>pharmacy</Name><Title>Pharmacy</Title>
        <ogc:Filter><ogc:PropertyIsEqualTo><ogc:PropertyName>category</ogc:PropertyName><ogc:Literal>pharmacy</ogc:Literal></ogc:PropertyIsEqualTo></ogc:Filter>
        <PointSymbolizer><Graphic><Mark><WellKnownName>circle</WellKnownName>
          <Fill><CssParameter name="fill">#2563eb</CssParameter></Fill>
          <Stroke><CssParameter name="stroke">#ffffff</CssParameter><CssParameter name="stroke-width">1</CssParameter></Stroke>
        </Mark><Size>11</Size></Graphic></PointSymbolizer>
      </Rule>
      <Rule><Name>clinic</Name><Title>Clinic</Title>
        <ogc:Filter><ogc:PropertyIsEqualTo><ogc:PropertyName>category</ogc:PropertyName><ogc:Literal>clinic</ogc:Literal></ogc:PropertyIsEqualTo></ogc:Filter>
        <PointSymbolizer><Graphic><Mark><WellKnownName>circle</WellKnownName>
          <Fill><CssParameter name="fill">#dc2626</CssParameter></Fill>
          <Stroke><CssParameter name="stroke">#ffffff</CssParameter><CssParameter name="stroke-width">1</CssParameter></Stroke>
        </Mark><Size>11</Size></Graphic></PointSymbolizer>
      </Rule>
      <Rule><Name>hospital</Name><Title>Hospital</Title>
        <ogc:Filter><ogc:PropertyIsEqualTo><ogc:PropertyName>category</ogc:PropertyName><ogc:Literal>hospital</ogc:Literal></ogc:PropertyIsEqualTo></ogc:Filter>
        <PointSymbolizer><Graphic><Mark><WellKnownName>circle</WellKnownName>
          <Fill><CssParameter name="fill">#7c3aed</CssParameter></Fill>
          <Stroke><CssParameter name="stroke">#ffffff</CssParameter><CssParameter name="stroke-width">1</CssParameter></Stroke>
        </Mark><Size>11</Size></Graphic></PointSymbolizer>
      </Rule>
      <Rule><Name>school</Name><Title>School</Title>
        <ogc:Filter><ogc:PropertyIsEqualTo><ogc:PropertyName>category</ogc:PropertyName><ogc:Literal>school</ogc:Literal></ogc:PropertyIsEqualTo></ogc:Filter>
        <PointSymbolizer><Graphic><Mark><WellKnownName>circle</WellKnownName>
          <Fill><CssParameter name="fill">#d97706</CssParameter></Fill>
          <Stroke><CssParameter name="stroke">#ffffff</CssParameter><CssParameter name="stroke-width">1</CssParameter></Stroke>
        </Mark><Size>11</Size></Graphic></PointSymbolizer>
      </Rule>
      <Rule><Name>other</Name><Title>Other POI</Title><ElseFilter/>
        <PointSymbolizer><Graphic><Mark><WellKnownName>circle</WellKnownName>
          <Fill><CssParameter name="fill">#64748b</CssParameter></Fill>
          <Stroke><CssParameter name="stroke">#ffffff</CssParameter><CssParameter name="stroke-width">1</CssParameter></Stroke>
        </Mark><Size>10</Size></Graphic></PointSymbolizer>
      </Rule>
    </FeatureTypeStyle>
  </UserStyle></NamedLayer>
</StyledLayerDescriptor>"""


def _geoserver_request(method: str, path: str, body: str | None = None, content_type: str = "application/json", not_found_ok: bool = False) -> bytes:
    base = environ["GEOSERVER_URL"].rstrip("/")
    user, password = environ["GEOSERVER_USER"], environ["GEOSERVER_PASSWORD"]
    auth = b64encode(f"{user}:{password}".encode()).decode()
    request = Request(
        base + "/rest/" + path,
        data=body.encode("utf-8") if body is not None else None,
        method=method,
        headers={"Authorization": "Basic " + auth, "Content-Type": content_type, "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            return response.read()
    except HTTPError as exc:
        if exc.code == 404 and not_found_ok:
            return b""
        if exc.code == 409 and method == "POST":
            return b""
        raise RuntimeError(f"GeoServer {method} {path} returned HTTP {exc.code}") from exc


def _verify_wms_layer(workspace: str, layer: str) -> None:
    base = environ["GEOSERVER_URL"].rstrip("/")
    auth = b64encode(f"{environ['GEOSERVER_USER']}:{environ['GEOSERVER_PASSWORD']}".encode()).decode()
    url = base + f"/{workspace}/wms?service=WMS&version=1.3.0&request=GetCapabilities"
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={"Authorization": "Basic " + auth}), timeout=30) as response:
                root = ElementTree.fromstring(response.read())
            names = {element.text for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "Name"}
            if layer in names or f"{workspace}:{layer}" in names:
                return
        except Exception:
            if attempt == 2:
                raise
        sleep(2)
    raise RuntimeError(f"GeoServer did not expose {workspace}:{layer} in WMS capabilities")


def publish_geoserver(layer: str, metadata: dict, database: str, workspace: str, schema: str = "public") -> str:
    """Register the PostGIS view as a styled GeoServer feature type."""
    layer, workspace, schema = map(_identifier, (layer, workspace, schema))
    store = _store(database, schema)
    if not _geoserver_request("GET", f"workspaces/{workspace}.json", not_found_ok=True):
        _geoserver_request("POST", "workspaces", json.dumps({"workspace": {"name": workspace}}))
    params = {
        "host": environ.get("GEOSERVER_PGHOST") or environ["PGHOST"],
        "port": environ.get("PGPORT", "5432"),
        "database": database,
        "user": environ["PGUSER"],
        "passwd": environ["PGPASSWORD"],
        "dbtype": "postgis", "schema": schema,
    }
    body = json.dumps({"dataStore": {
        "name": store, "type": "PostGIS", "workspace": {"name": workspace},
        "enabled": True,
        "connectionParameters": {"entry": [{"@key": key, "$": value} for key, value in params.items()]},
    }})
    if not _geoserver_request("GET", f"workspaces/{workspace}/datastores/{store}.json", not_found_ok=True):
        _geoserver_request("POST", f"workspaces/{workspace}/datastores", body)
    attribution = "; ".join(sorted({item["attribution"] for item in metadata.get("contributors", [])}))
    demo_data = bool(metadata.get("demo_data"))
    disclaimer = "DEMO DATA: invented locations for software testing; not verified POIs. " if demo_data else ""
    abstract = f"{disclaimer}POI Harvester layer. Source attribution: {attribution or 'none'}. Field provenance is exposed in provenance_* columns."
    feature_type = {
        "name": layer, "nativeName": layer, "title": ("DEMO - " if demo_data else "") + layer.replace("_", " ").title(),
        "abstract": abstract, "srs": "EPSG:4326",
    }
    if not _geoserver_request("GET", f"workspaces/{workspace}/datastores/{store}/featuretypes/{layer}.json", not_found_ok=True):
        _geoserver_request("POST", f"workspaces/{workspace}/datastores/{store}/featuretypes", json.dumps({"featureType": feature_type}))
    _geoserver_request("PUT", f"workspaces/{workspace}/datastores/{store}/featuretypes/{layer}", json.dumps({
        "featureType": {"title": feature_type["title"], "abstract": abstract}
    }))
    style_name = "poi_harvester_style"
    if not _geoserver_request("GET", f"styles/{style_name}.json", not_found_ok=True):
        _geoserver_request("POST", f"styles?name={style_name}", STYLE_SLD, "application/vnd.ogc.sld+xml")
    else:
        _geoserver_request("PUT", f"styles/{style_name}", STYLE_SLD, "application/vnd.ogc.sld+xml")
    _geoserver_request("PUT", f"layers/{workspace}:{layer}", json.dumps({
        "layer": {"defaultStyle": {"name": style_name}}
    }))
    _verify_wms_layer(workspace, layer)
    base = environ["GEOSERVER_URL"].rstrip("/")
    return f"{base}/{workspace}/wms?service=WMS&request=GetCapabilities"


def _guard_publication_target(layer: str, database: str, workspace: str, schema: str) -> None:
    """Prevent a workspace/schema mismatch or an accidental shared-table overwrite."""
    layer, workspace, schema = map(_identifier, (layer, workspace, schema))
    store = _store(database, schema)
    catalog = json.loads(_geoserver_request("GET", "layers.json"))
    entries = catalog.get("layers", {}).get("layer", [])
    for item in entries if isinstance(entries, list) else []:
        name = item["name"]
        if not name.endswith(":" + layer):
            continue
        response = json.loads(_geoserver_request("GET", f"layers/{name}.json"))
        resource = response["layer"]["resource"]["href"]
        target_suffix = f"/workspaces/{workspace}/datastores/{store}/featuretypes/{layer}.json"
        shared_suffix = f"/datastores/{store}/featuretypes/{layer}.json"
        if name == f"{workspace}:{layer}" and not resource.endswith(target_suffix):
            raise ValueError(f"{name} already points to a different PostGIS store; choose its existing schema or another workspace/layer")
        if name != f"{workspace}:{layer}" and resource.endswith(shared_suffix):
            raise ValueError(f"{database}.{schema}.{layer} is already published in {name}; use a different schema or layer")


def publish(output_dir: Path, layer: str, database: str, workspace: str, schema: str = "public", allow_demo: bool = False) -> dict:
    publication_started = perf_counter()
    records = json.loads((output_dir / "records.json").read_text(encoding="utf-8"))
    metadata = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
    snapshot = output_dir / "sources_snapshot.json"
    if snapshot.exists():
        selected = {item["source"] for item in metadata.get("contributors", [])}
        metadata["demo_data"] = any(
            item["kind"] == "fixture" and item["name"] in selected
            for item in json.loads(snapshot.read_text(encoding="utf-8"))
        )
    if metadata.get("demo_data") and not allow_demo:
        raise ValueError("Fixture coordinates are invented. Publication requires explicit allow_demo=True for an isolated test.")
    guard_started = perf_counter()
    _guard_publication_target(layer, database, workspace, schema)
    postgis_started = perf_counter()
    publish_postgis(records, layer, database, schema, bool(metadata.get("demo_data")))
    postgis_seconds = perf_counter() - postgis_started
    geoserver_started = perf_counter()
    url = publish_geoserver(layer, metadata, database, workspace, schema)
    geoserver_seconds = perf_counter() - geoserver_started
    result = {"database": database, "schema": schema, "layer": f"{workspace}:{layer}", "wms_url": url, "feature_count": len(records), "demo_data": bool(metadata.get("demo_data"))}
    result["timings"] = {"publication_setup_seconds": guard_started - publication_started,
                         "target_guard_seconds": postgis_started - guard_started,
                         "postgis_seconds": postgis_seconds, "geoserver_seconds": geoserver_seconds,
                         "publication_seconds": perf_counter() - publication_started}
    (output_dir / "publication.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def verify_local(layer: str, database: str, workspace: str, schema: str = "public", output_dir: Path | None = None) -> dict:
    """Read the real PostGIS view and GeoServer catalog/WMS after publication."""
    try:
        import psycopg
        from psycopg import sql
    except ImportError as exc:
        raise RuntimeError("Local verification requires: pip install '.[postgis]'") from exc
    layer, workspace = map(_identifier, (layer, workspace))
    schema = _identifier(schema)
    with psycopg.connect(**_pg_kwargs(database)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT PostGIS_Version()")
            postgis_version = cursor.fetchone()[0]
            cursor.execute(sql.SQL("""
                SELECT count(*),
                    count(*) FILTER (WHERE ST_SRID(geom) <> 4326),
                    count(*) FILTER (WHERE geometry_provenance IS NULL OR attributions IS NULL),
                    count(*) FILTER (WHERE ST_X(geom) <> longitude OR ST_Y(geom) <> latitude)
                FROM {}.{}
            """).format(sql.Identifier(schema), sql.Identifier(layer)))
            feature_count, wrong_srid, missing_provenance, coordinate_mismatch = cursor.fetchone()
            cursor.execute(sql.SQL("SELECT stable_id, ST_X(geom), ST_Y(geom) FROM {}.{}").format(
                sql.Identifier(schema), sql.Identifier(layer)))
            database_coordinates = {stable_id: (lon, lat) for stable_id, lon, lat in cursor.fetchall()}
    if wrong_srid or missing_provenance or coordinate_mismatch:
        raise RuntimeError(f"PostGIS layer invalid: {wrong_srid} wrong-SRID features, {missing_provenance} missing provenance, {coordinate_mismatch} coordinate mismatches")
    layer_response = json.loads(_geoserver_request("GET", f"layers/{workspace}:{layer}.json"))
    style_name = layer_response["layer"]["defaultStyle"]["name"]
    if style_name != "poi_harvester_style":
        raise RuntimeError(f"GeoServer layer has unexpected default style: {style_name}")
    feature_response = json.loads(_geoserver_request(
        "GET", f"workspaces/{workspace}/datastores/{_store(database, schema)}/featuretypes/{layer}.json"
    ))
    abstract = feature_response["featureType"].get("abstract", "")
    expected_count = None
    expected_generated_names = 0
    expected_records = []
    source_coordinate_checks = 0
    if output_dir is not None:
        metadata = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
        expected_count = metadata["feature_count"]
        expected_generated_names = metadata.get("generated_name_count", 0)
        if feature_count != expected_count:
            raise RuntimeError(f"PostGIS count {feature_count} differs from run output {expected_count}")
        missing = [item["attribution"] for item in metadata["contributors"] if item["attribution"] not in abstract]
        if missing:
            raise RuntimeError("GeoServer feature type metadata is missing source attribution")
        expected_records = json.loads((output_dir / "records.json").read_text(encoding="utf-8"))
        if expected_generated_names:
            with psycopg.connect(**_pg_kwargs(database)) as name_connection:
                with name_connection.cursor() as name_cursor:
                    name_cursor.execute(sql.SQL("""
                        SELECT count(*) FILTER
                          (WHERE name_en_method IS NOT NULL OR name_ar_method IS NOT NULL)
                        FROM {}.{}
                    """).format(sql.Identifier(schema), sql.Identifier(layer)))
                    published_generated = name_cursor.fetchone()[0]
            if published_generated != sum(bool(row.get("name_en_method") or row.get("name_ar_method"))
                                          for row in expected_records):
                raise RuntimeError("PostGIS generated-name count differs from saved harvest")
        if set(database_coordinates) != {row["stable_id"] for row in expected_records}:
            raise RuntimeError("PostGIS IDs differ from the saved harvest")
        for row in expected_records:
            lon, lat = database_coordinates[row["stable_id"]]
            if abs(lon - row["lon"]) > 1e-8 or abs(lat - row["lat"]) > 1e-8:
                raise RuntimeError(f"PostGIS coordinate differs from harvest for {row['stable_id']}")
        raw_path = output_dir / "raw.json"
        if raw_path.exists():
            raw_coordinates = {
                f"{item['source']}:{item['record']['id']}": item["record"]
                for item in json.loads(raw_path.read_text(encoding="utf-8"))
            }
            for row in expected_records:
                if row.get("geometry_method") != "osm_node":
                    continue
                source = raw_coordinates.get(row["geometry_provenance"])
                if not source or abs(source["lon"] - row["lon"]) > 1e-8 or abs(source["lat"] - row["lat"]) > 1e-8:
                    raise RuntimeError(f"Published coordinate differs from OSM node for {row['stable_id']}")
                source_coordinate_checks += 1
    _verify_wms_layer(workspace, layer)
    service_auth = b64encode(f"{environ['GEOSERVER_USER']}:{environ['GEOSERVER_PASSWORD']}".encode()).decode()
    wfs_url = environ["GEOSERVER_URL"].rstrip("/") + f"/{workspace}/ows?" + urlencode({
        "service": "WFS", "version": "2.0.0", "request": "GetFeature",
        "typeNames": f"{workspace}:{layer}", "outputFormat": "application/json", "count": 1,
    })
    with urlopen(Request(wfs_url, headers={"Authorization": "Basic " + service_auth}), timeout=30) as response:
        wfs_data = json.load(response)
    wfs_fields = set(wfs_data["features"][0]["properties"]) if wfs_data.get("features") else set()
    required_fields = {"stable_id", "longitude", "latitude", "primary_source", "primary_source_id",
                       "name_en", "name_ar", "alternate_names", "email", "footprint_ref",
                       "category", "source_category", "address", "phone", "hours", "website", "confidence",
                       "geometry_method", "source_keys", "attributions", "licenses", "geometry_provenance",
                       "provenance_name_en", "provenance_name_ar", "provenance_category"}
    if expected_generated_names:
        required_fields.update({"name_en_method", "name_en_version", "name_en_confidence",
                                "name_ar_method", "name_ar_version", "name_ar_confidence",
                                "original_name_en", "original_name_ar"})
    if any("name_en_generated" in row or "name_ar_generated" in row for row in expected_records):
        required_fields.update({"name_en_generated", "name_ar_generated"})
    if feature_count and (missing_fields := required_fields - wfs_fields):
        raise RuntimeError(f"GeoServer WFS omitted dedicated POI fields: {sorted(missing_fields)}")
    if "properties" in wfs_fields:
        raise RuntimeError("GeoServer WFS still exposes a bundled properties column")
    if wfs_data.get("features"):
        first_feature = wfs_data["features"][0]
        point = database_coordinates.get(first_feature["properties"].get("stable_id"))
        geometry = first_feature.get("geometry") or {}
        if geometry.get("type") != "Point" or point is None or any(
                abs(float(actual) - expected) > 1e-8 for actual, expected in zip(geometry["coordinates"], point)):
            raise RuntimeError("WFS geometry differs from the PostGIS point")
        if expected_records:
            expected = next(row for row in expected_records if row["stable_id"] == first_feature["properties"]["stable_id"])
            for name in ("name_en", "name_ar", "category", "geometry_provenance"):
                if first_feature["properties"].get(name) != expected.get(name):
                    raise RuntimeError(f"WFS field {name} differs from the saved harvest")
    style_xml = ElementTree.fromstring(_geoserver_request("GET", f"styles/{style_name}.sld"))
    rules = {node.text for rule in style_xml.iter() if rule.tag.rsplit("}", 1)[-1] == "Rule"
             for node in rule if node.tag.rsplit("}", 1)[-1] == "Name"}
    if not {"pharmacy", "clinic", "hospital", "school", "other"} <= rules:
        raise RuntimeError("GeoServer category style rules are missing")
    if database_coordinates:
        longitudes, latitudes = zip(*database_coordinates.values())
        padding = 0.001
        bbox = (min(longitudes) - padding, min(latitudes) - padding,
                max(longitudes) + padding, max(latitudes) + padding)
    else:
        bbox = (-180, -90, 180, 90)
    image_url = environ["GEOSERVER_URL"].rstrip("/") + f"/{workspace}/wms?" + urlencode({
        "service": "WMS", "version": "1.1.1", "request": "GetMap", "layers": f"{workspace}:{layer}",
        "styles": "", "srs": "EPSG:4326", "bbox": ",".join(map(str, bbox)),
        "width": 256, "height": 256, "format": "image/png"})
    with urlopen(Request(image_url, headers={"Authorization": "Basic " + service_auth}), timeout=30) as response:
        map_bytes = response.read()
    if not map_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError("WMS GetMap did not return a PNG map")
    return {
        "status": "passed",
        "layer": f"{workspace}:{layer}",
        "database": database,
        "schema": schema,
        "postgis_version": postgis_version,
        "postgis_feature_count": feature_count,
        "expected_feature_count": expected_count,
        "wrong_srid_count": wrong_srid,
        "missing_provenance_count": missing_provenance,
        "coordinate_mismatch_count": coordinate_mismatch,
        "gold_coordinate_accuracy_verified": False,
        "geoserver_default_style": style_name,
        "wms_layer_available": True,
        "wms_getmap_png_verified": True,
        "category_style_rules_verified": sorted(rules),
        "wfs_geometry_and_values_verified": bool(feature_count),
        "wfs_dedicated_fields_verified": bool(feature_count),
        "source_node_coordinate_checks": source_coordinate_checks,
    }

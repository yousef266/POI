# Local Windows services

This PC has PostgreSQL 17 with PostGIS 3.6.2 on port 5432. The test database `poi_agent_test` has the PostGIS extension enabled. GeoServer 2.28.5 and Java 17 are installed under the ignored `.runtime` folder. GeoServer listens only on `127.0.0.1:8080` and can be started after a reboot with:

```powershell
.\scripts\start-native-geoserver.ps1
```

The ignored `.env` holds only server addresses and credentials. Copy `.env.example` when configuring another server. For each run, supply the target database and GeoServer workspace; schema defaults to `public`.

```powershell
.\run.ps1 run --bbox 24.70 46.66 24.73 46.69 --category pharmacy --sources 'demo,demo_alt' --out output/local --publish --allow-demo-publish --database poi_agent_test --workspace poi_agent_test
.\run.ps1 verify-local --database poi_agent_test --workspace poi_agent_test --layer poi_pharmacy --out output/local
```

The default `public` schema passed local publication and verification with two invented fixture POIs. The verification checks the PostGIS count, SRID, coordinates, and provenance, plus the GeoServer style, attribution, WMS layer, and WFS fields. This verifies publication mechanics, not real-world coordinate accuracy. The `.runtime` folder is local to this PC; on another server, install or connect to its services and edit `.env`.

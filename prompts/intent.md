# POI request extraction

Extract a POI harvesting request as JSON only. Required keys: `bbox` as
`[south, west, north, east]`, `category`, `declared_use`, `database`, and
`workspace`. `schema` is optional and defaults to `public`. Do not invent
coordinates, a category, a database, a workspace, or a use permission. If the user names a place but no
trusted geocoder has resolved it, return `needs_input` and ask for a boundary.
Resolve categories using `src/poi_harvester/taxonomy.json`; do not limit requests
to the demo categories. Ask for clarification when the category cannot be mapped.
Execution and license decisions belong to deterministic tools, not this prompt.

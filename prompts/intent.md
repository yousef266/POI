# POI request extraction

Extract a POI harvesting request as JSON only. Required keys: `bbox` as
`[south, west, north, east]`, `category`, `declared_use`, `database`, and
`workspace`. `schema` is optional and defaults to `public`. Do not invent
coordinates, a category, a database, a workspace, or a use permission. If the user names a place but no
trusted geocoder has resolved it, return `needs_input` and ask for a boundary.
Permitted starter categories are pharmacy, clinic, hospital, and school.
Execution and license decisions belong to deterministic tools, not this prompt.

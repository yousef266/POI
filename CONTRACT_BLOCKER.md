# Common Agent Contract blocker

The bounty PDF's page 18 says the Common Agent Contract applies to all six agents with no deviations. It points to `https://jenkins.penta-b.net/pentabdev/gura` for repository layout, contribution instructions, and onboarding samples. That URL was inaccessible from this workspace on 2026-09-25, and no contract file is present in the project.

The current `agent.json`, `poi_harvester.agent.invoke`, and CLI are **internal interfaces only**. They must not be described as compliant with the unpublished contract.

To close this blocker, obtain the official contract/repository files, map their required inputs, outputs, lifecycle states, manifest, repository layout, and tests to the current interfaces, then run the official contract suite. No interface or layout has been invented to substitute for that specification.

## Search performed on 2026-09-26

Searched the repository file inventory and text references (excluding installed runtimes/dependencies and generated output), README, internal agent manifest, design/readiness/audit documents, tests, build configuration, source modules and onboarding prompt. There is no official contract schema, lifecycle specification, reference implementation or contract test suite in those files. Existing references point back to the bounty PDF and the previously inaccessible Jenkins reference URL.

Required to certify: the exact contract version; authoritative manifest/input/output schemas; lifecycle/error/progress rules; required repository/package layout and entry point; provenance/replay requirements; deployment rules; and the official compliance test suite. The current internal CLI/invoke adapters can be mapped after those documents arrive. This blocker is external; it does not certify any local adapter as contract compliant.

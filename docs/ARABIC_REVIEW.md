# Human Arabic name review

`fixtures/arabic_name_review.json` contains 100 deterministic, project-authored generated-name examples across ten existing taxonomy categories. Every example starts as `NOT_REVIEWED`, with an empty reviewer and rating. These names are a local review corpus; they are not official gold data or a representative real-source benchmark.

Prepare an empty ratings file and confirm there is no human score:

```powershell
.\run.ps1 review-names --ratings output/arabic-review/ratings.json --out output/arabic-review/score.json
```

Run or resume review:

```powershell
.\run.ps1 review-names --interactive --reviewer "YOUR NAME" --ratings output/arabic-review/ratings.json --out output/arabic-review/score.json
```

For each name, accept (`a`) only when both the generic translation and proper-name rendering are acceptable. Reject (`r`) an incorrect output, skip (`s`) an uncertain one, or quit (`q`) and resume later. Each submitted decision is saved immediately. A dataset hash prevents ratings being reused after names or algorithm versions change.

Score an existing ratings file without prompting:

```powershell
.\run.ps1 review-names --ratings output/arabic-review/ratings.json --out output/arabic-review/score.json
.\run.ps1 evaluate --out output/evaluation-reviewed --ratings output/arabic-review/ratings.json
```

The partial score is accepted/reviewed. A complete-sample score is produced only after all 100 names are explicitly rated by a named reviewer. No automatic rating is generated, and the official status always remains `NOT_CERTIFIED`. Human review of this synthetic corpus does not certify Arabic quality on the official real-source sample.

## Queue uncertain names first

Export the 30 uncertain examples without generating human decisions:

```powershell
.\run.ps1 review-names --queue-out output/arabic-review/queue.json
.\run.ps1 review-names --queue output/arabic-review/queue.json --interactive --reviewer "Yousef"
```

The export also creates `queue.md` for reading. Each item includes its ID, current
Arabic name, source English name, proposed Unicode/whitespace normalization only,
reason, confidence and provenance. A queue hash binds it to the complete dataset.
Reviewing just this queue remains a partial review of 100; run the regular command
afterward to review the remaining names. Human decisions are saved only after
explicit keyboard input. The synthetic corpus remains separate from Cairo POIs.

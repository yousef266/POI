# Human Arabic name review

## Completed review

Yousef explicitly confirmed that all 100 existing examples were manually reviewed and accepted. This user attestation is authoritative evidence for this verification run:

- AI assessed: 100.
- Human reviewed: 100.
- Human accepted: 100.
- Human rejected: 0.
- Unreviewed: 0.

`fixtures/arabic_name_review_human_ratings.json` records ACCEPT for the exact 100 existing IDs. `fixtures/arabic_name_review_manifest.json` binds the input and decisions with canonical hashes, independent of LF/CRLF formatting. No name, ID, category, confidence, transformation or POI data was altered. Recorded time is transcription time; the human did not supply a review timestamp.

The original `arabic_name_review.json` remains the unchanged unrated generator/input fixture. Its NOT_REVIEWED defaults describe the input template, not the effective state after applying the accepted ratings. The old priority queue had 30 items from this 100-example corpus. Its IDs were preserved; the explicit correction covers the entire corpus.

Score and export the completed priority queue:

```powershell
.\run.ps1 review-names --ratings fixtures/arabic_name_review_human_ratings.json --queue-out output/arabic-review/queue.json --out output/arabic-review/score.json
.\run.ps1 evaluate --ratings fixtures/arabic_name_review_human_ratings.json --out output/evaluation-reviewed
```

The queue exporter now shows supplied decisions rather than incorrectly marking approved entries pending. A complete 100-example acceptance score is 1.0. Human Arabic review is not a remaining blocker. The corpus is project-authored; judge/platform acceptance is not fabricated as an official certification.

## Other review datasets

For a genuinely new corpus, supply its dataset and a separate ratings path. Interactive review records explicit ACCEPT/REJECT decisions, validates IDs and dataset hashes, saves each decision, and can resume. No automatic human decisions are generated.

```powershell
.\run.ps1 review-names --dataset PATH_TO_NEW_DATASET --ratings output/new-review/ratings.json --out output/new-review/score.json --interactive --reviewer "YOUR NAME"
```

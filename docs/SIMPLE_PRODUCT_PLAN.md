# Movement Lens 0.3: one clear movement-review task

Historical version: implemented October 28, 2026, then superseded by the cluster-level 0.4 workflow in [CLUSTER_MATCH_PLAN.md](CLUSTER_MATCH_PLAN.md).

## User outcome

Pick a player's movement, find comparable moments in one sample match, inspect the evidence, and share a concise explanation with the clips. The primary user is an analyst or coach. A physio perspective means describing projected posture and movement observations, not maintaining medical notes or estimating treatment.

## Three screens

1. **Browse movements.** Match selection and observed coverage stay visible. Two broad numerical groups show three examples each. The sample match opens with six explicitly labelled, hand-selected highlights. The rest of the match's usable windows remain accessible in a collapsed browser. Import is a secondary action.
2. **Compare moments.** Source video and player-scaled pose appear side by side. Search defaults to the selected match, across its available source halves. An optional all-imported-matches scope enables broader retrieval. Fixed exploratory closeness presets are simpler than a numerical distance control. Counts are candidate clips, merged source intervals and matched observed seconds. Keep relevant comparisons; reveal timelines and traces only when needed. Show the largest measured differences without a muscle-risk body map.
3. **Explain & export.** One question and one explanation action. Microsoft Foundry describes the selected movement from an observational physiotherapy perspective in plain language. Selected-window descriptors are retrieved before drafting; an actual pair comparison is required before comparing the clips. No symptoms, RPE, reviewer, treatment decision or follow-up form is shown. Export includes the current saved explanation, its citations and generation provenance, selected clips and computed evidence. A local measured snapshot works without Foundry.

## Demo and honesty

The local default sample is Real Madrid versus Real Sociedad: 290 usable windows from two source halves. Group examples are curated, but the source data and feature values are unmodified and the full usable match sample is searched. The complete local library still contains 540 usable windows across four matches. Other matches remain available from the match selector.

Two K-means groups are an intentional browsing choice, not an optimized number of real football activities. Labels describe broad projected leg-bend patterns; neither is a validated action class. Curated highlights are explicitly identified. The first dynamic highlight is first-half source time 21:36.04. Its default same-match search returns three candidate clips in the current selected-library scaling.

Demo settings are private and ignored: `runtime/prepared/simple-demo.json`. Fresh installations choose the largest available match and use examples near group centres. All clipping, pose checks, source provenance and original snapshots are retained. No new pose estimation or source-drive processing was needed.

## Import and Microsoft integration

Import accepts a Touchline ZIP with movement-window pose data and optional source clips. Any imported usable window can become the search example. Arbitrary raw MP4 sample upload is not implemented because it requires the upstream pose/window preparation step. Private Azure dataset import remains a secondary option in the import dialog. Report export can be saved to private Azure storage using the existing adapter.

Foundry explanations are stored server-side as immutable artifacts associated with the exact movement, scope, cutoff, comparison and curated selection. Export verifies that association. Changing the selection invalidates the displayed draft and prevents attaching an earlier explanation to new evidence. A report can include a computed snapshot when no AI draft was requested.

## Acceptance proof

- Three-screen browser workflow; no old sidebar or clinical form.
- Curated example frames load, with all match windows available on demand.
- Same-match search includes both source halves and excludes other matches; optional library-wide search works.
- Video and pose remain bounded and synchronized at desktop, tablet and mobile widths.
- Curated clips and the same live AI explanation are included in a downloaded ZIP; its standalone HTML plays its included videos.
- Changing selection clears the explanation and export result.
- Existing datasets and analyses are preserved.

Proof lives privately under `runtime/simple-proof/`, including screenshots, downloaded pack and verification JSON. Existing research APIs and older review records are retained for reproducibility, without exposing a second UI workflow.

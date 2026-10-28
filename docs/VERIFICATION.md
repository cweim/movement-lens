# Build verification — 2026-10-27

The first local Movement Lens application is implemented in this standalone folder. The submitted Touchline application and original research data/model outputs were not modified by this build.

## Checks completed

- `python3 -m pytest -q`: **33 passed** after the reference expansion. Tests exercise masks and geometry, source gaps, original-observation visibility, identity-review exclusions, overlapping coverage, safe ZIP/NPZ parsing including forged giant headers, stable IDs, reference-only scaling, match/player splits including opposite source halves, half-open source clip frame boundaries, calibration absence, reports, API import/download and cloud boundaries.
- `npm run build`: TypeScript and production Vite build pass. The interface uses installed local assets and system fonts.
- Editable package installation succeeded in a temporary Python environment with shared existing dependencies. Import was verified from outside the project directory. This is not a claim that a fresh machine's entire dependency environment or optional SDKs were tested.
- A real 430-window Touchline ZIP imported through the browser. Its unverified pose-source provenance was retained, with zero windows eligible for scoring. Its quality screen was inspected.
- The completed app ran on `127.0.0.1:8770`. Existing Touchline service on port 8767 was preserved.
- A headless-browser workflow decoded two real clips, advanced playback/scrubbing, switched reference examples, generated a deterministic explanation with source IDs, selected an episode, downloaded a media-inclusive report, and opened its HTML independently of the app. No JavaScript page errors were recorded.
- The comparison view was checked at 390px mobile width without horizontal document overflow. Desktop comparison, explanation, quality and export screens and the portable report were rendered and visually inspected.

The final browser evidence is in ignored `runtime/browser-proof-final/verification.json` and associated screenshots/report. Reproduce with Playwright and a prepared analysis:

```bash
PLAYWRIGHT_BROWSERS_PATH=runtime/playwright \
python scripts/browser_smoke.py \
  --analysis ANALYSIS_ID \
  --output runtime/browser-proof
```

The browser package is a development check dependency, not a requirement for running the application. The local verification environment used a project-private Playwright browser installation.

## Initial private example data (historical snapshot)

A compact selection was recomputed from three existing match-half sources, using the existing YOLOv8x pose checkpoint on CPU. The full SHA-256 of each source was checked against its recorded job before inference. The helper reused existing bounds and generated actual source clip videos; it did not run full-match tracking or change the original caches.

| Role | Retained windows | Usable in initial demo |
|---|---:|---:|
| First reference source | 15 | 14 |
| Second reference source | 16 | 15 |
| Query source | 14 | 14 |
| Total | 45 | 43 |

Three of 48 attempted windows produced no adequate matched pose and were not exported. One retained reference failed pose checks. An additional reference was explicitly marked `identity_ambiguous` after visual review found an ambiguous beginning, and was withheld in a new derived snapshot. Previous generated snapshots were retained privately as superseded records. This review did not establish identity correctness for every remaining frame: their identity provenance remains imported/unspecified and is visible in the interface.

The initial demo scored 14 query windows against 29 usable reference windows from separate sources. It had no independent calibration dataset. These selected examples demonstrate software behavior; they are not an unbiased retrieval, pose-accuracy or medical evaluation.

Private preparation inputs, clips, logs, checkpoint references, generated reports and superseded artifacts are under ignored `runtime/`. None should be included in a source upload merely because the app can display it.

## Current private reference library

H3 was added as reference data, followed by H1's and H2's second halves. The current analysis scores the same 14 E02 query windows against **319 eligible reference windows from three matches and six source halves**.

| Reference match | First-half eligible windows | Second-half eligible windows |
|---|---:|---:|
| H1: Real Madrid–Málaga | 14 | 77 |
| H2: Real Madrid–Real Sociedad | 15 | 174 |
| H3: Real Madrid–Villarreal | 12 | 27 |

Both new source videos passed full SHA-256 checks. Full-frame views confirmed the fixtures and second-half indicators. All 344 selected non-overlapping tracklet-window candidates received three-frame source-crop screening. There were 77 conservative identity flags; 57 were skipped before further pose inference. Twelve candidates had no adequate matched source-bound pose. The resulting 275 prepared windows were imported with their review provenance: 251 are eligible, while 18 identity-ambiguous, five poor-pose and one redundant overlapping window remain withheld. Screening is not exhaustive frame-by-frame identity certification.

All 275 imported clips decoded at their first and last frame, with exactly 50 frames at 25 fps. Thirteen clips had a trailing frame removed after a floating-point boundary bug was found and fixed in the preparation helper. The pose arrays were unaffected. An unused earlier H1 import was preserved privately as a superseded derived artifact. All pre-existing dataset and analysis record hashes remained unchanged.

The new analysis and media-inclusive report passed the browser workflow again, with no page errors or mobile overflow. Browser evidence is under ignored `runtime/browser-proof-six-halves/`; preparation, exclusion reasons and rollback pointers are under `runtime/second-half-references/`.

The six source halves are represented by extracted player windows, not continuous whole-match observation. H1/H2 first-half imports remain the initial compact selections. Calibration is still absent: scores are uncalibrated distances without percentile badges. Existing frozen analyses remain available; open the latest analysis link to see its expanded references.

## Microsoft integration status

The optional Azure Blob adapter is implemented and covered with a fake private container: immutable upload, duplicate-save behavior, exact download bytes, checksum rejection and public-container refusal. This build did **not** perform a live Movement Lens Azure upload/download. Touchline's earlier user-reported cloud test is a separate application result.

The optional Foundry adapter is implemented with a bounded, stateless read-only function-tool loop. Tests exercise returned tool evidence, real window-ID citations, unsupported citations, missing tool retrieval and numeric model-prose rejection. The app retains exact numerical comparisons outside model prose.

No Foundry project/model was provisioned or contacted, and the optional `azure-ai-projects` package was not installed for a live request in this build. SDK/project configuration, authentication, endpoint compatibility and actual inference still require a live account check. The core local workflow and local explanations function without it.

## Remaining product/evaluation work

- Expand independently reviewed player-identity and movement examples; verify source/pose/identity correspondence on more matches.
- Add a genuinely separate calibration cohort before interpreting empirical ranks; hold out additional matches for evaluation.
- Evaluate retrieval relevance, distinct-episode precision and quality-error rejection without tuning on the evaluation examples.
- Connect and verify optional Azure/Foundry resources if used in a second submission.
- Review the second entry's current hackathon requirements and media permissions before publishing a demo.

This build is a functional local MVP, with a small inspected demo. It does not establish injury prediction, gait classification or production cloud deployment readiness.

## Full-library preparation helper, 2026-10-27

Added `scripts/expand_local_library.py` and documented it in `docs/FULL_LIBRARY.md`. Its read-only plan was run against the attached-drive workspace: 37/124/91 new candidates in H1 first/H2 first/E02 second respectively, 252 total. Checkpoint/import correspondence for H1/H2 second halves and both H3 halves passed. No long inference, new data import or active-pointer change was started during this helper's development; the active analysis remains 319 references and 14 query windows.

Full suite: **41 passed**, including eight expansion-specific tests. These cover uncapped candidate selection, preserved identity exclusions, verified reuse without inference, resume and corrupt-artifact detection, immutable previous records, activation failure/concurrency checks, disconnected-drive handling, and a controlled new window through real ffmpeg encoding, ZIP packaging and application import. Pose inference in that controlled test is mocked; it is not a new real-video pose benchmark. Existing dependency warnings remain (Starlette deprecation and sandbox physical-core detection fallback).

The recovery-oriented product direction is planned in `docs/RECOVERY_PRODUCT_PLAN.md`. Similarity timelines, the regional map, clinical context collection and validated recovery estimation are proposed work; they were not implemented by this preparation change.

## Clip/pose display correction, 2026-10-27

Reproduced a fixed-height clip card whose SVG intrinsic sizing expanded a 254-pixel stage's child row to 361 pixels. The video was vertically centered in that oversized row and then clipped by the card, with footer text overlapping it. Standalone pose auto-fitting also gave it a different scale from the source player.

The grid row and both media panels now have bounded sizing. Video and pose stay in equal-sized side-by-side viewports at all breakpoints. A display-only API field projects the existing keypoints through Touchline's padded tracked-player crop/resize/letterbox convention (256×512), including source-boundary clipping. Original hip-centred skeleton output is retained for compatibility. Descriptors, scores, NPZ files, imported records and source videos are unchanged by this display fix. Missing joints remain gaps. It does not reconstruct body parts outside the source frame or certify pose accuracy.

Full suite: **45 passed**; production frontend build passed. Live browser proof covers all 14 current query clips, start/end scrubbing, play/pause, all three reference choices, and widths 390/768/900/1024/1440/1800. Every tested video and pose panel remained within its stage with equal viewport dimensions, no horizontal overflow and no page errors. Private before/after screenshots, measured layout and verification output are under `runtime/crop-review/`.

Only the local web server was restarted to load the API change. The separately running library expansion process and its shared preparation helper/checkpoints were left untouched.

## Movement review workspace 0.2, built with the source drive unplugged

Implemented the connected workflow: K-means discovery with anonymous groups and WCSS/silhouette/Davies–Bouldin diagnostics; arbitrary-example similarity search with adjustable radius; source-time recurrence timelines and cross-match filtering; nonoverlapping sample profiles across matches; synchronized source/pose/trace comparison; interactive regional descriptor-distance contributions; staff-entered symptoms/exposure/assessment/decision/follow-up; immutable draft or named staff-reviewed snapshots; local evidence briefs; and portable curated review ZIPs with clips, research and provenance.

The default cached catalogue contains **364 unique usable windows, seven sources and four matches**, with **350 independent reference observations** used to fit scaling/groups. It uses the newest selected source snapshots, including the completed H1 first-half import. Search does not fit a new scaler to the example. Exact source-interval duplicates are deduplicated. Overlapping seed observations are excluded; other-matches-only also excludes both labelled halves and the seed source. Recurrence merges overlapping/adjacent intervals per source and counts unique seconds. Match group shares use nonoverlapping sampled windows, not whole-match workload. Groups/thresholds remain exploratory; there is no validated activity classifier or clinical recovery predictor.

Added private Azure Touchline dataset listing/import with paging, bounded download, ETag pinning, exact SHA-256/size checks and the standard importer. Added a Foundry pattern assistant with read-only timeline/profile/region/staff-context/curated-research tools, citations restricted to retrieved evidence and exact numerical fields outside model prose. These integrations are **mock-tested, not live cloud-verified**. Both remain unconfigured in the local running app; no account resources were provisioned or contacted.

Validation: **66 tests passed**, including the existing suite and new reference-only fitting, duplicate-source handling, recurrence/coverage, same-game half filtering, regional contributions, immutable/escaped review reports, API-to-download, private Azure integrity failures and grounded Foundry-tool cases. Production frontend build passed. Live browser proof exercised selecting an example, radius and cross-match filters, seven timelines, curation, side-by-side playback/scrubbing, regional interaction, staff context save/restore and a downloaded ZIP with playable source clips opened as a standalone report. Widths 390/768/1024/1440 passed without page errors or horizontal overflow.

Private proof: `runtime/offline-final-proof/verification.json`, screenshots, the extracted report and preserved-record hashes. Test-created clinical contexts were explicitly marked as demonstration data and then moved, with their test reports, into `runtime/offline-final-proof/demo-artifacts/`; they are not presented as actual staff reviews in the application.

All 12 pre-existing dataset/analysis records retained their hashes. The external volume remained unmounted. The original novelty analysis is still 319 references/14 query windows, and expansion remains stopped at H2 first-half candidate 113/140. No original video, Touchline database, pose cache, original model output or expansion checkpoint was modified by this offline build. Resume expansion separately after reconnecting the source drive, then rebuild the explorer using latest snapshots.

## Live Microsoft connection check — October 27, 2026

Verified the existing private Blob container and snapshot listing, and connected the local app to the user's Foundry project using Azure CLI identity. Installed Azure AI Projects 2.9.0 and its dependencies in an ignored, isolated runtime environment; shared Python packages were not replaced. The private launcher loads both storage and Foundry settings.

The `movement-lens-mini` GPT-5 mini Global Standard deployment reports Succeeded. A live SDK Responses request returned the expected connection confirmation. The movement assistant also successfully requested timeline, cross-match, regional and research evidence through its read-only tools. **A complete final AI explanation is not yet verified**: its follow-up request returned HTTP 429. The deployment was updated from 1,000 TPM / 1 RPM to 60,000 TPM / 60 RPM, but live error headers still reported the old limits. Microsoft documents that quota changes can take up to 15 minutes to propagate: [quota management](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/quota). No new cloud resource was created by this check.

Both Foundry adapters now bound each response to 4,096 output tokens, allow one SDK retry and show a specific rate-limit message without exposing SDK details. Focused cloud tests: **17 passed**. The running app reports storage, dataset import and Foundry configured/available; that availability flag indicates configuration and installed dependencies, not a successful end-to-end AI explanation. Private live proof is under `runtime/microsoft-connection/`. Report storage upload/download remains unverified for Movement Lens; the older cloud dataset remains an unverified-pose snapshot.

## Foundry end-to-end verification — October 28, 2026

The previous rate-limit error cleared. Live testing exposed an exact-ID citation error in unconstrained model output. The pattern assistant now uses a strict Responses JSON Schema with citation choices limited to IDs returned by tools. It requires both the pattern timeline and staff-context retrieval before accepting a draft, and forces missing required retrieval before synthesis. Structured-output requests disable parallel tool calls. Existing local output validation still rejects unseen citations and unsupported numerical/treatment statements. Method labels such as 2D/3D are accepted as dimensionality descriptions; numerical measurements in model prose remain rejected. See [Microsoft structured-output documentation](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs).

Focused cloud tests: **18 passed**, including schema citation scope, required staff-context retrieval, 2D terminology, numerical-claim rejection and invalid-citation rejection. A real request through the running app's exploration explanation endpoint passed in **30.17 seconds**, using the expanded 540-window / 451-reference catalogue and all five tools: timeline, match profiles, regional comparison, staff context and curated research. All returned observation citations belonged to retrieved evidence. This is a successful integration case, not a validation of clinical interpretation or model reliability across all questions.

Private proof: `runtime/microsoft-connection/foundry-pattern-live.json` and `verification.json`. The app was restarted with the verified adapter. Dataset snapshots, expansion outputs and the active expanded analysis remain unchanged. Movement Lens report upload/download to Blob Storage still requires its own live round-trip verification; this check did not upload report media or change cloud resources.

## Simplified movement workflow 0.3 — October 28, 2026

Replaced the primary interface with three screens: Browse movements, Compare moments, Explain & export. The local demo opens Real Madrid versus Real Sociedad with 290 usable windows and six explicitly curated highlights in two numerical groups. The other 250 usable windows remain available through match selection; all selected-match usable windows are searched, not only the highlighted examples. Group cards are descriptive browsing aids, not validated activity classes. The full clip browser, coverage timelines and traces use progressive disclosure. Clinical notes, symptom/RPE fields, treatment-plan entry, old sidebar navigation, diagnostics and the regional body map are absent from the primary UI.

Added same-match retrieval covering both source halves, match-specific representative examples, a movement-only Foundry prompt/tool boundary, and immutable server-side explanation artifacts. The movement assistant must read selected-window descriptors and, when a comparison exists, actual regional pair evidence. It has no staff-context tool. Export verifies that the saved explanation belongs to the current exact evidence selection and includes that draft, citations, model/question provenance, computed evidence and selected source clips. Old records and APIs remain compatible. Clinical context sections are omitted from movement-only evidence packs.

Validation: the full suite passed **72 tests** after adding same-match, curated-example scope, explanation snapshot/export binding and movement-only tool tests. A final focused recheck of **22 tests** passed after requiring actual pair evidence. Production frontend build passed. The final live browser exercise checked all three screens, six loaded preview frames, two source-half timelines, same-match and optional all-match search, source/pose playback and scrubbing, kept clips, a real Foundry explanation, its exact exported draft/provenance, three included playable clips, independent HTML report opening, and draft invalidation after the evidence selection changes. Widths **390/768/1440** passed without horizontal overflow or pose escaping its frame, with no browser errors.

Private proof: `runtime/simple-proof/verification.json`, screenshots and `evidence-pack.zip`. The browser verification hash-checked **15 pre-existing dataset/analysis records** for preservation. No new tracking, pose processing or source-drive access was required. The private Microsoft launcher remains available and the app is running at `http://127.0.0.1:8770/`.

The optional import accepts Touchline ZIP exports containing pose windows; arbitrary raw-video sample inference is not implemented. Azure dataset import and report storage controls are retained, but no new live storage upload/download was performed by this UI change. Historical recovery-plan documentation is explicitly marked as historical; the implemented direction is documented in `docs/SIMPLE_PRODUCT_PLAN.md`.


## Single-match cluster workflow 0.4 — October 28, 2026

Replaced the primary interface with Clusters → Match timeline → Explain cluster, implementing observed movement → reviewed category → recurrence → possible demands → general recovery context. It fits only Marcelo's Real Sociedad match, with both halves and all 290 usable independent observations. Automatic selection evaluates K=2–8 using silhouette; WCSS, Davies–Bouldin and cross-initialization ARI remain visible as supporting diagnostics. K=2 is selected (174/116 members; silhouette 0.2548). These are broad projected-posture groups, not validated activities.

Raw/prepared audit: 690 raw candidates → 403 independent candidates → 328 imported windows → 290 usable. Of independent candidates, 57 identity-withheld, 18 preparation-withheld and 38 quality/review-withheld rows account for the difference. The 287 overlapping sliding candidates are not counted as extra exposure. Usable movement totals 580 seconds; unobserved match time is unknown. Scoreboard spot checks at source seconds 10/600/1800 in both halves support approximate match-minute display (about ±2s), while exact source-half timestamps stay on clips and in exports. No new tracking or pose inference was run.

Validation:

- Full regression suite: **80 passed**. Eight cluster-specific tests cover match selection, automatic K, complete-member aggregates, nonoverlapping time accounting, representative selection, category gates, mixed-category evidence gaps, constrained citations, required read-only AI tools, image-input payload construction, stale category/K/membership/research rejection, portable export and the API flow. The AI test uses a mocked SDK; it is not a live multimodal result.
- TypeScript and Vite production build pass at version 0.4.0.
- Local Chromium checks load six model-selected preview frames, inspect synchronized video/player-scaled pose and scrubbing, paginate the complete cluster browser, enforce category review, display all 290 timeline intervals including both halves, inspect source clips from timeline marks, and verify the 690/403/328/290 audit display.
- The computed-brief path was exercised in the browser with Foundry availability disabled only for that browser's status response. It exported all 116 selected-group members, the exact saved local explanation, aggregate statistics, timeline and four typical/boundary videos. The extracted standalone HTML report decoded all four clips. Changing category clears the draft and downloaded-pack state.
- Widths 390/768/1440 passed without horizontal document overflow or browser JavaScript errors. Cluster, inspector, timeline, explanation and standalone report screenshots were reviewed.
- SHA-256 checks confirm all **15 pre-existing dataset/analysis records** are unchanged. Older analyses, reports, source arrays and the separate submitted Touchline app remain preserved.

The Foundry cluster adapter is implemented with required aggregate/examples/timeline/research retrieval, strict retrieved-ID citations, bounded image inputs and an explicit evidence gap for descriptive/mixed categories. The new path can send four three-frame JPEG strips, cluster aggregates and the curated primary research to the existing Foundry deployment. **The live call was not performed:** automatic approval review rejected transmission of private match-derived frames/evidence without explicit payload approval. Prior metadata-only/clip-level Foundry checks remain separate historical results. Do not claim live multimodal cluster verification. No new cloud report upload/download was performed.

Private evidence: `runtime/cluster-proof/browser-check.json`, `verification.json`, `computed-cluster.json`, screenshots, extracted standalone report and `cluster-evidence-pack.zip`; `runtime/prepared/cluster-match-audit.json` contains detailed row accounting. A live verification script is prepared privately but must not be run until the frame/evidence transmission is approved. All these runtime artifacts remain ignored by Git.


## Repository presentation review — October 28, 2026

Reviewed both public GitHub repositories and added the shared Touchline → dataset
ZIP → Movement Lens overview and exact handoff guide. The repositories remain
independent. Documentation explicitly distinguishes the different matches in the
older Touchline demo and the Movement Lens prepared example.

The existing runtime now contains real saved cluster-level Foundry results using
`movement-lens-mini`, four three-frame image strips and all four evidence tools.
The screenshot review checked one immutable result against its current evidence
signature, displayed that saved result in the actual UI, and exported it unchanged
with all 116 cluster members and four representative clips. No new cloud request
was made during this repository review. This supersedes the earlier approval-pending
status; it does not turn the mocked SDK test into a live evaluation or establish
clinical validity.

Both current suites pass: Movement Lens **80**, Touchline **57**. Both production
frontend builds pass. New CI workflows reproduce tests and builds on GitHub-hosted
runners without private datasets or cloud credentials; the hosted run remains
pending publication of the workflow files. Private screenshot/export proof is in
`runtime/repo-polish/capture-proof.json`.

The cleanup removes the editable video production folder from the next tracked
snapshot, preserves the local files, and adds selected screenshots and media
provenance under `docs/media/`. It does not rewrite previous public Git history.
App source, existing final videos, datasets and model outputs are preserved.

## V2 presentation assets — October 28, 2026

Created a separate 104-second, 1920×1080, 30 fps walkthrough and six 1920×1080
showcase PNGs. Fresh browser interaction covers cluster inspection, source/pose
playback, a timeline selection, the existing saved Foundry result, export and a
playing representative clip in the extracted standalone report. No application
code, tracking, pose inference or new cloud request was needed.

HyperFrames browser checks report no runtime, layout, contrast or audio errors.
Final lint reports zero errors and one composition-density warning. Secondary
metadata remains smaller than the recommended primary-text size; key captions
were enlarged. Source media durations are bounded and explicit final-frame holds
cover longer reading slots. The encoded render passes a complete FFmpeg decode;
sampled encoded frames and all six stills were visually reviewed. Still-image
layout checks found no clipped or overflowing text.

The demonstration retains the measured scope: 290 usable independent windows,
580 observed seconds, a selected cluster of 116 members, complete membership and
four representative clips in the export. The AI section displays a real saved
result bound to the current evidence and category. Touchline's schematic bridge
does not claim that the different demo matches are a recorded same-file transfer.
The original video and composition hashes remain unchanged. Private production
proof stays under ignored `brag-output/v2/`; selected public assets are in
`docs/media/`. Repository changes have not been committed or pushed.

## Final clean-install and security recheck — October 28, 2026

Created a clean temporary checkout from the published Git tree and an isolated
Python 3.11 environment. Declared test/Azure/Foundry extras install successfully;
`pip check` passes. The suite reports **79 passed, 1 skipped**: the skipped
optional source-preparation test requires OpenCV, which the analysis app does
not require. The existing prepared development environment previously passed all
80 tests. Locked `npm ci` and the TypeScript/Vite production build pass.

The clean first-run interface displays the request to import a verified Touchline
dataset, with no browser JavaScript errors. A canonical-origin browser proxy
forwarded this test to a separate temporary backend, leaving the existing app
untouched. An API exercise imported 24 controlled geometry fixture windows and
built a two-cluster workspace. The fixture is test geometry, not real football
data or a demonstration of biomechanical validity. No live AI request was made.

The README now includes clone commands, upgrades installer tooling and makes
the private demo-data boundary explicit. Dependency floors require a compatible
FastAPI and Starlette 1.3.1 or later. Final `pip-audit` and `npm audit` report
**zero known dependency vulnerabilities**. The local application package is
not covered by PyPI advisory lookup. These results do not replace code review
or establish that the application has no security defects.

Credential-pattern scanning covered all 102 historical Git blobs (77 text
blobs), with no matches for private keys, common API/access tokens, Azure storage
keys or SAS signatures. Current tracked files exclude runtime data, `.env`,
credentials, dependencies and editable video production files. Private proof
is kept outside Git. Both applications remain intended for local use; no public
server deployment or cloud credential exchange was part of this check.

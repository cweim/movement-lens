# Movement Lens: from match movement evidence to recovery support

> Historical plan: the current version 0.3 uses the [simple movement workflow](SIMPLE_PRODUCT_PLAN.md). Clinical forms, staff notes and recovery-plan entry are no longer part of the user interface.

Implementation update: 2026-10-27. Version 0.2 implements the movement catalogue, seed search, recurrence timelines, cross-match profiles, regional descriptor map, staff context, immutable reviews, portable review reports and optional Azure dataset/Foundry adapters. The complete local workflow was exercised with the source drive unplugged. The cloud adapters have mocked integration tests; live cloud resources are not configured/verified here. Clinical recovery estimation remains future research, not implemented medical inference.

The locally cached library currently supports 364 unique usable windows across seven sources/four matches, with 350 independent reference observations in the default scaling library. H1 first-half expansion completed before drive removal. H2 first-half and E02 expansion remain paused; the original frozen novelty analysis still contains 319 references and 14 query windows. No source reprocessing occurred during the offline feature build.

## Intended outcome and user

Primary user: a team physio working with a performance analyst. An analyst locates and checks recurring movement patterns within a match and across the player's matches. The physio combines the evidence with the athlete's symptoms, training exposure and assessments to decide what to check, how to monitor recovery, and which existing team recovery plan to use. Coaches can review a non-clinical movement summary and staff-approved availability notes.

Long-term objective: contribute validated player-specific evidence to recovery decisions and treatment review. The present Marcelo dataset can demonstrate movement discovery and comparison; it cannot train or validate a patient-specific muscle-recovery or treatment recommendation model because the required recovery outcomes and clinical context are missing.

Suggested product statement:

> Find recurring movement patterns across a player's matches, inspect the body regions and source clips involved, and build an evidence-backed recovery review for the team physio.

The inferential chain must be explicit:

`Visible movement → validated movement pattern → observed exposure → possible physiological relevance → measured athlete response → clinician's recovery decision`

The current app measures only the initial part. An LLM does not replace the missing measurements or validation later in the chain. Frequent movement may be routine sporting activity; frequency alone does not establish overload, damaged tissue or a need for a specific treatment.

## What the literature supports

| Primary study | Finding relevant to the idea | Limit for this project |
|---|---|---|
| Nedelec et al., 2014 | In ten professional players/four matches (14 observations), some match-action frequencies correlated with subsequent soreness or performance changes. Recovery was measured before and at 24/48/72 hours after matches. | Small observational sample; action associations do not validate our pose-based clusters or individual muscle-treatment predictions. |
| Varley et al., 2017 | Ten professional players were assessed around two matches; accelerations/decelerations and some sprint measures were associated with fatigue-related measures. | Used actual match-activity and follow-up measurements, not arbitrary similarity counts or unvalidated joint descriptors. |
| Tan et al., 2025 | Thirty-nine U19 outfield players were followed over two weeks. Neuromuscular performance declined, but individual-session acceleration/deceleration loads did not correlate significantly with the measured impairments. | Highlights that relationships depend on population, timescale, accumulated exposure and outcome; there is no universal count-to-recovery rule. |
| Uhlrich et al., OpenCap, 2023 | Video, calibrated 3D reconstruction and musculoskeletal simulation can estimate dynamic measures under validated conditions. | Those model/measurement assumptions differ from this single-view broadcast pipeline; physiological accuracy cannot be borrowed. |

Design consequence: recurring movement is useful evidence for a recovery review, and its relationship with recovery is a research hypothesis worth testing. Do not turn an observed pattern into a particular muscle's expected soreness, treatment, or recovery duration through generic LLM knowledge.

## Review workflow and future validation

`Import full available library → Inspect coverage → Discover/select a pattern → Locate recurrence within and across matches → Inspect regional evidence → Add recovery context → Draft physio review → Staff records decision and follow-up`

### 1. Dataset and coverage

- Finish the existing nonoverlapping candidates in H1/H2 first halves and E02; reuse H3 and the other reference halves. Preserve all quality/exclusion reasons and model/source signatures.
- Show one row per match/half with observed intervals, usable intervals and gaps. “Throughout the match” means navigating its timeline, not continuous observation of the player.
- Retain video-relative source timestamps. Add verified match-clock anchors before claiming an exact game minute; never confuse half-relative times or assume elapsed broadcast seconds equal scoreboard time.
- Label pattern counts/shares as within the available footage. Do not extrapolate selected broadcast visibility to full-match movement totals or workload. At present the 319 nonoverlapping reference windows represent about 10.6 minutes across three matches, not 270 minutes of continuous observations.
- Preserve player-identity review provenance separately from source binding and pose validity. “Usable” is technical eligibility, not certification of identity or movement normality.

### 2. Numerical movement representation

- Retain the audited 16 projected-2D descriptors as a transparent baseline.
- Add a small time-aware set only where it improves held-out retrieval: joint-angle change over real time, phase/direction of change, robust temporal variation and coarse ordered subsequences. Handle confidence, gaps and interpolation explicitly. Two-second windows can limit reliable cadence estimates.
- Keep temporal traces available beside the video. Camera normalization removes translation/scale but not viewing direction, depth or perspective; compare compatible examples and record obvious viewpoint differences.
- Version descriptors/scalers. Fit learned transforms on reference matches only for evaluation. A user's deliberate same-match exploration is a browsing mode, not a held-out performance result.

### 3. Discover, search and count recurrence

- Optional K-means discovery browser: show neutral group names, representative and diverse source clips, group size and descriptor summaries. Candidate k uses internal metrics plus initialization/resampling checks and expert-reviewed semantic usefulness; four activities are not presumed.
- Query-by-example search: a selected window is the seed; compute distance from its frozen scaled vector to every eligible candidate. A radius slider and top-k view expose the selection. This differs from the existing mean-ten-neighbor novelty score.
- Overlay matching intervals on each match/half timeline. Show matched windows, merged bouts and unique observed matching seconds. Distinct bouts are not automatically steps or repetitions of an exercise.
- Validate an initial similarity radius on independently reviewed similar/dissimilar clip pairs. When reporting retrieval performance, exclude self and adjacent/overlapping near-duplicates. In a recurrence-browsing mode, merge duplicates rather than count them twice.
- Cross-match comparisons show observed pattern mix and matched examples with denominators, quality and missing coverage. Match proportions may differ because of filming/selection, so pose-pattern changes do not automatically establish physiological or tactical change.

### 4. Interactive regional body map

- Start with joint regions supported by the current descriptors: knees, hips and trunk. Clicking a region filters the relevant traces, clips and descriptor differences.
- Color may encode a clearly named measured quantity, such as normalized descriptor difference or contribution to the specified squared-distance calculation. It must not silently encode muscle strain, pain, activation or injury risk.
- A separate anatomy/research panel explains general functional context, with sources and applicability notes. Current 17-point pose data has no direct muscle observation, foot/toe anatomy or force measurements.
- If an athlete reports soreness, show a separate, explicitly athlete-reported layer with its timestamp. Never present a reported symptom as a video-derived estimate. This is an anatomy illustration, not body-composition analysis.

### 5. Physio context and recovery follow-up

For a later clinician-partnered pilot, collect the smallest useful longitudinal set, agreed with the physio:

- Match/training minutes, dates and relevant recent exposures; validated GPS/IMU measures where available.
- Session perceived exertion, reported recovery/wellness and region-specific soreness with collection times.
- Relevant clinician-entered history and current restrictions, distinguished from automatically derived data.
- Team-selected follow-up assessments and clinician decisions, with outcomes across the chosen recovery period.

The interface should identify what is missing. With movement footage only, produce a movement-evidence brief. With reported symptoms, show their co-occurrence in time. Only after prospective validation should an estimated recovery endpoint be displayed, with its endpoint, time horizon, uncertainty and applicable population.

### 6. Microsoft Foundry evidence assistant

Reuse the existing optional Foundry adapter and verify a real deployment/model call before claiming live integration. At the last live status check it was not configured. Current local explanation is deterministic; existing Foundry tests are mocked.

Extend the evidence tools only as needed for the proposed workflow:

- `find_similar_windows(seed, sources, radius)`
- `get_pattern_timeline(...)` and deterministic recurrence/coverage aggregation
- `compare_matches(...)` with explicit observed denominators
- `get_region_evidence(...)` with source clips and descriptor semantics
- `get_recovery_context(...)` for clinician/athlete-provided data, when present
- `retrieve_research(...)` against a small curated evidence collection

The model can select tools and explain results. Every player-specific observation must cite actual clip/context IDs. Research claims cite retrieved passages and distinguish the population/setup from this dataset. Exact quantities remain computed and rendered by the application. Existing episode tools (`get_coverage`, `get_episode`, `get_comparisons`) remain available. Movement tools for timelines, profiles, regional evidence, staff context and curated research are implemented as fixed-scope read-only operations.

Structure the draft into measured observations, reported athlete context, relevant general evidence, missing evidence and questions for staff review. If an approved team protocol is available, the assistant may retrieve and summarize that version for clinician review. It must not invent a bespoke recovery/treatment prescription from a similarity count. Clinician selections and subsequent outcomes are separately recorded.

Azure Blob Storage can preserve the dataset, report and staff-reviewed snapshot. Foundry contributes evidence retrieval and explanation. Neither is itself a biomechanics model. Cloud integration is useful when it helps staff inspect or share the evidence, rather than adding another unsupported medical score.

The implemented cloud dataset handoff is **Touchline → private Azure Blob dataset snapshot → Movement Lens import**. Touchline saves immutable dataset ZIPs under `touchline/<job>/<sha256>/dataset.zip`. Movement Lens can list those snapshots, pin their ETag, bound the download and verify its exact checksum before using the standard quality/provenance importer. The source container and report destination are separately configurable. The adapter is tested with mocked storage; a live account handoff remains unverified. [Microsoft's Blob download documentation](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-blob-download-python) supports authenticated download using the existing Azure client libraries.

### 7. Staff-reviewed report

Include source/player/half identities, observed coverage, pattern definition/version, recurrence timelines, representative comparison clips, regional measurements, reported symptoms if supplied, cited research context, limitations, clinician notes/decision and follow-up fields. Keep measured, reported, model-estimated and clinician-authored information visibly distinct.

## Delivery stages and acceptance

| Stage | Deliverable | Required proof |
|---|---|---|
| A: usable match review | Expanded library, seed search, recurrence timelines and clip selection | Audited source/identity samples; validated timeline merge/count behavior; relevance among top-five cross-match retrievals; timing compared with manual clip browsing. |
| B: explainable physio brief | Regional map, curated research, live Foundry tool/citation workflow and portable report | Regional metrics trace to code/clip evidence; factual/citation checks; handles poor coverage and missing clinical data; staff can correct/approve a draft. |
| C: longitudinal pilot | Athlete context and recovery follow-up in partnership with a physio | Predefined outcomes and times, consistent collection, agreement with measured assessments, clinician usefulness and documented missingness. No recovery prediction claim from retrospective pose data alone. |
| D: validated recovery support | Estimate a specified recovery outcome only if evidence supports it | Athlete-separated and forward-time evaluation, appropriate calibration/error reporting, comparison against simple baseline models, external/prospective validation and clinician review of utility. |

No sample-size number is asserted here. A study/power plan needs the partner, target endpoint, variability and collection design. Similarity to historical clips is not a validated substitute for a recovery outcome.

The current software delivers A and a focused B. Human retrieval-relevance evaluation, clinical utility measurement and live cloud verification remain outstanding. The pitch can state the longer-term goal of supporting recovery planning while demonstrating the evidence brief that actually exists. Coaching/physio benefit should be measured as improved access to relevant evidence and less time preparing a review, not injury prevention or treatment efficacy without a study.

## Sources

- [Nedelec et al.: The influence of soccer playing actions on recovery kinetics](https://pubmed.ncbi.nlm.nih.gov/24172722/).
- [Varley et al.: Match activity, fatigue and neuromuscular performance](https://pubmed.ncbi.nlm.nih.gov/29339989/).
- [Tan et al.: Weekly acceleration/deceleration loads and neuromuscular performance](https://pmc.ncbi.nlm.nih.gov/articles/PMC12590203/).
- [Uhlrich et al.: OpenCap](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1011462).
- [Baumgartner and Klatt: 3D pose from sports broadcasts with field registration](https://arxiv.org/abs/2304.04437).
- [Baldinger et al.: Camera-view effects on OpenPose angle validity](https://pmc.ncbi.nlm.nih.gov/articles/PMC11819822/).
- [Microsoft Foundry function calling](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/function-calling).

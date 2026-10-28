# Movement Lens 0.4: one match, cluster-level movement interpretation

Status: implemented October 28, 2026. Local browser/export checks pass; the new multimodal cluster Foundry check awaits explicit approval for private frame/evidence transmission. Earlier metadata-only AI verification is a separate result.

## Agreed scope

Use Marcelo in Real Madrid versus Real Sociedad on December 30, 2015, with both source halves. Analyse all eligible observed movement from that match, discover numerical groups, review each group as a whole, locate those groups on the match timeline, then explain possible physical demands and research-backed general recovery context at the group level.

The exact reasoning chain is:

Observed movement → reviewed movement category → recurrence timeline → possible physical demands → research-backed general recovery context.

Clip playback supports inspection of a group. A single clip and its nearest neighbour are no longer the main object of analysis. No cross-match comparison, similarity-radius controls, clinical notes, symptom intake or treatment-plan form is part of this version.

## Data preparation and what full-match means

Both source files already exist. The first is 2,749 seconds and the second 2,700 seconds. This is a complete-match source scope; it does not mean the broadcast continuously observes Marcelo.

Existing imports contain 130 first-half and 198 second-half windows, with 116 and 174 passing the current pose/source/review gates. The independent usable analysis sample is therefore 290 two-second windows and 580 seconds (9m40s) of observed movement. Upstream manifests contain 230 + 460 = 690 raw windows, including sliding overlaps and rows outside the prepared usable sample.

The audit is complete. The 690 raw rows contain 287 sliding-overlap candidates outside the independent sampling policy. Of 403 independent candidates, 57 were withheld for identity concerns, 18 had no prepared result, 38 prepared imports fail current quality/review gates, and 290 are usable. All independent outcomes are accounted for; no further pose processing is needed for this declared sample. Original files and immutable snapshots are preserved. No demo cap is applied.

Use independent eligible observations for fitting and duration/count summaries so sliding overlaps do not become extra exposure. All eligible overlapping windows may additionally be assigned and browsed, but their total cannot be represented as independent events or extra observed seconds. The UI and export must distinguish raw windows, eligible windows, independent analysis windows and merged source intervals. Unobserved footage remains unknown.

## Clustering and suggested K

Fit only this match, rather than the current 540-window multi-match library. Reuse the current 16 projected-pose descriptors and robust scaling; remove constant dimensions. Evaluate K=2–8 with multiple initializations. Use silhouette as the primary stated selection criterion. Show WCSS/elbow, Davies–Bouldin, cluster sizes and initialization agreement in a collapsed method explanation as supporting diagnostics, without inventing an opaque combined score.

Check if a proposed solution is dominated by tiny groups, pose artifacts, a single source half or camera/viewpoint characteristics. A stable partition is not proof of distinct football actions. If grouping is weak, explicitly describe broad groups or mixed groups. Do not force four activity labels or cherry-pick data to make a prettier result. The chosen K is a suggested partition under the stated criterion, not a proven natural count of movement types.

The implemented single-match fit on all 290 usable independent windows finds:

| K | Silhouette | Davies–Bouldin | Sizes | Initialization ARI |
|---|---:|---:|---|---:|
| 2 | 0.2548 | 1.6348 | 174, 116 | 1.0000 |
| 3 | 0.1897 | 1.8727 | 125, 120, 45 | 0.9713 |
| 4 | 0.2084 | 1.6578 | 122, 23, 55, 90 | 0.9738 |

At K=2 the straighter-leg group includes 72 first-half and 102 second-half windows; the more-bent/variable group includes 44 first-half and 72 second-half windows. Thus this particular partition does not simply split the halves. Additional eligible raw windows may change these results. The modest silhouette does not establish activity-recognition accuracy. The activated workspace and verification artifacts are private under `runtime/cluster_workspaces/` and `runtime/cluster-proof/`. The original planning calculation remains under `runtime/cluster-plan/`.

## Three screens implementing the five-step reasoning chain

### 1. Discover and review clusters

A compact match header states the player, match, both halves, usable observed time and independent window count. A suggested-K badge replaces a tuning dashboard. Each cluster card shows its size, observed duration and three typical example clips from different tracklets, selected by distance to the group centre. Avoid hand-picking only flattering examples. Include a less-typical/boundary example inside the cluster view to show its variation.

Opening a cluster shows playable representative videos with pose, the entire paginated cluster gallery, and the main aggregate differences versus other clusters. A proposed label remains a description until the user confirms it after inspection. Confirmation is one action, not a clinical form. Permit a mixed/uncertain category. Numerical cluster IDs and tentative labels must not be confused with validated activity classes.

### 2. Where this cluster occurs

One match-wide chart has a row for each cluster, using a consistent colour everywhere. Each observed eligible independent window appears at its source interval. Clicking an interval opens the actual clip. Selecting a cluster highlights its row, while the rest remain as context.

For this local match, scoreboard checks at source seconds 10, 600 and 1800 in both halves support approximate source-to-match offsets of zero and 2700 seconds, with about two seconds of uncertainty. The chart marks half-time and labels its match-minute positions approximate; source-half timestamps remain exact. No available usable independent window extends past the displayed half boundary. This is not a continuous ninety-minute tracking stream. Unverified imported sources retain an unverified-source-half clock basis; do not treat their approximate positions as official timestamps.

Show independent window count, merged observed duration and share of usable observed footage. A five-minute-bin summary may show distribution within observed footage, with its coverage denominator. Grey/blank areas are unknown, not inactivity. Windows or merged intervals are not steps, repetitions, sprint counts or measured workload.

### 3. Explain this cluster

The AI output has three visibly separated blocks:

1. **Observed pattern:** aggregate posture/variation, the reviewed category, representative evidence, how homogeneous or mixed the group is, and its observed distribution in the match.
2. **Possible physical demands:** conditional general interpretation tied to the reviewed movement category and supporting sources. Do not derive muscle force, activation, damaged tissue, fatigue or injury probability from image-plane descriptors or cluster frequency. If the category is too broad or mixed, explain that movement-specific demand cannot be assigned confidently.
3. **General recovery context:** relevant research findings and general post-match recovery considerations, with citations, study population and limitations. Distinguish general evidence from demonstrated needs of this player. No individualized treatment, recovery duration or invented diagnosis is generated.

The category review and aggregate facts must come before the demand/recovery explanation. A confirmed descriptive category is still a human interpretation, not new validation of the detector. More observed windows alone do not establish excessive exposure.

## What Microsoft AI receives

Create a frozen cluster evidence bundle containing:

- Cluster ID, membership, fit/model version and reviewed label/status.
- Independent and eligible window counts, merged seconds and usable-coverage denominator.
- First/second-half distribution and verified source/match-time intervals.
- Median, IQR and relevant ranges of the 16 features across the cluster, and differences from the other groups.
- Representative examples from different tracklets, a boundary example and pose/identity quality summaries.
- Up to four JPEG strips with three sampled frames each, associated with example IDs and relative clip times. Full videos are not transmitted. Without images, the AI receives metadata and must not claim visual inspection. Frame preparation is local; live multimodal inference verification is pending approval.
- Retrieved primary research summaries with study type, population, measured activity/exposure, recovery outcomes, applicability and limitations.

The source-backed aggregate describes all included cluster windows; representative examples are a bounded illustration, not the whole evidence base. Do not send only a centroid, a single clip or an unbounded video library. Keep exact numerical results deterministic and citations traceable. Require the aggregate and research tools before generating physical-demand or recovery sections. Missing or unsuitable research should produce an explicit evidence gap rather than fabricated guidance.

Research that relates measured football activity to subsequent recovery motivates the interpretation layer, but does not validate our clusters. Relevant starting points include:

- Nedelec et al.: https://pubmed.ncbi.nlm.nih.gov/24172722/ — playing actions and measured recovery outcomes.
- Varley et al.: https://pubmed.ncbi.nlm.nih.gov/29339989/ — match activity and subsequent fatigue/neuromuscular measures.
- Ascensão et al.: https://pubmed.ncbi.nlm.nih.gov/21170794/ — a small randomized post-match recovery-intervention study, not a cluster-specific treatment rule.
- Silhouette guidance: https://scikit-learn.org/stable/auto_examples/cluster/plot_kmeans_silhouette_analysis.html

The implemented research library also includes Kinugasa et al. (https://pubmed.ncbi.nlm.nih.gov/19620926/), a youth-football comparison of post-match recovery modalities with outcome-dependent findings. Study summaries include design, population, findings and limitations. There is no cluster-to-treatment lookup table or medical-notes collection.

## Export and cache correctness

Export the selected cluster's summary, complete member list, representatives, timeline, aggregate measurements, reviewed label and cited AI explanation, plus dataset/model/research provenance. Include representative clips rather than automatically including every video in a potentially large cluster pack; provide the complete member CSV/JSON.

An explanation is bound to the match snapshot, selected K/model, exact cluster membership, reviewed category and research version. Changing any of these invalidates that explanation. Reuse the existing immutable artifact, report, Microsoft authentication and storage boundaries. Previously generated clip-level reviews remain preserved.

## Implementation sequence and verification status

1. Audit the single-match raw/prepared/usable data; prepare missing eligible candidates only if needed. Confirm time alignment and sampling policy.
2. Fit single-match candidate K values, record the selection rule, and build cluster aggregates and representative/boundary selection.
3. Replace the current clip-query interface with cluster review and a whole-match coloured timeline.
4. Add the reviewed-category step and grounded aggregate-demand/recovery AI output, with a curated primary evidence library.
5. Export the same frozen cluster explanation and verify the full three-screen/five-stage flow.

Implemented: single-match audit, automatic K diagnostics, complete aggregates, centre-nearest and boundary examples, full member browser, category review gate, both-half clickable timeline, bounded cluster/research AI tools, deterministic evidence-gap behavior, frozen cluster export and existing Azure storage controls. Eight new regression tests join the existing suite, for 80 passing tests. Local browser verification covers representative playback/pose, member pagination, coverage accounting, computed explanation/export, four playable standalone-report clips, category-change invalidation and unchanged hashes for 15 existing dataset/analysis records. Model/K/membership/research invalidation and AI evidence boundaries are tested with controlled fixtures. The new live multimodal Foundry call remains unverified because automatic approval review requires explicit approval to transmit private match-derived frames and evidence. Do not present the mocked test or older clip-level AI verification as that live check. See `docs/VERIFICATION.md`.

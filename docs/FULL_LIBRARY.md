# Expand the local research library

This developer helper is for the existing local Marcelo workspace. It needs the attached drive, current Touchline window caches, the existing `models/yolov8x-pose.pt`, OpenCV, Ultralytics and ffmpeg. It downloads nothing and never opens Touchline's database. The current `python3` environment has these dependencies.

From the parent project directory:

```bash
cd /Users/chinweiming/Desktop/player-movement-anamoly-detection
python3 movement-lens/scripts/expand_local_library.py
```

The default is a read-only plan. To process, import and activate the expanded datasets, keeping the Mac awake:

```bash
caffeinate -i python3 -u movement-lens/scripts/expand_local_library.py --run
```

Keep the drive connected. `Ctrl+C` stops the job; run the same command to resume. The current window may be repeated if interrupted before its checkpoint was committed. CPU is intentional: the installed pose package warns about Apple MPS pose inference. Run one expansion at a time; the script enforces a process lock.

## What “full” means

All currently available **greedy nonoverlapping two-second candidates per tracklet**, with no demo sampling cap. Quality gates and known review exclusions remain. This does not recover player movement when it was never tracked, was off camera or was occluded. Sliding windows that overlap are a separate sampling choice; the script reports their raw count alongside the selected count.

| Half | Cached windows | Candidate selection | Previously prepared selected IDs | Additional candidates |
|---|---:|---:|---:|---:|
| H1 first | 83 | 52 | 15 | 37 |
| H2 first | 230 | 140 | 16 | 124 |
| E02 second, query | 187 | 103 | 12 | 91 |
| Total | 500 | 295 | 43 | 252 |

Two of the current E02 demo windows are outside this greedy nonoverlapping selection. The new snapshot follows the declared selection. The original demo dataset and analysis remain available unchanged.

H1/H2 second halves and both H3 halves are already expanded under this selection policy. The script verifies that their prior preparation checkpoints account for their candidates and that their imported windows match the prepared outcomes, then preserves their current snapshots. It does not rerun inference on those four halves.

Budget approximately **30–45 minutes of preparation computation, 45–75 minutes overall** on the current machine; actual time varies with source decoding, model performance and encoding. This is based on observed previous runs, not a fresh timing benchmark. Candidate count is not guaranteed usable count. No long inference run was performed while creating this helper.

## Outputs and preservation

Outputs are private and ignored by Git, under `movement-lens/runtime/full-library-expansion/`:

- `previous-active-demo.json`: original active pointer for rollback.
- Per-job/model/preparer/input-signature directories containing checkpoint JSON, validated NPZ, MP4 and retained ZIP snapshots.
- `progress.json`: current progress, also printed in Terminal.
- `completed-subsets.json`: completed import summaries; retained even if a later subset fails.
- `summary.json`: final counts, verification result and the exact new analysis URL.

Sources are SHA-256 checked before use. Verified matching poses are reused; missing candidates are recomputed from the exact source. Resume checks completed artifact hashes. Clips must decode as 50 frames at 25 FPS. Imports run through the application's normal schema/quality checks. Existing review flags and provenance are retained. Newly processed poses do **not** acquire a human-reviewed identity label automatically. Source binding is not player-identity certification.

New references are additionally screened for overlapping eligible observations across tracklets in the same source half. Excluded rows remain inspectable. Their flag does not change the original dataset. This automatic preparation does not perform a new exhaustive visual identity review; review uncertain clips before using them as evidence in clinical decisions.

Only after all three expanded imports and the new analysis succeed does the script update `runtime/prepared/active-demo.json`. Old dataset and analysis records are hash-checked for preservation. A failure keeps the previous active pointer and completed checkpoints. Partial imported snapshots may be visible in the library, but the active analysis does not change partially.

Open the exact URL printed at completion. Existing browser tabs retain their old analysis; refreshing one does not necessarily select the new analysis. The app can remain running at port 8770 while preparation occurs.

To roll back the active pointer (original immutable datasets/analyses are retained):

```bash
cp movement-lens/runtime/full-library-expansion/previous-active-demo.json movement-lens/runtime/prepared/active-demo.json
```

Then open the old analysis ID from that JSON in the app URL. Rollback changes the pointer, not the generated artifacts.

## Completed local expansion — October 27, 2026

The completed run imported and activated all three expanded snapshots. H1/H2 second halves and both H3 halves were retained after their candidate accounting checks. The refreshed explorer uses seven snapshots across four matches, with **540 unique usable windows** and **451 independent reference observations**. E02 contributes **89 usable query windows**.

| Source | First-half usable | Second-half usable | Role |
|---|---:|---:|---|
| H1 | 45 | 77 | Reference |
| H2 | 116 | 174 | Reference |
| H3 | 12 | 27 | Reference |
| E02 | — | 89 | Query |

There is no demo sampling cap. These counts still reflect the declared nonoverlapping candidate selection and quality/review gates; they do not imply continuous whole-match coverage. Old snapshots and analyses remain available. New query ID selection is necessary to leave a browser tab that remembers the earlier demo. The exact current analysis/explorer URLs and catalogue ID are stored in `runtime/prepared/active-demo.json` and `runtime/full-library-expansion/activation-verification.json`.

Verification checked all 295 expanded candidate checkpoints and the SHA-256 hashes of all 548 prepared NPZ/MP4 artifacts, rebuilt the reference-fitted catalogue, and exercised similarity, cross-match filtering and regional comparisons.

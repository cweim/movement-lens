# Publishing Movement Lens

Publish this standalone folder, separately from Touchline and the parent research
workspace. The [handoff guide](HANDOFF.md) explains the connection without coupling
the repositories or shipping private data.

## Public file boundary

Keep source, tests, dependency manifests, `.env.example`, docs, the shared SVG and
selected `docs/media/` screenshots. Runtime records, datasets, source footage,
weights, credentials, dependencies and compiled output remain ignored.

The editable `brag-output/` production workspace is local. Some production files
were present in the initial public commit; the presentation cleanup removes them
from the next tracked snapshot and preserves the local copies. It does not rewrite
the existing Git history. Do not force-add ignored media or runtime folders.

The application code has no project-wide license selected. Third-party notices
are documented separately; choose a license deliberately before advertising the
repository as licensed open source.

## GitHub About fields

Use the repository's **About → Edit** panel:

- **Description:** Explore a player's observed movement patterns from Touchline pose windows: reviewed clusters, match timelines and Microsoft Foundry explanations with evidence exports.
- **Topics:** `football`, `sports-analytics`, `movement-analysis`, `pose-estimation`, `kmeans-clustering`, `microsoft-foundry`, `azure-blob-storage`, `fastapi`, `react`.
- **Website:** add a real hosted demo or accepted public demo-video URL when available. The local app address is not a public website.

The corresponding Touchline fields are in its
[publishing notes](https://github.com/cweim/touchline/blob/main/docs/PUBLISHING.md).

## Review before pushing

```bash
git status --short
git diff --stat
git diff --cached --stat
git ls-files --cached --others --exclude-standard
```

Review the exact staged list, including removed production assets. Commit the
documentation/media cleanup and push to the existing `origin/main`. Original
production files remain available locally.

## Selected demo and gallery

V2 is the selected **1:44, 1080p** demo at
[`media/movement-lens-demo.mp4`](media/movement-lens-demo.mp4), with its poster and
README link prepared. It replaces the earlier video's presentation copy with
observed recurrence, source/pose review side by side, research limits and the
actual evidence-pack contents. The original 110-second render remains unchanged
in the ignored local production folder; the app is unchanged.

The Touchline Windows export → dataset ZIP → Movement Lens beat is explicitly a
format/workflow connection. The older Touchline footage uses another match.
The AI section displays a saved real result for this exact cluster and category.
No new model request or Azure report upload was made for this video.

The [six numbered showcase PNGs](media/showcase/README.md) are ready for the
hackathon gallery; [captions and alt text](media/showcase/upload-captions.md) are
included. Music and production credits are in [media notes](media/CREDITS.md).
Keep editable compositions and source recordings excluded.

Upload the final MP4 to a supported public video host and use that URL on the
hackathon page. The GitHub MP4 link is a repository preview, not that hosted URL.


## Push this presentation update

From the `movement-lens` repository root:

```bash
git add README.md docs .github .gitignore THIRD_PARTY_NOTICES.md
git diff --cached --stat
git commit -m "docs: connect Touchline and Movement Lens with a visual handoff"
git push origin main
```

The already-staged removals of `brag-output/` are included in the commit. Those
files remain on disk and are now ignored.

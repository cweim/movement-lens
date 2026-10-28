# Hyperframes Composition Brief: Movement Lens

## Objective
Create a short polished brag video for Movement Lens — a football movement analysis tool that clusters player movements from broadcast footage, maps them across a match, then calls Microsoft AI to explain patterns with cited research.

## Output
- Composition directory: `brag-output/composition/`
- Rendered video: `brag-output/brag.mp4`
- Format: landscape — 1920x1080
- Duration: 20 seconds

## Source Material
- Project root: `movement-lens/`
- Primary files read: `frontend/src/App.tsx`, `frontend/src/style.css`, `frontend/src/cluster.css`, `frontend/index.html`, `README.md`
- Product name: Movement Lens
- Tagline: "Observed patterns. Reviewed categories. Research-backed context."
- Key UI or visual moment to recreate: the cluster inspection panel — side-by-side crop video with skeleton overlay + category review, plus the AI explanation with three numbered sections and citation pills
- Copy that must appear verbatim:
  - "290 windows. One player."
  - "Every movement pattern."
  - "Explain with Microsoft AI"
  - "Movement Lens"
  - "Observed patterns. Reviewed categories. Research-backed context."
  - "Built for the Microsoft Premier League Hackathon"

## Creative Direction
- Tone preset: polished
- Creative direction: serious sports-science product film
- Interpretation: Measured confidence, restrained motion. Let the real data and real UI speak. No hyperbole. The impressiveness is the evidence chain from broadcast footage to AI-backed physiotherapy insight.
- Angle: This is real sports science powered by AI. Not a mockup. One match, one player (Marcelo, Real Madrid vs Real Sociedad), 290 observed windows of actual movement — clustered, reviewed, explained, and exported.
- Hook: Marcelo skeleton overlay + "290 windows. One player. Every movement pattern."
- Outro: Movement Lens wordmark + tagline + "Built for the Microsoft Premier League Hackathon"
- Avoid:
  - Generic SaaS language
  - Abstract filler visuals
  - Unrelated visual redesign
  - Flashy or aggressive transitions

## Visual Identity
- Background: #f5f6f1 (warm off-white)
- Accent: #205d45 (deep forest green)
- Text: #203b30 (dark green-black)
- Secondary green: #174e3e
- Card background: white with subtle shadow
- Display font: Inter (600/700 weight)
- Body font: Inter (400 weight)
- Visual references from the project: cluster cards with color dots and stats, skeleton overlay on video crop, match timeline SVG with colored marks, AI output sections with numbered headers and green citation pills, evidence pack download

## Storyboard
Use the storyboard in `brag-output/brag-plan.md` as the creative contract.

Scene summary:
1. Hook — 3s — Skeleton overlay on broadcast crop, "290 windows. One player." slam, "Every movement pattern." beneath
2. Clusters — 5s — Two cluster cards arrive one by one with stats, then inspection panel opens (crop video + skeleton + category review)
3. Timeline — 4s — Match timeline SVG with colored marks cascading left-to-right across 90 minutes, stats below
4. Microsoft AI Explain — 5s — Button press → loading → AI output: summary badge, three numbered sections (01 Observed, 02 Physical demands, 03 Recovery context) with green citation pills
5. Export & Outro — 3s — "Cluster evidence pack ready" + Download ZIP, crossfade to Movement Lens wordmark with tagline

## Audio
- Audio role: warm professional bed — confidence without flash
- Audio arc: enters with hook, builds through cluster/timeline reveals, peaks during AI explanation cascade, resolves at export
- Music: `happy-beats-business-moves-vol-11-by-ende-dot-app.mp3` (115 BPM, warm and business-y)
- Music treatment: fade in from 0s at 0.35 volume, steady, gentle fade out last 2s
- Music cue guidance: bundled preset at `assets/music/cues/happy-beats-business-moves-vol-11-by-ende-dot-app.music-cues.json`. Strong cues at 1.60s, 3.70s, 5.80s, 8.96s, 12.65s. Beat grid ~0.52s spacing.
- Audio-reactive treatment: subtle; sage green glow on UI panels breathes slightly with RMS
- Audio-coupled moments:
  - Scene 1 hook text slam — lands on 1.60s strong cue
  - Scene 2 cluster card arrivals — land on 3.70s and 4.23s beats
  - Scene 4 AI sections appearing — land on beats near 8.96s
- SFX selection guidance: polished tone = 2-3 very subtle SFX. `interface/bong_001.ogg` for soft accent. `interface/drop_001.ogg` for gentle reveal. Nothing aggressive. See `sfx-analysis.md` for safer picks.
- SFX analysis guidance: `/Users/chinweiming/.claude/skills/brag/assets/sfx/sfx-analysis.md`
- Exact SFX choice: Hyperframes should choose filenames, timestamps, density, and volume based on the implemented animation.
- Audio files: copy the chosen music and any Hyperframes-selected SFX into `brag-output/composition/assets/`

## Hyperframes Instructions
Load the composition-building Hyperframes domain skills — `hyperframes-core` (composition contract + `data-*` timing), `hyperframes-animation` (motion), `hyperframes-creative` (design spec, beats, audio-reactive), `hyperframes-keyframes` (seek-safe keyframes), and `hyperframes-cli` (lint/check/render). /brag is its own workflow: do not enter the `hyperframes` entry-point intent interview and do not route into its generic promo / launch-video workflow. Prefer native Hyperframes conventions over anything in `/brag`.

Requirements:
- Show at least one real UI, copy, or visual element from the source project.
- Keep all text readable in the final render.
- Keep the video within 15-25 seconds.
- Include the planned music/SFX layer.
- Treat `/brag` audio notes as guidance, not a fixed cue sheet. Choose SFX after the visual animation exists.
- Treat music cue metadata as optional timing hints. Hyperframes decides exact animation timing and should ignore cues that hurt readability, scene pacing, or the product story.
- Major reveals may move toward nearby strong cues within about 0.15s. Smaller entrances may align to nearby beat points within about 0.10s. Use only 1-3 strong cue locks in a 15-25s video unless the edit clearly benefits from more.
- Use SFX to support motion and interaction: card sounds for card-like reveals, short announcement cues for major payoffs, key/click sounds for text or user actions, and restraint when the edit is already busy.
- Honor planned music treatment such as fade-outs, ducking, beat-aligned reveals, or letting a final SFX ring over the music.
- When music is present, consider Hyperframes audio-reactive workflow: extract audio data and use RMS/frequency bands for subtle motion. Good targets: glow on UI panels, card presence on bass. Avoid waveform/equalizer visuals, strobing, heavy pulsing.
- Use local assets for audio.
- Run `hyperframes check` before render — it is brag's single gate.

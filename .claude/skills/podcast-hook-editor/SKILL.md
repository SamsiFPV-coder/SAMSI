---
name: podcast-hook-editor
description: Research current trends and hook angles for a podcast topic, then edit an audio-only podcast around them — transcribe, find the strongest hook moments, build a cold open, cut fillers/dead air/off-topic detours, polish the sound to -16 LUFS and export the episode plus short audio clips. Use when the user wants to edit, clean up, tighten or "make more engaging" a podcast/audio recording, find hooks or a cold open, cut highlight clips, or edit an episode based on what's trending.
---

# Podcast Hook Editor (audio only)

Turns a raw podcast recording into a hook-first, trend-aware episode:

```
 1. Trend research  ──►  trends_brief.md + keywords.txt
 2. Transcribe      ──►  transcript.json (word timestamps)
 3. Clean plan      ──►  cuts.json (fillers, stutters, dead air)
 4. Hook scan       ──►  hooks.json (ranked candidates, trend-weighted)
 5. Editorial pass  ──►  edit_plan.json  (YOU decide: cold open, cuts, order, clips)
 6. Render          ──►  final.mp3 + timeline.json + clips/*.mp3
 7. Verify          ──►  loudness, duration, splice spot-checks, report
```

Steps 1 and 5 are judgment work done by you (Claude). Steps 2–4 and 6–7 are scripts in `scripts/`.
Everything runs locally with `ffmpeg` + Python 3. No video is touched — audio in, audio out.

## Prerequisites

- `ffmpeg` / `ffprobe` on PATH (check: `ffmpeg -version`)
- Python 3.9+; `numpy` (optional, enables energy scoring in the hook scan)
- A transcription backend, either:
  - local: `pip install faster-whisper` (CPU works; `small` model ≈ real-time/3 on a laptop), or
  - API: `OPENAI_API_KEY` set → uses `whisper-1` with word timestamps
- Web search tools (for trend research). If the `last30days` skill (github.com/mvanhorn/last30days-skill) is installed, prefer it for social-signal research.

Script paths below are relative to this skill's folder. Work in a per-episode folder, e.g. `work/ep012/`, and never overwrite the user's original file.

---

## Step 1 — Trend & hook research

Goal: know what the target audience is talking about *right now*, so the hooks and the cold open speak to it.

1. Ask (once, only if unknown): podcast niche/topic of this episode, target audience, language/market (e.g. Polish vs English audience), where clips will be posted (Spotify, YouTube audio, TikTok/Reels audiograms, LinkedIn).
2. Research — run several searches, separately per angle (see `references/trend-research.md` for the query playbook):
   - recent news / debates in the episode's topic (last 30 days)
   - Reddit / X / YouTube / TikTok discussion: questions people keep asking, hot takes, controversies
   - top podcast episodes and YouTube titles in the niche: which titles/hooks are performing
   - search-demand signals (Google Trends, "people also ask")
3. Write `trends_brief.md` using the template in `references/trend-research.md`: top 5–10 trends, the exact phrasing audiences use, open questions, contrarian angles, and 5–10 hook *angles* this episode could own. Cite sources.
4. Write `keywords.txt`: one term/phrase per line (trend terms, entity names, audience phrasing, both languages if bilingual). The hook scan weights these.

## Step 2 — Transcribe

```bash
python3 scripts/transcribe.py INPUT.m4a --out work/ep012/transcript.json --language pl   # or en, or omit to auto-detect
#   --backend faster-whisper|openai   --model small|medium|large-v3
```

Outputs `transcript.json` (segments + word timestamps) and `transcript.txt` (`[MM:SS] text` lines — read this one; it's compact).
The script prompts Whisper to keep fillers ("um", "yyy", "eee"), which Whisper normally drops — without that, filler cutting can't see them.

**Name check:** Whisper mangles names and brands. Skim `transcript.txt`, list proper nouns, and confirm unclear ones with the user before they go into titles or show notes.

## Step 3 — Clean plan (mechanical cuts)

```bash
python3 scripts/clean_plan.py work/ep012/transcript.json --out work/ep012/cuts.json
#   --max-pause 1.2 --target-pause 0.45 --lang pl,en  [--aggressive]
```

Finds: hard fillers (um/uh/yyy/eee…), stutters/immediate word repeats, and dead air (pauses longer than `--max-pause` get shortened to `--target-pause`, not removed).
"Soft fillers" (like, you know, no, znaczy, jakby, w sumie…) are only **flagged** in `review` — they're often meaningful. Cut them only if the user wants an aggressive edit.

Never cut so tightly that breaths vanish entirely — natural rhythm matters more than seconds saved. A typical clean pass saves 5–12% of runtime.

## Step 4 — Hook scan

```bash
python3 scripts/hook_candidates.py work/ep012/transcript.json \
   --audio INPUT.m4a --keywords work/ep012/keywords.txt --top 15 --out work/ep012/hooks.json
```

Scores 10–40 s windows on: trend-keyword hits, curiosity triggers (questions, "the truth is", "nobody tells you", "ale tak naprawdę"), concrete numbers, contrast/conflict, story openers, strong opinions, vocal energy and pace, and low filler density. Output is a ranked shortlist with the feature breakdown and text.

The score is a **shortlist, not the answer**. Read the top candidates in context (`transcript.txt` around them) and judge them yourself with `references/hooks.md`.

## Step 5 — Editorial pass (you)

Build `edit_plan.json`. Decide, using the trends brief + hook shortlist:

1. **Cold open** (the hook): 1–3 excerpts, 15–45 s total, played before the intro. Best cold opens: a provocative claim, an unresolved question, or the peak moment of a story — cut *before* the payoff so the listener has to stay. It must make sense with zero context. Tie it to a trend from the brief when possible.
2. **Content cuts** beyond the clean plan: slow warm-ups ("so, how's your week"), tech chatter ("can you hear me?", "you're muted"), dead-end detours, false starts and re-takes (keep the clean take — always check the last 3 minutes for a re-recorded ending), repeated explanations.
3. **Structure:** the first 60 s after the cold open must state what the listener gets. If the strongest, most on-trend segment is buried at minute 40, consider moving it earlier via `sections` (reordering) — but only when it doesn't break the conversation's logic. Ask the user before reordering.
4. **Clips:** 3–6 standalone clips (20–60 s each; ≤ 90 s for LinkedIn/YouTube), each opening on its strongest line, one idea each, cover every speaker. Name them by hook.
5. **Titles & notes** (optional but recommended): 3 episode-title options and 3 clip captions written from the trend brief's audience phrasing; chapter timestamps come from `timeline.json` after render.

Plan schema (all times are seconds in the **source** file; full spec in `references/edit-plan-schema.md`):

```json
{
  "source": "INPUT.m4a",
  "output": "work/ep012/ep012-final.mp3",
  "cold_open": [{"start": 1834.2, "end": 1861.0, "note": "AI-agents hot take"}],
  "sting": true,
  "sections": [{"start": 42.0, "end": 3550.0}],
  "cuts_file": "work/ep012/cuts.json",
  "cuts": [{"start": 300.5, "end": 352.0, "reason": "mic trouble chatter"}],
  "clips": [{"name": "clip1-agents-hot-take", "start": 1834.2, "end": 1879.0}],
  "enhance": true,
  "target_lufs": -16,
  "bitrate": "192k"
}
```

Show the user a short summary of the plan (cold-open text, what's cut and why, clip list, minutes saved) before rendering if the session is interactive and the edit is substantial.

## Step 6 — Render

```bash
python3 scripts/render.py work/ep012/edit_plan.json            # episode + clips
python3 scripts/render.py work/ep012/edit_plan.json --clips-only
python3 scripts/render.py work/ep012/edit_plan.json --dry-run  # print ranges, render nothing
```

What it does: subtracts cuts from sections → splices with 10 ms micro-fades (no clicks) → prepends cold open + a synthesized transition sting → cut to WAV first (lossless), then one enhancement + encode pass:
`highpass 80 → lowpass → afftdn gentle denoise → EQ (-2 dB @180, +3 dB @2.5k, +1.5 dB @4.5k) → dynaudnorm (balances quiet guest vs loud host) → gentle 2:1 compressor → loudnorm -16 LUFS / -1.5 dBTP`.
Never add a noise gate (`agate`) — it silences quieter guests. Details and variants: `references/audio-chain.md`.

Clips are mastered at -14 LUFS (social platforms) unless the plan says otherwise.
It also writes `<output>.timeline.json` (e.g. `ep012-final.timeline.json`): every kept range with its source and output times, so chapter markers and show-note timestamps can be mapped from the transcript to the edited file (`scripts/render.py --map SECONDS` converts one source time).

## Step 7 — Verify (mandatory)

```bash
python3 scripts/verify.py work/ep012/ep012-final.mp3 --timeline work/ep012/ep012-final.timeline.json --spot 6
```

Reports integrated loudness (target -16 ±1 LUFS), true peak (≤ -1 dBTP), LRA, duration vs source, and extracts short windows around the riskiest splices into `work/ep012/spot/` for checking. If a transcription backend is available, re-transcribe 2–3 spot files to confirm splices read cleanly (no clipped first word, no half-filler).

## Deliver

Report briefly: final duration (and time saved), cold-open text, list of clips, loudness numbers, anything flagged for the user (soft fillers left in, uncertain names, a reorder you suggested but didn't apply). Hand over `final.mp3`, `clips/`, `trends_brief.md`, and chapters/title options if made.

## Quick modes

- "Just clean it up" → steps 2, 3, 6, 7 (no research, no cold open).
- "Find hooks / make clips" → steps 1, 2, 4, then a plan with `clips` only and `--clips-only`.
- "Re-cut a finished episode" → transcribe the final file, put the bad ranges in `cuts`, set `"enhance": false` (it's already mastered — don't double-process).

## Credits

Built from patterns in open-source skills found on GitHub — see `references/sources.md`.

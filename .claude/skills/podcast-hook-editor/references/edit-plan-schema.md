# edit_plan.json

All times are **seconds in the source file**. Relative paths resolve against the plan's folder.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `source` | string | required | Raw recording (any format ffmpeg reads; video files work — only audio is used). |
| `output` | string | `final.mp3` | `.mp3`, `.m4a` or `.wav`. |
| `cold_open` | `[{start,end,note?}]` | `[]` | Excerpts played first, in this order. |
| `sting` | bool | `true` | Synthesized 1.45 s bell between cold open and episode (only if cold_open). |
| `sections` | `[{start,end}]` | whole file | Body ranges **in playback order** — use to drop the pre-show/post-show or to reorder segments. |
| `cuts_file` | string | – | `cuts.json` from `clean_plan.py`; its `cuts` are applied. |
| `cuts` | `[{start,end,reason}]` | `[]` | Extra editorial cuts (detours, tech chatter, re-takes). Applied to body and clips. |
| `clips` | `[{name,start,end,apply_cuts?,target_lufs?}]` | `[]` | Social clips → `clips/<name>.mp3`. Cuts applied unless `apply_cuts:false`. |
| `enhance` | bool | `true` | Run the cleanup/EQ/dynamics chain. Set `false` when re-cutting an already mastered file. |
| `enhance_chain` | string | built-in | Override the ffmpeg filter chain (without loudnorm). |
| `loudnorm` | bool | `true` | Normalize loudness. |
| `target_lufs` | number | `-16` | Episode loudness (Spotify/Apple podcast standard). |
| `clip_lufs` | number | `-14` | Default loudness for clips. |
| `true_peak` | number | `-1.5` | dBTP ceiling. |
| `bitrate` | string | `192k` | Encoder bitrate. |

## Example: clean + cold open + reorder + clips

```json
{
  "source": "../../raw/ep012.wav",
  "output": "ep012-final.mp3",
  "cold_open": [
    {"start": 1834.2, "end": 1852.9, "note": "guest: 'agents will replace dashboards'"},
    {"start": 1901.4, "end": 1910.0, "note": "host pushback"}
  ],
  "sections": [
    {"start": 41.5, "end": 1200.0},
    {"start": 2410.0, "end": 2905.0, "note": "moved up: the on-trend case study"},
    {"start": 1200.0, "end": 2410.0},
    {"start": 2905.0, "end": 3550.0}
  ],
  "cuts_file": "cuts.json",
  "cuts": [
    {"start": 300.5, "end": 352.0, "reason": "mic trouble"},
    {"start": 3380.0, "end": 3462.7, "reason": "first take of the outro (re-recorded)"}
  ],
  "clips": [
    {"name": "01-agents-replace-dashboards", "start": 1834.2, "end": 1880.5},
    {"name": "02-pricing-mistake", "start": 2533.0, "end": 2581.0}
  ]
}
```

Tips
- `render.py plan.json --dry-run` prints kept ranges and estimated length without rendering.
- `render.py plan.json --map 1834.2 2533` converts source times to output times (for chapters).
- After rendering, `<output>.timeline.json` lists every range with `src_*` and `out_*` times.

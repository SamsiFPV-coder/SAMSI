# Sources & related skills (researched October 2026)

No single public skill did all three things (trend research → hook finding → audio-only edit),
so this skill combines patterns from these:

## Audio editing
- **OpenClaudia/openclaudia-skills → `podcast-edit`** — filler/silence removal from Whisper word
  timestamps, two-pass WAV→MP3, the dynaudnorm-based enhancement chain (no gate), re-cut workflow,
  highlight clips with synthesized stings. Main inspiration for `render.py` and `audio-chain.md`.
  https://github.com/OpenClaudia/openclaudia-skills
- **danielmiessler/personal_ai_infrastructure → `audioeditor`** — transcribe → classify segments
  (filler, false start, stutter, dead air) → edit with crossfades; preview mode.
  https://github.com/danielmiessler/personal_ai_infrastructure
- **guia-matthieu/clawfu-skills → `audio-editing`** — audio-engineering background (why denoise before
  compression, EQ problem frequencies). https://github.com/guia-matthieu/clawfu-skills
- **praisonai-editor** (PyPI) — CLI/agent tool with podcast presets for fillers, repetitions, silence.
  https://pypi.org/project/praisonai-editor/

## Trends & hooks research
- **mvanhorn/last30days-skill** — engagement-ranked research across Reddit, X, YouTube, TikTok, HN,
  Polymarket, web. https://github.com/mvanhorn/last30days-skill
- **ScrapeCreators/social-media-research-skills** — `trend-discovery`, `outlier-post-finder`,
  `transcript-intelligence` (hooks from transcripts). https://github.com/ScrapeCreators/social-media-research-skills
- **hardhackerlabs/podwise-cli** — trending podcast episodes, transcript Q&A. https://github.com/hardhackerlabs/podwise-cli

## Not used (out of scope)
- Podcast *generators* (TTS from text): sgasser/claude-skill-podcast, geek-skills-podcast-generator.
- Video pipelines: OpenMontage (podcast → video highlights), praisonai video module.

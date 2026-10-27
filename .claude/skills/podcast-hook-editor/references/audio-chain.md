# Audio chain (speech podcasts)

Default chain in `render.py` (then `loudnorm=I=-16:TP=-1.5:LRA=13`):

```
highpass=f=80                                  # rumble, desk thumps, HVAC
lowpass=f=12000                                # hiss (7500 for 16 kHz sources, 10500 for 22 kHz)
afftdn=nf=-25:nr=8:nt=w                        # gentle broadband denoise
equalizer=f=180:t=q:w=1.5:g=-2                 # reduce mud / boxiness
equalizer=f=2500:t=q:w=1.2:g=3                 # presence / intelligibility
equalizer=f=4500:t=q:w=1.5:g=1.5               # clarity
dynaudnorm=f=200:g=5:p=0.95:m=5:s=0            # rolling 200 ms normalization: lifts the quiet guest independently
acompressor=threshold=-20dB:ratio=2:attack=5:release=200:makeup=1   # gentle glue
```

Order matters: denoise before EQ boosts (don't amplify noise), `dynaudnorm` before the compressor
(so the compressor sees a balanced signal), loudness normalization last.

## Never in the default chain
- `agate` (noise gate) — cuts quieter speakers mid-word.
- Heavy compression (ratio > 3:1, makeup > 2 dB) — pumping, fatigue.
- `loudnorm` LRA < 11 — crushes natural dynamics.

## Variants (pass as `enhance_chain` in the plan)

**Noisy room / fan noise** — stronger denoise, keep it before EQ:
`highpass=f=90,lowpass=f=11000,afftdn=nf=-20:nr=14:nt=w,equalizer=f=200:t=q:w=1.5:g=-3,equalizer=f=3000:t=q:w=1.2:g=2.5,dynaudnorm=f=200:g=5:p=0.95:m=5,acompressor=threshold=-20dB:ratio=2:attack=5:release=200:makeup=1`

**Harsh / sibilant voice** — add a de-esser after EQ:
`... ,deesser=i=0.4:m=0.5:f=0.5:s=o, ...`

**Already clean studio recording** — minimal:
`highpass=f=70,dynaudnorm=f=250:g=7:p=0.95:m=4,acompressor=threshold=-18dB:ratio=1.8:attack=8:release=250:makeup=1`

**Reverberant room**: ffmpeg can't truly de-reverb. Suggest a dedicated tool (e.g. Adobe Podcast
Enhance Speech, iZotope RX, Auphonic) on the raw file, then run this skill with `enhance:false`
except loudness.

**Separate tracks per speaker** (multitrack): mix first, with per-track `dynaudnorm`, e.g.
`ffmpeg -i host.wav -i guest.wav -filter_complex "[0]dynaudnorm=f=200[a];[1]dynaudnorm=f=200[b];[a][b]amix=inputs=2:normalize=0[out]" -map "[out]" mixed.wav`
then use `mixed.wav` as `source`.

## Loudness targets
- Podcast episode: −16 LUFS integrated (Apple/Spotify spec), true peak ≤ −1 dBTP.
- Social clips: −14 LUFS.
- Mono for speech-only shows (half the file size, nothing lost). Use stereo only if the source has
  meaningful stereo content (music beds, separate speaker channels).

## Splicing
- 10–12 ms fade-in/out at every splice avoids clicks without audible dips.
- Cut on word boundaries from word timestamps + ~30 ms pad; never inside a word.
- Shorten long pauses to ~0.4–0.5 s rather than deleting them; zero-gap joins sound robotic.
- Cut to lossless WAV first, encode once at the end (no generation loss).

#!/usr/bin/env python3
"""Render an edit plan into a finished podcast episode (+ clips) with ffmpeg.

  python3 render.py edit_plan.json [--dry-run] [--clips-only] [--no-clips]
  python3 render.py edit_plan.json --map 1834.2     # source time -> output time

Pipeline: sections - cuts -> splice with micro-fades -> [cold open + sting] + body
          -> lossless WAV -> enhancement chain + loudnorm -> MP3
Writes <output>, timeline.json (next to output) and clips/<name>.mp3.
See references/edit-plan-schema.md for the plan format.
"""
import argparse, atexit, json, os, subprocess, sys, tempfile

ENHANCE = ("highpass=f=80,lowpass=f={lp},afftdn=nf=-25:nr=8:nt=w,"
           "equalizer=f=180:t=q:w=1.5:g=-2,equalizer=f=2500:t=q:w=1.2:g=3,"
           "equalizer=f=4500:t=q:w=1.5:g=1.5,dynaudnorm=f=200:g=5:p=0.95:m=5:s=0,"
           "acompressor=threshold=-20dB:ratio=2:attack=5:release=200:makeup=1")
FADE = 0.012  # seconds of micro-fade at each splice -> no clicks


def run(cmd, quiet=True):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"ffmpeg failed:\n{' '.join(cmd)}\n{r.stderr[-3000:]}")
    return r


def probe(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=sample_rate,channels",
               "-select_streams", "a:0", "-of", "json", path]).stdout
    j = json.loads(out)
    st = j["streams"][0]
    return float(j["format"]["duration"]), int(st["sample_rate"]), int(st["channels"])


def subtract(ranges, cuts, min_len=0.05):
    keep = []
    cuts = sorted(cuts, key=lambda c: c[0])
    for s, e in ranges:
        cur = s
        for cs, ce in cuts:
            if ce <= cur or cs >= e:
                continue
            if cs > cur:
                keep.append([cur, min(cs, e)])
            cur = max(cur, ce)
        if cur < e:
            keep.append([cur, e])
    return [[round(s, 3), round(e, 3)] for s, e in keep if e - s >= min_len]


def rng(x):
    return [round(float(x["start"]), 3), round(float(x["end"]), 3)]


def make_sting(path, sr):
    """Short soft bell chord (C-E-G) as cold-open -> episode transition. No assets needed."""
    run(["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "sine=f=523.25:d=1.1", "-f", "lavfi", "-i", "sine=f=659.25:d=1.1",
         "-f", "lavfi", "-i", "sine=f=783.99:d=1.1",
         "-filter_complex", "[0][1][2]amix=inputs=3:normalize=1,afade=t=in:st=0:d=0.02,"
         "afade=t=out:st=0.25:d=0.85,lowpass=f=3800,volume=0.30,apad=pad_dur=0.35[s]",
         "-map", "[s]", "-ar", str(sr), "-ac", "1", "-c:a", "pcm_s16le", path])


def splice(src, ranges, out_wav, sr, extra_inputs=(), order=None):
    """Concat source ranges (and optional extra wav inputs) into one WAV.
    order: list of ("src", idx) / ("in", n) items; defaults to all src ranges."""
    # Strategy: decode the source ONCE to mono PCM WAV (sample-accurate seeking), cut every
    # range to its own small WAV with micro-fades (in parallel), then join with the concat
    # demuxer. Scales to hundreds of cuts and any playback order without buffering the
    # whole file in a filter graph.
    from concurrent.futures import ThreadPoolExecutor
    order = order or [("src", i) for i in range(len(ranges))]
    work = tempfile.mkdtemp(prefix="splice_")
    pcm = _decoded(src, sr)
    jobs = []
    for k, (kind, idx) in enumerate(order):
        part = os.path.join(work, f"p{k:05d}.wav")
        if kind == "src":
            s, e = ranges[idx]
            d = e - s
            f = min(FADE, d / 4)
            cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{s:.4f}", "-t", f"{d:.4f}", "-i", pcm,
                   "-af", f"afade=t=in:st=0:d={f:.4f},afade=t=out:st={d - f:.4f}:d={f:.4f}",
                   "-ar", str(sr), "-ac", "1", "-c:a", "pcm_s16le", part]
        else:
            cmd = ["ffmpeg", "-y", "-v", "error", "-i", extra_inputs[idx],
                   "-ar", str(sr), "-ac", "1", "-c:a", "pcm_s16le", part]
        jobs.append((cmd, part))
    with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 2)) as ex:
        list(ex.map(lambda j: run(j[0]), jobs))
    lst = os.path.join(work, "list.txt")
    with open(lst, "w") as fh:
        for _, part in jobs:
            fh.write(f"file '{part}'\n")
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out_wav])
    for _, part in jobs:
        os.unlink(part)
    os.unlink(lst); os.rmdir(work)


_DECODED = {}


@atexit.register
def _cleanup():
    for p in _DECODED.values():
        try:
            os.unlink(p)
        except OSError:
            pass


def _decoded(src, sr):
    """Decode source to a cached mono 16-bit WAV at `sr` (sample-accurate seeks)."""
    key = (src, sr)
    if key not in _DECODED:
        path = os.path.join(tempfile.gettempdir(), f"phe_src_{os.getpid()}_{sr}.wav")
        run(["ffmpeg", "-y", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le", path])
        _DECODED[key] = path
    return _DECODED[key]


def master(in_wav, out_path, plan, sr):
    lufs, tp, br = plan.get("target_lufs", -16), plan.get("true_peak", -1.5), plan.get("bitrate", "192k")
    chain = []
    if plan.get("enhance", True):
        lp = 7500 if sr <= 16000 else (10500 if sr <= 22050 else 12000)
        chain.append(plan.get("enhance_chain") or ENHANCE.format(lp=lp))
    if plan.get("loudnorm", True):
        chain.append(f"loudnorm=I={lufs}:TP={tp}:LRA=13")
    af = ",".join(chain) or "anull"
    codec = (["-c:a", "libmp3lame", "-b:a", br] if out_path.endswith(".mp3") else
             ["-c:a", "aac", "-b:a", br] if out_path.endswith((".m4a", ".aac")) else
             ["-c:a", "pcm_s16le"])
    # loudnorm resamples to 192 kHz internally, so always set the output rate explicitly
    run(["ffmpeg", "-y", "-v", "error", "-i", in_wav, "-af", af, "-ar", "44100", "-ac", "1"] + codec + [out_path])


def build(plan, base):
    src = os.path.join(base, plan["source"]) if not os.path.isabs(plan["source"]) else plan["source"]
    dur, sr, _ = probe(src)
    sr = max(sr, 16000)
    sections = [rng(x) for x in plan.get("sections", [])] or [[0.0, dur]]
    cuts = [rng(c) for c in plan.get("cuts", [])]
    cf = plan.get("cuts_file")
    if cf:
        cf = cf if os.path.isabs(cf) else os.path.join(base, cf)
        cuts += [rng(c) for c in json.load(open(cf, encoding="utf-8"))["cuts"]]
    body = subtract(sections, cuts)
    cold = [rng(x) for x in plan.get("cold_open", [])]
    return src, dur, sr, body, cold, cuts


def timeline(body, cold, sting_len):
    t, tl = 0.0, []
    for s, e in cold:
        tl.append({"part": "cold_open", "src_start": s, "src_end": e, "out_start": round(t, 3), "out_end": round(t + e - s, 3)})
        t += e - s
    if cold and sting_len:
        tl.append({"part": "sting", "out_start": round(t, 3), "out_end": round(t + sting_len, 3)}); t += sting_len
    for s, e in body:
        tl.append({"part": "body", "src_start": s, "src_end": e, "out_start": round(t, 3), "out_end": round(t + e - s, 3)})
        t += e - s
    return tl, t


def map_time(tl, x):
    for r in tl:
        if r["part"] == "body" and r["src_start"] <= x <= r["src_end"]:
            return r["out_start"] + (x - r["src_start"])
    return None


def fmt(t):
    t = int(round(t))
    return f"{t//3600}:{t%3600//60:02d}:{t%60:02d}" if t >= 3600 else f"{t//60:02d}:{t%60:02d}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--clips-only", action="store_true")
    ap.add_argument("--no-clips", action="store_true")
    ap.add_argument("--map", type=float, nargs="*", help="map source seconds to output seconds and exit")
    a = ap.parse_args()

    base = os.path.dirname(os.path.abspath(a.plan))
    plan = json.load(open(a.plan, encoding="utf-8"))
    src, dur, sr, body, cold, cuts = build(plan, base)
    out = plan.get("output", "final.mp3")
    out = out if os.path.isabs(out) else os.path.join(base, out)
    use_sting = bool(cold) and plan.get("sting", True)
    sting_len = 1.45 if use_sting else 0.0
    tl, total = timeline(body, cold, sting_len)

    if a.map is not None:
        for x in a.map:
            m = map_time(tl, x)
            print(f"{x:.2f}s ({fmt(x)}) -> " + (f"{m:.2f}s ({fmt(m)})" if m is not None else "cut / not in output"))
        return

    kept = sum(e - s for s, e in body)
    print(f"source {fmt(dur)} | body kept {fmt(kept)} ({len(body)} ranges, {len(cuts)} cuts) | "
          f"cold open {sum(e-s for s,e in cold):.1f}s | output ≈ {fmt(total)} | saved {fmt(dur - kept)}")
    if a.dry_run:
        for r in tl[:40]:
            print(r)
        if len(tl) > 40:
            print(f"... {len(tl) - 40} more ranges")
        return

    os.makedirs(os.path.dirname(out), exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        if not a.clips_only:
            ranges = cold + body
            order = [("src", i) for i in range(len(cold))]
            extra = []
            if use_sting:
                sting = os.path.join(td, "sting.wav"); make_sting(sting, sr); extra.append(sting)
                order.append(("in", 0))
            order += [("src", len(cold) + i) for i in range(len(body))]
            cut_wav = os.path.join(td, "cut.wav")
            print("splicing ...")
            splice(src, ranges, cut_wav, sr, extra, order)
            print("mastering ...")
            master(cut_wav, out, plan, sr)
            tl_path = os.path.splitext(out)[0] + ".timeline.json"
            json.dump({"source": src, "output": out, "source_duration": dur, "output_duration": round(total, 3),
                       "timeline": tl}, open(tl_path, "w"), indent=1)
            print(f"wrote {out}\nwrote {tl_path}")

        if plan.get("clips") and not a.no_clips:
            cdir = os.path.join(os.path.dirname(out), "clips")
            os.makedirs(cdir, exist_ok=True)
            for c in plan["clips"]:
                cr = subtract([rng(c)], cuts if c.get("apply_cuts", True) else [])
                if not cr:
                    print(f"skip clip {c['name']}: fully cut"); continue
                wav = os.path.join(td, c["name"] + ".wav")
                splice(src, cr, wav, sr)
                d = sum(e - s for s, e in cr)
                faded = os.path.join(td, c["name"] + ".f.wav")
                run(["ffmpeg", "-y", "-v", "error", "-i", wav, "-af",
                     f"afade=t=in:st=0:d=0.15,afade=t=out:st={max(d - 0.6, 0):.3f}:d=0.6", faded])
                cpath = os.path.join(cdir, c["name"] + ".mp3")
                master(faded, cpath, {**plan, "target_lufs": c.get("target_lufs", plan.get("clip_lufs", -14))}, sr)
                print(f"wrote {cpath} ({d:.1f}s)")


if __name__ == "__main__":
    main()

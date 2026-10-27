#!/usr/bin/env python3
"""Rank hook / cold-open / clip candidates in a transcript.

Windows of --min..--max seconds are built from consecutive transcript segments
and scored on text signals (trend keywords, curiosity triggers, numbers,
contrast, story openers, strong opinions) and audio signals (vocal energy,
speaking pace). The output is a SHORTLIST for an editor to judge, not a verdict.

Output hooks.json: [{"rank","start","end","score","features":{...},"text"}]
"""
import argparse, json, math, re, subprocess, sys

TRIGGERS = {
    "curiosity": [
        r"\bwhy\b", r"\bhow come\b", r"\bwhat if\b", r"\bthe (real )?reason\b", r"\bthe truth\b",
        r"\bnobody (tells|talks|knows)\b", r"\bsecret\b", r"\bmost people\b", r"\bhere'?s the thing\b",
        r"\bturns out\b", r"\bthe problem is\b", r"\bwhat nobody\b", r"\byou won'?t believe\b",
        r"\bdlaczego\b", r"\bczemu\b", r"\bco jeśli\b", r"\bprawda jest\b", r"\btak naprawdę\b",
        r"\bnikt (nie )?(mówi|wie)\b", r"\bsekret\b", r"\bwiększość ludzi\b", r"\bproblem (jest|polega)\b",
        r"\bokazuje się\b", r"\bokazało się\b",
    ],
    "contrast": [
        r"\bbut\b", r"\bactually\b", r"\bwrong\b", r"\bmistake\b", r"\bmyth\b", r"\bopposite\b",
        r"\boverrated\b", r"\bunpopular\b", r"\bdisagree\b", r"\bstop\b", r"\bnever\b", r"\bdead\b",
        r"\bale\b", r"\bbłąd\b", r"\bmit\b", r"\bodwrotnie\b", r"\bprzereklamowan\w*", r"\bnie zgadzam\b",
        r"\bnigdy\b", r"\bprzestań\w*", r"\bbzdura\b", r"\bkontrowersyjn\w*",
    ],
    "story": [
        r"\bi was\b", r"\bwhen i\b", r"\bone day\b", r"\bi remember\b", r"\bthe first time\b",
        r"\bwe almost\b", r"\bi lost\b", r"\bi got fired\b", r"\bi failed\b",
        r"\bpamiętam\b", r"\bpierwszy raz\b", r"\bkiedyś\b", r"\bstraciłem\b", r"\bstraciłam\b",
        r"\bwywalili mnie\b", r"\bprawie\b",
    ],
    "opinion": [
        r"\bi (really |honestly )?think\b", r"\bi believe\b", r"\bin my opinion\b", r"\bhonestly\b",
        r"\bthe biggest\b", r"\bthe best\b", r"\bthe worst\b", r"\beveryone\b", r"\bnobody\b",
        r"\buważam\b", r"\bmoim zdaniem\b", r"\bszczerze\b", r"\bnajwiększ\w*", r"\bnajlepsz\w*",
        r"\bnajgorsz\w*", r"\bwszyscy\b", r"\bnikt\b",
    ],
    "stakes": [
        r"\bmoney\b", r"\bmillion\b", r"\bdollars?\b", r"\bfired\b", r"\bquit\b", r"\bbroke\b",
        r"\bdie\b", r"\bdanger\w*", r"\brisk\w*", r"\bchanged my life\b",
        r"\bpieniądz\w*", r"\bmilion\w*", r"\bzł\b", r"\bzłotych\b", r"\bzwolni\w*", r"\bryzyk\w*",
        r"\bzmienił\w* (moje )?życie\b",
    ],
}
FILLER_RE = re.compile(r"\b(um+|uh+|erm|y{2,}|e{2,}|hmm+|like|you know|jakby|znaczy)\b", re.I)
NUM_RE = re.compile(r"\b\d+([.,]\d+)?\s*(%|k|m|procent|tys\w*|mln|million|billion|x)?\b", re.I)
WEIGHTS = {"keywords": 3.0, "curiosity": 2.0, "contrast": 1.2, "story": 1.5, "opinion": 1.0,
           "stakes": 1.3, "numbers": 1.0, "question": 1.5, "energy": 1.5, "pace": 0.8,
           "filler_penalty": -2.5, "clean_start": 1.0}


def load_energy(audio, hop=0.5):
    """RMS (dB) per hop seconds via ffmpeg pipe; needs numpy. Returns (list, hop) or (None, hop)."""
    try:
        import numpy as np
    except ImportError:
        print("numpy not installed: skipping energy feature", file=sys.stderr)
        return None, hop
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", audio, "-ac", "1", "-ar", "8000",
                        "-f", "f32le", "-"], capture_output=True)
    if p.returncode != 0:
        print("ffmpeg decode failed: skipping energy", file=sys.stderr)
        return None, hop
    x = np.frombuffer(p.stdout, dtype=np.float32)
    n = int(8000 * hop)
    k = len(x) // n
    if k == 0:
        return None, hop
    frames = x[:k * n].reshape(k, n)
    rms = np.sqrt((frames ** 2).mean(axis=1) + 1e-12)
    return (20 * np.log10(rms)).tolist(), hop


def window_energy(db, hop, s, e):
    if db is None:
        return None
    a, b = int(s / hop), max(int(e / hop), int(s / hop) + 1)
    vals = [v for v in db[a:b] if v > -55]  # ignore silence
    return sum(vals) / len(vals) if vals else None


def zscores(vals):
    xs = [v for v in vals if v is not None]
    if len(xs) < 2:
        return [0.0 for _ in vals]
    m = sum(xs) / len(xs)
    sd = math.sqrt(sum((v - m) ** 2 for v in xs) / len(xs)) or 1.0
    return [0.0 if v is None else (v - m) / sd for v in vals]


def fmt(t):
    t = int(t)
    return f"{t//3600}:{t%3600//60:02d}:{t%60:02d}" if t >= 3600 else f"{t//60:02d}:{t%60:02d}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript")
    ap.add_argument("--audio", help="source audio, enables energy scoring")
    ap.add_argument("--keywords", help="file, one trend keyword/phrase per line")
    ap.add_argument("--min", type=float, default=10.0, help="min window length (s)")
    ap.add_argument("--max", type=float, default=40.0, help="max window length (s)")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--skip-start", type=float, default=0.0, help="ignore first N s (intro)")
    ap.add_argument("--out", default="hooks.json")
    a = ap.parse_args()

    doc = json.load(open(a.transcript, encoding="utf-8"))
    segs = [s for s in doc["segments"] if s["end"] > a.skip_start and s["text"].strip()]
    kws = []
    if a.keywords:
        kws = [l.strip().lower() for l in open(a.keywords, encoding="utf-8") if l.strip() and not l.startswith("#")]
    db, hop = load_energy(a.audio) if a.audio else (None, 0.5)
    compiled = {k: [re.compile(p, re.I) for p in v] for k, v in TRIGGERS.items()}

    cands = []
    for i in range(len(segs)):
        text, j = "", i
        while j < len(segs) and segs[j]["end"] - segs[i]["start"] <= a.max:
            text = (text + " " + segs[j]["text"]).strip()
            dur = segs[j]["end"] - segs[i]["start"]
            if dur >= a.min:
                cands.append((segs[i]["start"], segs[j]["end"], text, i))
            j += 1

    rows, energies, paces = [], [], []
    for s, e, text, i in cands:
        low = text.lower()
        f = {}
        f["keywords"] = sum(low.count(k) for k in kws) if kws else 0
        f["keyword_hits"] = sorted({k for k in kws if k in low})
        for k, pats in compiled.items():
            f[k] = sum(len(p.findall(low)) for p in pats)
        f["numbers"] = len(NUM_RE.findall(low))
        f["question"] = text.count("?")
        nwords = len(text.split())
        fillers = len(FILLER_RE.findall(low))
        f["filler_density"] = round(fillers / max(nwords, 1), 3)
        prev = segs[i - 1]["text"].strip() if i > 0 else "."
        f["clean_start"] = 1 if (prev.endswith((".", "?", "!")) and text[:1].isupper()) else 0
        energies.append(window_energy(db, hop, s, e))
        paces.append(nwords / max(e - s, 1))
        rows.append([s, e, text, f])

    ez, pz = zscores(energies), zscores(paces)
    out = []
    for (s, e, text, f), ezz, pzz in zip(rows, ez, pz):
        f["energy_z"], f["pace_z"] = round(ezz, 2), round(pzz, 2)
        sat = lambda x, cap=3: min(x, cap)  # diminishing returns
        score = (WEIGHTS["keywords"] * sat(f["keywords"]) + WEIGHTS["curiosity"] * sat(f["curiosity"])
                 + WEIGHTS["contrast"] * sat(f["contrast"]) + WEIGHTS["story"] * sat(f["story"], 2)
                 + WEIGHTS["opinion"] * sat(f["opinion"]) + WEIGHTS["stakes"] * sat(f["stakes"])
                 + WEIGHTS["numbers"] * sat(f["numbers"], 2) + WEIGHTS["question"] * sat(f["question"], 2)
                 + WEIGHTS["energy"] * max(min(ezz, 2.5), -1.5) + WEIGHTS["pace"] * max(min(pzz, 2), -2)
                 + WEIGHTS["filler_penalty"] * f["filler_density"] * 10 + WEIGHTS["clean_start"] * f["clean_start"])
        # mild preference for 15-30 s (cold-open / clip sweet spot)
        dur = e - s
        score -= 0.05 * max(0, abs(dur - 22) - 8)
        out.append({"start": round(s, 2), "end": round(e, 2), "dur": round(dur, 1),
                    "at": fmt(s), "score": round(score, 2), "features": f, "text": text})

    # non-maximum suppression: drop windows overlapping a better one by >40%
    out.sort(key=lambda r: -r["score"])
    picked = []
    for r in out:
        ok = True
        for p in picked:
            ov = min(r["end"], p["end"]) - max(r["start"], p["start"])
            if ov > 0.4 * min(r["dur"], p["dur"]):
                ok = False; break
        if ok:
            picked.append(r)
        if len(picked) >= a.top:
            break
    for n, r in enumerate(picked, 1):
        r["rank"] = n
    json.dump(picked, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for r in picked:
        hits = ",".join(r["features"]["keyword_hits"]) or "-"
        print(f"#{r['rank']:>2} {r['at']} ({r['dur']:>4.0f}s) score {r['score']:>5.1f}  kw[{hits}]  "
              f"{r['text'][:110]}{'…' if len(r['text']) > 110 else ''}")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()

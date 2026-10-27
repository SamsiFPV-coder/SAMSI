#!/usr/bin/env python3
"""Verify a rendered episode: loudness, peak, duration, and splice spot-checks.

  python3 verify.py final.mp3 [--timeline final.timeline.json] [--spot 6] [--lufs -16]

Prints a pass/warn report and (with --timeline) extracts ~6 s windows around
splice points into ./spot/ next to the output, so they can be listened to or
re-transcribed to confirm no clipped words remain.
"""
import argparse, json, os, re, subprocess, sys


def ebur128(path):
    r = subprocess.run(["ffmpeg", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    txt = r.stderr
    summ = txt[txt.rfind("Summary:"):]
    g = lambda pat: (float(m.group(1)) if (m := re.search(pat, summ)) else None)
    return {"I": g(r"I:\s+(-?[\d.]+) LUFS"), "LRA": g(r"LRA:\s+(-?[\d.]+) LU"),
            "TP": g(r"Peak:\s+(-?[\d.]+) dBFS")}


def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", path], capture_output=True, text=True)
    return float(r.stdout.strip())


def fmt(t):
    t = int(round(t))
    return f"{t//3600}:{t%3600//60:02d}:{t%60:02d}" if t >= 3600 else f"{t//60:02d}:{t%60:02d}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio")
    ap.add_argument("--timeline")
    ap.add_argument("--spot", type=int, default=6, help="number of splice windows to extract")
    ap.add_argument("--lufs", type=float, default=-16.0)
    a = ap.parse_args()

    m, d = ebur128(a.audio), duration(a.audio)
    ok = True
    print(f"file      {a.audio}")
    print(f"duration  {fmt(d)} ({d:.1f}s)")
    if m["I"] is not None:
        good = abs(m["I"] - a.lufs) <= 1.0
        ok &= good
        print(f"loudness  {m['I']:.1f} LUFS  (target {a.lufs:.0f} ±1)  {'OK' if good else 'WARN'}")
    if m["TP"] is not None:
        good = m["TP"] <= -1.0
        ok &= good
        print(f"peak      {m['TP']:.1f} dBFS (≤ -1.0)  {'OK' if good else 'WARN'}")
    if m["LRA"] is not None:
        good = 3 <= m["LRA"] <= 15
        print(f"LRA       {m['LRA']:.1f} LU   (3–15 typical speech)  {'OK' if good else 'CHECK'}")

    if a.timeline:
        tl = json.load(open(a.timeline))
        src_d, out_d = tl["source_duration"], tl["output_duration"]
        body = sum(r["out_end"] - r["out_start"] for r in tl["timeline"] if r["part"] == "body")
        extra = out_d - body
        print(f"source    {fmt(src_d)} -> output {fmt(out_d)}  (body {fmt(body)}, removed {fmt(src_d - body)} = "
              f"{100 * (src_d - body) / src_d:.1f}%; cold open + sting add {extra:.1f}s)")
        if abs(out_d - d) > 1.5:
            print(f"WARN      timeline says {out_d:.1f}s but file is {d:.1f}s"); ok = False
        # riskiest splices: joins where a lot of source time was removed
        joins = []
        rows = tl["timeline"]
        for prev, cur in zip(rows, rows[1:]):
            removed = (cur.get("src_start", 0) - prev.get("src_end", 0)) if prev["part"] == cur["part"] == "body" else 99
            joins.append((removed, cur["out_start"], prev["part"], cur["part"]))
        joins.sort(key=lambda j: -j[0])
        sdir = os.path.join(os.path.dirname(os.path.abspath(a.audio)), "spot")
        os.makedirs(sdir, exist_ok=True)
        for n, (removed, t, p, c) in enumerate(joins[:a.spot], 1):
            s = max(t - 3, 0)
            outp = os.path.join(sdir, f"splice{n:02d}_{fmt(t).replace(':', '-')}.mp3")
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{s:.2f}", "-t", "6", "-i", a.audio, outp])
            label = f"{p}->{c}" if p != c else f"removed {removed:.1f}s"
            print(f"spot      {outp}  @ {fmt(t)}  ({label})")
    print("RESULT    " + ("PASS" if ok else "CHECK WARNINGS"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

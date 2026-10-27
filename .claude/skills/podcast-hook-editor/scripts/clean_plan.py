#!/usr/bin/env python3
"""Build a mechanical cut list from a word-timestamped transcript.

Detects
  * hard fillers  (um, uh, erm, yyy, eee, ...)            -> cut
  * stutters      (immediate repeat of the same word)     -> cut the earlier copy
  * dead air      (gap between words > --max-pause)       -> shortened to --target-pause
  * soft fillers  (like, you know, znaczy, jakby, ...)    -> flagged in "review" only
                                                             (cut with --aggressive)

Output cuts.json:
  {"cuts": [{"start", "end", "reason", "text"}], "review": [...], "stats": {...}}
Times are seconds in the source audio.
"""
import argparse, json, re, sys

HARD = {
    "en": {"um", "umm", "uh", "uhh", "erm", "er", "ah", "ahh", "hmm", "hm", "mm", "mmm", "uhm"},
    "pl": {"yyy", "yy", "yyyy", "eee", "ee", "eeee", "mmm", "mm", "hmm", "hm", "eem", "yhm", "aaa"},
    "de": {"äh", "ähm", "öh", "hm", "hmm", "mhm"},
    "es": {"eh", "em", "mmm"},
    "fr": {"euh", "heu", "bah", "hum"},
}
SOFT = {
    "en": ["you know", "i mean", "kind of", "sort of", "like", "basically", "literally", "actually", "so yeah"],
    "pl": ["no to", "tak jakby", "w sumie", "znaczy", "jakby", "generalnie", "po prostu", "wiesz", "no"],
    "de": ["halt", "quasi", "sozusagen", "irgendwie"],
    "es": ["o sea", "bueno", "pues"],
    "fr": ["en fait", "genre", "du coup", "voilà"],
}
PUNCT = re.compile(r"[^\w']+", re.UNICODE)


def norm(w):
    return PUNCT.sub("", w.lower())


def is_hard_filler(tok, hard):
    if tok in hard:
        return True
    # elongated variants: "ummmm", "yyyyy", "eeeee"
    return bool(re.fullmatch(r"(u+m+|u+h+|e+r?m+|y{2,}|e{2,}|m{2,}|h+m+|a{3,})", tok))


def merge(cuts, join_gap=0.06):
    cuts = sorted(cuts, key=lambda c: c["start"])
    out = []
    for c in cuts:
        if out and c["start"] <= out[-1]["end"] + join_gap:
            out[-1]["end"] = max(out[-1]["end"], c["end"])
            if c["reason"] not in out[-1]["reason"]:
                out[-1]["reason"] += "+" + c["reason"]
            out[-1]["text"] = (out[-1].get("text", "") + " " + c.get("text", "")).strip()
        else:
            out.append(dict(c))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript")
    ap.add_argument("--out", default="cuts.json")
    ap.add_argument("--lang", default=None, help="comma list, e.g. pl,en (default: transcript language + en)")
    ap.add_argument("--max-pause", type=float, default=1.2, help="pauses longer than this get shortened")
    ap.add_argument("--target-pause", type=float, default=0.45, help="length a long pause is shortened to")
    ap.add_argument("--pad", type=float, default=0.03, help="safety pad around filler cuts (s)")
    ap.add_argument("--stutter-gap", type=float, default=0.7, help="max gap for repeated word to count as stutter")
    ap.add_argument("--min-filler-gap", type=float, default=0.0,
                    help="only cut a filler if it is this far from neighbours on BOTH sides (0 = always)")
    ap.add_argument("--aggressive", action="store_true", help="also cut standalone soft fillers")
    a = ap.parse_args()

    doc = json.load(open(a.transcript, encoding="utf-8"))
    langs = (a.lang.split(",") if a.lang else [(doc.get("language") or "en")[:2], "en"])
    hard = set().union(*(HARD.get(l, set()) for l in langs))
    soft = [p for l in langs for p in SOFT.get(l, [])]

    words = [w for s in doc["segments"] for w in s.get("words", [])
             if w.get("start") is not None and w.get("end") is not None]
    words.sort(key=lambda w: w["start"])
    if not words:
        sys.exit("transcript has no word timestamps -- re-run transcribe.py")
    toks = [norm(w["word"]) for w in words]

    cuts, review = [], []
    stats = {"fillers": 0, "stutters": 0, "pauses": 0, "soft_flagged": 0, "soft_cut": 0}

    def bounds(i, j=None):
        j = i if j is None else j
        prev_end = words[i - 1]["end"] if i > 0 else 0.0
        next_start = words[j + 1]["start"] if j + 1 < len(words) else words[j]["end"] + a.pad
        s = max(prev_end, words[i]["start"] - a.pad)
        e = min(next_start, words[j]["end"] + a.pad)
        return s, e

    # hard fillers
    for i, t in enumerate(toks):
        if t and is_hard_filler(t, hard):
            s, e = bounds(i)
            if a.min_filler_gap:
                gl = words[i]["start"] - (words[i-1]["end"] if i else 0)
                gr = (words[i+1]["start"] if i + 1 < len(words) else 1e9) - words[i]["end"]
                if min(gl, gr) < a.min_filler_gap:
                    review.append({"start": s, "end": e, "reason": "filler-glued", "text": words[i]["word"]})
                    continue
            cuts.append({"start": s, "end": e, "reason": "filler", "text": words[i]["word"]})
            stats["fillers"] += 1

    # stutters: "the the", "I I I", "że że"
    for i in range(len(toks) - 1):
        if toks[i] and toks[i] == toks[i + 1] and len(toks[i]) <= 12 \
                and words[i + 1]["start"] - words[i]["end"] <= a.stutter_gap \
                and not is_hard_filler(toks[i], hard):
            # keep genuine emphasis like "very very" / "bardzo bardzo"? keep if long word
            if toks[i] in {"very", "really", "bardzo", "no", "tak", "nie", "bye", "pa"}:
                continue
            s, e = bounds(i)
            e = min(e, words[i + 1]["start"])
            cuts.append({"start": s, "end": e, "reason": "stutter", "text": words[i]["word"]})
            stats["stutters"] += 1

    # soft fillers (phrase match on token stream)
    soft_tok = [p.split() for p in soft]
    for i in range(len(toks)):
        for ph in soft_tok:
            n = len(ph)
            if toks[i:i + n] == ph:
                s, e = bounds(i, i + n - 1)
                item = {"start": round(s, 3), "end": round(e, 3), "reason": "soft-filler",
                        "text": " ".join(w["word"] for w in words[i:i + n])}
                # "standalone" = surrounded by small pauses on both sides
                gl = words[i]["start"] - (words[i-1]["end"] if i else 0)
                gr = (words[i+n]["start"] if i + n < len(words) else 9) - words[i+n-1]["end"]
                if a.aggressive and gl > 0.12 and gr > 0.12:
                    cuts.append(item); stats["soft_cut"] += 1
                else:
                    review.append(item); stats["soft_flagged"] += 1
                break

    # dead air
    for i in range(len(words) - 1):
        gap = words[i + 1]["start"] - words[i]["end"]
        if gap > a.max_pause:
            half = a.target_pause / 2
            cuts.append({"start": words[i]["end"] + half, "end": words[i + 1]["start"] - half,
                         "reason": "dead-air", "text": f"{gap:.1f}s pause"})
            stats["pauses"] += 1
    # leading silence
    if words[0]["start"] > a.max_pause:
        cuts.append({"start": 0.0, "end": words[0]["start"] - 0.3, "reason": "dead-air", "text": "lead-in"})

    cuts = [c for c in merge(cuts) if c["end"] - c["start"] >= 0.04]
    for c in cuts:
        c["start"], c["end"] = round(c["start"], 3), round(c["end"], 3)
    saved = sum(c["end"] - c["start"] for c in cuts)
    stats["seconds_saved"] = round(saved, 1)
    stats["percent_saved"] = round(100 * saved / max(doc.get("duration") or words[-1]["end"], 1), 1)

    json.dump({"source": doc.get("source"), "cuts": cuts, "review": review, "stats": stats},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"wrote {a.out}: {len(cuts)} cuts, {stats}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Transcribe a podcast with word-level timestamps.

Backends:
  faster-whisper  (local, `pip install faster-whisper`)   -- default when installed
  openai          (OPENAI_API_KEY, model whisper-1)        -- chunked, 10-min pieces

Output: transcript.json
  {"language": "pl", "duration": 3600.0, "backend": "...",
   "segments": [{"start": s, "end": e, "text": "...",
                 "words": [{"word": "...", "start": s, "end": e, "prob": p}]}]}
plus transcript.txt with "[MM:SS] text" lines.

Whisper normally deletes disfluencies. We pass an initial prompt written WITH
fillers so the model keeps "um", "uh", "yyy", "eee" -- otherwise the cleaner
cannot find them.
"""
import argparse, json, os, shutil, subprocess, sys, tempfile, time, urllib.request, uuid

FILLER_PROMPTS = {
    "en": "Umm, so, uh, I think, like, you know... Hmm. Okay, uh, here's the thing, um.",
    "pl": "Yyy, no więc, eee, tak jakby... Mmm. No i, yyy, w sumie to, eee, chodzi o to, że...",
    "de": "Ähm, also, äh, ich meine, halt... Hmm. Ja, ähm, genau.",
    "es": "Eh, bueno, este, o sea... Mmm. Pues, eh, la cosa es que...",
    "fr": "Euh, donc, ben, en fait... Hmm. Bah, euh, voilà.",
}
DEFAULT_PROMPT = FILLER_PROMPTS["en"]


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"command failed: {' '.join(cmd)}\n{r.stderr[-2000:]}")
    return r.stdout


def probe_duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", path])
    return float(out.strip())


def to_wav16k(src, dst, start=None, dur=None):
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    if dur is not None:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-i", src, "-vn", "-ac", "1", "-ar", "16000"]
    cmd += ["-c:a", "libmp3lame", "-b:a", "48k", dst] if dst.endswith(".mp3") else ["-c:a", "pcm_s16le", dst]
    run(cmd)


# ---------------------------------------------------------------- faster-whisper
def transcribe_local(path, language, model_name, prompt):
    from faster_whisper import WhisperModel  # noqa
    device = "auto"
    compute = os.environ.get("FW_COMPUTE", "int8")
    model = WhisperModel(model_name, device=device, compute_type=compute)
    with tempfile.TemporaryDirectory() as td:
        wav = os.path.join(td, "a.wav")
        to_wav16k(path, wav)
        seg_iter, info = model.transcribe(
            wav, language=language, word_timestamps=True, initial_prompt=prompt,
            vad_filter=False,            # VAD would swallow fillers and pauses we want to see
            condition_on_previous_text=False, beam_size=5)
        segments = []
        for s in seg_iter:
            words = [{"word": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3),
                      "prob": round(w.probability, 3)} for w in (s.words or []) if w.word.strip()]
            segments.append({"start": round(s.start, 3), "end": round(s.end, 3),
                             "text": s.text.strip(), "words": words})
            print(f"\r  {fmt(s.end)} transcribed", end="", file=sys.stderr, flush=True)
        print(file=sys.stderr)
        return segments, info.language


# ---------------------------------------------------------------- OpenAI API
def _multipart(fields, file_field, file_path):
    boundary = uuid.uuid4().hex
    body = bytearray()
    for k, v in fields:
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    with open(file_path, "rb") as f:
        data = f.read()
    body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; "
             f"filename=\"{os.path.basename(file_path)}\"\r\nContent-Type: audio/mpeg\r\n\r\n").encode()
    body += data + f"\r\n--{boundary}--\r\n".encode()
    return bytes(body), boundary


def _openai_chunk(mp3, language, prompt, key, retries=4):
    fields = [("model", "whisper-1"), ("response_format", "verbose_json"),
              ("timestamp_granularities[]", "word"), ("timestamp_granularities[]", "segment"),
              ("prompt", prompt)]
    if language:
        fields.append(("language", language))
    body, boundary = _multipart(fields, "file", mp3)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                "https://api.openai.com/v1/audio/transcriptions", data=body, method="POST",
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": f"multipart/form-data; boundary={boundary}"})
            with urllib.request.urlopen(req, timeout=600) as r:
                txt = r.read().decode()
            if txt.strip():
                return json.loads(txt)
        except Exception as e:  # network flake / empty body: retry sequentially
            print(f"  retry {attempt+1}: {e}", file=sys.stderr)
        time.sleep(2 * (attempt + 1))
    sys.exit("OpenAI transcription failed repeatedly")


def transcribe_openai(path, language, prompt, chunk=600):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("OPENAI_API_KEY not set")
    total = probe_duration(path)
    segments, lang = [], language
    with tempfile.TemporaryDirectory() as td:
        off = 0.0
        while off < total:
            mp3 = os.path.join(td, f"c{int(off)}.mp3")
            to_wav16k(path, mp3, start=off, dur=chunk)
            res = _openai_chunk(mp3, language, prompt, key)
            lang = lang or res.get("language")
            words = res.get("words", [])
            for s in res.get("segments", []):
                ws = [{"word": w["word"].strip(), "start": round(w["start"] + off, 3),
                       "end": round(w["end"] + off, 3), "prob": None}
                      for w in words if w["start"] >= s["start"] - 0.05 and w["end"] <= s["end"] + 0.05]
                segments.append({"start": round(s["start"] + off, 3), "end": round(s["end"] + off, 3),
                                 "text": s["text"].strip(), "words": ws})
            print(f"  chunk @{fmt(off)} done", file=sys.stderr)
            off += chunk
    # de-duplicate words claimed by two adjacent segments
    seen = set()
    for s in segments:
        keep = []
        for w in s["words"]:
            k = (w["start"], w["word"])
            if k not in seen:
                seen.add(k); keep.append(w)
        s["words"] = keep
    return segments, lang


def fmt(t):
    t = int(t)
    return f"{t//3600}:{t%3600//60:02d}:{t%60:02d}" if t >= 3600 else f"{t//60:02d}:{t%60:02d}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio")
    ap.add_argument("--out", default="transcript.json")
    ap.add_argument("--language", default=None, help="ISO code, e.g. en, pl. Omit to auto-detect")
    ap.add_argument("--backend", choices=["auto", "faster-whisper", "openai"], default="auto")
    ap.add_argument("--model", default="small", help="faster-whisper model (small, medium, large-v3)")
    ap.add_argument("--prompt", default=None, help="override the filler-preserving prompt")
    a = ap.parse_args()

    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found on PATH")
    prompt = a.prompt or FILLER_PROMPTS.get((a.language or "en")[:2], DEFAULT_PROMPT)

    backend = a.backend
    if backend == "auto":
        try:
            import faster_whisper  # noqa
            backend = "faster-whisper"
        except ImportError:
            backend = "openai" if os.environ.get("OPENAI_API_KEY") else None
    if backend is None:
        sys.exit("No transcription backend. `pip install faster-whisper` or set OPENAI_API_KEY.")

    print(f"Transcribing with {backend} ...", file=sys.stderr)
    if backend == "faster-whisper":
        segments, lang = transcribe_local(a.audio, a.language, a.model, prompt)
    else:
        segments, lang = transcribe_openai(a.audio, a.language, prompt)

    doc = {"source": os.path.abspath(a.audio), "language": lang, "backend": backend,
           "duration": probe_duration(a.audio), "segments": segments}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    txt = os.path.splitext(a.out)[0] + ".txt"
    with open(txt, "w", encoding="utf-8") as f:
        for s in segments:
            f.write(f"[{fmt(s['start'])}] {s['text']}\n")
    nwords = sum(len(s["words"]) for s in segments)
    print(f"wrote {a.out} ({len(segments)} segments, {nwords} words, lang={lang}) and {txt}")


if __name__ == "__main__":
    main()

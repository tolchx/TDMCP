#!/usr/bin/env python3
"""fetch_youtube_transcripts.py — baja transcripts de tutoriales de YouTube a la KB local.

Escribe un `.txt` por video en `--out` (por defecto `knowledge/kb/tutorials/pop_tutorial/`)
con el mismo formato que los transcripts ya versionados localmente:

    # <titulo>
    - video: https://www.youtube.com/watch?v=<id>
    - duration: HH:MM:SS
    - transcript source: YouTube captions (<lang>), timestamps every ~30s
    - extracted: <fecha> con youtube-transcript-api

    [HH:MM:SS] texto del bloque ...

Usa `youtube-transcript-api` para el transcript (funciona cuando yt-dlp da HTTP 429) y
`yt-dlp` sólo para metadata (`--skip-download --print`). Si falta la metadata, cae al
título del manifest.

Uso:
    python tools/fetch_youtube_transcripts.py ID [ID ...]
    python tools/fetch_youtube_transcripts.py --manifest manifest.json
    python tools/fetch_youtube_transcripts.py --out DIR --prefix pop ID [ID ...]

Manifest (JSON): [{ "index": 1, "id": "abc12345678", "title": "...", "series": "..." }, ...]

Salida además: `<out>/INDEX.json` con lo bajado (id, título, duración, palabras, archivo).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import subprocess
import sys

BUCKET = 30.0  # segundos por bloque con timestamp
LANGS = ["en", "en-US", "en-GB", "en-orig", "es", "es-AR"]


def fetch_segments(video_id: str):
    """Devuelve (lang, [{'text','start'}...]) o lanza."""
    from youtube_transcript_api import YouTubeTranscriptApi

    api = YouTubeTranscriptApi()
    result = api.fetch(video_id, languages=LANGS)
    lang = getattr(result, "language_code", None) or "en"
    segs = [{"text": s.text, "start": float(s.start)} for s in result]
    # limpiar artefactos de auto-captions
    for s in segs:
        s["text"] = re.sub(r"\[(?:music|applause|laughter|música|aplausos)\]",
                           " ", s["text"], flags=re.I)
        s["text"] = re.sub(r"\s+", " ", s["text"]).strip()
    return lang, [s for s in segs if s["text"]]


def ytdlp_meta(video_id: str):
    """Metadata vía yt-dlp (best-effort). Devuelve dict o {}."""
    exe = os.environ.get("YTDLP", "yt-dlp")
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        out = subprocess.run(
            [exe, "--skip-download", "--no-warnings", "--print",
             "%(title)s\t%(duration)s\t%(uploader)s\t%(upload_date)s", url],
            capture_output=True, text=True, timeout=90,
        )
    except Exception:
        return {}
    line = (out.stdout or "").strip().splitlines()
    if not line:
        return {}
    parts = line[-1].split("\t")
    if len(parts) < 4:
        return {}
    title, dur, uploader, date = parts[:4]
    try:
        dur = int(float(dur))
    except ValueError:
        dur = 0
    return {"title": title, "duration": dur, "channel": uploader, "upload_date": date}


def hms(seconds) -> str:
    seconds = int(seconds or 0)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def bucketize(segments):
    """Agrupa segmentos en bloques de ~BUCKET s, devolviendo (t_start, texto)."""
    buckets, cur_start, cur = None, None, []
    out = []
    for s in segments:
        if cur_start is None:
            cur_start = s["start"]
        if s["start"] - cur_start >= BUCKET and cur:
            out.append((cur_start, " ".join(cur)))
            cur, cur_start = [], s["start"]
        cur.append(s["text"])
    if cur:
        out.append((cur_start, " ".join(cur)))
    return out


def render(video_id, title, series, lang, duration, segments, extracted):
    lines = [f"# {title}"]
    if series:
        lines.append(f"- series: {series}")
    lines.append(f"- video: https://www.youtube.com/watch?v={video_id}")
    lines.append(f"- duration: {hms(duration)}")
    lines.append(f"- transcript source: YouTube captions ({lang}), timestamps every ~{int(BUCKET)}s")
    lines.append(f"- extracted: {extracted} con youtube-transcript-api")
    lines.append("")
    for start, text in bucketize(segments):
        lines.append(f"[{hms(start)}] {text}")
    lines.append("")
    return "\n".join(lines)


def slug(s: str, n: int = 60) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s[:n]


def load_manifest(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        data = data.get("videos", [])
    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="*", help="video IDs (11 chars)")
    ap.add_argument("--manifest", help="JSON con [{index,id,title,series}]")
    ap.add_argument("--out", default=os.path.join("knowledge", "kb", "tutorials", "pop_tutorial"),
                    help="directorio de salida")
    ap.add_argument("--prefix", default="", help="prefijo de archivo (ej. 'pop')")
    ap.add_argument("--no-meta", action="store_true", help="no llamar a yt-dlp")
    args = ap.parse_args()

    items = []
    if args.manifest:
        for it in load_manifest(args.manifest):
            items.append({"index": it.get("index"), "id": it["id"],
                          "title": it.get("title", ""), "series": it.get("series", "")})
    for vid in args.ids:
        items.append({"index": None, "id": vid, "title": "", "series": ""})
    if not items:
        ap.error("pasá al menos un ID o --manifest")

    os.makedirs(args.out, exist_ok=True)
    extracted = _dt.date.today().isoformat()
    index, ok, fail = [], 0, 0

    for pos, it in enumerate(items, 1):
        vid = it["id"]
        meta = {} if args.no_meta else ytdlp_meta(vid)
        title = meta.get("title") or it["title"] or vid
        duration = meta.get("duration", 0)
        try:
            lang, segs = fetch_segments(vid)
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] {vid} {title[:50]!r}: {type(exc).__name__}: {exc}", file=sys.stderr)
            fail += 1
            continue
        words = sum(len(s["text"].split()) for s in segs)
        num = it["index"] if it["index"] is not None else pos
        fname = f"{int(num):02d}_{vid}.txt"
        if args.prefix:
            fname = f"{args.prefix}_{fname}"
        path = os.path.join(args.out, fname)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(render(vid, title, it["series"], lang, duration, segs, extracted))
        index.append({"index": num, "id": vid, "title": title, "series": it["series"],
                      "channel": meta.get("channel", ""), "duration": duration,
                      "duration_hms": hms(duration), "words": words, "segments": len(segs),
                      "lang": lang, "file": os.path.basename(path)})
        print(f"[OK] {fname}  {hms(duration)}  {words} words  {lang}  {title[:60]}")
        ok += 1

    ipath = os.path.join(args.out, "INDEX.json")
    prev = []
    if os.path.exists(ipath):
        try:
            with open(ipath, encoding="utf-8") as fh:
                prev = json.load(fh).get("transcripts", [])
        except Exception:
            prev = []
    merged = {t["id"]: t for t in prev}
    for t in index:
        merged[t["id"]] = t
    with open(ipath, "w", encoding="utf-8") as fh:
        json.dump({"count": len(merged), "transcripts": sorted(merged.values(),
                  key=lambda t: (t["series"] or "", t["index"]))}, fh, ensure_ascii=False, indent=2)
    print(f"\n{ok} ok, {fail} fail · índice: {ipath}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

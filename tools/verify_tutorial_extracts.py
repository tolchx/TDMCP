#!/usr/bin/env python3
"""verify_tutorial_extracts.py — verifica que cada cita de un extracto exista en su transcript.

Los extractos (`_extract_<video_id>.json`) los producen subagentes que leen los transcripts de
`knowledge/kb/tutorials/**`. Este script es la parte mecánica de la QA: por cada `quote` de cada
extracto, comprueba que el texto aparezca (normalizado: minúsculas, sin puntuación, espacios
colapsados) en el `.txt` correspondiente. Nada de "el subagente dice que lo leyó": substring real
o falla.

Uso:
  python tools/verify_tutorial_extracts.py --dir knowledge/kb/tutorials/pop_2026
  python tools/verify_tutorial_extracts.py --dir ... --strict   # exit 1 si alguna cita falla

Nota: las captions automáticas tienen errores ("Jello Cell" = glslPOP, "gouge and splatting" =
gaussian splatting). Una cita que falla puede ser (a) invención del extractor o (b) cita
parafraseada — el reporte muestra la cita para que lo decidas a mano; NO reescribe nada.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]


TS_RE = re.compile(r"\[\d{1,3}:\d{2}:\d{2}\]|\b\d{1,3}:\d{2}:\d{2}\b")


def norm(s: str) -> str:
    """Minúsculas, sin puntuación, sin marcas de tiempo y con espacios colapsados.

    Las marcas `[HH:MM:SS]` se quitan de AMBOS lados: una cita que cruza el borde de un bloque
    de 30 s trae el marcador en el medio del transcript y, sin quitarlo, la comparación por
    substring da un falso negativo.
    """
    s = TS_RE.sub(" ", s)
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def iter_quotes(obj, path=""):
    """Devuelve (ruta, cita, timestamp) para cada clave 'quote' del JSON anidado."""
    if isinstance(obj, dict):
        q = obj.get("quote")
        if isinstance(q, str) and q.strip():
            yield path, q.strip(), str(obj.get("t", obj.get("timestamp", "")) or "")
        for k, v in obj.items():
            yield from iter_quotes(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from iter_quotes(v, f"{path}[{i}]")


def main() -> int:
    ap = argparse.ArgumentParser(description="Verifica citas de extractos contra su transcript")
    ap.add_argument("--dir", default=str(ROOT / "knowledge" / "kb" / "tutorials" / "pop_2026"),
                    help="carpeta con los _extract_*.json y los pop_*.txt")
    ap.add_argument("--strict", action="store_true", help="exit 1 si alguna cita no aparece")
    ap.add_argument("--show", type=int, default=6, help="cuántas citas fallidas imprimir por archivo")
    args = ap.parse_args()

    d = Path(args.dir)
    extracts = sorted(d.glob("_extract_*.json"))
    if not extracts:
        print(f"verify_tutorial_extracts: sin extractos en {d}")
        return 0

    total = ok = 0
    for ex in extracts:
        data = json.loads(ex.read_text(encoding="utf-8"))
        tname = data.get("file") or ""
        tf = d / tname
        if not tf.exists():  # fallback: el id está en el nombre del extracto
            vid = ex.stem.replace("_extract_", "")
            cands = list(d.glob(f"*{vid}.txt"))
            tf = cands[0] if cands else None
        if tf is None or not tf.exists():
            print(f"[?] {ex.name}: no encontré el transcript ({tname!r})")
            continue
        txt = norm(tf.read_text(encoding="utf-8"))
        n = bad = 0
        fails = []
        for path, quote, ts in iter_quotes(data):
            n += 1
            if norm(quote) in txt:
                ok += 1
            else:
                bad += 1
                fails.append((path, quote, ts))
        total += n
        pct = (100.0 * (n - bad) / n) if n else 100.0
        print(f"[{'OK ' if bad == 0 else 'WARN'}] {ex.name}: {n - bad}/{n} citas verificadas ({pct:.0f}%)"
              f" <- {tf.name}")
        for path, quote, ts in fails[: args.show]:
            print(f"      ✗ {ts} {path}: {quote[:150]}")

    pct = (100.0 * ok / total) if total else 100.0
    print(f"\nverify_tutorial_extracts: {ok}/{total} citas verificadas ({pct:.0f}%)")
    if args.strict and ok != total:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

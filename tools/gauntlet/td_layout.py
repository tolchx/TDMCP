#!/usr/bin/env python3
"""td_layout.py — layout determinista de redes POP y auditoria de solapamiento.

Regla del harness: ningun nodo de una red de prueba queda encima de otro. El layout
separa por PROFUNDIDAD de conexiones (fuentes a la izquierda, consumidores a la
derecha) y apila los nodos de la misma profundidad en filas. Para un `poptoCHOP`
tambien cuenta el `par.pop`, que es un enlace de parametro, no un cable.

`tidy()` es la unica implementacion del layout (host -> TD); la usan el build de
mathcombine y `layout_pop.py` para auditar todas las redes `/pop_*`.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gauntlet_client import Gauntlet  # noqa: E402

LAYOUT_SRC = r'''
import json

def _rows_of(parent):
    return [dict(name=ch.name, x=float(ch.nodeX), y=float(ch.nodeY),
                 w=float(ch.nodeWidth), h=float(ch.nodeHeight)) for ch in parent.children]


def _overlaps(rows):
    out = []
    for i in range(len(rows)):
        a = rows[i]
        for j in range(i + 1, len(rows)):
            b = rows[j]
            if (a['x'] < b['x'] + b['w'] and a['x'] + a['w'] > b['x'] and
                    a['y'] < b['y'] + b['h'] and a['y'] + a['h'] > b['y']):
                out.append([a['name'], b['name']])
    return out


def _tidy(parent):
    kids = list(parent.children)
    if not kids:
        return dict(parent=parent.path, n=0, overlaps=[], rows=[])

    paths = {ch.path for ch in kids}

    def ins_of(ch):
        ins = [i for i in (ch.inputs or []) if i is not None and i.path in paths]
        # poptoCHOP / poptoTOP: el POP se enlaza por parametro, no por cable.
        try:
            p = ch.par.pop.eval()
            if p is not None and p.path in paths and p.path not in {i.path for i in ins}:
                ins.append(p)
        except Exception:
            pass
        return ins

    maxw = max(float(ch.nodeWidth) for ch in kids)
    maxh = max(float(ch.nodeHeight) for ch in kids)
    cw = max(190.0, maxw + 60.0)
    chh = max(140.0, maxh + 50.0)
    memo = {}

    def dep(ch, stack):
        p = ch.path
        if p in memo:
            return memo[p]
        if p in stack:
            return 0
        stack.add(p)
        ins = ins_of(ch)
        d = 0 if not ins else 1 + max(dep(i, stack) for i in ins)
        stack.discard(p)
        memo[p] = d
        return d

    groups = {}
    for ch in kids:
        groups.setdefault(dep(ch, set()), []).append(ch)

    for d in sorted(groups):
        for row, ch in enumerate(sorted(groups[d], key=lambda x: x.name)):
            ch.nodeX = d * cw
            ch.nodeY = -row * chh

    rows = _rows_of(parent)
    return dict(parent=parent.path, n=len(kids), overlaps=_overlaps(rows), rows=rows)


def _walk(parent, seen):
    if parent.path in seen:
        return []
    seen.add(parent.path)
    out = [_tidy(parent)]
    for ch in parent.children:
        if getattr(ch, 'isCOMP', False):
            out += _walk(ch, seen)
    return out


results = []
if ROOTS:
    for p in ROOTS:
        try:
            results += _walk(op(p), set())
        except Exception as e:
            results.append(dict(parent=p, n=0, overlaps=[], error=repr(e), rows=[]))
else:
    for o in op('/').children:
        if o.type == 'base' and o.name.startswith(PREFIX):
            results += _walk(o, set())

total = sum(len(r.get('overlaps') or []) for r in results)
print('<<JSON>>' + json.dumps(dict(parents=results, total=total)))
'''


SNAPSHOT_SRC = r'''
import json


def _rows_of(parent):
    return [dict(name=ch.name, x=float(ch.nodeX), y=float(ch.nodeY),
                 w=float(ch.nodeWidth), h=float(ch.nodeHeight)) for ch in parent.children]


def _overlaps(rows):
    out = []
    for i in range(len(rows)):
        a = rows[i]
        for j in range(i + 1, len(rows)):
            b = rows[j]
            if (a['x'] < b['x'] + b['w'] and a['x'] + a['w'] > b['x'] and
                    a['y'] < b['y'] + b['h'] and a['y'] + a['h'] > b['y']):
                out.append([a['name'], b['name']])
    return out


def _walk(parent, seen):
    if parent.path in seen:
        return []
    seen.add(parent.path)
    rows = _rows_of(parent)
    out = [dict(parent=parent.path, rows=rows, overlaps=_overlaps(rows))]
    for ch in parent.children:
        if getattr(ch, 'isCOMP', False):
            out += _walk(ch, seen)
    return out


results = []
if ROOTS:
    for p in ROOTS:
        try:
            results += _walk(op(p), set())
        except Exception as e:
            results.append(dict(parent=p, rows=[], overlaps=[], error=repr(e)))
else:
    for o in op('/').children:
        if o.type == 'base' and o.name.startswith(PREFIX):
            results += _walk(o, set())

total = sum(len(r.get('overlaps') or []) for r in results)
print('<<JSON>>' + json.dumps(dict(parents=results, total=total)))
'''


def snapshot(g: Gauntlet, roots: list[str] | None = None, prefix: str = "pop_") -> tuple[bool, dict]:
    """Lee posiciones sin mover nada. Es la foto que usa el test de persistencia.

    No reutiliza `tidy()`: si el test reacomodara la red antes de comparar,
    enmascararía justamente lo que tiene que detectar (que el guardado no tomó).
    """
    code = ("ROOTS = %s\nPREFIX = %r\n%s" %
            (json.dumps(roots) if roots else "None", prefix, SNAPSHOT_SRC))
    ok, data = g.exec_code(code)
    if not ok:
        return False, data or {}
    return True, data


def fingerprint(data: dict) -> tuple[str, int]:
    """SHA-256 estable de (red, nodo, x, y), redondeado a 2 decimales."""
    flat = []
    for p in data.get("parents") or []:
        for r in p.get("rows") or []:
            flat.append([p.get("parent"), r.get("name"),
                         round(float(r.get("x", 0)), 2), round(float(r.get("y", 0)), 2)])
    flat.sort()
    blob = json.dumps(flat, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest(), len(flat)


def tidy(g: Gauntlet, roots: list[str] | None = None, prefix: str = "pop_") -> tuple[bool, dict]:
    """Reacomoda los hijos de roots (o de todos los /<prefix>*) y verifica solapamiento.

    Devuelve (ok, data). `ok` exige que TODAS las redes hayan quedado sin pares
    solapados; `data['total']` es la suma de pares solapados.
    """
    code = ("ROOTS = %s\nPREFIX = %r\n%s" %
            (json.dumps(roots) if roots else "None", prefix, LAYOUT_SRC))
    ok, data = g.exec_code(code)
    if not ok:
        return False, data or {}
    return data.get("total") == 0, data


def main() -> int:
    run = os.environ.get("GAUNTLET_RUN_ID") or time.strftime("%Y%m%d-%H%M%S")
    g = Gauntlet(phase="layout-pop", run_id=run)
    g.init()
    ok, data = tidy(g)
    parents = data.get("parents") or []
    total = data.get("total")
    print("layout: %d redes, %d pares solapados" % (len(parents), total if total is not None else -1))
    bad = [p for p in parents if p.get("overlaps")]
    for p in bad:
        print("  SOLAPA %s: %s" % (p.get("parent"), p["overlaps"][:8]))
    for p in parents:
        if p.get("error"):
            print("  ERROR %s: %s" % (p.get("parent"), p["error"]))
    report = dict(run_id=run, ok=bool(ok), total=total, parents=parents,
                  phase="layout-pop")
    os.makedirs(g.out_dir, exist_ok=True)
    path = os.path.join(g.out_dir, "layout-pop-report.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("Reporte:", path)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

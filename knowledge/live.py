#!/usr/bin/env python3
r"""live.py — tools de td-knowledge que necesitan TouchDesigner.

No hay bridge: se habla MCP contra el server OFICIAL de Derivative
(`127.0.0.1:13316/mcp`), que corre dentro de TD. Si TD no está abierto, estas
tools devuelven un error claro y las offline siguen funcionando.

Env: TDMCP_URL (default http://127.0.0.1:13316/mcp), TDMCP_TIMEOUT (default 60).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

URL = os.environ.get("TDMCP_URL", "http://127.0.0.1:13316/mcp")
TIMEOUT = float(os.environ.get("TDMCP_TIMEOUT", "60"))
_SID: str | None = None
_ID = 500


def _post(payload: dict, timeout: float | None = None) -> dict:
    global _SID
    data = json.dumps(payload).encode("utf-8")
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if _SID:
        h["Mcp-Session-Id"] = _SID
    req = urllib.request.Request(URL, data=data, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=timeout or TIMEOUT) as r:
        got = r.headers.get("Mcp-Session-Id")
        if got:
            _SID = got
        raw = r.read().decode("utf-8", "replace")
    if not raw.strip():  # notificaciones: 202 Accepted sin cuerpo
        return {}
    s = raw.lstrip()
    if s.startswith("event:") or s.startswith("data:"):
        for line in raw.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
    return json.loads(raw)


def _init() -> None:
    if _SID:
        return
    _post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
           "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                      "clientInfo": {"name": "td-knowledge", "version": "0.2.0"}}})
    _post({"jsonrpc": "2.0", "method": "notifications/initialized"})


def call(tool: str, args: dict | None = None, timeout: float | None = None) -> tuple[bool, dict]:
    """Llama una tool del MCP oficial. -> (ok, data)."""
    global _ID
    try:
        _init()
    except Exception as e:  # TD cerrado, .tox sin activar, puerto ocupado...
        return False, {"error": f"TouchDesigner no responde en {URL} ({type(e).__name__}: {e})",
                       "hint": "abrí TouchDesigner con el .tox TDMCP en el root y pulsá Active en su página MCP"}
    _ID += 1
    try:
        r = _post({"jsonrpc": "2.0", "id": _ID, "method": "tools/call",
                   "params": {"name": tool, "arguments": args or {}}}, timeout)
    except Exception as e:
        return False, {"error": f"falló {tool}: {type(e).__name__}: {e}"}
    if "error" in r:
        return False, {"error": "error MCP", "detail": r["error"]}
    res = r.get("result") or {}
    txt = "".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
    bad = bool(res.get("isError")) or txt.lstrip().startswith("*** isError=true ***")
    txt = txt.replace("*** isError=true ***", "").strip()
    try:
        data = json.loads(txt) if txt else {}
    except Exception:
        data = {"raw": txt}
    return (not bad), data


MARK = "<<JSON>>"


def exec_code(code: str, timeout: float | None = None) -> tuple[bool, dict]:
    """Corre Python dentro de TD y devuelve el JSON que imprimió tras MARK."""
    ok, d = call("execute_code", {"code": code}, timeout)
    if not ok:
        return False, d
    out = d.get("output", "") or ""
    if MARK not in out:
        return False, {"error": "el código no devolvió el marcador", "output": out[:500], "variables": list(d.get("variables", {}))}
    try:
        return True, json.loads(out.split(MARK, 1)[1].strip())
    except Exception as e:
        return False, {"error": f"payload ilegible: {e}", "output": out[:500]}


# ── 1. status ────────────────────────────────────────────────────────────────

def t_status(a: dict) -> dict:
    ok, d = call("project_info", {}, timeout=15)
    if not ok:
        return {"td_up": False, **d}
    return {"td_up": True, "url": URL, "project": d.get("name"), "folder": d.get("folder"),
            "saveBuild": d.get("saveBuild"), "cookRate": d.get("cookRate"),
            "serverVersion": d.get("serverVersion"), "performMode": d.get("performMode")}


# ── 2. find_in_ops ───────────────────────────────────────────────────────────

_FIND = r'''
import json
q = __Q__; root = op(__ROOT__); o = __OPTS__
res = {"query": q, "root": root.path, "matches": [], "scanned": 0, "truncated": False}
def push(m):
    res['matches'].append(m)
    return len(res['matches']) >= o['limit']
def scan(x):
    if res['truncated']: return
    res['scanned'] += 1
    if o['in_name'] and q.lower() in x.name.lower():
        push({"op": x.path, "where": "name", "text": x.name})
    if o['in_comment'] and q.lower() in str(getattr(x, 'comment', '') or '').lower():
        push({"op": x.path, "where": "comment", "text": str(x.comment)[:200]})
    for p in x.pars():
        if o['in_name'] and q.lower() in p.name.lower():
            push({"op": x.path, "where": "par_name", "text": p.name})
            if res['truncated']: return
        if o['in_expr']:
            try:
                if str(p.mode).endswith('EXPRESSION') and q.lower() in str(p.expr or '').lower():
                    push({"op": x.path, "where": "expr", "text": "%s = %s" % (p.name, str(p.expr)[:200]), "expr": str(p.expr)})
                    if res['truncated']: return
            except Exception: pass
    if x.family == 'DAT' and o['in_dat']:
        try:
            txt = x.text if getattr(x, 'isText', False) else "\n".join(["\t".join(r) for r in x.rows()])
        except Exception:
            txt = ''
        for i, line in enumerate(txt.splitlines(), 1):
            if q.lower() in line.lower():
                if push({"op": x.path, "where": "dat", "line": i, "text": line[:200]}): break
    if x.family == 'COMP':
        for c in x.children:
            scan(c)
            if res['truncated']: return
scan(root)
if len(res['matches']) >= o['limit']: res['truncated'] = True
print('<<JSON>>' + json.dumps(res))
'''


def t_find_in_ops(a: dict) -> dict:
    q = str(a.get("query") or "").strip()
    if not q:
        return {"error": "falta 'query'"}
    opts = {"limit": int(a.get("limit") or 40), "in_dat": a.get("in_dat", True) is not False,
            "in_expr": a.get("in_expr", True) is not False, "in_name": a.get("in_name", False) is True,
            "in_comment": a.get("in_comment", True) is not False}
    code = (_FIND.replace("__Q__", repr(q)).replace("__ROOT__", repr(str(a.get("root_path") or "/")))
            .replace("__OPTS__", repr(opts)))
    return exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))


# ── 3. auto_layout ───────────────────────────────────────────────────────────

_GRAPH = r'''
import json
root = op(__ROOT__); o = __OPTS__
nodes = []
def walk(x, depth):
    for c in x.children:
        if c.name.startswith('.'): continue
        ins = []
        try:
            for i, conn in enumerate(c.inputConnectors):
                for cc in conn.connections:
                    ins.append([i, cc.owner.name])
        except Exception: pass
        nodes.append({"name": c.name, "type": getattr(c, 'OPType', c.type), "family": c.family,
                      "y": c.nodeY, "x": c.nodeX, "inputs": ins})
        if c.family == 'COMP' and depth < o['depth']:
            walk(c, depth + 1)
walk(root, 0)
print('<<JSON>>' + json.dumps({"parent": root.path, "nodes": nodes}))
'''


def t_auto_layout(a: dict) -> dict:
    parent = str(a.get("parent_path") or "/")
    direction = str(a.get("direction") or "lr").lower()
    hgap = int(a.get("hgap") or 175)
    vgap = int(a.get("vgap") or 130)
    code = _GRAPH.replace("__ROOT__", repr(parent)).replace("__OPTS__", repr({"depth": 0}))
    ok, g = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    if not ok:
        return g
    nodes = g.get("nodes") or []
    if not nodes:
        return {"ok": False, "error": f"{parent} no tiene operadores"}
    names = {n["name"] for n in nodes}
    # capas por camino más largo (sólo entre hermanos directos)
    level = {n["name"]: 0 for n in nodes}
    srcs = {n["name"]: [s for _i, s in n["inputs"] if s in names] for n in nodes}
    for _ in range(len(nodes) + 1):
        changed = False
        for nm, ss in srcs.items():
            want = max([level[s] + 1 for s in ss], default=0)
            if want > level[nm]:
                level[nm] = want; changed = True
        if not changed:
            break
    # orden dentro de la capa: media de las capas de sus fuentes, luego el nodeY original
    order: dict[int, list] = {}
    for n in nodes:
        order.setdefault(level[n["name"]], []).append(n)
    for lv, group in order.items():
        group.sort(key=lambda n: (sum(level[s] for s in srcs[n["name"]]) / max(1, len(srcs[n["name"]])), n["y"], n["x"], n["name"]))
    positions, moved = {}, []
    for lv, group in sorted(order.items()):
        for lane, n in enumerate(group):
            x, y = (lv * hgap, lane * vgap) if direction == "lr" else (lane * hgap, lv * vgap)
            positions[n["name"]] = [int(x), int(y)]
            if [int(n["x"]), int(n["y"])] != [int(x), int(y)]:
                moved.append(n["name"])
    if a.get("dry_run"):
        return {"ok": True, "dry_run": True, "parent": parent, "nodes": len(nodes),
                "levels": max(level.values()) + 1, "positions": positions, "moved": moved}
    ok2, r = call("reposition_operators", {"parent_path": parent, "positions": positions,
                                           "include_docked": a.get("include_docked", True) is not False})
    if not ok2:
        return {"ok": False, "error": "el layout se calculó pero TP rechazó el move", "detail": r, "positions": positions}
    return {"ok": True, "parent": parent, "nodes": len(nodes), "levels": max(level.values()) + 1,
            "moved": len(moved), "result": r}


# ── 4. smart_connect ─────────────────────────────────────────────────────────

_FAM = ("TOP", "CHOP", "SOP", "DAT", "COMP", "POP", "MAT")


def _kb_inputs(op_type: str) -> tuple[list[str], str]:
    """Familias que acepta el tipo según la KB (texto de 'inputs' del doc del operador)."""
    kb = os.environ.get("TD_KNOWLEDGE_KB") or ""
    if not kb:
        return [], ""
    import glob
    stem = op_type.lower()
    for fp in glob.glob(os.path.join(kb, "ops", "operators", "*", "*.json")):
        try:
            with open(fp, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        guess = str(d.get("tdOpTypeGuess") or "").lower()
        slug = str(d.get("pageSlug") or "").replace("_", "").lower()
        if stem in (guess, slug) or stem.replace("top", "") == guess.replace("top", ""):
            txt = d.get("inputs")
            blob = json.dumps(txt, ensure_ascii=False) if not isinstance(txt, str) else txt
            fams = [f for f in _FAM if f in blob.upper()]
            return fams, blob[:400]
    return [], ""


def _doc_inputs(op_type: str) -> tuple[list[str], str]:
    """Fallback: pide la página del operador al MCP oficial (docs del build instalado)
    y saca las familias mencionadas en la sección de inputs."""
    ok, d = call("get_docs", {"query": op_type}, timeout=25)
    if not ok:
        return [], ""
    txt = json.dumps(d, ensure_ascii=False)
    i = txt.find("Inputs")
    sec = txt[i:i + 900] if i >= 0 else txt[:900]
    up = sec.upper()
    return [f for f in _FAM if f in up], sec[:400]


def t_smart_connect(a: dict) -> dict:
    src = str(a.get("from_path") or "")
    dst = str(a.get("to_path") or "")
    if not src or not dst:
        return {"error": "hacen falta 'from_path' y 'to_path'"}
    ok1, si = call("get_operator_info", {"path": src}, timeout=20)
    ok2, di = call("get_operator_info", {"path": dst}, timeout=20)
    if not (ok1 and ok2):
        return {"error": "no pude leer alguno de los operadores", "from": si if not ok1 else "ok", "to": di if not ok2 else "ok"}
    sf, df = si.get("family"), di.get("family")
    st, dt = si.get("type"), di.get("type")
    want = int(a["input_index"]) if a.get("input_index") is not None else None
    fams, kbtext = _kb_inputs(str(dt))
    origen = "KB"
    if not fams:                      # la KB no lo documenta → preguntar a los docs del build
        fams, kbtext = _doc_inputs(str(dt))
        origen = "docs del build"
    reasoning = []
    if want is None:
        if fams and sf in fams:
            want = fams.index(sf)
            reasoning.append(f"{dt} acepta {fams} ({origen}) → índice {want}")
        else:
            want = 0
            reasoning.append(f"sin certeza de la familia esperada por {dt}"
                             + (f" (según {origen}: {fams})" if fams else f" (ni la KB ni los {origen} lo documentan)"))
    ok3, r = call("wiring", {"from_path": src, "to_path": dst, "to_index": want})
    out = {"from": f"{src} ({st}/{sf})", "to": f"{dst} ({dt}/{df})", "to_index": want,
           "reasoning": reasoning, "kb_inputs": fams}
    if ok3:
        out["ok"] = True; out["result"] = r
    else:
        out["ok"] = False; out["error"] = r
        if kbtext:
            out["kb_inputs_text"] = kbtext
        if fams and sf not in fams:
            out["hint"] = (f"el destino {dt} acepta {fams} y el origen es {sf}: probablemente no se pueda "
                           "cablear directo (hace falta un convert/adaptador intermedio)")
        else:
            out["hint"] = "probá otro input_index, o mirá mcp_tdmcp_get_help del tipo destino"
    return out


# ── 5. TDN export ────────────────────────────────────────────────────────────

_TDN = r'''
import json, datetime
root = op(__ROOT__); o = __OPTS__
VOLATIL_NO = 0
def pars(x):
    out = {}
    for p in x.pars():
        try:
            if p.isDefault: continue
            if str(p.mode).endswith('EXPRESSION'):
                out[p.name] = {'expr': str(p.expr)}
            elif str(getattr(p, 'style', '')) == 'Pulse':
                continue
            else:
                v = p.eval()
                out[p.name] = v if isinstance(v, (int, float, bool, str)) else str(v)
        except Exception:
            continue
    return out
def flg(x):
    f = []
    for n in ('bypass', 'lock', 'display', 'render', 'viewer', 'expose', 'allowCooking'):
        try:
            v = getattr(x, n, None)
            if v is None: continue
            f.append(n if v else '-' + n)
        except Exception: pass
    return f
def cpars(x):
    out = []
    for p in getattr(x, 'customPars', []) or []:
        try:
            out.append({'name': p.name, 'style': str(getattr(p, 'style', '')), 'label': str(getattr(p, 'label', ''))})
        except Exception: pass
    return out
def node(x):
    d = {'name': x.name, 'type': getattr(x, 'OPType', x.type)}
    try: d['position'] = [int(x.nodeX), int(x.nodeY)]
    except Exception: pass
    try: d['size'] = [int(x.nodeWidth), int(x.nodeHeight)]
    except Exception: pass
    try:
        # el color del nodo puede cambiar solo entre exports (TD lo re-deriva) → opt-in para no ensuciar el diff
        if o.get('include_color') and str(x.color) != 'None':
            d['color'] = [round(float(v), 4) for v in x.color]
    except Exception: pass
    try:
        if x.comment: d['comment'] = x.comment
    except Exception: pass
    try:
        if len(x.tags): d['tags'] = sorted(x.tags)
    except Exception: pass
    if x.parent() and x.parent().family == 'COMP':
        for dn in getattr(x.parent(), 'docked', []) or []:
            if dn.name == x.name: d['dock'] = x.parent().name
    f = flg(x)
    if f: d['flags'] = f
    ps = pars(x)
    if ps: d['parameters'] = ps
    cp = cpars(x)
    if cp: d['custom_pars'] = cp
    if o['include_storage']:
        try:
            st = {k: (v if isinstance(v, (int, float, bool, str, list, dict)) else str(v)) for k, v in x.storage.items()}
            if st: d['storage'] = st
        except Exception: pass
    try:
        if x.family == 'DAT':
            if getattr(x, 'isText', False):
                d['dat_content'], d['dat_content_format'] = x.text, 'text'
            elif getattr(x, 'isTable', False):
                d['dat_content'], d['dat_content_format'] = [[str(c) for c in r] for r in x.rows()], 'table'
    except Exception: pass
    try:
        if x.family != 'DAT':
            ins = []
            for conn in x.inputConnectors:
                ins.append(conn.connections[0].owner.name if conn.connections else None)
            if any(i is not None for i in ins): d['inputs'] = ins
    except Exception: pass
    if x.family == 'COMP':
        kids = [node(c) for c in x.children if not c.name.startswith('__')]
        if kids: d['children'] = kids
    return d
if o['include_dat_content'] is False:
    pass
ops = [node(c) for c in root.children if not c.name.startswith('__')]
doc = {'format': 'tdn', 'version': '1.4', 'generator': 'td-knowledge/tdn_export',
       'build': (int(app.build) if str(getattr(app, 'build', '')).isdigit() else None),
       'td_build': str(getattr(app, 'build', '') or getattr(app, 'version', '')),
       'exported_at': datetime.datetime.now().isoformat(timespec='seconds'),
       'network_path': root.path, 'options': {'include_dat_content': bool(o['include_dat_content']),
                                             'include_storage': bool(o['include_storage'])},
       'operators': ops}
print('<<JSON>>' + json.dumps(doc))
'''

_TDN_VOLATILE = ("build", "generator", "td_build", "exported_at", "source_file")


def _count_nodes(ops: list) -> int:
    n = 0
    stack = list(ops)
    while stack:
        o = stack.pop()
        n += 1
        stack.extend(o.get("children") or [])
    return n


def t_tdn_export(a: dict) -> dict:
    root = str(a.get("root_path") or "/")
    opts = {"include_dat_content": a.get("include_dat_content", False) is True,
            "include_storage": a.get("include_storage", False) is True,
            "include_color": a.get("include_color", False) is True}
    code = _TDN.replace("__ROOT__", repr(root)).replace("__OPTS__", repr(opts))
    ok, doc = exec_code(code, timeout=float(a.get("timeout") or 120))
    if not ok:
        return doc
    n = _count_nodes(doc.get("operators") or [])
    out_path = a.get("out_path")
    res = {"ok": True, "network_path": doc.get("network_path"), "operators": n,
           "with_dat_content": opts["include_dat_content"], "td_build": doc.get("td_build")}
    if out_path:
        try:
            with open(str(out_path), "w", encoding="utf-8") as f:
                json.dump(doc, f, indent="\t", ensure_ascii=False)
            res["file"] = str(out_path)
            res["bytes"] = os.path.getsize(str(out_path))
        except Exception as e:
            res["ok"] = False; res["error"] = f"no pude escribir {out_path}: {e}"
    else:
        res["json"] = doc
    return res


# ── 6. TDN diff (offline) ────────────────────────────────────────────────────

def _flat(ops: list, out: dict | None = None, prefix: str = "") -> dict:
    out = {} if out is None else out
    for o in ops or []:
        p = f"{prefix}/{o.get('name')}"
        out[p] = o
        _flat(o.get("children") or [], out, p)
    return out


def _slim(o: dict) -> dict:
    d = {k: v for k, v in o.items() if k not in ("position", "children", "dat_content")}
    return d


def t_tdn_diff(a: dict) -> dict:
    pa, pb = a.get("path_a"), a.get("path_b")
    if not (pa and pb):
        return {"error": "hacen falta 'path_a' y 'path_b'"}
    try:
        A = json.load(open(str(pa), encoding="utf-8"))
        B = json.load(open(str(pb), encoding="utf-8"))
    except Exception as e:
        return {"error": f"no pude leer los TDN: {e}"}
    fa, fb = _flat(A.get("operators")), _flat(B.get("operators"))
    added = sorted(set(fb) - set(fa))
    removed = sorted(set(fa) - set(fb))
    changed = {}
    for k in sorted(set(fa) & set(fb)):
        sa, sb = _slim(fa[k]), _slim(fb[k])
        keys = set(sa) | set(sb)
        diff = {}
        for kk in sorted(keys):
            va, vb = sa.get(kk), sb.get(kk)
            if va == vb:
                continue
            if kk == "parameters":
                pch = {}
                for pn in sorted(set(va or {}) | set(vb or {})):
                    x, y = (va or {}).get(pn), (vb or {}).get(pn)
                    if x != y:
                        pch[pn] = {"a": x, "b": y}
                if pch:
                    diff["parameters"] = pch
            else:
                diff[kk] = {"a": va, "b": vb}
        if diff:
            changed[k] = diff
    return {"ok": True, "a": str(pa), "b": str(pb),
            "network": {"a": A.get("network_path"), "b": B.get("network_path")},
            "operators": {"a": len(fa), "b": len(fb)},
            "added": added, "removed": removed, "changed": changed,
            "summary": {"added": len(added), "removed": len(removed), "changed": len(changed)}}


# ── registro ─────────────────────────────────────────────────────────────────

LIVE_TOOLS = [
    ("td_status", "¿Está TouchDesigner vivo? Devuelve proyecto, build, fps y versión del server oficial. Usalo primero si dudás de la conexión.",
     {}, t_status),
    ("find_in_ops", "Busca un texto en TODO un subárbol: contenido de DATs, expresiones de parámetros, nombres de par, comentarios y nombres de operador. Una sola llamada (corre dentro de TD). No existía en el MCP oficial.",
     {"query": "string (requerido)", "root_path": "string (default /)", "in_dat": "bool (default true)",
      "in_expr": "bool (default true)", "in_name": "bool (default false)", "in_comment": "bool (default true)",
      "limit": "int (default 40)"}, t_find_in_ops),
    ("auto_layout", "Ordena los operadores de un COMP por dependencias (capas topológicas), sin cruces: calcula las posiciones localmente y las aplica con el oficial. dry_run=true para verlas sin mover.",
     {"parent_path": "string (requerido)", "direction": "lr|tb (default lr)", "hgap": "int (default 175)",
      "vgap": "int (default 130)", "dry_run": "bool", "include_docked": "bool (default true)"}, t_auto_layout),
    ("smart_connect", "Conecta dos operadores eligiendo el índice de input según la familia que espera el destino (lo lee de la KB). Acepta input_index para forzarlo.",
     {"from_path": "string (requerido)", "to_path": "string (requerido)", "input_index": "int (opcional)"}, t_smart_connect),
    ("tdn_export", "Exporta una red a TDN v1.4 (JSON versionable en git) leyendo el proyecto en vivo. include_dat_content para incluir el texto/tablas de los DATs. Si das out_path escribe el .tdn.",
     {"root_path": "string (default /)", "out_path": "string (opcional)", "include_dat_content": "bool (default false)",
      "include_storage": "bool (default false)", "include_color": "bool (default false: el color del nodo cambia solo)"}, t_tdn_export),
    ("tdn_diff", "Compara dos archivos .tdn (offline, sin TD): operadores agregados/quitados y cambios de parámetros, tipos, flags y cableado.",
     {"path_a": "string (requerido)", "path_b": "string (requerido)"}, t_tdn_diff),
]

LIVE_NAMES = [n for n, _d, _s, _f in LIVE_TOOLS]

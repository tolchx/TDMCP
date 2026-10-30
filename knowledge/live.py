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
import re
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
    """Llama una tool del MCP oficial con reintento transparente ante micro-cortes o sesión expirada. -> (ok, data)."""
    global _ID, _SID
    import time
    last_err = None
    for attempt in range(2):
        try:
            _init()
            _ID += 1
            r = _post({"jsonrpc": "2.0", "id": _ID, "method": "tools/call",
                       "params": {"name": tool, "arguments": args or {}}}, timeout)
            break
        except Exception as e:
            last_err = e
            _SID = None
            if attempt == 0:
                time.sleep(0.25)
    else:
        return False, {"error": f"TouchDesigner no responde en {URL} tras reintento ({type(last_err).__name__}: {last_err})",
                       "hint": "abrí TouchDesigner con el .tox TDMCP en el root y pulsá Active en su página MCP"}
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

_STATUS_PROBE = r'''
import json
comp = op('/TDMCP') or op('/project1/TDMCP')
comp_ver = None
if comp:
    for pn in ('Version', 'version'):
        if hasattr(comp.par, pn):
            try:
                comp_ver = str(getattr(comp.par, pn).eval())
                break
            except Exception:
                pass
tm_play = True
try:
    tm_play = bool(op('/').time.play)
except Exception:
    pass
pwr = bool(getattr(app, 'power', True))
rt_flag = bool(getattr(project, 'realTime', True))
print('<<JSON>>' + json.dumps({
    "runningBuild": str(getattr(app, 'build', '')),
    "runningVersion": str(getattr(app, 'version', '')),
    "osName": str(getattr(app, 'osName', '')),
    "componentVersion": comp_ver,
    "power": pwr,
    "timelinePlay": tm_play,
    "realTime": rt_flag,
}))
'''


def t_status(a: dict) -> dict:
    ok, d = call("project_info", {}, timeout=15)
    if not ok:
        return {"td_up": False, **d}
    out = {
        "td_up": True,
        "url": URL,
        "project": d.get("name"),
        "folder": d.get("folder"),
        "saveBuild": d.get("saveBuild"),
        "cookRate": d.get("cookRate"),
        "serverVersion": d.get("serverVersion"),
        "performMode": d.get("performMode"),
    }
    ok_rt, rt = exec_code(_STATUS_PROBE, timeout=10)
    if ok_rt and isinstance(rt, dict):
        if rt.get("runningBuild"):
            out["runningBuild"] = rt["runningBuild"]
            out["buildMismatch"] = bool(out.get("saveBuild") and str(out["saveBuild"]) != str(rt["runningBuild"]))
        if rt.get("runningVersion"):
            out["runningVersion"] = rt["runningVersion"]
        if rt.get("componentVersion"):
            out["componentVersion"] = rt["componentVersion"]
        out["power"] = rt.get("power", True)
        out["timelinePlay"] = rt.get("timelinePlay", True)
        out["realTime"] = rt.get("realTime", True)
        if not out["power"]:
            out["cookingVerdict"] = "DEGRADED_POWER_OFF: app.power está en False (F12); TouchDesigner no está cocinando nada."
        elif not out["timelinePlay"]:
            out["cookingVerdict"] = "DEGRADED_TIMELINE_PAUSED: el timeline está en pausa; simulaciones y absTime/frame no avanzan (Contrato C1)."
        else:
            out["cookingVerdict"] = "OK"
    return out


# ── 2. find_in_ops ───────────────────────────────────────────────────────────

_FIND = r'''
import json, time
q = __Q__; root = op(__ROOT__); o = __OPTS__
t0 = time.perf_counter()
res = {"query": q, "root": root.path if root else __ROOT__, "matches": [], "scanned": 0, "truncated": False}
def push(m):
    res['matches'].append(m)
    if len(res['matches']) >= o['limit']:
        res['truncated'] = True
        res['truncation_reason'] = f"limit={o['limit']} coincidencias alcanzado"
        return True
    return False
def scan(x):
    if res['truncated']: return
    if res['scanned'] >= o['max_nodes'] or (time.perf_counter() - t0) >= o['max_sec']:
        res['truncated'] = True
        res['truncation_reason'] = f"presupuesto alcanzado ({res['scanned']} nodos escaneados). Acotá root_path a un sub-COMP."
        return
    res['scanned'] += 1
    if o['in_name'] and q.lower() in x.name.lower():
        if push({"op": x.path, "where": "name", "text": x.name}): return
    if o['in_comment'] and q.lower() in str(getattr(x, 'comment', '') or '').lower():
        if push({"op": x.path, "where": "comment", "text": str(x.comment)[:200]}): return
    for p in x.pars():
        if o['in_name'] and q.lower() in p.name.lower():
            if push({"op": x.path, "where": "par_name", "text": p.name}): return
        if o['in_expr']:
            try:
                if str(p.mode).endswith('EXPRESSION') and q.lower() in str(p.expr or '').lower():
                    if push({"op": x.path, "where": "expr", "text": "%s = %s" % (p.name, str(p.expr)[:200]), "expr": str(p.expr)}): return
            except Exception: pass
    if x.family == 'DAT' and o['in_dat']:
        try:
            txt = x.text if getattr(x, 'isText', False) else "\n".join(["\t".join(r) for r in x.rows()])
        except Exception:
            txt = ''
        for i, line in enumerate(txt.splitlines(), 1):
            if q.lower() in line.lower():
                if push({"op": x.path, "where": "dat", "line": i, "text": line[:200]}): return
    if x.family == 'COMP':
        for c in x.children:
            scan(c)
            if res['truncated']: return
if root:
    scan(root)
else:
    res['error'] = 'contenedor no encontrado: ' + str(__ROOT__)
print('<<JSON>>' + json.dumps(res))
'''


def t_find_in_ops(a: dict) -> dict:
    q = str(a.get("query") or "").strip()
    if not q:
        return {"error": "falta 'query'"}
    opts = {
        "limit": int(a.get("limit") or 40),
        "max_nodes": int(a.get("max_nodes") or 2500),
        "max_sec": float(a.get("max_sec") or 8.0),
        "in_dat": a.get("in_dat", True) is not False,
        "in_expr": a.get("in_expr", True) is not False,
        "in_name": a.get("in_name", False) is True,
        "in_comment": a.get("in_comment", True) is not False,
    }
    code = (_FIND.replace("__Q__", repr(q)).replace("__ROOT__", repr(str(a.get("root_path") or "/")))
            .replace("__OPTS__", repr(opts)))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    return res


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
    """Familias que acepta el tipo según la KB (primero topology.json, luego ops/operators)."""
    kb = os.environ.get("TD_KNOWLEDGE_KB") or ""
    if not kb:
        return [], ""
    stem = op_type.lower()
    topo_path = os.path.join(kb, "topology.json")
    if os.path.exists(topo_path):
        try:
            with open(topo_path, encoding="utf-8") as f:
                topo = (json.load(f) or {}).get("operators") or {}
            rec = topo.get(op_type) or next((v for k, v in topo.items() if k.lower() == stem), None)
            if rec and rec.get("inputs"):
                blob = json.dumps(rec["inputs"], ensure_ascii=False)
                fams = []
                for inp in rec["inputs"]:
                    af = str(inp.get("acceptedFamily") or "").upper()
                    if af in _FAM and af not in fams:
                        fams.append(af)
                for f in _FAM:
                    if f in blob.upper() and f not in fams:
                        fams.append(f)
                if fams:
                    return fams, blob[:400]
        except Exception:
            pass
    import glob
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


# ── 7. TDXN Export (v2.1 YAML) ───────────────────────────────────────────────

_TDXN_EXTRACT = r'''
import json, datetime
root = op(__ROOT__); o = __OPTS__

def format_val(p):
    try:
        if str(p.mode).endswith('EXPRESSION'):
            return "=" + str(p.expr)
        elif str(p.mode).endswith('BIND'):
            return "~" + str(p.bindExpr or '')
        elif str(getattr(p, 'style', '')) == 'Pulse':
            return None
        v = p.eval()
        return v if isinstance(v, (int, float, bool, str)) else str(v)
    except Exception:
        return None

def pars(x):
    out = {}
    for p in x.pars():
        try:
            if p.isDefault: continue
            val = format_val(p)
            if val is not None:
                out[p.name] = val
        except Exception:
            continue
    return out

def flg(x):
    f = []
    for n in ('display', 'render', 'viewer', 'lock', 'bypass', 'allowCooking'):
        try:
            if getattr(x, n, False) is True:
                f.append(n)
        except Exception: pass
    return f

def node(x):
    d = {'name': x.name, 'type': getattr(x, 'OPType', x.type)}
    try: d['position'] = [int(x.nodeX), int(x.nodeY)]
    except Exception: pass
    try: d['size'] = [int(x.nodeWidth), int(x.nodeHeight)]
    except Exception: pass
    if o.get('include_color') and str(getattr(x, 'color', 'None')) != 'None':
        try: d['color'] = [round(float(v), 3) for v in x.color]
        except Exception: pass
    if getattr(x, 'comment', None):
        d['comment'] = str(x.comment)
    if getattr(x, 'tags', None) and len(x.tags):
        d['tags'] = sorted(list(x.tags))
    if x.parent() and x.parent().family == 'COMP':
        for dn in getattr(x.parent(), 'docked', []) or []:
            if dn.name == x.name: d['dock'] = x.parent().name
    f = flg(x)
    if f: d['flags'] = f
    ps = pars(x)
    if ps: d['parameters'] = ps
    if x.family == 'DAT':
        try:
            if getattr(x, 'isText', False):
                d['dat_content'], d['dat_content_format'] = x.text, 'text'
            elif getattr(x, 'isTable', False):
                d['dat_content'], d['dat_content_format'] = [[str(c) for c in r] for r in x.rows()], 'table'
        except Exception: pass
    if x.family != 'DAT':
        try:
            ins = []
            for conn in x.inputConnectors:
                ins.append(conn.connections[0].owner.name if conn.connections else None)
            if any(i is not None for i in ins): d['inputs'] = ins
        except Exception: pass
    if x.family == 'COMP':
        kids = [node(c) for c in x.children if not c.name.startswith('__')]
        if kids: d['children'] = kids
    return d

ops = [node(c) for c in root.children if not c.name.startswith('__')]
doc = {
    'format': 'tdxn',
    'version': '2.0',
    'generator': 'tolchx-TDMCP/tdxn_export',
    'build': (int(app.build) if str(getattr(app, 'build', '')).isdigit() else None),
    'td_build': str(getattr(app, 'build', '') or getattr(app, 'version', '')),
    'exported_at': datetime.datetime.now().isoformat(timespec='seconds'),
    'network_path': root.path,
    'options': {'include_dat_content': bool(o['include_dat_content']), 'include_storage': bool(o['include_storage'])},
    'operators': ops
}
print('<<JSON>>' + json.dumps(doc))
'''

def t_tdxn_export(a: dict) -> dict:
    """Exporta red a formato TDXN v2.1 YAML (estándar Embody)."""
    root = str(a.get("root_path") or "/")
    opts = {"include_dat_content": a.get("include_dat_content", True) is not False,
            "include_storage": a.get("include_storage", False) is True,
            "include_color": a.get("include_color", False) is True}
    code = _TDXN_EXTRACT.replace("__ROOT__", repr(root)).replace("__OPTS__", repr(opts))
    ok, doc = exec_code(code, timeout=float(a.get("timeout") or 120))
    if not ok:
        return doc
    n = _count_nodes(doc.get("operators") or [])
    out_path = a.get("out_path")
    res = {"ok": True, "format": "tdxn", "version": "2.0", "network_path": doc.get("network_path"),
           "operators": n, "with_dat_content": opts["include_dat_content"], "td_build": doc.get("td_build")}
    
    if out_path:
        try:
            import yaml
            with open(str(out_path), "w", encoding="utf-8") as f:
                yaml.dump(doc, f, sort_keys=False, allow_unicode=True, default_flow_style=False)
            res["file"] = str(out_path)
            res["bytes"] = os.path.getsize(str(out_path))
        except Exception as e:
            # Fallback a JSON si YAML falla
            with open(str(out_path), "w", encoding="utf-8") as f:
                json.dump(doc, f, indent=2, ensure_ascii=False)
            res["file"] = str(out_path)
            res["bytes"] = os.path.getsize(str(out_path))
            res["notice"] = f"guardado como json ({e})"
    else:
        res["tdxn"] = doc
    return res


# ── 7b. TDXN Import / Network Builder ────────────────────────────────────────

_TDXN_BUILD = r'''
import json
spec = __SPEC__
parent_path = spec.get('parent_path') or '/project1'
clear_first = bool(spec.get('clear_first', False))

parent = op(parent_path)
if not parent:
    parts = parent_path.rstrip('/').rsplit('/', 1)
    grand = op(parts[0] or '/')
    if grand:
        parent = grand.create(td.baseCOMP, parts[1])

if not parent:
    print('<<JSON>>' + json.dumps({"error": "contenedor padre no encontrado: " + parent_path}))
else:
    res = {
        "ok": True,
        "parent": parent.path,
        "created": [],
        "connections": [],
        "parameters_set": 0,
        "errors": [],
        "warnings": []
    }

    if clear_first:
        for c in list(parent.children):
            try:
                c.destroy()
            except Exception as e:
                res['warnings'].append(f"no se pudo destruir {c.name}: {e}")

    type_defaults = spec.get('type_defaults', {})
    operators = spec.get('operators', [])

    # 1. Crear nodos y setear dat_content/flags/posicion
    created_nodes = {}
    for op_info in operators:
        op_name = op_info.get('name')
        op_type = op_info.get('type')
        if not op_name or not op_type:
            continue
        
        op_cls = getattr(td, op_type, None)
        if not op_cls:
            res['errors'].append(f"tipo desconocido de operador: {op_type}")
            continue
        
        try:
            node = parent.op(op_name)
            if not node:
                node = parent.create(op_cls, op_name)
            created_nodes[op_name] = node
            res['created'].append(op_name)
            
            pos = op_info.get('position')
            if pos and len(pos) >= 2:
                try:
                    node.nodeX = float(pos[0])
                    node.nodeY = float(pos[1])
                except Exception: pass
                
            flags = op_info.get('flags', [])
            if 'display' in flags and hasattr(node, 'display'): node.display = True
            if 'render' in flags and hasattr(node, 'render'): node.render = True
            if 'viewer' in flags and hasattr(node, 'viewer'): node.viewer = True
            if 'bypass' in flags and hasattr(node, 'bypass'): node.bypass = True
            if 'lock' in flags and hasattr(node, 'lock'): node.lock = True
            
            dat_content = op_info.get('dat_content')
            dat_fmt = op_info.get('dat_content_format', 'text')
            if dat_content is not None and node.family == 'DAT':
                if dat_fmt == 'table' or isinstance(dat_content, list):
                    node.clear()
                    for row in dat_content:
                        if isinstance(row, list):
                            node.appendRow([str(cell) for cell in row])
                        else:
                            node.appendRow([str(row)])
                else:
                    node.text = str(dat_content)
        except Exception as e:
            res['errors'].append(f"error creando {op_name} ({op_type}): {e}")

    # 2. Conectar inputs
    for op_info in operators:
        op_name = op_info.get('name')
        node = created_nodes.get(op_name)
        if not node:
            continue
        inputs = op_info.get('inputs', [])
        for idx, inp_name in enumerate(inputs):
            if not inp_name:
                continue
            src = parent.op(inp_name) or op(inp_name)
            if src:
                try:
                    if idx < len(node.inputConnectors):
                        node.inputConnectors[idx].connect(src)
                        res['connections'].append([src.name, node.name, idx])
                except Exception as e:
                    res['warnings'].append(f"no se pudo conectar {src.name} -> {node.name} [{idx}]: {e}")

    # 3. Aplicar Parámetros (Type Defaults + Node Parameters)
    for op_info in operators:
        op_name = op_info.get('name')
        op_type = op_info.get('type')
        node = created_nodes.get(op_name)
        if not node:
            continue
        
        pars = {}
        if op_type in type_defaults and 'parameters' in type_defaults[op_type]:
            pars.update(type_defaults[op_type]['parameters'])
        if 'parameters' in op_info:
            pars.update(op_info['parameters'])
            
        for p_name, val in pars.items():
            if not hasattr(node.par, p_name):
                continue
            p = getattr(node.par, p_name)
            try:
                sval = str(val).strip() if isinstance(val, str) else None
                if sval and sval.startswith('='):
                    p.expr = sval[1:]
                elif sval and sval.startswith('~'):
                    p.bindExpr = sval[1:]
                else:
                    p.val = val
                res['parameters_set'] += 1
            except Exception as e:
                res['warnings'].append(f"{node.name}.par.{p_name}: {e}")

    # 4. Cocinar
    for n in created_nodes.values():
        try:
            n.cook(force=True)
        except Exception: pass

    print('<<JSON>>' + json.dumps(res))
'''

def t_tdxn_build(a: dict) -> dict:
    """Construye una red en TouchDesigner a partir de una especificación TDXN v2.1 YAML.
    
    Acepta el documento TDXN como string YAML o ruta a un archivo .tdxn.
    Crea todos los nodos, cablea inputs, setea expresiones (=) y bindings (~),
    puebla DATs y aplica flags en un único llamado atómico.
    """
    raw = a.get("tdxn")
    if not raw:
        return {"ok": False, "error": "falta 'tdxn' (string YAML o ruta a archivo .tdxn)"}
    
    doc = None
    if isinstance(raw, str):
        if os.path.exists(raw):
            try:
                import yaml
                with open(raw, "r", encoding="utf-8") as f:
                    doc = yaml.safe_load(f)
            except Exception as e:
                return {"ok": False, "error": f"error leyendo archivo {raw}: {e}"}
        else:
            try:
                import yaml
                doc = yaml.safe_load(raw)
            except Exception as e:
                try:
                    doc = json.loads(raw)
                except Exception:
                    return {"ok": False, "error": f"error parseando YAML/JSON: {e}"}
    elif isinstance(raw, dict):
        doc = raw
    else:
        return {"ok": False, "error": f"tipo inválido para tdxn: {type(raw).__name__}"}
    
    if not isinstance(doc, dict):
        return {"ok": False, "error": "el documento TDXN no es un diccionario válido"}
        
    parent_path = a.get("parent_path") or doc.get("network_path") or "/project1"
    clear_first = bool(a.get("clear_first", False))
    dry_run = bool(a.get("dry_run", False))
    
    ops = doc.get("operators") or []
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "parent_path": parent_path,
            "clear_first": clear_first,
            "operators_count": len(ops),
            "operators": [o.get("name") for o in ops if o.get("name")]
        }
        
    spec = {
        "parent_path": parent_path,
        "clear_first": clear_first,
        "type_defaults": doc.get("type_defaults") or {},
        "operators": ops
    }
    
    code = _TDXN_BUILD.replace("__SPEC__", repr(spec))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or 60))
    if not ok:
        return res
    return res


# ── 8. Render Frame Quality Evaluator ────────────────────────────────────────

def t_eval_render_frame(a: dict) -> dict:
    """Evalúa calidad visual de una imagen/render (detección de negro, flat o transparente)."""
    img_path = a.get("image_path")
    op_path = a.get("op_path")
    
    # Si viene un op_path y TouchDesigner está vivo, guardar el TOP a temp
    if op_path and not img_path:
        import tempfile
        tmp_target = os.path.join(tempfile.gettempdir(), "td_eval_frame.png")
        # Python de TD (<=3.11) PROHIBE un backslash dentro de una expresion f-string:
        # el .replace() de la ruta sale afuera y el f-string interpola solo el resultado.
        tmp_target_slash = tmp_target.replace('\\', '/')
        save_script = f'''
import json
node = op({repr(op_path)})
if not node:
    print('<<JSON>>' + json.dumps({{"error": "operador no encontrado: " + {repr(op_path)}}}))
elif node.family != 'TOP':
    print('<<JSON>>' + json.dumps({{"error": "operador no es TOP: " + {repr(op_path)}}}))
else:
    try:
        node.save({repr(tmp_target_slash)})
        print('<<JSON>>' + json.dumps({{"ok": True, "saved": {repr(tmp_target_slash)}}}))
    except Exception as e:
        print('<<JSON>>' + json.dumps({{"error": str(e)}}))
'''
        ok, res = exec_code(save_script, timeout=15)
        if not ok or "error" in res:
            return {"ok": False, "error": f"no se pudo guardar frame de {op_path}", "detail": res}
        img_path = tmp_target

    if not img_path or not os.path.exists(str(img_path)):
        return {"ok": False, "error": f"archivo de imagen no encontrado: {img_path}"}

    try:
        from PIL import Image
        import numpy as np
        img = Image.open(str(img_path))
        arr = np.array(img).astype(np.float32)
        h, w = arr.shape[:2]
        channels = arr.shape[2] if arr.ndim == 3 else 1
        
        # Separar color y alfa si existe
        if channels >= 3:
            rgb = arr[..., :3]
            # Luminancia percibida: 0.299 R + 0.587 G + 0.114 B
            lum = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
        else:
            lum = arr[..., 0] if arr.ndim == 3 else arr

        mean_lum = float(np.mean(lum))
        std_lum = float(np.std(lum))
        min_val = float(np.min(lum))
        max_val = float(np.max(lum))
        
        has_alpha = channels == 4
        alpha_max = float(np.max(arr[..., 3])) if has_alpha else 255.0
        alpha_mean = float(np.mean(arr[..., 3])) if has_alpha else 255.0

        # Criterios de evaluación (Quality Verdict):
        if max_val == 0.0 or mean_lum < 0.5:
            quality = "FAIL"
            reason = "Frame completamente NEGRO (luminancia nula). Revisá cámaras, luces y flags de render en geometryCOMPs."
        elif has_alpha and alpha_max == 0.0:
            quality = "FAIL"
            reason = "Frame completamente TRANSPARENTE (alfa nulo)."
        elif std_lum < 0.5:
            quality = "FAIL"
            reason = "Frame PLANO / sólido sin variación o detalle (desviación estándar < 0.5)."
        else:
            quality = "PASS"
            reason = "Salida visual verificada correctamente: rango dinámico y contraste activo."

        return {
            "ok": True,
            "quality": quality,
            "verdict": reason,
            "file": str(img_path),
            "resolution": f"{w}x{h}",
            "metrics": {
                "mean_luminance": round(mean_lum, 2),
                "std_contrast": round(std_lum, 2),
                "min": round(min_val, 2),
                "max": round(max_val, 2),
                "alpha_mean": round(alpha_mean, 2) if has_alpha else None
            }
        }
    except Exception as e:
        return {"ok": False, "error": f"error evaluando imagen: {e}"}


# ── 9. Deep Operator Errors & Shader Diagnostics ─────────────────────────────

_DEEP_ERRORS = r'''
import json, time
root = op(__ROOT__); o = __OPTS__
if not root:
    print('<<JSON>>' + json.dumps({"ok": False, "error": "contenedor no encontrado: " + str(__ROOT__)}))
else:
    t0 = time.monotonic()
    max_nodes = int(o.get('max_nodes', 2500))
    max_sec = float(o.get('max_sec', 8.0))
    scanned = 0
    truncated = None
    res = {"root": root.path, "errors": [], "warnings": [], "shader_errors": []}

    def scan(x):
        global scanned, truncated
        if truncated:
            return
        scanned += 1
        if scanned > max_nodes:
            truncated = f"max_nodes ({max_nodes}) alcanzado"
            return
        if (time.monotonic() - t0) > max_sec:
            truncated = f"max_sec ({max_sec}s) alcanzado"
            return

        # 1. Errores de cocinado de TD
        try:
            e = x.errors()
            if e: res['errors'].append({"op": x.path, "type": x.type, "errors": e})
        except Exception: pass
        
        # 2. Advertencias
        try:
            w = x.warnings()
            if w: res['warnings'].append({"op": x.path, "type": x.type, "warnings": w})
        except Exception: pass
        
        # 3. Diagnóstico de shaders GLSL (docked _info DAT)
        try:
            if 'glsl' in x.type.lower():
                for d in getattr(x, 'docked', []) or []:
                    if d.name.endswith('_info') and getattr(d, 'isText', False):
                        txt = d.text.strip()
                        if txt and any(k in txt.lower() for k in ('error', 'failed', 'compilation error')):
                            res['shader_errors'].append({"op": x.path, "info_dat": d.path, "details": txt[:800]})
        except Exception: pass

        if o['recurse'] and x.family == 'COMP':
            for c in x.children:
                if truncated:
                    break
                scan(c)

    scan(root)
    res["scanned_nodes"] = scanned
    if truncated:
        res["truncated"] = truncated
    print('<<JSON>>' + json.dumps(res))
'''

def t_get_op_errors_deep(a: dict) -> dict:
    """Inspección profunda de errores: cocinado, advertencias y compilación GLSL (con budget max_nodes/max_sec)."""
    root = str(a.get("root_path") or "/")
    opts = {
        "recurse": a.get("recurse", True) is not False,
        "max_nodes": int(a.get("max_nodes") or 2500),
        "max_sec": float(a.get("max_sec") or 8.0),
    }
    code = _DEEP_ERRORS.replace("__ROOT__", repr(root)).replace("__OPTS__", repr(opts))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    if not ok or res.get("ok") is False:
        return res
    err_count = len(res.get("errors", [])) + len(res.get("shader_errors", []))
    warn_count = len(res.get("warnings", []))
    out = {
        "ok": err_count == 0,
        "clean": err_count == 0 and warn_count == 0,
        "error_count": err_count,
        "warning_count": warn_count,
        "scanned_nodes": res.get("scanned_nodes", 0),
        "errors": res.get("errors", []),
        "shader_errors": res.get("shader_errors", []),
        "warnings": res.get("warnings", []),
    }
    if res.get("truncated"):
        out["truncated"] = res["truncated"]
    return out


# ── 10. td_measure — Medición real de señal / geometría / imagen / tabla ─────

_MEASURE = r'''
import json
spec = __SPEC__
node = op(spec['path'])
if not node:
    print('<<JSON>>' + json.dumps({"ok": False, "error": "operador no encontrado: " + spec['path']}))
else:
    try:
        node.cook(force=True)
    except Exception:
        pass
    fam = node.family
    out = {"ok": True, "path": node.path, "name": node.name, "type": getattr(node, 'OPType', node.type), "family": fam}
    if fam == 'CHOP':
        ns = int(getattr(node, 'numSamples', 0))
        nc = int(getattr(node, 'numChans', 0))
        out.update({"numChans": nc, "numSamples": ns, "rate": float(getattr(node, 'rate', 60.0))})
        want_ch = spec.get('channel')
        chans = []
        for ch in node.chans():
            if want_ch and ch.name != want_ch:
                continue
            vals = [float(ch[i]) for i in range(min(ns, 2048))] if ns > 0 else [float(ch.eval())]
            mn = min(vals) if vals else 0.0
            mx = max(vals) if vals else 0.0
            mean = (sum(vals) / len(vals)) if vals else 0.0
            rng = mx - mn
            abs_mx = max(abs(mn), abs(mx))
            cur = float(ch.eval())
            is_const = rng < 1e-6
            is_01 = (mn >= -0.05 and mx <= 1.05 and rng > 0.05)
            is_sym = (mn >= -1.05 and mx <= 1.05 and mn < -0.05)
            t_min = float(spec.get('target_min', 0.0))
            t_max = float(spec.get('target_max', 1.0))
            t_rng = t_max - t_min
            scale = (t_rng / rng) if rng > 1e-6 else 1.0
            offset = (t_min - mn * scale) if rng > 1e-6 else (t_min - mn)
            if is_const:
                interp = f"Canal '{ch.name}' constante en {cur:.4g} (sin variación temporal)."
            elif is_01:
                interp = f"Canal '{ch.name}' normalizado ~[0, 1] (rango [{mn:.3g}, {mx:.3g}], media {mean:.3g})."
            elif is_sym:
                interp = f"Canal '{ch.name}' bipolar ~[-1, 1] (rango [{mn:.3g}, {mx:.3g}], media {mean:.3g})."
            else:
                interp = f"Canal '{ch.name}' en rango [{mn:.4g}, {mx:.4g}] (amplitud {rng:.4g}, media {mean:.4g}). Para llevar a [{t_min:g}, {t_max:g}] multiplicá por {scale:.4g} y sumá {offset:.4g}."
            chans.append({
                "name": ch.name, "current": round(cur, 6), "min": round(mn, 6), "max": round(mx, 6),
                "mean": round(mean, 6), "range": round(rng, 6), "abs_max": round(abs_mx, 6),
                "is_constant": is_const, "is_normalized_01": is_01, "is_normalized_bipolar": is_sym,
                "suggested_scale": round(scale, 6), "suggested_offset": round(offset, 6),
                "interpretation": interp,
            })
            if len(chans) >= 12:
                break
        out["channels"] = chans
    elif fam == 'TOP':
        w = int(getattr(node, 'width', 0))
        h = int(getattr(node, 'height', 0))
        out.update({
            "width": w, "height": h, "aspect": round(w / h, 4) if h else 0.0,
            "depth": int(getattr(node, 'depth', 1)),
            "pixelFormat": str(getattr(node, 'pixelFormat', '')),
        })
    elif fam in ('POP', 'SOP'):
        np_fn = getattr(node, 'numPoints', 0)
        npts = int(np_fn() if callable(np_fn) else np_fn)
        npr_fn = getattr(node, 'numPrims', 0)
        nprims = int(npr_fn() if callable(npr_fn) else npr_fn)
        out.update({"numPoints": npts, "numPrims": nprims})
        try:
            b_fn = getattr(node, 'bounds', None)
            if b_fn:
                b = b_fn() if callable(b_fn) else b_fn
                out["bounds"] = {
                    "min": [round(float(b.min[0]), 5), round(float(b.min[1]), 5), round(float(b.min[2]), 5)],
                    "max": [round(float(b.max[0]), 5), round(float(b.max[1]), 5), round(float(b.max[2]), 5)],
                    "size": [round(float(b.size[0]), 5), round(float(b.size[1]), 5), round(float(b.size[2]), 5)],
                    "center": [round(float(b.center[0]), 5), round(float(b.center[1]), 5), round(float(b.center[2]), 5)],
                }
        except Exception:
            pass
        try:
            pattrs = getattr(node, 'pointAttributes', None)
            if pattrs is not None:
                pa_list = pattrs() if callable(pattrs) else pattrs
                out["pointAttributes"] = [getattr(a, 'name', str(a)) for a in pa_list]
        except Exception:
            pass
    elif fam == 'DAT':
        nr = int(getattr(node, 'numRows', 0))
        nc = int(getattr(node, 'numCols', 0))
        is_tbl = bool(getattr(node, 'isTable', False))
        out.update({"numRows": nr, "numCols": nc, "isTable": is_tbl, "isText": bool(getattr(node, 'isText', False))})
        if is_tbl and nr > 0:
            out["preview_rows"] = [[str(node[r, c].val) for c in range(min(nc, 10))] for r in range(min(nr, 5))]
        else:
            txt = str(getattr(node, 'text', ''))
            out["text_length"] = len(txt)
            out["preview_text"] = txt[:500]
    print('<<JSON>>' + json.dumps(out))
'''


def t_measure(a: dict) -> dict:
    """Mide en vivo el rango real de un CHOP, geometría de un POP/SOP, dimensiones de un TOP o contenido de un DAT."""
    path = str(a.get("path") or a.get("op_path") or "").strip()
    if not path:
        return {"ok": False, "error": "falta 'path' (ej. '/project1/audio1' o '/project1/noise1')"}
    spec = {
        "path": path,
        "channel": str(a.get("channel") or "").strip() or None,
        "target_min": float(a.get("target_min") if a.get("target_min") is not None else 0.0),
        "target_max": float(a.get("target_max") if a.get("target_max") is not None else 1.0),
    }
    code = _MEASURE.replace("__SPEC__", repr(spec))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    return res


# ── 11. td_glsl_apply — Pipeline atómico GLSL (análisis + DAT + nodo + attrs + compile) ──

_GLSL_APPLY = r'''
import json
spec = __SPEC__
parent = op(spec['parent_path'])
if not parent:
    print('<<JSON>>' + json.dumps({"ok": False, "error": "contenedor padre no encontrado: " + spec['parent_path']}))
else:
    name = spec['name']
    dat_name = name + '_code'
    fam = spec['family']
    op_type = 'glslTOP' if fam == 'top' else ('glslcopyPOP' if fam == 'copy' else 'glslPOP')
    op_cls = getattr(td, op_type, None)
    if not op_cls:
        print('<<JSON>>' + json.dumps({"ok": False, "error": "tipo de operador no disponible en este build: " + op_type}))
    else:
        dat_node = parent.op(dat_name) or parent.create(td.textDAT, dat_name)
        dat_node.text = spec['code']
        node = parent.op(name)
        if node and getattr(node, 'OPType', node.type) != op_type:
            node.destroy()
            node = None
        if not node:
            node = parent.create(op_cls, name)
        try:
            dat_node.nodeX = node.nodeX
            dat_node.nodeY = node.nodeY - 130
        except Exception:
            pass

        # Enlazar DAT del shader
        linked_par = None
        for pname in ('dat', 'computedat', 'pixeldat'):
            if hasattr(node.par, pname):
                getattr(node.par, pname).val = dat_node.name
                linked_par = pname
                break

        warnings = []
        attrs_configured = []
        if fam in ('pop', 'copy'):
            create_attrs = spec.get('create_attrs') or []
            if create_attrs and hasattr(node.par, 'attr'):
                try:
                    node.par.attr.numBlocks = max(int(node.par.attr.numBlocks), len(create_attrs))
                except Exception:
                    pass
            for i, ca in enumerate(create_attrs):
                p_name = f'attr{i}name'
                p_cname = f'attr{i}customname'
                p_ncomp = f'attr{i}numcomps'
                if hasattr(node.par, p_name):
                    try:
                        getattr(node.par, p_name).val = 'custom'
                        if hasattr(node.par, p_cname):
                            getattr(node.par, p_cname).val = ca['name']
                        if hasattr(node.par, p_ncomp):
                            getattr(node.par, p_ncomp).val = str(min(max(int(ca['comps']), 1), 4))
                        attrs_configured.append(ca)
                    except Exception as e:
                        warnings.append(f"error configurando atributo {ca}: {e}")
            out_attrs = spec.get('outputattrs')
            if out_attrs and hasattr(node.par, 'outputattrs'):
                try:
                    node.par.outputattrs.val = out_attrs
                except Exception as e:
                    warnings.append(f"outputattrs: {e}")
            out_acc = spec.get('outputaccess')
            if out_acc and hasattr(node.par, 'outputaccess'):
                try:
                    node.par.outputaccess.val = out_acc
                except Exception as e:
                    warnings.append(f"outputaccess: {e}")
        elif fam == 'top':
            res_wh = spec.get('resolution')
            if res_wh and len(res_wh) == 2:
                try:
                    if hasattr(node.par, 'outputresolution'):
                        node.par.outputresolution.val = 'custom'
                    if hasattr(node.par, 'resolutionw'):
                        node.par.resolutionw.val = int(res_wh[0])
                    if hasattr(node.par, 'resolutionh'):
                        node.par.resolutionh.val = int(res_wh[1])
                except Exception as e:
                    warnings.append(f"resolution: {e}")

        # Uniforms (vec0name + vec0type + vec0valuex/y/z/w)
        uniforms_set = []
        uniforms = spec.get('uniforms') or {}
        if uniforms and hasattr(node.par, 'vec'):
            try:
                node.par.vec.numBlocks = max(int(node.par.vec.numBlocks), len(uniforms))
            except Exception:
                pass
        for idx, (uname, uval) in enumerate(uniforms.items()):
            vn = f'vec{idx}name'
            vt = f'vec{idx}type'
            if hasattr(node.par, vn):
                try:
                    getattr(node.par, vn).val = uname
                    vals = list(uval) if isinstance(uval, (list, tuple)) else [uval]
                    if hasattr(node.par, vt):
                        vtype_str = ('float', 'vec2', 'vec3', 'vec4')[min(max(len(vals), 1), 4) - 1]
                        getattr(node.par, vt).val = vtype_str
                    for c_i, suf in enumerate(('x', 'y', 'z', 'w')):
                        if c_i < len(vals) and hasattr(node.par, f'vec{idx}value{suf}'):
                            getattr(node.par, f'vec{idx}value{suf}').val = float(vals[c_i])
                    uniforms_set.append(uname)
                except Exception as e:
                    warnings.append(f"uniform {uname}: {e}")

        # Conexiones de entrada
        wired = []
        for idx, sp in enumerate(spec.get('inputs') or []):
            if not sp:
                continue
            src = op(sp) or parent.op(sp)
            if src and idx < len(node.inputConnectors):
                try:
                    node.inputConnectors[idx].connect(src)
                    wired.append([src.path, idx])
                except Exception as e:
                    warnings.append(f"input[{idx}] ({sp}): {e}")
            elif not src:
                warnings.append(f"input[{idx}] no encontrado: {sp}")

        try:
            node.cook(force=True)
        except Exception as e:
            warnings.append(f"cook: {e}")

        errs = ""
        warns_td = ""
        try:
            errs = node.errors() or ""
            warns_td = node.warnings() or ""
        except Exception:
            pass
        info_txt = ""
        for d in (getattr(node, 'docked', []) or []):
            if d.name.endswith('_info') and getattr(d, 'isText', False):
                try:
                    d.cook(force=True)
                except Exception:
                    pass
                info_txt = (d.text or "").strip()
                break
        if not info_txt:
            info_cand = parent.op(name + '_info')
            if info_cand and getattr(info_cand, 'isText', False):
                info_txt = (info_cand.text or "").strip()

        has_shader_err = any(k in info_txt.lower() for k in ('error:', 'compilation error', 'failed')) or bool(errs)
        print('<<JSON>>' + json.dumps({
            "ok": not has_shader_err,
            "op_path": node.path,
            "dat_path": dat_node.path,
            "op_type": op_type,
            "linked_par": linked_par,
            "attrs_configured": attrs_configured,
            "uniforms_set": uniforms_set,
            "wired_inputs": wired,
            "compile_ok": not has_shader_err,
            "td_errors": errs,
            "td_warnings": warns_td,
            "compiler_info": info_txt[:1500] if info_txt else "Compile Results: Success",
            "warnings": warnings,
        }))
'''


def t_glsl_apply(a: dict) -> dict:
    """Valida estáticamente un shader GLSL (POP/TOP), crea el textDAT + operador GLSL, configura atributos/uniforms, cablea inputs y verifica la compilación en vivo."""
    parent_path = str(a.get("parent_path") or "/project1").strip()
    name = str(a.get("name") or "").strip()
    code_str = str(a.get("code") or "")
    family = str(a.get("family") or "pop").strip().lower()
    if not name or not code_str.strip():
        return {"ok": False, "error": "hacen falta 'name' y 'code'"}
    if family not in ("pop", "top", "copy"):
        return {"ok": False, "error": f"family inválida '{family}' (usar 'pop', 'top' o 'copy')"}

    from server import t_glsl_analyze, COMPONENTS, BUILTIN_WRITE_OK
    analysis = t_glsl_analyze({"code": code_str, "family": "top" if family == "top" else "pop"})
    skip_val = str(a.get("skip_validation") or "").lower() in ("1", "true", "yes", "si", "sí") or a.get("skip_validation") is True
    if not analysis.get("ok") and not skip_val:
        return {
            "ok": False,
            "stage": "static_analysis",
            "error": "El shader tiene errores estáticos verificados. Corregilos o pasá skip_validation=true.",
            "analysis": analysis,
        }

    # Determinar atributos a crear en POP
    create_attrs = []
    seen_attrs = set()
    for attr in analysis.get("escribe") or []:
        if attr.lower() not in BUILTIN_WRITE_OK and attr not in seen_attrs:
            seen_attrs.add(attr)
            create_attrs.append({"name": attr, "comps": COMPONENTS.get(attr.lower(), 3)})

    raw_wa = str(a.get("write_attrs") or "").strip()
    if raw_wa:
        for part in re.split(r"[,;]+", raw_wa):
            part = part.strip()
            if not part:
                continue
            if ":" in part:
                aname, acomps = part.split(":", 1)
                aname, acomps_i = aname.strip(), int(acomps.strip() or 3)
            else:
                aname, acomps_i = part, COMPONENTS.get(part.lower(), 3)
            if aname.lower() not in BUILTIN_WRITE_OK and aname not in seen_attrs:
                seen_attrs.add(aname)
                create_attrs.append({"name": aname, "comps": acomps_i})

    out_builtins = [x for x in (analysis.get("escribe") or []) if x.lower() in BUILTIN_WRITE_OK]
    outputattrs = " ".join(out_builtins) if out_builtins else None
    reads_set = set(analysis.get("lee") or [])
    writes_set = set(analysis.get("escribe") or [])
    outputaccess = "readwrite" if (reads_set & writes_set) else None

    # Uniforms
    uniforms = {}
    raw_u = a.get("uniforms")
    if isinstance(raw_u, dict):
        uniforms = raw_u
    elif isinstance(raw_u, str) and raw_u.strip():
        try:
            uniforms = json.loads(raw_u)
        except Exception as e:
            return {"ok": False, "error": f"uniforms debe ser JSON válido: {e}"}

    # Resolution (para TOP)
    res_wh = None
    raw_res = str(a.get("resolution") or "").strip().lower()
    if raw_res and "x" in raw_res:
        try:
            w_s, h_s = raw_res.split("x", 1)
            res_wh = [int(w_s.strip()), int(h_s.strip())]
        except Exception:
            pass

    # Inputs
    inputs = []
    if a.get("source_path"):
        inputs.append(str(a["source_path"]).strip())
    if a.get("extra_inputs"):
        if not inputs:
            inputs.append("")
        for xp in str(a["extra_inputs"]).split(","):
            inputs.append(xp.strip())

    spec = {
        "parent_path": parent_path,
        "name": name,
        "code": code_str,
        "family": family,
        "create_attrs": create_attrs,
        "outputattrs": outputattrs,
        "outputaccess": outputaccess,
        "uniforms": uniforms,
        "resolution": res_wh,
        "inputs": inputs,
    }
    script = _GLSL_APPLY.replace("__SPEC__", repr(spec))
    ok, res = exec_code(script, timeout=float(a.get("timeout") or TIMEOUT))
    if isinstance(res, dict):
        res["static_analysis"] = {"ok": analysis.get("ok"), "escribe": analysis.get("escribe"), "lee": analysis.get("lee"), "warnings": analysis.get("warnings")}
    return res


# ── 12. td_explore_project — Radiografía rápida de un contenedor o proyecto ──

_EXPLORE_PROJECT = r'''
import json, time
spec = __SPEC__
root = op(spec['root_path'])
if not root:
    print('<<JSON>>' + json.dumps({"ok": False, "error": "contenedor no encontrado: " + spec['root_path']}))
else:
    t0 = time.monotonic()
    max_depth = int(spec.get('max_depth', 3))
    max_nodes = int(spec.get('max_nodes', 2500))
    max_sec = float(spec.get('max_sec', 8.0))
    truncated = None
    by_fam = {}
    by_type = {}
    containers = []
    shaders = []
    custom_pars = []
    issues = []
    cook_times = []
    total = 0

    def walk(comp, depth):
        global total, truncated
        if truncated:
            return
        for c in comp.children:
            if c.name.startswith('.'):
                continue
            total += 1
            if total > max_nodes:
                truncated = f"max_nodes ({max_nodes}) alcanzado"
                return
            if (time.monotonic() - t0) > max_sec:
                truncated = f"max_sec ({max_sec}s) alcanzado"
                return
            f = c.family
            t = getattr(c, 'OPType', c.type)
            by_fam[f] = by_fam.get(f, 0) + 1
            by_type[t] = by_type.get(t, 0) + 1
            try:
                ct = float(getattr(c, 'cookTime', 0.0))
                if ct > 0.01:
                    cook_times.append({"path": c.path, "type": t, "cook_ms": round(ct, 4)})
            except Exception:
                pass
            try:
                e = c.errors()
                w = c.warnings()
                if e or w:
                    issues.append({"path": c.path, "type": t, "errors": e or None, "warnings": w or None})
            except Exception:
                pass
            if 'glsl' in t.lower():
                dat_ref = ""
                for pn in ('dat', 'computedat', 'pixeldat'):
                    if hasattr(c.par, pn):
                        dat_ref = str(getattr(c.par, pn).eval())
                        break
                shaders.append({"path": c.path, "type": t, "dat": dat_ref})
            if f == 'COMP':
                ch_cnt = len([x for x in getattr(c, 'children', []) if not x.name.startswith('.')])
                containers.append({"path": c.path, "type": t, "children_count": ch_cnt, "depth": depth + 1})
                cp = [p.name for p in (getattr(c, 'customPars', []) or [])]
                if cp:
                    custom_pars.append({"path": c.path, "custom_pars": cp[:30]})
                if depth + 1 < max_depth:
                    walk(c, depth + 1)

    walk(root, 0)
    cook_times.sort(key=lambda x: -x['cook_ms'])
    top_types = sorted(by_type.items(), key=lambda x: -x[1])[:15]
    out_payload = {
        "ok": True,
        "root": root.path,
        "max_depth": max_depth,
        "total_operators": total,
        "by_family": by_fam,
        "top_types": dict(top_types),
        "containers": containers[:60],
        "shaders": shaders[:40],
        "custom_pars": custom_pars[:30],
        "issues": issues[:40],
        "heaviest_ops": cook_times[:10],
    }
    if truncated:
        out_payload["truncated"] = truncated
    print('<<JSON>>' + json.dumps(out_payload))
'''


def t_explore_project(a: dict) -> dict:
    """Radiografía completa de un contenedor o proyecto en una sola llamada: conteos por familia/tipo, sub-COMPs, shaders GLSL, customPars, errores y operadores más pesados por cookTime."""
    root_path = str(a.get("root_path") or "/project1").strip()
    max_depth = int(a.get("max_depth") or 3)
    spec = {
        "root_path": root_path,
        "max_depth": max_depth,
        "max_nodes": int(a.get("max_nodes") or 2500),
        "max_sec": float(a.get("max_sec") or 8.0),
    }
    code = _EXPLORE_PROJECT.replace("__SPEC__", repr(spec))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    return res


# ── 13. td_compare_networks — Comparación en vivo de dos contenedores COMP ───

_COMPARE_NETS = r'''
import json
spec = __SPEC__
ca = op(spec['path_a'])
cb = op(spec['path_b'])
if not ca or not cb:
    print('<<JSON>>' + json.dumps({"ok": False, "error": f"contenedor no encontrado: a={bool(ca)} ({spec['path_a']}), b={bool(cb)} ({spec['path_b']})"}))
else:
    def snap(comp):
        out = {}
        for c in comp.children:
            if c.name.startswith('.'):
                continue
            pars = {}
            for p in c.pars():
                try:
                    if p.isDefault or str(getattr(p, 'style', '')) == 'Pulse':
                        continue
                    if str(p.mode).endswith('EXPRESSION'):
                        pars[p.name] = '=' + str(p.expr)
                    else:
                        v = p.eval()
                        pars[p.name] = v if isinstance(v, (int, float, bool, str)) else str(v)
                except Exception:
                    pass
            ins = []
            try:
                for i, conn in enumerate(c.inputConnectors):
                    for cc in conn.connections:
                        ins.append(f"{i}:{cc.owner.name}")
            except Exception:
                pass
            out[c.name] = {"type": getattr(c, 'OPType', c.type), "family": c.family, "pars": pars, "inputs": ins}
        return out

    sa = snap(ca)
    sb = snap(cb)
    ka, kb_set = set(sa.keys()), set(sb.keys())
    only_a = sorted(ka - kb_set)
    only_b = sorted(kb_set - ka)
    common = sorted(ka & kb_set)
    type_diffs, param_diffs, conn_diffs = [], {}, {}
    for name in common:
        na, nb = sa[name], sb[name]
        if na['type'] != nb['type']:
            type_diffs.append({"name": name, "a": na['type'], "b": nb['type']})
            continue
        pa, pb = na['pars'], nb['pars']
        pdiff = {}
        for pk in sorted(set(pa.keys()) | set(pb.keys())):
            if pa.get(pk) != pb.get(pk):
                pdiff[pk] = {"a": pa.get(pk, "<default>"), "b": pb.get(pk, "<default>")}
        if pdiff:
            param_diffs[name] = pdiff
        if na['inputs'] != nb['inputs']:
            conn_diffs[name] = {"a": na['inputs'], "b": nb['inputs']}

    identical = not (only_a or only_b or type_diffs or param_diffs or conn_diffs)
    print('<<JSON>>' + json.dumps({
        "ok": True,
        "path_a": ca.path,
        "path_b": cb.path,
        "identical": identical,
        "common_count": len(common),
        "only_in_a": only_a,
        "only_in_b": only_b,
        "type_mismatches": type_diffs,
        "param_diffs": param_diffs,
        "connection_diffs": conn_diffs,
    }))
'''


def t_compare_networks(a: dict) -> dict:
    """Compara en vivo dos contenedores COMP: operadores exclusivos de cada uno, diferencias de tipos, parámetros no-default y conexiones."""
    pa = str(a.get("path_a") or "").strip()
    pb = str(a.get("path_b") or "").strip()
    if not pa or not pb:
        return {"ok": False, "error": "hacen falta 'path_a' y 'path_b'"}
    code = _COMPARE_NETS.replace("__SPEC__", repr({"path_a": pa, "path_b": pb}))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    return res


# ── 14. td_spatial_context — Contexto del editor de red y timeline activo ────

_SPATIAL_CTX = r'''
import json
out = {"ok": True}
try:
    p = ui.panes.current
    if p:
        owner = getattr(p, 'owner', None)
        out["pane"] = {
            "name": getattr(p, 'name', ''),
            "type": str(getattr(p, 'type', '')),
            "owner_path": owner.path if owner else None,
            "zoom": round(float(getattr(p, 'zoom', 1.0)), 3),
            "x": round(float(getattr(p, 'x', 0.0)), 1),
            "y": round(float(getattr(p, 'y', 0.0)), 1),
        }
        if owner:
            cur = getattr(owner, 'currentChild', None)
            sel = getattr(owner, 'selectedChildren', []) or []
            out["current_child"] = {"name": cur.name, "path": cur.path, "type": getattr(cur, 'OPType', cur.type)} if cur else None
            out["selected_children"] = [{"name": s.name, "path": s.path, "type": getattr(s, 'OPType', s.type)} for s in sel[:30]]
except Exception as e:
    out["pane_warning"] = str(e)

try:
    tm = op('/').time
    out["timeline"] = {
        "play": bool(tm.play),
        "frame": float(tm.frame),
        "seconds": round(float(tm.seconds), 3),
        "rate": float(tm.rate),
        "start": float(tm.start),
        "end": float(tm.end),
        "realTime": bool(project.realTime),
    }
except Exception as e:
    out["timeline_warning"] = str(e)

print('<<JSON>>' + json.dumps(out))
'''


def t_spatial_context(_: dict) -> dict:
    """Devuelve dónde está parado el usuario en la UI de TouchDesigner (pane activo, contenedor abierto, operador actual, selección múltiple y estado del timeline)."""
    ok, res = exec_code(_SPATIAL_CTX, timeout=15)
    return res


# ── 15. td_build_pop_render — Pipeline atómico de renderizado POP ────────────

_BUILD_POP_RENDER = r'''
import json
spec = __SPEC__
parent = op(spec['parent_path'])
if not parent:
    print('<<JSON>>' + json.dumps({"ok": False, "error": "contenedor padre no encontrado: " + spec['parent_path']}))
else:
    prefix = spec['name']
    geo_name = prefix + '_geo'
    cam_name = prefix + '_cam'
    mat_name = prefix + '_mat'
    ren_name = prefix + '_ren'
    out_name = prefix + '_out'
    light_name = prefix + '_light'
    warnings = []

    def get_or_create(comp, cls_name, n_name):
        cls = getattr(td, cls_name, None)
        if not cls:
            raise RuntimeError("Tipo de operador no disponible: " + cls_name)
        existing = comp.op(n_name)
        if existing and getattr(existing, 'OPType', existing.type) != cls_name:
            existing.destroy()
            existing = None
        return existing or comp.create(cls, n_name)

    geo = get_or_create(parent, 'geometryCOMP', geo_name)
    torus_deleted = False
    t1 = geo.op('torus1')
    if t1:
        t1.destroy()
        torus_deleted = True

    # Fuente POP dentro de geometryCOMP
    src_path = spec.get('source_pop') or ''
    src_node = None
    if src_path:
        ext_src = op(src_path) or parent.op(src_path) or geo.op(src_path)
        if ext_src:
            if ext_src.parent == geo:
                src_node = ext_src
            else:
                sel = get_or_create(geo, 'selectPOP', 'select_src')
                if hasattr(sel.par, 'pop'):
                    sel.par.pop = ext_src.path
                src_node = sel
        else:
            warnings.append(f"source_pop '{src_path}' no encontrado; se creó spherePOP por defecto")

    if not src_node:
        sph = get_or_create(geo, 'spherePOP', 'sphere1')
        if hasattr(sph.par, 'rows'):
            sph.par.rows = 32
        if hasattr(sph.par, 'cols'):
            sph.par.cols = 32
        src_node = sph

    prim_mode = spec.get('primitive_mode', 'points')
    tail_pop = src_node
    conv_path = None
    if prim_mode == 'points':
        conv = get_or_create(geo, 'convertPOP', 'to_points')
        if hasattr(conv.par, 'convert'):
            conv.par.convert = 'topointprims'
        try:
            conv.inputConnectors[0].connect(src_node)
        except Exception as e:
            warnings.append(f"wire convertPOP: {e}")
        tail_pop = conv
        conv_path = conv.path

    null_pop = get_or_create(geo, 'nullPOP', 'null_out')
    try:
        null_pop.inputConnectors[0].connect(tail_pop)
    except Exception as e:
        warnings.append(f"wire null_out: {e}")
    null_pop.display = True
    null_pop.render = True
    null_pop.viewer = True

    # Posicionar nodos internos del geometryCOMP
    try:
        src_node.nodeX, src_node.nodeY = 0, 0
        if conv_path:
            conv.nodeX, conv.nodeY = 200, 0
            null_pop.nodeX, null_pop.nodeY = 400, 0
        else:
            null_pop.nodeX, null_pop.nodeY = 200, 0
    except Exception:
        pass

    # Cámara
    cam = get_or_create(parent, 'cameraCOMP', cam_name)
    if hasattr(cam.par, 'tz'):
        cam.par.tz = float(spec.get('camera_tz', 5.0))

    # Material
    mat_kind = spec.get('material', 'pointsprite').lower()
    if mat_kind == 'constant':
        mat_cls = 'constantMAT'
    elif mat_kind == 'pbr':
        mat_cls = 'pbrMAT'
    else:
        mat_cls = 'pointspriteMAT'
    mat = get_or_create(parent, mat_cls, mat_name)
    if mat_cls == 'pointspriteMAT' and hasattr(mat.par, 'pointsize'):
        mat.par.pointsize = float(spec.get('point_size', 4.0))
    if hasattr(geo.par, 'material'):
        geo.par.material = mat.name

    light_path = None
    if mat_kind == 'pbr':
        lgt = get_or_create(parent, 'lightCOMP', light_name)
        if hasattr(lgt.par, 'tx'):
            lgt.par.tx, lgt.par.ty, lgt.par.tz = 2.0, 3.0, 4.0
        light_path = lgt.path

    # Render TOP y Null TOP
    ren = get_or_create(parent, 'renderTOP', ren_name)
    w, h = spec.get('resolution', [1280, 720])
    if hasattr(ren.par, 'outputresolution'):
        ren.par.outputresolution = 'custom'
    if hasattr(ren.par, 'resolutionw'):
        ren.par.resolutionw = int(w)
    if hasattr(ren.par, 'resolutionh'):
        ren.par.resolutionh = int(h)
    if hasattr(ren.par, 'geometry'):
        ren.par.geometry = geo.name
    if hasattr(ren.par, 'camera'):
        ren.par.camera = cam.name
    if hasattr(ren.par, 'lights'):
        ren.par.lights = '*'

    out_top = get_or_create(parent, 'nullTOP', out_name)
    try:
        out_top.inputConnectors[0].connect(ren)
    except Exception as e:
        warnings.append(f"wire nullTOP: {e}")

    # Posicionar nodos en parent
    try:
        geo.nodeX, geo.nodeY = 0, 150
        cam.nodeX, cam.nodeY = 0, 0
        mat.nodeX, mat.nodeY = 0, -150
        ren.nodeX, ren.nodeY = 250, 50
        out_top.nodeX, out_top.nodeY = 450, 50
    except Exception:
        pass

    # Settle (4 pasadas de cook)
    for _ in range(4):
        for n in (src_node, tail_pop, null_pop, geo, cam, mat, ren, out_top):
            try:
                n.cook(force=True)
            except Exception:
                pass

    npts = int(null_pop.numPoints() if callable(getattr(null_pop, 'numPoints', None)) else getattr(null_pop, 'numPoints', 0))
    nprims = int(null_pop.numPrims() if callable(getattr(null_pop, 'numPrims', None)) else getattr(null_pop, 'numPrims', 0))

    print('<<JSON>>' + json.dumps({
        "ok": npts > 0 and nprims > 0 and not bool(ren.errors()),
        "parent_path": parent.path,
        "geo_path": geo.path,
        "source_pop_path": src_node.path,
        "convert_pop_path": conv_path,
        "null_pop_path": null_pop.path,
        "camera_path": cam.path,
        "material_path": mat.path,
        "light_path": light_path,
        "render_top_path": ren.path,
        "out_top_path": out_top.path,
        "torus1_deleted": torus_deleted or (geo.op('torus1') is None),
        "numPoints": npts,
        "numPrims": nprims,
        "resolution": f"{ren.width}x{ren.height}",
        "render_errors": ren.errors() or None,
        "warnings": warnings,
    }))
'''


def t_build_pop_render(a: dict) -> dict:
    """Construye en 1 llamada el pipeline completo de renderizado POP (geometryCOMP sin torus1 + convertPOP topointprims + nullPOP display/render + cameraCOMP + MAT + renderTOP + nullTOP) y verifica su salida."""
    parent_path = str(a.get("parent_path") or "/project1").strip()
    name = str(a.get("name") or "pop_scene").strip()
    source_pop = str(a.get("source_pop") or "").strip() or None
    primitive_mode = str(a.get("primitive_mode") or "points").strip().lower()
    material = str(a.get("material") or "pointsprite").strip().lower()
    raw_res = str(a.get("resolution") or "1280x720").strip().lower()
    res_wh = [1280, 720]
    if "x" in raw_res:
        try:
            w_s, h_s = raw_res.split("x", 1)
            res_wh = [int(w_s.strip()), int(h_s.strip())]
        except Exception:
            pass
    spec = {
        "parent_path": parent_path,
        "name": name,
        "source_pop": source_pop,
        "primitive_mode": primitive_mode,
        "material": material,
        "resolution": res_wh,
        "point_size": float(a.get("point_size") if a.get("point_size") is not None else 4.0),
        "camera_tz": float(a.get("camera_tz") if a.get("camera_tz") is not None else 5.0),
    }
    code = _BUILD_POP_RENDER.replace("__SPEC__", repr(spec))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    if ok and isinstance(res, dict) and res.get("out_top_path") and a.get("eval_frame", True) is not False:
        ev = t_eval_render_frame({"op_path": res["out_top_path"]})
        res["frame_evaluation"] = {
            "quality": ev.get("quality"),
            "verdict": ev.get("verdict"),
            "metrics": ev.get("metrics"),
        }
    return res


# ── 16. td_instantiate_template — Instanciador de templates/recetas en vivo ──

_INSTANTIATE_TEMPLATE = r'''
import json, re
spec = __SPEC__
base_parent = op(spec['parent_path'])
if not base_parent:
    print('<<JSON>>' + json.dumps({"ok": False, "error": "parent_path no encontrado: " + spec['parent_path']}))
else:
    container_name = spec.get('container_name')
    if container_name:
        target_comp = base_parent.op(container_name)
        if not target_comp:
            target_comp = base_parent.create(td.baseCOMP, container_name)
    else:
        target_comp = base_parent

    if spec.get('clear_first'):
        for c in list(target_comp.children):
            if not c.name.startswith('.'):
                try:
                    c.destroy()
                except Exception:
                    pass

    TYPE_ALIASES = {
        "base": "baseCOMP", "container": "containerCOMP", "geometry": "geometryCOMP",
        "camera": "cameraCOMP", "light": "lightCOMP", "window": "windowCOMP",
        "feedbackPop": "feedbackPOP", "mathMixPop": "mathmixPOP", "mathCombinePop": "mathcombinePOP",
        "pointSpriteMat": "pointspriteMAT", "constantMat": "constantMAT", "pbrMat": "pbrMAT",
    }

    def resolve_cls(t_str):
        t_clean = TYPE_ALIASES.get(t_str, t_str)
        c = getattr(td, t_clean, None)
        if c:
            return c, t_clean
        # Probar capitalización de sufijo de familia (ej. noisePop -> noisePOP)
        for fam in ('POP', 'TOP', 'CHOP', 'SOP', 'DAT', 'MAT', 'COMP'):
            if t_clean.upper().endswith(fam):
                cand = t_clean[:-len(fam)].lower() + fam
                c = getattr(td, cand, None)
                if c:
                    return c, cand
        return None, t_clean

    created_ops = []
    warnings = []
    explicit_torus = any(n.get('name') == 'torus1' or str(n.get('name', '')).endswith('/torus1') for n in spec['nodes'])

    # 1. Crear operadores (soportando sub-rutas como 'geo1/sphere1' o parent relativo)
    node_map = {}
    for nd in spec['nodes']:
        raw_name = str(nd['name']).strip('/')
        parent_rel = str(nd.get('parent') or '').strip('/')
        if '/' in raw_name and not parent_rel:
            parent_rel, n_name = raw_name.rsplit('/', 1)
        else:
            n_name = raw_name
        comp = target_comp.op(parent_rel) if parent_rel else target_comp
        if not comp:
            warnings.append(f"contenedor padre '{parent_rel}' no encontrado para '{n_name}'")
            continue

        cls, cls_name = resolve_cls(nd['type'])
        if not cls:
            warnings.append(f"tipo de operador no disponible para '{n_name}': {nd['type']}")
            continue

        existing = comp.op(n_name)
        if existing and getattr(existing, 'OPType', existing.type) != cls_name:
            existing.destroy()
            existing = None
        node = existing or comp.create(cls, n_name)
        if cls_name == 'geometryCOMP' and not explicit_torus:
            t1 = node.op('torus1')
            if t1:
                t1.destroy()

        pos = nd.get('position')
        if isinstance(pos, (list, tuple)) and len(pos) == 2:
            try:
                node.nodeX, node.nodeY = int(pos[0]), int(pos[1])
            except Exception:
                pass

        # Contenido de texto para textDAT (de templates cosechados con td_harvest_pattern)
        if nd.get('dat_content') is not None and getattr(node, 'isText', False):
            try:
                node.text = str(nd['dat_content'])
            except Exception as e:
                warnings.append(f"{node.path}.text: {e}")

        # Flags / OP properties
        for fk, fv in (nd.get('flags') or {}).items():
            try:
                setattr(node, fk, bool(fv))
            except Exception as e:
                warnings.append(f"{node.path}.{fk}: {e}")

        # Parámetros (con expansión automática de sequence numBlocks si aplica)
        for pk, pv in (nd.get('parameters') or {}).items():
            if pk in ('display', 'render', 'viewer', 'bypass', 'lock'):
                try:
                    setattr(node, pk, bool(pv))
                except Exception:
                    pass
                continue
            m_seq = re.match(r'^([a-zA-Z]+)(\d+)([a-zA-Z0-9_]*)$', pk)
            if m_seq:
                seq_prefix, seq_idx = m_seq.group(1), int(m_seq.group(2))
                seq_par = getattr(node.par, seq_prefix, None)
                if seq_par is not None and hasattr(seq_par, 'numBlocks'):
                    try:
                        if int(seq_par.numBlocks) <= seq_idx:
                            seq_par.numBlocks = seq_idx + 1
                    except Exception:
                        pass
            p_obj = getattr(node.par, pk, None)
            if p_obj is None:
                warnings.append(f"parámetro '{pk}' no existe en {node.path} ({cls_name})")
                continue
            try:
                if isinstance(pv, str) and pv.startswith('='):
                    p_obj.expr = pv[1:].strip()
                else:
                    p_obj.val = pv
            except Exception as e:
                warnings.append(f"error seteando {node.path}.par.{pk}={pv!r}: {e}")

        key_id = str(nd.get('id') or raw_name)
        node_map[key_id] = node
        node_map[n_name] = node
        if cls_name not in node_map:
            node_map[cls_name] = node
        for fam_suf in ('POP', 'TOP', 'CHOP', 'SOP', 'DAT', 'MAT', 'COMP'):
            if cls_name.endswith(fam_suf):
                short_base = cls_name[:-len(fam_suf)].lower()
                if short_base not in node_map:
                    node_map[short_base] = node
        created_ops.append({"name": n_name, "path": node.path, "type": cls_name})

    # 1b. Referencias diferidas entre parámetros (ej. feedbackTOP.par.targettop = transform.name)
    for pref in (spec.get('deferred_pars') or []):
        target_node = node_map.get(pref['node'])
        ref_node = node_map.get(pref['ref_target'])
        if target_node and hasattr(target_node.par, pref['par']):
            try:
                getattr(target_node.par, pref['par']).val = ref_node.name if ref_node else pref['ref_target']
            except Exception as e:
                warnings.append(f"deferred_par {pref}: {e}")

    # 2. Conectar cables
    wired = []
    for cn in spec['connections']:
        f_key = str(cn.get('from') or '').strip('/')
        t_key = str(cn.get('to') or '').strip('/')
        src = node_map.get(f_key) or target_comp.op(f_key)
        dst = node_map.get(t_key) or target_comp.op(t_key)
        if not src or not dst:
            warnings.append(f"conexión omitida ({f_key} -> {t_key}): nodo no encontrado")
            continue
        out_idx = int(cn.get('from_index', 0))
        in_idx = int(cn.get('to_index', 0))
        try:
            if in_idx < len(dst.inputConnectors) and out_idx < len(src.outputConnectors):
                dst.inputConnectors[in_idx].connect(src.outputConnectors[out_idx])
                wired.append({"from": src.path, "to": dst.path, "from_index": out_idx, "to_index": in_idx})
            else:
                warnings.append(f"índice de conector fuera de rango en {src.path}[{out_idx}] -> {dst.path}[{in_idx}]")
        except Exception as e:
            warnings.append(f"wire {src.path} -> {dst.path}: {e}")

    # 3. Cook de estabilización
    for _ in range(3):
        for item in created_ops:
            n = op(item['path'])
            if n:
                try:
                    n.cook(force=True)
                except Exception:
                    pass

    print('<<JSON>>' + json.dumps({
        "ok": True,
        "template_name": spec['template_name'],
        "container_path": target_comp.path,
        "created_count": len(created_ops),
        "created_ops": created_ops,
        "wired_count": len(wired),
        "wired": wired,
        "warnings": warnings,
    }))
'''


def t_instantiate_template(a: dict) -> dict:
    """Materializa en TouchDesigner un template de red (network_templates.json) o receta (recipes) en una sola llamada, creando nodos, expandiendo bloques de secuencia, aplicando parámetros/expresiones, cableando y ordenando el layout."""
    t_name = str(a.get("template_name") or a.get("name") or "").strip()
    if not t_name:
        return {"ok": False, "error": "falta 'template_name' (ej. 'particle_gpu_basic', 'feedback_loop_top', 'basic_3d_render')"}
    parent_path = str(a.get("parent_path") or "/project1").strip()
    container_name = str(a.get("container_name") or "").strip() or None
    clear_first = str(a.get("clear_first") or "").lower() in ("1", "true", "yes", "si", "sí") or a.get("clear_first") is True

    from server import _all_network_templates, ts
    tpls = _all_network_templates()
    recipes = ts("recipes", "listRecipes") or []

    tpl_list = [{"name": k, **v} for k, v in tpls.items()] if isinstance(tpls, dict) else [x for x in tpls if isinstance(x, dict)]
    rec_list = [{"name": k, **v} for k, v in recipes.items()] if isinstance(recipes, dict) else [x for x in recipes if isinstance(x, dict)]

    tpl = None
    source_kind = None
    t_norm = t_name.lower().replace("-", "_")
    for item in tpl_list:
        k = str(item.get("name") or "")
        if k.lower().replace("-", "_") == t_norm:
            tpl = item
            t_name = k
            source_kind = "network_template"
            break
    if not tpl:
        for item in rec_list:
            k = str(item.get("name") or "")
            if k.lower().replace("-", "_") == t_norm:
                tpl = item
                t_name = k
                source_kind = "ts_recipe"
                break
    if not tpl:
        avail = sorted({str(x.get("name")) for x in (tpl_list + rec_list) if x.get("name")})
        return {"ok": False, "error": f"template '{t_name}' no encontrado", "available_templates": avail}

    # Normalizar nodos, parámetros y conexiones entre los 3 esquemas (operators / chain / nodes)
    par_by_id: dict[str, dict] = {}
    top_pars = tpl.get("parameters")
    if isinstance(top_pars, list):
        for p_item in top_pars:
            if not isinstance(p_item, dict):
                continue
            oid = str(p_item.get("opId") or "")
            pname = str(p_item.get("paramName") or "")
            pval = p_item.get("value")
            if not oid or not pname:
                continue
            d = par_by_id.setdefault(oid, {})
            if pname == "resolution" and isinstance(pval, (list, tuple)) and len(pval) == 2:
                d["outputresolution"] = "custom"
                d["resolutionw"] = int(pval[0])
                d["resolutionh"] = int(pval[1])
            elif pname == "scale" and isinstance(pval, (list, tuple)) and len(pval) == 2:
                d["sx"] = float(pval[0])
                d["sy"] = float(pval[1])
            else:
                d[pname] = pval
    elif isinstance(top_pars, dict):
        for k, v in top_pars.items():
            if isinstance(v, dict):
                par_by_id[str(k)] = dict(v)

    norm_nodes = []
    has_positions = False
    ops_raw = tpl.get("operators") or tpl.get("chain") or tpl.get("nodes") or []
    type_counts: dict[str, int] = {}
    for idx, op_spec in enumerate(ops_raw):
        if isinstance(op_spec, str):
            op_type = op_spec.strip()
            base = re.sub(r"(POP|TOP|CHOP|SOP|DAT|MAT|COMP)$", "", op_type).lower() or "op"
            type_counts[base] = type_counts.get(base, 0) + 1
            op_name = f"{base}{type_counts[base]}"
            merged_pars = dict(par_by_id.get(op_type, {}))
            norm_nodes.append({
                "id": str(idx),
                "name": op_name,
                "type": op_type,
                "parent": None,
                "position": None,
                "parameters": merged_pars,
                "flags": {},
            })
        elif isinstance(op_spec, dict):
            if op_spec.get("position"):
                has_positions = True
            op_type = str(op_spec.get("type") or op_spec.get("opType") or "")
            op_name = str(op_spec.get("name") or op_spec.get("id") or f"op_{idx}")
            op_id = str(op_spec.get("id") or op_name)
            merged_pars = {}
            merged_pars.update(par_by_id.get(op_type, {}))
            merged_pars.update(par_by_id.get(op_id, {}))
            merged_pars.update(par_by_id.get(op_name, {}))
            merged_pars.update(op_spec.get("parameters") or op_spec.get("params") or {})
            norm_nodes.append({
                "id": op_id,
                "name": op_name,
                "type": op_type,
                "parent": op_spec.get("parent"),
                "position": op_spec.get("position"),
                "parameters": merged_pars,
                "flags": op_spec.get("flags") or {},
                "dat_content": op_spec.get("dat_content"),
            })

    norm_conns = []
    deferred_pars = []
    raw_conns = tpl.get("connections")
    if isinstance(raw_conns, list):
        for c in raw_conns:
            if isinstance(c, dict):
                f_raw = c.get("from")
                t_raw = c.get("to")
                if isinstance(f_raw, int) and 0 <= f_raw < len(norm_nodes):
                    f_raw = norm_nodes[f_raw]["name"]
                if isinstance(t_raw, int) and 0 <= t_raw < len(norm_nodes):
                    t_raw = norm_nodes[t_raw]["name"]
                in_idx = c.get("to_index") if c.get("to_index") is not None else (
                    c.get("inputIndex") if c.get("inputIndex") is not None else (
                        c.get("toInput") if c.get("toInput") is not None else c.get("input", 0)
                    )
                )
                out_idx = c.get("from_index") if c.get("from_index") is not None else c.get("fromOutput", 0)
                norm_conns.append({
                    "from": str(f_raw),
                    "to": str(t_raw),
                    "from_index": int(out_idx or 0),
                    "to_index": int(in_idx or 0),
                })
            elif isinstance(c, str):
                m_par = re.match(r"^\s*([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)\s*(?:→|->)\s*['\"]?([A-Za-z0-9_]+)['\"]?", c)
                if m_par:
                    deferred_pars.append({"node": m_par.group(1), "par": m_par.group(2), "ref_target": m_par.group(3)})
                    continue
                m_wire = re.match(r"^\s*([A-Za-z0-9_]+)\s*(?:→|->)\s*([A-Za-z0-9_]+)(?:\s+input\s+(\d+))?", c)
                if m_wire:
                    norm_conns.append({
                        "from": m_wire.group(1),
                        "to": m_wire.group(2),
                        "from_index": 0,
                        "to_index": int(m_wire.group(3) or 0),
                    })
    elif tpl.get("chain") and len(norm_nodes) > 1:
        norm_conns = [
            {"from": norm_nodes[i]["name"], "to": norm_nodes[i + 1]["name"], "from_index": 0, "to_index": 0}
            for i in range(len(norm_nodes) - 1)
        ]

    spec = {
        "template_name": t_name,
        "parent_path": parent_path,
        "container_name": container_name,
        "clear_first": clear_first,
        "nodes": norm_nodes,
        "connections": norm_conns,
        "deferred_pars": deferred_pars,
    }
    code = _INSTANTIATE_TEMPLATE.replace("__SPEC__", repr(spec))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    if ok and isinstance(res, dict) and res.get("ok") and not has_positions and res.get("container_path"):
        try:
            t_auto_layout({"parent_path": res["container_path"]})
            res["auto_layout_applied"] = True
        except Exception:
            pass
    return res


# ── 17. td_verify_network — Verificación física, temporal y visual en 1 llamada ─

_VERIFY_NETWORK = r'''
import json, math
spec = __SPEC__
root = op(spec['container_path'])
if not root:
    print('<<JSON>>' + json.dumps({"ok": False, "error": "contenedor no encontrado: " + spec['container_path']}))
else:
    # 1. Settle: 4 pasadas de cook forzadas en orden de hijos
    all_ops = []
    def collect(comp, depth):
        for c in comp.children:
            if c.name.startswith('.'):
                continue
            all_ops.append(c)
            if c.family == 'COMP' and depth < 4:
                collect(c, depth + 1)
    collect(root, 0)

    for _ in range(4):
        for n in all_ops:
            try:
                n.cook(force=True)
            except Exception:
                pass

    # 2. Auditoría de geometryCOMPs (ownership guard: torus1 borrado + display/render + numPoints/numPrims)
    geo_checks = []
    actionable_fixes = []
    geos = [n for n in ([root] + all_ops) if getattr(n, 'OPType', n.type) == 'geometryCOMP']
    for g in geos:
        t1 = g.op('torus1')
        torus_alive = bool(t1 and (getattr(t1, 'display', False) or getattr(t1, 'render', False)))
        active_children = []
        for gc in g.children:
            if gc.family in ('POP', 'SOP') and (getattr(gc, 'display', False) or getattr(gc, 'render', False)):
                npts = int(gc.numPoints() if callable(getattr(gc, 'numPoints', None)) else getattr(gc, 'numPoints', 0))
                nprims = int(gc.numPrims() if callable(getattr(gc, 'numPrims', None)) else getattr(gc, 'numPrims', 0))
                active_children.append({
                    "path": gc.path, "name": gc.name, "type": getattr(gc, 'OPType', gc.type),
                    "display": bool(getattr(gc, 'display', False)),
                    "render": bool(getattr(gc, 'render', False)),
                    "numPoints": npts, "numPrims": nprims,
                })
        mat_name = str(g.par.material.eval()) if hasattr(g.par, 'material') else ""
        mat_node = (op(mat_name) or g.parent().op(mat_name)) if mat_name else None
        mat_type = getattr(mat_node, 'OPType', mat_node.type) if mat_node else ""

        g_ok = (not torus_alive) and len(active_children) > 0 and all(ac['numPoints'] > 0 and ac['numPrims'] > 0 for ac in active_children)
        if torus_alive:
            actionable_fixes.append(f"En {g.path} sigue vivo el 'torus1' por defecto con display/render activo. Destruilo con op('{g.path}/torus1').destroy().")
        if not active_children:
            actionable_fixes.append(f"En {g.path} ningún POP/SOP tiene display=True y render=True. Activá ambos flags en el nullPOP/nullSOP final.")
        for ac in active_children:
            if ac['numPoints'] == 0:
                actionable_fixes.append(f"El nodo de salida {ac['path']} tiene 0 puntos (numPoints == 0). Revisá el generador POP/SOP aguas arriba.")
            elif ac['numPrims'] == 0:
                actionable_fixes.append(f"El nodo de salida {ac['path']} tiene {ac['numPoints']} puntos pero 0 primitivas (numPrims == 0). Insertá un convertPOP con convert='topointprims' antes del nullPOP.")

        geo_checks.append({
            "geo_path": g.path,
            "ok": g_ok,
            "torus1_alive": torus_alive,
            "material": mat_name or None,
            "material_type": mat_type or None,
            "active_outputs": active_children,
        })

    # 3. Verificación numérica (NaN / Inf) y actividad en POPs y CHOPs
    nan_issues = []
    pop_summaries = []
    chop_summaries = []
    if spec.get('check_temporal', True):
        for n in all_ops:
            if n.family == 'POP':
                try:
                    npts = int(n.numPoints() if callable(getattr(n, 'numPoints', None)) else getattr(n, 'numPoints', 0))
                    nprims = int(n.numPrims() if callable(getattr(n, 'numPrims', None)) else getattr(n, 'numPrims', 0))
                    b = n.bounds() if callable(getattr(n, 'bounds', None)) else getattr(n, 'bounds', None)
                    has_nan = False
                    if b:
                        coords = [float(b.min[0]), float(b.min[1]), float(b.min[2]), float(b.max[0]), float(b.max[1]), float(b.max[2])]
                        has_nan = any(math.isnan(v) or math.isinf(v) for v in coords)
                    if has_nan:
                        nan_issues.append({"path": n.path, "type": getattr(n, 'OPType', n.type), "issue": "NaN/Inf detectado en bounds de geometría POP"})
                        actionable_fixes.append(f"NaN/Inf detectado en {n.path}. Revisá divisiones por cero o dt sin clamp en shaders/fuerzas.")
                    pop_summaries.append({"path": n.path, "type": getattr(n, 'OPType', n.type), "numPoints": npts, "numPrims": nprims, "nan_free": not has_nan})
                except Exception:
                    pass
            elif n.family == 'CHOP':
                try:
                    for ch in n.chans():
                        v = float(ch.eval())
                        if math.isnan(v) or math.isinf(v):
                            nan_issues.append({"path": n.path, "channel": ch.name, "issue": "NaN/Inf en canal CHOP"})
                            actionable_fixes.append(f"Canal '{ch.name}' en {n.path} contiene NaN/Inf.")
                    chop_summaries.append({"path": n.path, "type": getattr(n, 'OPType', n.type), "numChans": int(getattr(n, 'numChans', 0))})
                except Exception:
                    pass

    # 4. Detectar TOP candidato de render si no fue provisto
    render_candidate = spec.get('render_top')
    if not render_candidate:
        for n in all_ops:
            if n.family == 'TOP' and getattr(n, 'OPType', n.type) in ('renderTOP', 'outTOP', 'nullTOP'):
                render_candidate = n.path
                if getattr(n, 'OPType', n.type) in ('outTOP', 'nullTOP'):
                    break

    print('<<JSON>>' + json.dumps({
        "ok": True,
        "container_path": root.path,
        "total_ops": len(all_ops),
        "geo_checks": geo_checks,
        "nan_issues": nan_issues,
        "pops": pop_summaries[:25],
        "chops": chop_summaries[:25],
        "render_candidate": render_candidate,
        "actionable_fixes": actionable_fixes,
    }))
'''


def t_verify_network(a: dict) -> dict:
    """Verificación física, temporal, de errores y visual de un contenedor en 1 sola llamada (settle 4 pasadas + ownership de geometryCOMPs + NaN/Inf check + get_op_errors_deep + eval_render_frame)."""
    container_path = str(a.get("container_path") or a.get("root_path") or "/project1").strip()
    render_top = str(a.get("render_top") or "").strip() or None
    check_temporal = a.get("check_temporal", True) is not False

    spec = {
        "container_path": container_path,
        "render_top": render_top,
        "check_temporal": check_temporal,
    }
    code = _VERIFY_NETWORK.replace("__SPEC__", repr(spec))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    if not ok or not isinstance(res, dict) or not res.get("ok"):
        return res

    # Integrar errores profundos y compilación GLSL
    deep = t_get_op_errors_deep({"root_path": container_path, "recurse": True})
    fixes = list(res.get("actionable_fixes") or [])
    for err in deep.get("errors") or []:
        fixes.append(f"Error de operador en {err['op']} ({err['type']}): {err['errors']}")
    for serr in deep.get("shader_errors") or []:
        fixes.append(f"Error de compilación GLSL en {serr['op']}: {serr['details'][:250]}")

    # Integrar evaluación visual si hay TOP de salida/render
    cand_top = render_top or res.get("render_candidate")
    frame_eval = None
    if cand_top:
        ev = t_eval_render_frame({"op_path": cand_top})
        frame_eval = {
            "op_path": cand_top,
            "quality": ev.get("quality"),
            "verdict": ev.get("verdict"),
            "resolution": ev.get("resolution"),
            "metrics": ev.get("metrics"),
        }
        if ev.get("quality") == "FAIL":
            fixes.append(f"Fallo visual en {cand_top}: {ev.get('verdict')}")

    geo_ok = all(g.get("ok", True) for g in (res.get("geo_checks") or []))
    nan_ok = len(res.get("nan_issues") or []) == 0
    err_ok = deep.get("error_count", 0) == 0
    vis_ok = (frame_eval is None) or (frame_eval.get("quality") == "PASS")

    all_pass = geo_ok and nan_ok and err_ok and vis_ok
    verdict = "PASS" if all_pass else "FAIL"

    return {
        "ok": all_pass,
        "verdict": verdict,
        "container_path": res.get("container_path"),
        "total_ops": res.get("total_ops", 0),
        "checks": {
            "geometry_ownership_ok": geo_ok,
            "nan_inf_free": nan_ok,
            "errors_and_shaders_clean": err_ok,
            "visual_render_ok": vis_ok,
        },
        "geo_checks": res.get("geo_checks", []),
        "nan_issues": res.get("nan_issues", []),
        "errors_deep": {
            "error_count": deep.get("error_count", 0),
            "warning_count": deep.get("warning_count", 0),
            "errors": deep.get("errors", []),
            "shader_errors": deep.get("shader_errors", []),
            "warnings": deep.get("warnings", []),
        },
        "frame_evaluation": frame_eval,
        "pops": res.get("pops", []),
        "actionable_fixes": fixes,
    }


# ── 18. td_profile_network — Profiler de rendimiento y detector de anti-patrones ─

_PROFILE_NETWORK = r'''
import json, time
spec = __SPEC__
root = op(spec['root_path'])
if not root:
    print('<<JSON>>' + json.dumps({"ok": False, "error": "contenedor no encontrado: " + spec['root_path']}))
else:
    t0 = time.monotonic()
    max_depth = int(spec.get('max_depth', 4))
    max_nodes = int(spec.get('max_nodes', 2500))
    max_sec = float(spec.get('max_sec', 8.0))
    force_cook = bool(spec.get('force_cook', False))
    fps_target = float(spec.get('fps_target', 60.0))
    frame_budget_ms = 1000.0 / max(fps_target, 1.0)

    nodes_data = []
    anti_patterns = []
    by_family_ms = {}
    total_cpu_ms = 0.0
    total_gpu_ms = 0.0
    scanned = 0
    truncated = None

    def walk(comp, depth):
        global scanned, total_cpu_ms, total_gpu_ms, truncated
        if truncated:
            return
        for c in comp.children:
            if c.name.startswith('.'):
                continue
            scanned += 1
            if scanned > max_nodes:
                truncated = f"max_nodes ({max_nodes}) alcanzado"
                return
            if (time.monotonic() - t0) > max_sec:
                truncated = f"max_sec ({max_sec}s) alcanzado"
                return
            if force_cook:
                try:
                    c.cook(force=True)
                except Exception:
                    pass
            fam = c.family
            op_t = getattr(c, 'OPType', c.type)
            cpu_ms = float(getattr(c, 'cookTime', 0.0) or 0.0)
            gpu_ms = float(getattr(c, 'gpuCookTime', 0.0) or 0.0)
            cpu_mem = int(getattr(c, 'cpuMemory', 0) or 0)
            gpu_mem = int(getattr(c, 'gpuMemory', 0) or 0)
            total_cpu_ms += cpu_ms
            total_gpu_ms += gpu_ms
            by_family_ms[fam] = round(by_family_ms.get(fam, 0.0) + cpu_ms + gpu_ms, 4)

            if cpu_ms > 0.005 or gpu_ms > 0.005 or cpu_mem > 0 or gpu_mem > 0:
                nodes_data.append({
                    "path": c.path,
                    "type": op_t,
                    "family": fam,
                    "cpu_ms": round(cpu_ms, 4),
                    "gpu_ms": round(gpu_ms, 4),
                    "total_ms": round(cpu_ms + gpu_ms, 4),
                    "cpu_mem_kb": round(cpu_mem / 1024.0, 1),
                    "gpu_mem_kb": round(gpu_mem / 1024.0, 1),
                })

            # Detección de anti-patrones de rendimiento (PERFORMANCE.md)
            try:
                if op_t == 'copyPOP':
                    npts = int(c.numPoints() if callable(getattr(c, 'numPoints', None)) else getattr(c, 'numPoints', 0))
                    if npts > 50000:
                        anti_patterns.append({
                            "op": c.path, "type": op_t, "severity": "HIGH",
                            "pattern": "copyPOP_high_geometry",
                            "message": f"copyPOP genera {npts} puntos reales en GPU. Si son copias idénticas, usá Hardware Instancing en geometryCOMP para ahorrar memoria y tiempo de geometría."
                        })
                elif fam == 'SOP' and getattr(comp, 'OPType', comp.type) == 'geometryCOMP':
                    has_pops = any(x.family == 'POP' for x in comp.children)
                    if has_pops and op_t != 'torusSOP':
                        anti_patterns.append({
                            "op": c.path, "type": op_t, "severity": "MEDIUM",
                            "pattern": "mixed_sop_in_pop_geo",
                            "message": f"Operador SOP ({op_t}) en CPU mezclado dentro de un geometryCOMP con POPs. Migralo a la familia POP para mantener el pipeline 100% en GPU."
                        })
                elif fam == 'TOP':
                    w = int(getattr(c, 'width', 0))
                    h = int(getattr(c, 'height', 0))
                    if w * h > 3840 * 2160:
                        anti_patterns.append({
                            "op": c.path, "type": op_t, "severity": "HIGH",
                            "pattern": "oversized_top",
                            "message": f"Textura {w}x{h} supera 4K UHD ({round(gpu_mem / (1024*1024), 1)} MB VRAM). Reducí la resolución si no es estrictamente necesaria."
                        })
                elif op_t in ('poptoCHOP', 'toptoCHOP', 'soptoCHOP'):
                    ns = int(getattr(c, 'numSamples', 0))
                    if ns > 2000:
                        anti_patterns.append({
                            "op": c.path, "type": op_t, "severity": "HIGH",
                            "pattern": "heavy_gpu_to_cpu_readback",
                            "message": f"{op_t} descarga {ns} muestras a CPU cada frame (cuello de botella de bus PCIe). Procesá los datos en POP/TOP o reducí la cantidad de muestras."
                        })
                if (cpu_ms + gpu_ms) > (frame_budget_ms * 0.25):
                    anti_patterns.append({
                        "op": c.path, "type": op_t, "severity": "WARN",
                        "pattern": "single_op_frame_hog",
                        "message": f"{c.path} consume {round(cpu_ms + gpu_ms, 2)} ms (>25% del presupuesto de {round(frame_budget_ms, 2)} ms para {int(fps_target)} FPS)."
                    })
            except Exception:
                pass

            if fam == 'COMP' and depth + 1 < max_depth:
                walk(c, depth + 1)

    walk(root, 0)
    nodes_data.sort(key=lambda x: -x['total_ms'])
    top_n = int(spec.get('top_n', 15))
    combined_ms = round(total_cpu_ms + total_gpu_ms, 3)
    budget_pct = round((combined_ms / frame_budget_ms) * 100.0, 1)

    out_payload = {
        "ok": True,
        "root": root.path,
        "scanned_nodes": scanned,
        "fps_target": fps_target,
        "frame_budget_ms": round(frame_budget_ms, 2),
        "total_cpu_ms": round(total_cpu_ms, 3),
        "total_gpu_ms": round(total_gpu_ms, 3),
        "combined_cook_ms": combined_ms,
        "frame_budget_used_pct": budget_pct,
        "budget_verdict": "OVER_BUDGET" if budget_pct > 85.0 else ("TIGHT" if budget_pct > 50.0 else "HEALTHY"),
        "by_family_ms": by_family_ms,
        "bottlenecks": nodes_data[:top_n],
        "anti_patterns_count": len(anti_patterns),
        "anti_patterns": anti_patterns[:30],
    }
    if truncated:
        out_payload["truncated"] = truncated
    print('<<JSON>>' + json.dumps(out_payload))
'''


def t_profile_network(a: dict) -> dict:
    """Perfila tiempos de cook CPU/GPU y uso de memoria en un subárbol, calcula el % del presupuesto de frame (ej. 16.67ms a 60fps) y detecta anti-patrones de rendimiento de TouchDesigner."""
    root_path = str(a.get("root_path") or "/project1").strip()
    spec = {
        "root_path": root_path,
        "max_depth": int(a.get("max_depth") or 4),
        "top_n": int(a.get("top_n") or 15),
        "fps_target": float(a.get("fps_target") or 60.0),
        "force_cook": str(a.get("force_cook") or "").lower() in ("1", "true", "yes", "si", "sí") or a.get("force_cook") is True,
        "max_nodes": int(a.get("max_nodes") or 2500),
        "max_sec": float(a.get("max_sec") or 8.0),
    }
    code = _PROFILE_NETWORK.replace("__SPEC__", repr(spec))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    return res


# ── 19. td_scaffold_component — Pilar 6: Custom Pars + Bindings + Extensions ─

_SCAFFOLD_COMPONENT = r'''
import json
spec = __SPEC__
comp_path = spec['comp_path']
comp = op(comp_path)
if not comp:
    parent_p, c_name = comp_path.rsplit('/', 1) if '/' in comp_path.strip('/') else ('/', comp_path.strip('/'))
    parent = op(parent_p or '/')
    if not parent:
        print('<<JSON>>' + json.dumps({"ok": False, "error": "contenedor padre no encontrado: " + str(parent_p)}))
        comp = None
    else:
        cls = getattr(td, spec.get('comp_type', 'baseCOMP'), td.baseCOMP)
        comp = parent.create(cls, c_name)

if comp:
    warnings = []
    created_pars = []
    wired_targets = []
    page_name = spec.get('page_name') or 'Controls'
    page = None
    for pg in comp.customPages:
        if pg.name == page_name:
            page = pg
            break
    if not page and spec.get('custom_pars'):
        page = comp.appendCustomPage(page_name)

    STYLE_METHODS = {
        'float': 'appendFloat', 'int': 'appendInt', 'toggle': 'appendToggle',
        'pulse': 'appendPulse', 'str': 'appendStr', 'string': 'appendStr',
        'menu': 'appendMenu', 'rgb': 'appendRGB', 'rgba': 'appendRGBA',
        'xy': 'appendXY', 'xyz': 'appendXYZ', 'wh': 'appendWH',
        'top': 'appendTOP', 'chop': 'appendCHOP', 'pop': 'appendPOP',
        'sop': 'appendSOP', 'dat': 'appendDAT', 'comp': 'appendCOMP', 'mat': 'appendMAT',
    }

    for cp in (spec.get('custom_pars') or []):
        raw_name = str(cp.get('name') or '').strip()
        if not raw_name:
            continue
        p_name = raw_name[0].upper() + raw_name[1:]
        style = str(cp.get('style') or 'Float').strip().lower()
        label = str(cp.get('label') or p_name)
        m_name = STYLE_METHODS.get(style, 'appendFloat')
        fn = getattr(page, m_name, None)
        if not fn:
            warnings.append(f"estilo de custom par no soportado: {style}")
            continue
        try:
            kwargs = {'label': label}
            if style in ('float', 'int') and cp.get('size'):
                kwargs['size'] = int(cp['size'])
            par_group = fn(p_name, **kwargs)
            p0 = par_group[0]
            if cp.get('min') is not None:
                for p in par_group:
                    p.min = float(cp['min'])
                    p.normMin = float(cp.get('normMin', cp['min']))
                    if cp.get('clampMin'):
                        p.clampMin = True
            if cp.get('max') is not None:
                for p in par_group:
                    p.max = float(cp['max'])
                    p.normMax = float(cp.get('normMax', cp['max']))
                    if cp.get('clampMax'):
                        p.clampMax = True
            if style == 'menu' and cp.get('menuNames'):
                p0.menuNames = [str(x) for x in cp['menuNames']]
                p0.menuLabels = [str(x) for x in (cp.get('menuLabels') or cp['menuNames'])]
            if cp.get('default') is not None:
                dval = cp['default']
                if isinstance(dval, (list, tuple)):
                    for idx, p in enumerate(par_group):
                        if idx < len(dval):
                            p.default = dval[idx]
                            p.val = dval[idx]
                else:
                    p0.default = dval
                    p0.val = dval
            created_pars.append({"name": p0.name, "style": style, "label": label})

            # Vincular targets internos (ej. "noise1.amp" o "glsl1.vec0valuex")
            mode = str(cp.get('link_mode') or 'expr').lower()
            for tgt in (cp.get('targets') or []):
                if '.' not in str(tgt):
                    continue
                t_op_rel, t_par_name = str(tgt).rsplit('.', 1)
                t_node = comp.op(t_op_rel)
                if not t_node or not hasattr(t_node.par, t_par_name):
                    warnings.append(f"target no encontrado: {tgt}")
                    continue
                tp = getattr(t_node.par, t_par_name)
                if mode == 'bind':
                    tp.bindExpr = f"parent().par.{p0.name}"
                else:
                    tp.expr = f"parent().par.{p0.name}"
                wired_targets.append({"custom_par": p0.name, "target": f"{t_node.path}.par.{t_par_name}", "mode": mode})
        except Exception as e:
            warnings.append(f"custom_par {p_name}: {e}")

    # Extensión Python opcional
    ext_info = None
    ext_code = spec.get('extension_code')
    ext_cls = spec.get('extension_class')
    if ext_code and ext_cls:
        dat_name = f"{ext_cls}Ext"
        edat = comp.op(dat_name) or comp.create(td.textDAT, dat_name)
        edat.text = ext_code
        try:
            if hasattr(comp.par, 'extension1'):
                comp.par.extension1 = f"op('./{dat_name}').module.{ext_cls}(me)"
            if hasattr(comp.par, 'extname1'):
                comp.par.extname1 = ext_cls
            if hasattr(comp.par, 'promoteextension1'):
                comp.par.promoteextension1 = True
            if hasattr(comp.par, 'reinitextensions'):
                comp.par.reinitextensions.pulse()
            ext_obj = getattr(comp.ext, ext_cls, None)
            ext_info = {
                "dat_path": edat.path,
                "class_name": ext_cls,
                "promoted": True,
                "initialized": ext_obj is not None,
            }
        except Exception as e:
            warnings.append(f"extension {ext_cls}: {e}")
            ext_info = {"dat_path": edat.path, "class_name": ext_cls, "initialized": False, "error": str(e)}

    tox_saved = None
    if spec.get('save_tox_path'):
        try:
            comp.save(spec['save_tox_path'])
            tox_saved = spec['save_tox_path']
        except Exception as e:
            warnings.append(f"save_tox: {e}")

    print('<<JSON>>' + json.dumps({
        "ok": True,
        "comp_path": comp.path,
        "comp_type": getattr(comp, 'OPType', comp.type),
        "page_name": page_name,
        "custom_pars_created": created_pars,
        "wired_targets": wired_targets,
        "extension": ext_info,
        "tox_saved": tox_saved,
        "warnings": warnings,
    }))
'''


def t_scaffold_component(a: dict) -> dict:
    """Encapsula un contenedor COMP como módulo profesional de producción: crea Custom Parameters tipados, los vincula por expresión o bind a operadores hijos, configura e inicializa una Python Extension y opcionalmente guarda el .tox."""
    comp_path = str(a.get("comp_path") or "").strip()
    if not comp_path:
        return {"ok": False, "error": "falta 'comp_path' (ej. '/project1/my_module')"}
    raw_cp = a.get("custom_pars")
    cp_list = []
    if isinstance(raw_cp, list):
        cp_list = raw_cp
    elif isinstance(raw_cp, str) and raw_cp.strip():
        try:
            cp_list = json.loads(raw_cp)
        except Exception as e:
            return {"ok": False, "error": f"custom_pars debe ser JSON válido (lista de objetos): {e}"}

    spec = {
        "comp_path": comp_path,
        "comp_type": str(a.get("comp_type") or "baseCOMP").strip(),
        "page_name": str(a.get("page_name") or "Controls").strip(),
        "custom_pars": cp_list,
        "extension_class": str(a.get("extension_class") or "").strip() or None,
        "extension_code": str(a.get("extension_code") or "") or None,
        "save_tox_path": str(a.get("save_tox_path") or "").strip() or None,
    }
    code = _SCAFFOLD_COMPONENT.replace("__SPEC__", repr(spec))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    return res


# ── 20. td_wire_reactive — Pilar 7: Puente reactivo auto-calibrado ───────────

_WIRE_REACTIVE = r'''
import json
spec = __SPEC__
src = op(spec['source_chop'])
dst = op(spec['target_op'])
if not src or src.family != 'CHOP':
    print('<<JSON>>' + json.dumps({"ok": False, "error": f"source_chop no encontrado o no es CHOP: {spec['source_chop']}"}))
elif not dst:
    print('<<JSON>>' + json.dumps({"ok": False, "error": f"target_op no encontrado: {spec['target_op']}"}))
else:
    t_par = spec['target_par']
    # Soportar expansión de sequence si apunta a vec0valuex, etc.
    import re
    m_seq = re.match(r'^([a-zA-Z]+)(\d+)([a-zA-Z0-9_]*)$', t_par)
    if m_seq:
        seq_par = getattr(dst.par, m_seq.group(1), None)
        if seq_par is not None and hasattr(seq_par, 'numBlocks'):
            try:
                idx = int(m_seq.group(2))
                if int(seq_par.numBlocks) <= idx:
                    seq_par.numBlocks = idx + 1
            except Exception:
                pass

    if not hasattr(dst.par, t_par):
        print('<<JSON>>' + json.dumps({"ok": False, "error": f"parámetro '{t_par}' no existe en {dst.path} ({dst.OPType})"}))
    else:
        try:
            src.cook(force=True)
        except Exception:
            pass
        chans = list(src.chans())
        if not chans:
            print('<<JSON>>' + json.dumps({"ok": False, "error": f"{src.path} no tiene canales activos"}))
        else:
            want_ch = spec.get('channel')
            ch_obj = next((c for c in chans if c.name == want_ch), chans[0]) if want_ch else chans[0]
            ch_name = ch_obj.name
            ns = int(getattr(src, 'numSamples', 1))
            vals = [float(ch_obj[i]) for i in range(min(max(ns, 1), 2048))] if ns > 1 else [float(ch_obj.eval())]
            r_min = min(vals)
            r_max = max(vals)
            if (r_max - r_min) < 1e-6:
                # Si es single-sample (ej. LFO o constante), inferir rango típico
                op_t = getattr(src, 'OPType', src.type)
                if op_t == 'lfoCHOP':
                    off = float(src.par.offset.eval()) if hasattr(src.par, 'offset') else 0.0
                    amp = float(src.par.amp.eval()) if hasattr(src.par, 'amp') else 1.0
                    r_min, r_max = off - amp, off + amp
                elif r_min < -1e-4:
                    r_min, r_max = -1.0, 1.0
                else:
                    r_min, r_max = 0.0, max(1.0, abs(r_max))

            parent = dst.parent()
            prefix = spec.get('prefix') or f"react_{dst.name}_{t_par}"

            def get_or_make(cls_name, n_name):
                c = parent.op(n_name)
                if c and getattr(c, 'OPType', c.type) != cls_name:
                    c.destroy()
                    c = None
                return c or parent.create(getattr(td, cls_name), n_name)

            sel = get_or_make('selectCHOP', prefix + '_sel')
            sel.par.chop = src.path
            sel.par.channames = ch_name

            mth = get_or_make('mathCHOP', prefix + '_map')
            mth.inputConnectors[0].connect(sel)
            mth.par.fromrange1 = float(r_min)
            mth.par.fromrange2 = float(r_max)
            mth.par.torange1 = float(spec['target_min'])
            mth.par.torange2 = float(spec['target_max'])

            tail = mth
            lag_path = None
            lag_u = float(spec.get('lag_up', 0.05))
            lag_d = float(spec.get('lag_down', 0.15))
            if lag_u > 0.0 or lag_d > 0.0:
                lg = get_or_make('lagCHOP', prefix + '_lag')
                lg.inputConnectors[0].connect(mth)
                lg.par.lag1 = lag_u
                lg.par.lag2 = lag_d
                tail = lg
                lag_path = lg.path

            nul = get_or_make('nullCHOP', prefix + '_ctrl')
            nul.inputConnectors[0].connect(tail)

            # Posicionar cadena cerca del operador destino
            try:
                base_x = dst.nodeX - 420
                base_y = dst.nodeY - 140
                for idx, n in enumerate([x for x in (sel, mth, op(lag_path) if lag_path else None, nul) if x]):
                    n.nodeX = base_x + idx * 140
                    n.nodeY = base_y
            except Exception:
                pass

            for n in (sel, mth, tail, nul):
                try:
                    n.cook(force=True)
                except Exception:
                    pass

            expr_str = f"op('{nul.name}')['{ch_name}']"
            getattr(dst.par, t_par).expr = expr_str
            try:
                dst.cook(force=True)
            except Exception:
                pass
            live_val = float(getattr(dst.par, t_par).eval())

            print('<<JSON>>' + json.dumps({
                "ok": True,
                "source_chop": src.path,
                "channel": ch_name,
                "measured_range": [round(r_min, 5), round(r_max, 5)],
                "target_range": [spec['target_min'], spec['target_max']],
                "chain_nodes": [x for x in (sel.path, mth.path, lag_path, nul.path) if x],
                "null_chop": nul.path,
                "target_op": dst.path,
                "target_par": t_par,
                "expression_set": expr_str,
                "live_evaluated_value": round(live_val, 5),
            }))
'''


def t_wire_reactive(a: dict) -> dict:
    """Puente reactivo auto-calibrado: mide el rango real de un canal CHOP, construye la cadena de acondicionamiento (selectCHOP -> mathCHOP auto-escalado -> lagCHOP -> nullCHOP) y lo vincula por expresión al parámetro o uniform destino."""
    source_chop = str(a.get("source_chop") or "").strip()
    target_op = str(a.get("target_op") or "").strip()
    target_par = str(a.get("target_par") or "").strip()
    if not source_chop or not target_op or not target_par:
        return {"ok": False, "error": "hacen falta 'source_chop', 'target_op' y 'target_par'"}
    spec = {
        "source_chop": source_chop,
        "channel": str(a.get("channel") or "").strip() or None,
        "target_op": target_op,
        "target_par": target_par,
        "target_min": float(a.get("target_min") if a.get("target_min") is not None else 0.0),
        "target_max": float(a.get("target_max") if a.get("target_max") is not None else 1.0),
        "lag_up": float(a.get("lag_up") if a.get("lag_up") is not None else 0.05),
        "lag_down": float(a.get("lag_down") if a.get("lag_down") is not None else 0.15),
        "prefix": str(a.get("prefix") or "").strip() or None,
    }
    code = _WIRE_REACTIVE.replace("__SPEC__", repr(spec))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    return res


# ── 21. td_frame_camera_to_geo — Pilar 8a: Auto-encuadre 3D matemático ───────

_FRAME_CAMERA = r'''
import json, math
spec = __SPEC__
root = op(spec['container_path'])
if not root:
    print('<<JSON>>' + json.dumps({"ok": False, "error": "contenedor no encontrado: " + spec['container_path']}))
else:
    cam = op(spec['camera_path']) if spec.get('camera_path') else None
    ren = None
    geos = []
    for c in ([root] + list(root.children)):
        t = getattr(c, 'OPType', c.type)
        if t == 'geometryCOMP':
            geos.append(c)
        elif t == 'cameraCOMP' and not cam:
            cam = c
        elif t == 'renderTOP' and not ren:
            ren = c

    if not cam:
        print('<<JSON>>' + json.dumps({"ok": False, "error": "no se encontró ningún cameraCOMP en " + root.path}))
    elif not geos:
        print('<<JSON>>' + json.dumps({"ok": False, "error": "no se encontró ningún geometryCOMP en " + root.path}))
    else:
        w_min = [float('inf'), float('inf'), float('inf')]
        w_max = [float('-inf'), float('-inf'), float('-inf')]
        measured_sources = []

        for g in geos:
            gx = float(g.par.tx.eval()) if hasattr(g.par, 'tx') else 0.0
            gy = float(g.par.ty.eval()) if hasattr(g.par, 'ty') else 0.0
            gz = float(g.par.tz.eval()) if hasattr(g.par, 'tz') else 0.0
            gsx = float(g.par.sx.eval()) if hasattr(g.par, 'sx') else 1.0
            gsy = float(g.par.sy.eval()) if hasattr(g.par, 'sy') else 1.0
            gsz = float(g.par.sz.eval()) if hasattr(g.par, 'sz') else 1.0

            for gc in g.children:
                if gc.family in ('POP', 'SOP') and (getattr(gc, 'display', False) or getattr(gc, 'render', False)):
                    try:
                        gc.cook(force=True)
                        b = gc.bounds() if callable(getattr(gc, 'bounds', None)) else getattr(gc, 'bounds', None)
                        if b:
                            bmin = [float(b.min[0]) * gsx + gx, float(b.min[1]) * gsy + gy, float(b.min[2]) * gsz + gz]
                            bmax = [float(b.max[0]) * gsx + gx, float(b.max[1]) * gsy + gy, float(b.max[2]) * gsz + gz]
                            for i in range(3):
                                w_min[i] = min(w_min[i], bmin[i], bmax[i])
                                w_max[i] = max(w_max[i], bmin[i], bmax[i])
                            measured_sources.append(gc.path)
                    except Exception:
                        pass

        if not measured_sources or any(math.isinf(v) or math.isnan(v) for v in w_min + w_max):
            print('<<JSON>>' + json.dumps({"ok": False, "error": "no se pudieron obtener bounds válidos de ningún POP/SOP con display/render en " + root.path}))
        else:
            center = [(w_min[i] + w_max[i]) * 0.5 for i in range(3)]
            size = [max(w_max[i] - w_min[i], 0.001) for i in range(3)]
            radius = max(math.sqrt(size[0]**2 + size[1]**2 + size[2]**2) * 0.5, 0.1)

            fov_deg = float(cam.par.fov.eval()) if hasattr(cam.par, 'fov') else 45.0
            aspect = (float(ren.width) / max(float(ren.height), 1.0)) if ren and getattr(ren, 'height', 0) else (16.0 / 9.0)
            fov_h_rad = math.radians(max(min(fov_deg, 160.0), 5.0))
            fov_v_rad = 2.0 * math.atan(math.tan(fov_h_rad * 0.5) / max(aspect, 0.1))
            min_half_fov = min(fov_h_rad, fov_v_rad) * 0.5

            padding = float(spec.get('padding', 1.35))
            dist = (radius * padding) / max(math.sin(min_half_fov), 0.05)

            old_pos = [float(cam.par.tx.eval()), float(cam.par.ty.eval()), float(cam.par.tz.eval())]
            cam.par.tx = round(center[0], 5)
            cam.par.ty = round(center[1], 5)
            cam.par.tz = round(center[2] + dist, 5)
            if hasattr(cam.par, 'rx'):
                cam.par.rx, cam.par.ry, cam.par.rz = 0.0, 0.0, 0.0
            if hasattr(cam.par, 'near'):
                cam.par.near = round(max(0.001, min(0.1, dist * 0.01)), 5)
            if hasattr(cam.par, 'far'):
                cam.par.far = round(max(1000.0, (dist + radius * 4.0) * 2.0), 2)

            if ren:
                for _ in range(3):
                    try:
                        ren.cook(force=True)
                    except Exception:
                        pass

            print('<<JSON>>' + json.dumps({
                "ok": True,
                "camera_path": cam.path,
                "render_top_path": ren.path if ren else None,
                "measured_sources": measured_sources,
                "world_bounds": {
                    "min": [round(v, 4) for v in w_min],
                    "max": [round(v, 4) for v in w_max],
                    "center": [round(v, 4) for v in center],
                    "size": [round(v, 4) for v in size],
                    "bounding_radius": round(radius, 4),
                },
                "camera_before": [round(v, 4) for v in old_pos],
                "camera_after": [round(float(cam.par.tx.eval()), 4), round(float(cam.par.ty.eval()), 4), round(float(cam.par.tz.eval()), 4)],
                "computed_distance": round(dist, 4),
                "near": float(cam.par.near.eval()) if hasattr(cam.par, 'near') else None,
                "far": float(cam.par.far.eval()) if hasattr(cam.par, 'far') else None,
            }))
'''


def t_frame_camera_to_geo(a: dict) -> dict:
    """Calcula el bounding box 3D mundial combinado de todos los POPs/SOPs activos en los geometryCOMP de un contenedor y auto-encuadra matemáticamente la cameraCOMP (tx/ty/tz y near/far según el FOV y aspect ratio)."""
    container_path = str(a.get("container_path") or "/project1").strip()
    spec = {
        "container_path": container_path,
        "camera_path": str(a.get("camera_path") or "").strip() or None,
        "padding": float(a.get("padding") if a.get("padding") is not None else 1.35),
    }
    code = _FRAME_CAMERA.replace("__SPEC__", repr(spec))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    if ok and isinstance(res, dict) and res.get("render_top_path") and a.get("eval_frame", True) is not False:
        ev = t_eval_render_frame({"op_path": res["render_top_path"]})
        res["frame_evaluation"] = {
            "quality": ev.get("quality"),
            "verdict": ev.get("verdict"),
            "metrics": ev.get("metrics"),
        }
    return res


# ── 22. td_visual_diff — Pilar 8b: Diff visual cuantitativo entre TOPs/PNGs ──

def t_visual_diff(a: dict) -> dict:
    """Compara cuantitativamente dos TOPs en vivo (top_a vs top_b) o dos imágenes PNG (image_a vs image_b) píxel a píxel, devolviendo mean_abs_diff, changed_pixels_pct, PSNR y veredicto (SIGNIFICANT_CHANGE / SUBTLE_CHANGE / IDENTICAL_NO_OP)."""
    import math
    import tempfile
    from pathlib import Path
    from PIL import Image

    top_a = str(a.get("top_a") or "").strip()
    top_b = str(a.get("top_b") or "").strip()
    img_a = str(a.get("image_a") or "").strip()
    img_b = str(a.get("image_b") or "").strip()

    tmp_files = []
    try:
        if top_a and not img_a:
            p_a = Path(tempfile.gettempdir()) / f"tdmcp_vdiff_a_{os.getpid()}.png"
            code_a = f"import json\nt = op({top_a!r})\nif not t: print('<<JSON>>' + json.dumps({{'error': 'no existe ' + {top_a!r}}}))\nelse:\n t.cook(force=True); t.save({str(p_a)!r}); print('<<JSON>>' + json.dumps({{'ok': True}}))"
            ok, ra = exec_code(code_a)
            if not ok or "error" in ra:
                return {"ok": False, "error": f"No se pudo capturar top_a ({top_a}): {ra}"}
            img_a = str(p_a)
            tmp_files.append(p_a)

        if top_b and not img_b:
            p_b = Path(tempfile.gettempdir()) / f"tdmcp_vdiff_b_{os.getpid()}.png"
            code_b = f"import json\nt = op({top_b!r})\nif not t: print('<<JSON>>' + json.dumps({{'error': 'no existe ' + {top_b!r}}}))\nelse:\n t.cook(force=True); t.save({str(p_b)!r}); print('<<JSON>>' + json.dumps({{'ok': True}}))"
            ok, rb = exec_code(code_b)
            if not ok or "error" in rb:
                return {"ok": False, "error": f"No se pudo capturar top_b ({top_b}): {rb}"}
            img_b = str(p_b)
            tmp_files.append(p_b)

        if not img_a or not img_b or not os.path.exists(img_a) or not os.path.exists(img_b):
            return {"ok": False, "error": "Debés proveer (top_a y top_b) o (image_a e image_b) válidos."}

        ia = Image.open(img_a).convert("RGBA")
        ib = Image.open(img_b).convert("RGBA")
        if ia.size != ib.size:
            ib = ib.resize(ia.size, Image.Resampling.BILINEAR)

        pa = list(ia.getdata())
        pb = list(ib.getdata())
        total_px = max(len(pa), 1)
        sum_abs = 0.0
        sum_sq = 0.0
        max_diff = 0.0
        changed_px = 0

        for rgba_a, rgba_b in zip(pa, pb):
            dr = abs(rgba_a[0] - rgba_b[0])
            dg = abs(rgba_a[1] - rgba_b[1])
            db = abs(rgba_a[2] - rgba_b[2])
            d_px = (dr + dg + db) / 3.0
            sum_abs += d_px
            sum_sq += (dr * dr + dg * dg + db * db) / 3.0
            if d_px > max_diff:
                max_diff = d_px
            if d_px > 2.0:
                changed_px += 1

        mae = sum_abs / total_px
        mse = sum_sq / total_px
        psnr = 99.0 if mse < 1e-9 else (10.0 * math.log10((255.0 * 255.0) / mse))
        changed_pct = (changed_px / total_px) * 100.0

        if mae < 0.2 and changed_pct < 0.1:
            verdict = "IDENTICAL_NO_OP"
        elif mae < 2.0 and changed_pct < 2.0:
            verdict = "SUBTLE_CHANGE"
        else:
            verdict = "SIGNIFICANT_CHANGE"

        return {
            "ok": True,
            "source_a": top_a or img_a,
            "source_b": top_b or img_b,
            "resolution": f"{ia.size[0]}x{ia.size[1]}",
            "verdict": verdict,
            "metrics": {
                "mean_abs_diff": round(mae, 3),
                "max_abs_diff": round(max_diff, 2),
                "changed_pixels_pct": round(changed_pct, 2),
                "psnr_db": round(psnr, 2),
            },
        }
    except Exception as e:
        return {"ok": False, "error": f"error en td_visual_diff: {e}"}
    finally:
        for tf in tmp_files:
            try:
                if tf.exists():
                    tf.unlink()
            except Exception:
                pass


# ── 23. td_control_simulation — Pilar 9: Reset, Pre-Roll y estabilidad temporal ─

_CONTROL_SIM = r'''
import json, math
spec = __SPEC__
root = op(spec['container_path'])
if not root:
    print('<<JSON>>' + json.dumps({"ok": False, "error": "contenedor no encontrado: " + spec['container_path']}))
else:
    all_ops = []
    def collect(comp, depth):
        for c in comp.children:
            if c.name.startswith('.'):
                continue
            all_ops.append(c)
            if c.family == 'COMP' and depth < 4:
                collect(c, depth + 1)
    collect(root, 0)

    TEMPORAL_TYPES = {
        'feedbackPOP', 'particlePOP', 'trailPOP', 'cachePOP',
        'feedbackTOP', 'cacheTOP', 'speedCHOP', 'filterCHOP', 'lagCHOP', 'trailCHOP',
    }
    temporal_nodes = []
    reset_pulsed = []
    action = spec.get('action', 'reset_and_preroll')

    for n in all_ops:
        t = getattr(n, 'OPType', n.type)
        if t in TEMPORAL_TYPES:
            temporal_nodes.append({"path": n.path, "type": t})
            if action in ('reset_and_preroll', 'reset_only'):
                for rp in ('resetpulse', 'reset', 'clear', 'preroll'):
                    p = getattr(n.par, rp, None)
                    if p is not None:
                        try:
                            if hasattr(p, 'pulse') and str(getattr(p, 'style', '')) == 'Pulse':
                                p.pulse()
                                reset_pulsed.append(f"{n.path}.par.{rp}.pulse()")
                        except Exception:
                            pass

    steps = int(spec.get('preroll_steps', 20)) if action != 'reset_only' else 2
    for _ in range(max(steps - 1, 1)):
        for n in all_ops:
            try:
                n.cook(force=True)
            except Exception:
                pass

    def snap_geo():
        out = {}
        for n in all_ops:
            if n.family in ('POP', 'SOP'):
                try:
                    npts = int(n.numPoints() if callable(getattr(n, 'numPoints', None)) else getattr(n, 'numPoints', 0))
                    b = n.bounds() if callable(getattr(n, 'bounds', None)) else getattr(n, 'bounds', None)
                    if b:
                        out[n.path] = {
                            "type": getattr(n, 'OPType', n.type),
                            "numPoints": npts,
                            "center": [float(b.center[0]), float(b.center[1]), float(b.center[2])],
                            "size": [float(b.size[0]), float(b.size[1]), float(b.size[2])],
                        }
                except Exception:
                    pass
        return out

    s0 = snap_geo()
    # Avanzar 1 frame del timeline para medir delta inter-frame real
    try:
        op('/').time.frame = op('/').time.frame + 1
    except Exception:
        pass
    for n in all_ops:
        try:
            n.cook(force=True)
        except Exception:
            pass
    s1 = snap_geo()

    max_ext = float(spec.get('max_extent', 10000.0))
    sim_reports = []
    has_nan = False
    has_explosion = False
    has_motion = False
    has_points = False

    for path, d1 in s1.items():
        d0 = s0.get(path, d1)
        c0, c1 = d0['center'], d1['center']
        sz1 = d1['size']
        coords = c1 + sz1
        nan_here = any(math.isnan(v) or math.isinf(v) for v in coords)
        if nan_here:
            has_nan = True
        max_dim = max(sz1) if not nan_here else float('inf')
        if max_dim > max_ext:
            has_explosion = True
        dc = math.sqrt(sum((c1[i] - c0[i])**2 for i in range(3))) if not nan_here else 0.0
        ds = math.sqrt(sum((sz1[i] - d0['size'][i])**2 for i in range(3))) if not nan_here else 0.0
        delta = dc + ds
        if delta > 1e-6:
            has_motion = True
        if d1['numPoints'] > 0:
            has_points = True
        sim_reports.append({
            "path": path,
            "type": d1['type'],
            "numPoints": d1['numPoints'],
            "max_extent": round(max_dim, 4) if not nan_here else None,
            "interframe_delta": round(delta, 6),
            "nan_detected": nan_here,
        })

    recs = []
    if has_nan:
        state = "NAN_CORRUPTED"
        recs.append("Se detectó NaN/Inf tras el pre-roll. Revisá divisiones por 0 (normalize(vec3(0))) en glslPOP y pulsá reset.")
    elif has_explosion:
        state = "EXPLODING"
        recs.append(f"Los bounds superan max_extent ({max_ext}). Agregá un limitPOP (clamp/loop) o reducí la amplitud de fuerzas / dt.")
    elif not has_points and sim_reports:
        state = "EMPTY"
        recs.append("0 puntos vivos tras el pre-roll. Revisá birthrate y lifeexpect en particlePOP o la geometría emisora.")
    elif has_motion:
        state = "STABLE_DYNAMIC"
    else:
        state = "STABLE_STATIC"

    print('<<JSON>>' + json.dumps({
        "ok": state in ("STABLE_DYNAMIC", "STABLE_STATIC"),
        "container_path": root.path,
        "action": action,
        "preroll_steps": steps,
        "simulation_state": state,
        "temporal_nodes_count": len(temporal_nodes),
        "temporal_nodes": temporal_nodes,
        "reset_pulsed": reset_pulsed,
        "node_metrics": sim_reports[:25],
        "recommendations": recs,
    }))
'''


def t_control_simulation(a: dict) -> dict:
    """Controlador de simulaciones y loops temporales: detecta nodos con estado (feedbackPOP, particlePOP, feedbackTOP, trailPOP, cachePOP, speedCHOP), pulsa todos los resets atómicamente, avanza N pasos de pre-roll y diagnostica si la simulación está STABLE_DYNAMIC, STABLE_STATIC, EMPTY, EXPLODING o NAN_CORRUPTED."""
    container_path = str(a.get("container_path") or "/project1").strip()
    spec = {
        "container_path": container_path,
        "action": str(a.get("action") or "reset_and_preroll").strip().lower(),
        "preroll_steps": int(a.get("preroll_steps") if a.get("preroll_steps") is not None else 20),
        "max_extent": float(a.get("max_extent") if a.get("max_extent") is not None else 10000.0),
    }
    code = _CONTROL_SIM.replace("__SPEC__", repr(spec))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    return res


# ── 24. td_harvest_pattern — Pilar 10: Cosecha de patrones hacia templates ───

_HARVEST_PATTERN = r'''
import json
spec = __SPEC__
root = op(spec['container_path'])
if not root:
    print('<<JSON>>' + json.dumps({"ok": False, "error": "contenedor no encontrado: " + spec['container_path']}))
else:
    operators = []
    connections = []
    root_prefix = root.path.rstrip('/') + '/'

    def walk(comp, depth):
        for c in comp.children:
            if c.name.startswith('.'):
                continue
            rel_path = c.path[len(root_prefix):] if c.path.startswith(root_prefix) else c.name
            parent_rel = comp.path[len(root_prefix):] if comp != root and comp.path.startswith(root_prefix) else None
            pars = {}
            for p in c.pars():
                try:
                    if p.isDefault or str(getattr(p, 'style', '')) == 'Pulse':
                        continue
                    if str(p.mode).endswith('EXPRESSION'):
                        pars[p.name] = '=' + str(p.expr)
                    else:
                        v = p.eval()
                        if isinstance(v, (int, float, bool, str)):
                            pars[p.name] = v
                except Exception:
                    pass
            flags = {}
            for fk in ('display', 'render', 'bypass', 'lock'):
                try:
                    if bool(getattr(c, fk, False)):
                        flags[fk] = True
                except Exception:
                    pass
            op_entry = {
                "name": c.name,
                "type": getattr(c, 'OPType', c.type),
                "parent": parent_rel,
                "position": [int(getattr(c, 'nodeX', 0)), int(getattr(c, 'nodeY', 0))],
                "parameters": pars,
                "flags": flags,
            }
            if getattr(c, 'isText', False) and not c.name.endswith('_info'):
                txt = str(getattr(c, 'text', '') or '')
                if txt.strip():
                    op_entry["dat_content"] = txt
            operators.append(op_entry)

            for in_idx, conn in enumerate(c.inputConnectors):
                for cc in conn.connections:
                    src = cc.owner
                    src_rel = src.path[len(root_prefix):] if src.path.startswith(root_prefix) else src.name
                    connections.append({
                        "from": src_rel,
                        "to": rel_path,
                        "from_index": int(getattr(cc, 'index', 0)),
                        "to_index": in_idx,
                    })

            if c.family == 'COMP' and depth < 3:
                walk(c, depth + 1)

    walk(root, 0)
    print('<<JSON>>' + json.dumps({
        "ok": True,
        "container_path": root.path,
        "operators": operators,
        "connections": connections,
    }))
'''


def t_harvest_pattern(a: dict) -> dict:
    """Cosecha un contenedor vivo de TouchDesigner y lo guarda como template reutilizable en knowledge/custom_templates/<name>.json (+ .tdxn), quedando disponible inmediatamente en templates y td_instantiate_template."""
    container_path = str(a.get("container_path") or "").strip()
    raw_name = str(a.get("name") or "").strip()
    if not container_path or not raw_name:
        return {"ok": False, "error": "hacen falta 'container_path' y 'name' (ej. name='my-curl-scene')"}
    clean_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", raw_name).strip("-").lower()
    desc = str(a.get("description") or f"Patrón cosechado en vivo desde {container_path}").strip()
    raw_tags = a.get("tags") or ""
    tags = [t.strip() for t in str(raw_tags).split(",") if t.strip()] if isinstance(raw_tags, str) else list(raw_tags)

    code = _HARVEST_PATTERN.replace("__SPEC__", repr({"container_path": container_path}))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    if not ok or not isinstance(res, dict) or not res.get("ok"):
        return res

    tpl_doc = {
        "name": clean_name,
        "description": desc,
        "tags": tags or ["custom", "harvested"],
        "complexity": "custom",
        "harvested_from": res.get("container_path"),
        "operators": res.get("operators", []),
        "connections": res.get("connections", []),
    }
    custom_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "custom_templates")
    os.makedirs(custom_dir, exist_ok=True)
    json_path = os.path.join(custom_dir, f"{clean_name}.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(tpl_doc, fh, ensure_ascii=False, indent=2)

    tdxn_path = os.path.join(custom_dir, f"{clean_name}.tdxn")
    try:
        t_tdxn_export({"root_path": container_path, "out_path": tdxn_path, "include_dat_content": True})
    except Exception:
        tdxn_path = None

    return {
        "ok": True,
        "name": clean_name,
        "container_path": res.get("container_path"),
        "operators_count": len(tpl_doc["operators"]),
        "connections_count": len(tpl_doc["connections"]),
        "template_json": json_path,
        "template_tdxn": tdxn_path,
        "hint": f"Ya podés instanciarlo en cualquier proyecto con td_instantiate_template(template_name={clean_name!r}).",
    }


# ── registro ─────────────────────────────────────────────────────────────────

LIVE_TOOLS = [
    ("td_status", "¿Está TouchDesigner vivo? Devuelve proyecto, build, fps, estado de cooking (power/timeline/realTime) y versión del server oficial. Usalo primero si dudás de la conexión.",
     {}, t_status),
    ("find_in_ops", "Busca un texto en TODO un subárbol: contenido de DATs, expresiones de parámetros, nombres de par, comentarios y nombres de operador. Una sola llamada (corre dentro de TD con budget max_nodes/max_sec).",
     {"query": "string (requerido)", "root_path": "string (default /)", "in_dat": "bool (default true)",
      "in_expr": "bool (default true)", "in_name": "bool (default false)", "in_comment": "bool (default true)",
      "limit": "int (default 40)", "max_nodes": "int (default 2500)", "max_sec": "float (default 8.0)"}, t_find_in_ops),
    ("auto_layout", "Ordena los operadores de un COMP por dependencias (capas topológicas), sin cruces: calcula las posiciones localmente y las aplica con el oficial. dry_run=true para verlas sin mover.",
     {"parent_path": "string (requerido)", "direction": "lr|tb (default lr)", "hgap": "int (default 175)",
      "vgap": "int (default 130)", "dry_run": "bool", "include_docked": "bool (default true)"}, t_auto_layout),
    ("smart_connect", "Conecta dos operadores eligiendo el índice de input según la familia que espera el destino (lo lee de topology.json y la KB). Acepta input_index para forzarlo.",
     {"from_path": "string (requerido)", "to_path": "string (requerido)", "input_index": "int (opcional)"}, t_smart_connect),
    ("tdn_export", "Exporta una red a TDN v1.4 (JSON versionable en git) leyendo el proyecto en vivo. include_dat_content para incluir el texto/tablas de los DATs. Si das out_path escribe el .tdn.",
     {"root_path": "string (default /)", "out_path": "string (opcional)", "include_dat_content": "bool (default false)",
      "include_storage": "bool (default false)", "include_color": "bool (default false: el color del nodo cambia solo)"}, t_tdn_export),
    ("tdn_diff", "Compara dos archivos .tdn (offline, sin TD): operadores agregados/quitados y cambios de parámetros, tipos, flags y cableado.",
     {"path_a": "string (requerido)", "path_b": "string (requerido)"}, t_tdn_diff),
    ("tdxn_export", "Exporta red completa a TDXN v2.1 YAML (estándar Embody diffable). Ideal para generación o versionado masivo de COMPs en Git.",
     {"root_path": "string (default /)", "out_path": "string (opcional)", "include_dat_content": "bool (default true)",
      "include_storage": "bool (default false)", "include_color": "bool (default false)"}, t_tdxn_export),
    ("tdxn_build", "Construye una red completa en TouchDesigner a partir de TDXN v2.1 YAML (estándar Embody). Crea operadores, conexiones, parámetros (=expr, ~bind) y DATs en un solo turno.",
     {"tdxn": "string o path (requerido: contenido YAML o ruta .tdxn)", "parent_path": "string (opcional)",
      "clear_first": "bool (default false)", "dry_run": "bool (default false)"}, t_tdxn_build),
    ("eval_render_frame", "Evalúa calidad visual de una imagen o TOP: detecta frames negros, planos o transparentes emitiendo veredicto PASS/FAIL y métricas de luminancia y contraste.",
     {"image_path": "string (opcional)", "op_path": "string (opcional)"}, t_eval_render_frame),
    ("get_op_errors_deep", "Diagnóstico profundo de un COMP y sus hijos: detecta errores de cocinado, advertencias y trazas de compilación GLSL en DATs _info (con budget max_nodes/max_sec).",
     {"root_path": "string (default /)", "recurse": "bool (default true)", "max_nodes": "int (default 2500)", "max_sec": "float (default 8.0)"}, t_get_op_errors_deep),
    ("td_measure", "Mide en vivo un operador: rango real de canales CHOP (min, max, media, si es constante/normalizado y scale/offset sugeridos), geometría POP/SOP (numPoints, numPrims, bounds, atributos), resolución TOP o filas/texto DAT.",
     {"path": "string (requerido: ruta del operador)", "channel": "string (opcional, nombre de canal CHOP)",
      "target_min": "string (opcional, float default 0.0)", "target_max": "string (opcional, float default 1.0)"}, t_measure),
    ("td_glsl_apply", "Pipeline GLSL atómico en vivo: valida estáticamente el código (POP/TOP), crea el textDAT + glslPOP/glslcopyPOP/glslTOP, auto-configura Create Attributes / outputattrs / outputaccess / uniforms, conecta inputs y verifica la compilación.",
     {"name": "string (requerido: nombre del nodo GLSL)", "code": "string (requerido: código GLSL)",
      "parent_path": "string (default /project1)", "family": "pop|top|copy (default pop)",
      "source_path": "string (opcional: input 0)", "extra_inputs": "string (opcional: inputs 1,2… separados por coma)",
      "write_attrs": "string (opcional: ej. 'Color:4, PartVel:3')", "uniforms": "string (opcional: JSON dict de uniforms)",
      "resolution": "string (opcional para TOP: ej. '1280x720')", "skip_validation": "bool (default false)"}, t_glsl_apply),
    ("td_explore_project", "Radiografía rápida de un contenedor o proyecto en vivo: conteos por familia y tipo, contenedores hijos, shaders GLSL, customPars, errores activos y top operadores por cookTime.",
     {"root_path": "string (default /project1)", "max_depth": "int (default 3)", "max_nodes": "int (default 2500)", "max_sec": "float (default 8.0)"}, t_explore_project),
    ("td_compare_networks", "Compara en vivo dos contenedores COMP (path_a vs path_b): operadores únicos de cada lado, diferencias de parámetros no-default y diferencias de cableado.",
     {"path_a": "string (requerido)", "path_b": "string (requerido)"}, t_compare_networks),
    ("td_spatial_context", "Contexto espacial de la UI de TouchDesigner: pane activo, ruta abierta en el editor, operador actual (currentChild), operadores seleccionados y estado del timeline.",
     {}, t_spatial_context),
    ("td_build_pop_render", "Construye en 1 llamada el pipeline completo de renderizado POP (geometryCOMP sin torus1 + source/spherePOP + convertPOP topointprims + nullPOP display/render + cameraCOMP + pointsprite/constant/pbr MAT + renderTOP + nullTOP), fuerza 4 pasadas de cook y evalúa el frame.",
     {"parent_path": "string (default /project1)", "name": "string (default pop_scene)",
      "source_pop": "string (opcional: ruta de POP existente a renderizar)", "primitive_mode": "points|native (default points)",
      "material": "pointsprite|constant|pbr (default pointsprite)", "resolution": "string (default 1280x720)",
      "point_size": "float (default 4.0)", "camera_tz": "float (default 5.0)"}, t_build_pop_render),
    ("td_instantiate_template", "Instancia en vivo cualquier template de red (network_templates.json, pop-chains, custom_templates) o receta (recipes) en una sola llamada: crea contenedores y operadores, expande bloques de secuencia, aplica parámetros/expresiones, cablea y ordena el layout.",
     {"template_name": "string (requerido: ej. 'particle_gpu_basic', 'feedback-loop-top', 'pop-curl-noise')",
      "parent_path": "string (default /project1)", "container_name": "string (opcional: crea un baseCOMP contenedor)",
      "clear_first": "bool (default false)"}, t_instantiate_template),
    ("td_verify_network", "Verificación integral en 1 llamada (Gauntlet vivo): fuerza 4 pasadas de cook (settle), audita ownership de geometryCOMPs (torus1 borrado, display/render activos, numPoints/numPrims > 0), detecta NaN/Inf en POPs/CHOPs, corre get_op_errors_deep y eval_render_frame, y devuelve veredicto PASS/FAIL con actionable_fixes.",
     {"container_path": "string (default /project1)", "render_top": "string (opcional: ruta del TOP a evaluar visualmente)",
      "check_temporal": "bool (default true)"}, t_verify_network),
    ("td_profile_network", "Profiler de rendimiento y cuellos de botella en vivo: mide cookTime CPU, gpuCookTime y memoria por nodo, calcula el % del presupuesto de frame (ej. 16.67ms a 60fps) y detecta anti-patrones de rendimiento (copyPOP masivo sin instancing, SOPs en pipeline POP, TOPs >4K, readbacks GPU->CPU).",
     {"root_path": "string (default /project1)", "max_depth": "int (default 4)", "top_n": "int (default 15)",
      "fps_target": "float (default 60.0)", "force_cook": "bool (default false)"}, t_profile_network),
    ("td_scaffold_component", "Pilar 6 — Encapsula un COMP como módulo profesional de producción: crea páginas de Custom Parameters tipados, los vincula por expresión o bind a operadores hijos, configura e inicializa una Python Extension y opcionalmente exporta el .tox.",
     {"comp_path": "string (requerido: ej. '/project1/my_fx')", "comp_type": "string (default baseCOMP)",
      "page_name": "string (default Controls)", "custom_pars": "string (JSON list de custom pars con name, style, default, min, max, targets)",
      "extension_class": "string (opcional: nombre de clase Python)", "extension_code": "string (opcional: código de la extensión)",
      "save_tox_path": "string (opcional: ruta donde guardar .tox)"}, t_scaffold_component),
    ("td_wire_reactive", "Pilar 7 — Puente reactivo auto-calibrado: mide en vivo el rango real de un canal CHOP, construye la cadena de acondicionamiento (selectCHOP -> mathCHOP auto-escalado -> lagCHOP -> nullCHOP) y lo enlaza al parámetro o uniform destino.",
     {"source_chop": "string (requerido: ruta del CHOP fuente)", "target_op": "string (requerido: ruta del operador destino)",
      "target_par": "string (requerido: nombre del parámetro en target_op)", "channel": "string (opcional: canal CHOP)",
      "target_min": "float (default 0.0)", "target_max": "float (default 1.0)",
      "lag_up": "float (default 0.05)", "lag_down": "float (default 0.15)"}, t_wire_reactive),
    ("td_frame_camera_to_geo", "Pilar 8a — Auto-encuadre 3D matemático: calcula el bounding box mundial combinado de todos los POPs/SOPs activos en los geometryCOMP de un contenedor y posiciona la cameraCOMP (tx/ty/tz y near/far según FOV y aspect ratio) para que toda la geometría quede en cuadro.",
     {"container_path": "string (default /project1)", "camera_path": "string (opcional: ruta del cameraCOMP)",
      "padding": "float (default 1.35)"}, t_frame_camera_to_geo),
    ("td_visual_diff", "Pilar 8b — Diff visual cuantitativo píxel a píxel entre dos TOPs en vivo (top_a vs top_b) o dos imágenes PNG (image_a vs image_b): devuelve mean_abs_diff, changed_pixels_pct, PSNR y veredicto (SIGNIFICANT_CHANGE / SUBTLE_CHANGE / IDENTICAL_NO_OP).",
     {"top_a": "string (opcional: ruta del primer TOP)", "top_b": "string (opcional: ruta del segundo TOP)",
      "image_a": "string (opcional: ruta PNG A)", "image_b": "string (opcional: ruta PNG B)"}, t_visual_diff),
    ("td_control_simulation", "Pilar 9 — Controlador de simulaciones y loops temporales: detecta operadores con estado (feedbackPOP, particlePOP, feedbackTOP, trailPOP, cachePOP, speedCHOP), pulsa todos los resets atómicamente, avanza N pasos de pre-roll y diagnostica si está STABLE_DYNAMIC, STABLE_STATIC, EMPTY, EXPLODING o NAN_CORRUPTED.",
     {"container_path": "string (default /project1)", "action": "reset_and_preroll|reset_only|diagnose (default reset_and_preroll)",
      "preroll_steps": "int (default 20)", "max_extent": "float (default 10000.0)"}, t_control_simulation),
    ("td_harvest_pattern", "Pilar 10 — Cosecha un contenedor verificado en vivo y lo guarda como plantilla reutilizable en knowledge/custom_templates/<name>.json (+ .tdxn), quedando disponible inmediatamente en templates y td_instantiate_template.",
     {"container_path": "string (requerido: ruta del COMP a cosechar)", "name": "string (requerido: slug del template)",
      "description": "string (opcional)", "tags": "string (opcional: tags separados por coma)"}, t_harvest_pattern),
]

LIVE_NAMES = [n for n, _d, _s, _f in LIVE_TOOLS]
# Tools de lectura que no modifican la red de TouchDesigner
LIVE_READONLY = {
    "td_status", "find_in_ops", "tdn_diff", "eval_render_frame", "get_op_errors_deep",
    "td_measure", "td_explore_project", "td_compare_networks", "td_spatial_context",
    "td_verify_network", "td_profile_network", "td_visual_diff",
}



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

import wire as _wire

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


def _txt_of(r: dict) -> str:
    """Texto de la respuesta MCP (para leer el aviso del rate limiter)."""
    res = (r or {}).get("result") or {}
    return "".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")


def call(tool: str, args: dict | None = None, timeout: float | None = None) -> tuple[bool, dict]:
    """Llama una tool del MCP oficial. -> (ok, data).

    Reintenta SOLO lo seguro de reintentar (ver `wire.is_refused`): un
    ECONNREFUSED no llegó al server, un timeout de lectura pudo ejecutar la
    llamada y se reporta como tal. El rate limiter del componente pide
    reintentar la MISMA llamada y dice cuánto esperar.
    """
    global _ID, _SID
    import time
    hint = "abrí TouchDesigner con el .tox TDMCP en el root y pulsá Active en su página MCP"
    last_err = None
    r = None
    for attempt in range(3):
        try:
            _init()
            _ID += 1
            r = _post({"jsonrpc": "2.0", "id": _ID, "method": "tools/call",
                       "params": {"name": tool, "arguments": args or {}}}, timeout)
            break
        except urllib.error.HTTPError as e:  # sesión vencida / server reiniciado
            last_err = e
            _SID = None
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:400]
            except Exception:
                pass
            if attempt < 2 and _wire.is_session_error(e.code, body):
                time.sleep(0.25)
                continue
            return False, {"error": f"HTTP {e.code} del MCP oficial", "detail": body, "hint": hint}
        except Exception as e:
            last_err = e
            _SID = None
            if attempt < 2 and _wire.is_refused(e):
                time.sleep(0.25 * (attempt + 1))
                continue
            return False, {"error": f"TouchDesigner no responde en {URL} ({type(last_err).__name__}: {last_err})",
                           "pudo_ejecutarse": not _wire.is_refused(e), "hint": hint}
    # rate limiter: la respuesta es "exitosa" pero trae un aviso; se repite la MISMA llamada
    for _ in range(2):
        wait = _wire.rate_wait(_txt_of(r))
        if wait is None:
            break
        time.sleep(min(wait + 0.1, 10.0))
        try:
            _ID += 1
            r = _post({"jsonrpc": "2.0", "id": _ID, "method": "tools/call",
                       "params": {"name": tool, "arguments": args or {}}}, timeout)
        except Exception as e:
            return False, {"error": f"rate limiter y luego {type(e).__name__}: {e}", "pudo_ejecutarse": True}
    if _wire.rate_wait(_txt_of(r)) is not None:
        return False, {"error": "TD sigue en cooldown (recovering from a slow operation)",
                       "detail": _txt_of(r)[:300]}
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


MARK = _wire.MARK  # hogar único del literal y del parseo: knowledge/wire.py


def exec_code(code: str, timeout: float | None = None) -> tuple[bool, dict]:
    """Corre Python dentro de TD y devuelve el JSON que imprimió tras MARK."""
    ok, d = call("execute_code", {"code": code}, timeout)
    if not ok:
        return False, d
    ok, payload = _wire.json_after_mark(d.get("output", "") or "")
    if not ok and payload.get("error") == "sin marcador":
        payload["variables"] = list(d.get("variables", {}))
    return ok, payload


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

        # Uniforms (vec0name + vec0type + vec0valuex/y/z/w), soporta floats, listas y '=expr'
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
                            p_val = getattr(node.par, f'vec{idx}value{suf}')
                            raw_v = vals[c_i]
                            if isinstance(raw_v, str) and raw_v.strip().startswith('='):
                                p_val.expr = raw_v.strip()[1:].strip()
                            else:
                                p_val.val = float(raw_v)
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

        # Asegurar infoDAT conectado al nodo GLSL para capturar el log real del compilador GPU
        info_node = parent.op(name + '_info')
        if not info_node or getattr(info_node, 'OPType', info_node.type) != 'infoDAT':
            if info_node:
                info_node.destroy()
            info_node = parent.create(td.infoDAT, name + '_info')
        try:
            info_node.par.op = node.path
            info_node.nodeX = node.nodeX
            info_node.nodeY = node.nodeY - 210
            info_node.dock = node
            info_node.cook(force=True)
        except Exception:
            pass
        info_txt = (info_node.text or "").strip()

        # Extraer líneas de error de compilación con contexto de código GLSL
        import re
        error_lines = []
        code_lines = (spec.get('code') or '').splitlines()
        for line in info_txt.splitlines():
            m_err = re.search(r'(?:0\((\d+)\)|0:(\d+):)\s*(?:error|warning)[^:]*:\s*(.+)', line, re.I)
            if m_err:
                lno = int(m_err.group(1) or m_err.group(2))
                src_line = code_lines[lno - 1].strip() if 1 <= lno <= len(code_lines) else ""
                error_lines.append({"line": lno, "message": m_err.group(3).strip(), "code_line": src_line})

        has_shader_err = any(k in info_txt.lower() for k in ('error:', 'compilation error', 'failed')) or bool(errs)
        print('<<JSON>>' + json.dumps({
            "ok": not has_shader_err,
            "op_path": node.path,
            "dat_path": dat_node.path,
            "info_dat_path": info_node.path,
            "op_type": op_type,
            "linked_par": linked_par,
            "attrs_configured": attrs_configured,
            "uniforms_set": uniforms_set,
            "wired_inputs": wired,
            "compile_ok": not has_shader_err,
            "error_lines": error_lines,
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

    # Uniforms (auto-extraídos del código GLSL + overrides explícitos del usuario)
    uniforms = {}
    for m_u in re.finditer(r"^\s*uniform\s+(float|int|uint|vec2|vec3|vec4|ivec2|ivec3|ivec4)\s+([A-Za-z_]\w*)\s*;", code_str, re.M):
        utype, uname = m_u.group(1), m_u.group(2)
        if uname.startswith(("uTD", "sTD", "mTD")):
            continue
        if uname.lower() in ("utime", "time", "itime"):
            uniforms[uname] = "=absTime.seconds"
        elif utype.endswith("2"):
            uniforms[uname] = [0.0, 0.0]
        elif utype.endswith("3"):
            uniforms[uname] = [0.0, 0.0, 0.0]
        elif utype.endswith("4"):
            uniforms[uname] = [0.0, 0.0, 0.0, 1.0]
        else:
            uniforms[uname] = 0.0

    raw_u = a.get("uniforms")
    if isinstance(raw_u, dict):
        uniforms.update(raw_u)
    elif isinstance(raw_u, str) and raw_u.strip():
        try:
            uniforms.update(json.loads(raw_u))
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
            tidy_res = t_network_tidy({"network_path": res["container_path"], "action": "tidy", "animate": False})
            if tidy_res and tidy_res.get("ok"):
                res["tidy_applied"] = True
                res["tidy_status"] = tidy_res.get("status")
            else:
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
    """Verificación física, temporal, de errores, visual y de layout de un contenedor en 1 sola llamada (settle 4 pasadas + ownership de geometryCOMPs + NaN/Inf check + get_op_errors_deep + eval_render_frame + NetworkTidy por defecto)."""
    container_path = str(a.get("container_path") or a.get("root_path") or "/project1").strip()
    render_top = str(a.get("render_top") or "").strip() or None
    check_temporal = a.get("check_temporal", True) is not False
    tidy = False if str(a.get("tidy") or "").lower() in ("0", "false", "no") else True

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

    # Ordenamiento y validación estructural con NetworkTidy por defecto
    tidy_layout = None
    tidy_ok = True
    if tidy:
        try:
            tidy_res = t_network_tidy({
                "network_path": container_path,
                "action": "tidy",
                "animate": False,
                "frame_result": False,
            })
            if tidy_res and isinstance(tidy_res, dict):
                tidy_ok = bool(tidy_res.get("ok", True))
                tidy_layout = {
                    "ok": tidy_ok,
                    "status": tidy_res.get("status"),
                    "moved_count": tidy_res.get("moved_count", 0),
                    "nodes_total": tidy_res.get("nodes_total", 0),
                }
                if not tidy_ok:
                    fixes.append(f"Fallo en layout NetworkTidy: {tidy_res.get('error')}")
        except Exception as _te:
            tidy_layout = {"ok": False, "error": str(_te)}

    geo_ok = all(g.get("ok", True) for g in (res.get("geo_checks") or []))
    nan_ok = len(res.get("nan_issues") or []) == 0
    err_ok = deep.get("error_count", 0) == 0
    vis_ok = (frame_eval is None) or (frame_eval.get("quality") == "PASS")

    all_pass = geo_ok and nan_ok and err_ok and vis_ok and tidy_ok
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
            "layout_tidy_ok": tidy_ok,
        },
        "tidy_layout": tidy_layout,
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


# ── 25. td_build_control_panel — Pilar 11: Generador de Panel UI Perform ────

_BUILD_CONTROL_PANEL = r'''
import json
spec = __SPEC__
parent = op(spec['parent_path']) or op('/')
targets = []
for tp in spec.get('target_ops') or []:
    t = op(tp) or parent.op(tp)
    if t:
        targets.append(t)

if not targets:
    print('<<JSON>>' + json.dumps({"ok": False, "error": f"ninguno de target_ops fue encontrado: {spec.get('target_ops')}"}))
else:
    p_name = spec['name']
    panel = parent.op(p_name)
    if panel and getattr(panel, 'OPType', panel.type) != 'containerCOMP':
        panel.destroy()
        panel = None
    if not panel:
        panel = parent.create(td.containerCOMP, p_name)

    W = int(spec.get('width', 1280))
    H = int(spec.get('height', 720))
    panel.par.w = W
    panel.par.h = H
    if hasattr(panel.par, 'align'):
        panel.par.align = 'lr'
    if hasattr(panel.par, 'bgcolorr'):
        panel.par.bgcolorr, panel.par.bgcolorg, panel.par.bgcolorb = 0.07, 0.08, 0.10
        panel.par.bgalpha = 1.0

    # Descubrir TOP de preview si no fue especificado explícitamente
    preview_op = op(spec['preview_top']) if spec.get('preview_top') else None
    if not preview_op:
        for t in targets:
            if t.family == 'TOP':
                preview_op = t
                break
            elif t.family == 'COMP':
                for cand_name in ('out1', 'null_final', 'out_visual', 'render1', 'bg'):
                    cand = t.op(cand_name)
                    if cand and cand.family == 'TOP':
                        preview_op = cand
                        break
                if not preview_op:
                    tops = [c for c in t.children if c.family == 'TOP']
                    if tops:
                        preview_op = tops[-1]
            if preview_op:
                break

    def ensure_child(comp, cls_name, cname):
        c = comp.op(cname)
        if c and getattr(c, 'OPType', c.type) != cls_name:
            c.destroy()
            c = None
        return c or comp.create(getattr(td, cls_name), cname)

    # Columna izquierda: Cabecera + Viewport en vivo
    vp_pane = ensure_child(panel, 'containerCOMP', 'viewport_pane')
    vp_pane.par.w = max(W - 380, 400)
    vp_pane.par.h = H
    vp_pane.par.hmode = 'fill'
    vp_pane.par.vmode = 'fill'
    vp_pane.par.align = 'tb'
    vp_pane.par.alignorder = 0
    vp_pane.nodeX, vp_pane.nodeY = 0, 0

    hdr = ensure_child(vp_pane, 'containerCOMP', 'header_bar')
    hdr.par.h = 44
    hdr.par.hmode = 'fill'
    hdr.par.alignorder = 0
    hdr.par.bgcolorr, hdr.par.bgcolorg, hdr.par.bgcolorb = 0.10, 0.12, 0.16
    hdr.par.bgalpha = 1.0
    hdr.nodeX, hdr.nodeY = 0, 140

    hdr_txt = ensure_child(hdr, 'textTOP', 'header_txt')
    title_str = spec.get('title') or f"STUDIO CONTROL — {', '.join(t.name for t in targets)}"
    hdr_txt.par.text = title_str
    if hasattr(hdr_txt.par, 'outputresolution'):
        hdr_txt.par.outputresolution = 'custom'
        hdr_txt.par.resolutionw = max(W - 380, 400)
        hdr_txt.par.resolutionh = 44
    if hasattr(hdr_txt.par, 'fontsize'):
        hdr_txt.par.fontsize = 16
    if hasattr(hdr_txt.par, 'alignx'):
        hdr_txt.par.alignx = 'left'
    hdr.par.top = hdr_txt.path

    viewer = ensure_child(vp_pane, 'opviewerCOMP', 'live_viewer')
    viewer.par.hmode = 'fill'
    viewer.par.vmode = 'fill'
    viewer.par.alignorder = 1
    viewer.nodeX, viewer.nodeY = 0, 0
    target_for_viewer = preview_op or targets[0]
    if hasattr(viewer.par, 'opviewer'):
        viewer.par.opviewer = target_for_viewer.path
    if preview_op and hasattr(viewer.par, 'top'):
        viewer.par.top = preview_op.path

    # Columna derecha: Inspector Dock con parameterCOMPs interactivos
    dock = ensure_child(panel, 'containerCOMP', 'inspector_dock')
    dock.par.w = 380
    dock.par.h = H
    dock.par.vmode = 'fill'
    dock.par.align = 'tb'
    dock.par.spacing = 6
    dock.par.alignorder = 1
    dock.par.bgcolorr, dock.par.bgcolorg, dock.par.bgcolorb = 0.11, 0.12, 0.15
    dock.par.bgalpha = 1.0
    dock.nodeX, dock.nodeY = 240, 0

    widgets = []
    inc_builtin = bool(spec.get('include_builtin', False))
    slot_h = max(180, int((H - 16) / max(len(targets), 1)))
    for idx, t in enumerate(targets):
        w_name = f"par_{idx}_{t.name}"
        pw = ensure_child(dock, 'parameterCOMP', w_name)
        pw.par.op = t.path
        has_custom = bool(list(getattr(t, 'customPars', [])))
        pw.par.custom = True
        pw.par.builtin = bool(inc_builtin or not has_custom)
        if hasattr(pw.par, 'header'):
            pw.par.header = True
        pw.par.w = 368
        pw.par.h = slot_h
        pw.par.hmode = 'fill'
        pw.par.alignorder = idx
        pw.nodeX, pw.nodeY = 0, -idx * 150
        widgets.append({
            "widget_path": pw.path,
            "target_op": t.path,
            "shows_custom": True,
            "shows_builtin": bool(pw.par.builtin.eval()),
            "custom_pars_count": len(list(getattr(t, 'customPars', []))),
        })

    win_path = None
    if spec.get('create_window'):
        win = ensure_child(parent, 'windowCOMP', p_name + '_window')
        if hasattr(win.par, 'winop'):
            win.par.winop = panel.path
        win.nodeX, win.nodeY = panel.nodeX + 220, panel.nodeY
        win_path = win.path

    try:
        panel.cook(force=True)
    except Exception:
        pass

    print('<<JSON>>' + json.dumps({
        "ok": True,
        "panel_path": panel.path,
        "resolution": f"{W}x{H}",
        "title": title_str,
        "preview_top": preview_op.path if preview_op else None,
        "viewer_path": viewer.path,
        "inspector_dock_path": dock.path,
        "parameter_widgets": widgets,
        "window_comp_path": win_path,
    }))
'''


def t_build_control_panel(a: dict) -> dict:
    """Pilar 11 — Construye un panel UI de control y monitoreo en vivo (containerCOMP Perform-ready con cabecera, visor opviewerCOMP conectado al TOP de salida y dock de parameterCOMPs vinculados a los Custom Parameters de cada operador objetivo)."""
    raw_targets = a.get("target_ops") or a.get("target_op") or ""
    if isinstance(raw_targets, str):
        target_ops = [x.strip() for x in raw_targets.split(",") if x.strip()]
    elif isinstance(raw_targets, list):
        target_ops = [str(x).strip() for x in raw_targets if str(x).strip()]
    else:
        target_ops = []
    if not target_ops:
        return {"ok": False, "error": "falta 'target_ops' (ruta o rutas separadas por coma de los COMPs/operadores a controlar)"}

    spec = {
        "parent_path": str(a.get("parent_path") or "/project1").strip(),
        "name": str(a.get("name") or "control_panel").strip(),
        "target_ops": target_ops,
        "preview_top": str(a.get("preview_top") or "").strip() or None,
        "title": str(a.get("title") or "").strip() or None,
        "include_builtin": str(a.get("include_builtin") or "").lower() in ("1", "true", "yes", "si", "sí") or a.get("include_builtin") is True,
        "width": int(a.get("width") if a.get("width") is not None else 1280),
        "height": int(a.get("height") if a.get("height") is not None else 720),
        "create_window": str(a.get("create_window") or "").lower() in ("1", "true", "yes", "si", "sí") or a.get("create_window") is True,
    }
    code = _BUILD_CONTROL_PANEL.replace("__SPEC__", repr(spec))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    return res


# ── 26. td_render_contact_sheet — Pilar 12: Visión temporal multi-frame ──────

_STEP_AND_SAVE_TOP = r'''
import json
spec = __SPEC__
t = op(spec['top_path'])
if not t or t.family != 'TOP':
    print('<<JSON>>' + json.dumps({"ok": False, "error": f"TOP no encontrado: {spec['top_path']}"}))
else:
    steps = int(spec.get('step_frames', 0))
    parent = t.parent()
    if steps > 0:
        try:
            op('/').time.frame = op('/').time.frame + steps
        except Exception:
            pass
        if parent:
            for _ in range(min(steps, 15)):
                for c in parent.children:
                    try:
                        c.cook(force=True)
                    except Exception:
                        pass
    try:
        t.cook(force=True)
    except Exception:
        pass
    t.save(spec['save_path'])
    print('<<JSON>>' + json.dumps({
        "ok": True,
        "frame": float(op('/').time.frame),
        "seconds": round(float(op('/').time.seconds), 4),
        "width": int(t.width),
        "height": int(t.height),
    }))
'''


def t_render_contact_sheet(a: dict) -> dict:
    """Pilar 12 — Visión temporal para TouchDesigner: avanza la red/simulación durante N muestras espaciadas por step_frames, captura cada frame del TOP objetivo, compone una hoja de contacto PNG (grilla R x C con barra de progreso temporal) y calcula métricas de movimiento inter-frame (ANIMATING / STATIC / BLANK)."""
    import math
    import tempfile
    import time
    from pathlib import Path
    from PIL import Image, ImageDraw

    top_path = str(a.get("top_path") or "").strip()
    if not top_path:
        return {"ok": False, "error": "falta 'top_path' (ruta del TOP a muestrear en el tiempo)"}

    num_frames = min(max(int(a.get("num_frames") if a.get("num_frames") is not None else 6), 2), 16)
    step_frames = max(int(a.get("step_frames") if a.get("step_frames") is not None else 4), 1)
    cols = min(max(int(a.get("cols") if a.get("cols") is not None else min(num_frames, 3)), 1), 8)
    rows = int(math.ceil(num_frames / float(cols)))
    tile_w = min(max(int(a.get("tile_width") if a.get("tile_width") is not None else 320), 96), 960)
    reset_first = str(a.get("reset_first") or "").lower() in ("1", "true", "yes", "si", "sí") or a.get("reset_first") is True

    if reset_first:
        parent_guess = top_path.rsplit("/", 1)[0] or "/"
        t_control_simulation({"container_path": parent_guess, "action": "reset_only"})

    tmp_files: list[Path] = []
    frames_meta: list[dict] = []
    try:
        for i in range(num_frames):
            if i > 0:
                time.sleep(min(0.12, max(0.02, step_frames / 60.0)))
            tmp_p = Path(tempfile.gettempdir()) / f"tdmcp_cs_{os.getpid()}_{i}.png"
            tmp_files.append(tmp_p)
            spec = {
                "top_path": top_path,
                "step_frames": 0 if i == 0 else step_frames,
                "save_path": str(tmp_p),
            }
            ok, r = exec_code(_STEP_AND_SAVE_TOP.replace("__SPEC__", repr(spec)))
            if not ok or not isinstance(r, dict) or not r.get("ok"):
                return {"ok": False, "error": f"falló captura de muestra {i} en {top_path}: {r}"}
            frames_meta.append({"sample": i, "frame": r.get("frame"), "seconds": r.get("seconds"), "w": r.get("width", 256), "h": r.get("height", 256)})

        src_w = max(int(frames_meta[0].get("w") or 256), 1)
        src_h = max(int(frames_meta[0].get("h") or 256), 1)
        tile_h = max(int(round(tile_w * (src_h / float(src_w)))), 64)
        hdr_h = 14
        pad = 6

        sheet_w = cols * (tile_w + pad) + pad
        sheet_h = rows * (tile_h + hdr_h + pad) + pad
        sheet = Image.new("RGBA", (sheet_w, sheet_h), (16, 18, 24, 255))
        draw = ImageDraw.Draw(sheet)

        loaded_rgb_small = []
        mean_lumas = []

        for idx, tf in enumerate(tmp_files):
            im = Image.open(tf).convert("RGBA")
            # Versión reducida para estadística rápida inter-frame
            im_stat = im.resize((96, 96), Image.Resampling.BILINEAR)
            px = list(im_stat.getdata())
            loaded_rgb_small.append(px)
            luma = sum((0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]) for p in px) / max(len(px), 1)
            mean_lumas.append(round(luma, 3))

            tile_im = im.resize((tile_w, tile_h), Image.Resampling.BILINEAR)
            r_idx = idx // cols
            c_idx = idx % cols
            x0 = pad + c_idx * (tile_w + pad)
            y0 = pad + r_idx * (tile_h + hdr_h + pad)

            # Barra superior de progreso temporal de la celda
            draw.rectangle([x0, y0, x0 + tile_w - 1, y0 + hdr_h - 1], fill=(28, 32, 42, 255))
            prog_w = int(round(((idx + 1) / float(num_frames)) * (tile_w - 4)))
            draw.rectangle([x0 + 2, y0 + 3, x0 + 2 + max(prog_w, 4), y0 + hdr_h - 4], fill=(0, 215, 255, 255))

            sheet.paste(tile_im, (x0, y0 + hdr_h))
            draw.rectangle([x0, y0, x0 + tile_w - 1, y0 + hdr_h + tile_h - 1], outline=(58, 66, 84, 255), width=1)

        per_step_mad = []
        for i in range(1, len(loaded_rgb_small)):
            pa, pb = loaded_rgb_small[i - 1], loaded_rgb_small[i]
            diff = sum((abs(a0[0] - b0[0]) + abs(a0[1] - b0[1]) + abs(a0[2] - b0[2])) / 3.0 for a0, b0 in zip(pa, pb)) / max(len(pa), 1)
            per_step_mad.append(round(diff, 3))

        mean_motion = sum(per_step_mad) / max(len(per_step_mad), 1)
        max_motion = max(per_step_mad) if per_step_mad else 0.0

        if max(mean_lumas or [0.0]) < 1.0:
            verdict = "BLANK"
        elif mean_motion < 0.2 and max_motion < 0.4:
            verdict = "STATIC"
        else:
            verdict = "ANIMATING"

        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", top_path.strip("/")) or "top"
        out_path = str(a.get("out_path") or "").strip() or str(Path(tempfile.gettempdir()) / f"td_contact_sheet_{slug}.png")
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        sheet.save(out_path, format="PNG")

        return {
            "ok": True,
            "top_path": top_path,
            "contact_sheet_path": out_path,
            "grid": f"{rows}x{cols}",
            "sheet_resolution": f"{sheet_w}x{sheet_h}",
            "tile_resolution": f"{tile_w}x{tile_h}",
            "num_frames": num_frames,
            "step_frames": step_frames,
            "temporal_verdict": verdict,
            "motion_metrics": {
                "mean_temporal_motion": round(mean_motion, 3),
                "max_step_mad": round(max_motion, 3),
                "per_step_mad": per_step_mad,
                "frame_mean_luma": mean_lumas,
            },
            "samples": frames_meta,
        }
    except Exception as e:
        return {"ok": False, "error": f"error en td_render_contact_sheet: {e}"}
    finally:
        for tf in tmp_files:
            try:
                if tf.exists():
                    tf.unlink()
            except Exception:
                pass


# ── 27. td_setup_audio_analyzer — Pilar 13: Analizador de audio multi-banda ──

_SETUP_AUDIO_ANALYZER = r'''
import json
spec = __SPEC__
parent = op(spec['parent_path']) or op('/')
c_name = spec['name']
comp = parent.op(c_name)
if comp and getattr(comp, 'OPType', comp.type) != 'baseCOMP':
    comp.destroy()
    comp = None
if not comp:
    comp = parent.create(td.baseCOMP, c_name)

def ensure_op(cls_name, n_name):
    c = comp.op(n_name)
    if c and getattr(c, 'OPType', c.type) != cls_name:
        c.destroy()
        c = None
    return c or comp.create(getattr(td, cls_name), n_name)

stype = spec.get('source_type', 'test_oscillator').lower()
if stype == 'file':
    src = ensure_op('audiofileinCHOP', 'audio_src')
    if spec.get('source_path'):
        src.par.file = spec['source_path']
elif stype == 'device':
    src = ensure_op('audiodeviceinCHOP', 'audio_src')
elif stype == 'op':
    src = ensure_op('selectCHOP', 'audio_src')
    if spec.get('source_path'):
        src.par.chop = spec['source_path']
else:
    # test_oscillator: sintetizador multi-banda autónomo (80Hz bass con pulso kick, 950Hz mid, 5200Hz high)
    osc_b = ensure_op('audiooscillatorCHOP', 'osc_bass')
    osc_b.par.frequency = 80.0
    osc_b.par.amp = 0.75
    osc_b.nodeX, osc_b.nodeY = -420, 180

    lfo_k = ensure_op('lfoCHOP', 'lfo_kick_env')
    lfo_k.par.frequency = 2.0
    lfo_k.par.offset = 0.55
    lfo_k.par.amp = 0.45
    lfo_k.nodeX, lfo_k.nodeY = -420, 60

    mod_b = ensure_op('mathCHOP', 'mod_bass')
    mod_b.par.chopop = 'mul'
    mod_b.inputConnectors[0].connect(osc_b)
    mod_b.inputConnectors[1].connect(lfo_k)
    mod_b.nodeX, mod_b.nodeY = -240, 140

    osc_m = ensure_op('audiooscillatorCHOP', 'osc_mid')
    osc_m.par.frequency = 950.0
    osc_m.par.amp = 0.45
    osc_m.nodeX, osc_m.nodeY = -240, 0

    osc_h = ensure_op('audiooscillatorCHOP', 'osc_high')
    osc_h.par.frequency = 5200.0
    osc_h.par.amp = 0.30
    osc_h.nodeX, osc_h.nodeY = -240, -140

    src = ensure_op('mathCHOP', 'audio_src')
    src.par.chopop = 'add'
    src.inputConnectors[0].connect(mod_b)
    src.inputConnectors[1].connect(osc_m)
    src.inputConnectors[2].connect(osc_h)
src.nodeX, src.nodeY = 0, 0

pre = ensure_op('mathCHOP', 'pre_gain')
pre.inputConnectors[0].connect(src)
pre.par.gain = float(spec.get('gain', 1.0))
pre.nodeX, pre.nodeY = 180, 0

bands_cfg = [
    ('bass', 'lowpass', 180.0, 2.2, 220),
    ('mid', 'bandpass', 1000.0, 2.6, 80),
    ('high', 'highpass', 4000.0, 3.2, -60),
]
lag_att = float(spec.get('lag_attack', 0.04))
lag_rel = float(spec.get('lag_release', 0.18))
band_tails = []

for bname, fmode, cutoff, mult_gain, y_pos in bands_cfg:
    flt = ensure_op('audiofilterCHOP', f'filt_{bname}')
    flt.inputConnectors[0].connect(pre)
    flt.par.units = 'frequency'
    flt.par.filter = fmode
    flt.par.cutofffrequency = cutoff
    flt.nodeX, flt.nodeY = 380, y_pos

    an = ensure_op('analyzeCHOP', f'rms_{bname}')
    an.inputConnectors[0].connect(flt)
    an.par.function = 'rmspower'
    an.nodeX, an.nodeY = 560, y_pos

    mth = ensure_op('mathCHOP', f'norm_{bname}')
    mth.inputConnectors[0].connect(an)
    mth.par.gain = mult_gain
    mth.nodeX, mth.nodeY = 740, y_pos

    lg = ensure_op('lagCHOP', f'env_{bname}')
    lg.inputConnectors[0].connect(mth)
    lg.par.lag1 = lag_att
    lg.par.lag2 = lag_rel
    lg.par.renamefrom = '*'
    lg.par.renameto = bname
    lg.nodeX, lg.nodeY = 920, y_pos
    band_tails.append(lg)

# Canal RMS general (espectro completo)
an_full = ensure_op('analyzeCHOP', 'rms_full')
an_full.inputConnectors[0].connect(pre)
an_full.par.function = 'rmspower'
an_full.nodeX, an_full.nodeY = 560, -200

mth_full = ensure_op('mathCHOP', 'norm_rms')
mth_full.inputConnectors[0].connect(an_full)
mth_full.par.gain = 1.8
mth_full.nodeX, mth_full.nodeY = 740, -200

lg_full = ensure_op('lagCHOP', 'env_rms')
lg_full.inputConnectors[0].connect(mth_full)
lg_full.par.lag1 = lag_att
lg_full.par.lag2 = lag_rel
lg_full.par.renamefrom = '*'
lg_full.par.renameto = 'rms'
lg_full.nodeX, lg_full.nodeY = 920, -200
band_tails.append(lg_full)

# Canal Kick (ataque ultrarrápido derivado de rms_bass)
mth_kick = ensure_op('mathCHOP', 'norm_kick')
mth_kick.inputConnectors[0].connect(comp.op('rms_bass'))
mth_kick.par.gain = 3.0
mth_kick.nodeX, mth_kick.nodeY = 740, 340

lg_kick = ensure_op('lagCHOP', 'env_kick')
lg_kick.inputConnectors[0].connect(mth_kick)
lg_kick.par.lag1 = 0.01
lg_kick.par.lag2 = 0.10
lg_kick.par.renamefrom = '*'
lg_kick.par.renameto = 'kick'
lg_kick.nodeX, lg_kick.nodeY = 920, 340
band_tails.append(lg_kick)

mrg = ensure_op('mergeCHOP', 'merge_bands')
for c_conn in mrg.inputConnectors:
    c_conn.disconnect()
for idx, bt in enumerate(band_tails):
    mrg.inputConnectors[idx].connect(bt)
mrg.nodeX, mrg.nodeY = 1120, 60

out_null = ensure_op('nullCHOP', 'out_audio')
out_null.inputConnectors[0].connect(mrg)
out_null.nodeX, out_null.nodeY = 1300, 60

out_port = ensure_op('outCHOP', 'out1')
out_port.inputConnectors[0].connect(out_null)
out_port.nodeX, out_port.nodeY = 1480, 60

for c in comp.children:
    try:
        c.cook(force=True)
    except Exception:
        pass

live_channels = {}
for ch in out_null.chans():
    try:
        live_channels[ch.name] = round(float(ch.eval()), 5)
    except Exception:
        pass

wired_bindings = []
warnings = []
for b in (spec.get('bindings') or []):
    band = str(b.get('band') or 'bass').strip()
    t_path = str(b.get('target_op') or '').strip()
    t_par = str(b.get('target_par') or '').strip()
    scale = float(b.get('scale', 1.0))
    offset = float(b.get('offset', 0.0))
    t_node = op(t_path) or parent.op(t_path)
    if not t_node or not hasattr(t_node.par, t_par):
        warnings.append(f"binding destino inválido: {t_path}.{t_par}")
        continue
    expr_str = f"op('{out_null.path}')['{band}'] * {scale} + {offset}"
    getattr(t_node.par, t_par).expr = expr_str
    wired_bindings.append({"band": band, "target": f"{t_node.path}.par.{t_par}", "expression": expr_str})

print('<<JSON>>' + json.dumps({
    "ok": True,
    "analyzer_comp": comp.path,
    "output_null_chop": out_null.path,
    "out_chop": out_port.path,
    "source_type": stype,
    "live_channels": live_channels,
    "wired_bindings": wired_bindings,
    "warnings": warnings,
}))
'''


def t_setup_audio_analyzer(a: dict) -> dict:
    """Pilar 13 — Construye un módulo analizador de audio multi-banda llave en mano (baseCOMP con fuente audiofilein/audiodevicein/select/test_oscillator -> filtros lowpass/bandpass/highpass -> envolvente RMS -> normalización y lag -> nullCHOP con canales bass, mid, high, rms y kick) y opcionalmente los vincula a parámetros de la escena."""
    raw_b = a.get("bindings")
    b_list = []
    if isinstance(raw_b, list):
        b_list = raw_b
    elif isinstance(raw_b, str) and raw_b.strip():
        try:
            b_list = json.loads(raw_b)
        except Exception as e:
            return {"ok": False, "error": f"bindings debe ser JSON válido (lista de objetos): {e}"}

    spec = {
        "parent_path": str(a.get("parent_path") or "/project1").strip(),
        "name": str(a.get("name") or "audio_analyzer").strip(),
        "source_type": str(a.get("source_type") or "test_oscillator").strip().lower(),
        "source_path": str(a.get("source_path") or "").strip() or None,
        "gain": float(a.get("gain") if a.get("gain") is not None else 1.0),
        "lag_attack": float(a.get("lag_attack") if a.get("lag_attack") is not None else 0.04),
        "lag_release": float(a.get("lag_release") if a.get("lag_release") is not None else 0.18),
        "bindings": b_list,
    }
    code = _SETUP_AUDIO_ANALYZER.replace("__SPEC__", repr(spec))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    return res


# ── 28. td_setup_scene_switcher — Pilar 14: Switcher de escenas + Smart Cook ─

_SETUP_SCENE_SWITCHER = r'''
import json
spec = __SPEC__
parent = op(spec['parent_path']) or op('/')
raw_scenes = spec.get('scene_paths') or []
resolved_scenes = []
for sp in raw_scenes:
    s_op = op(sp) or parent.op(sp)
    if not s_op:
        continue
    if s_op.family == 'TOP':
        top_op = s_op
        comp_op = s_op.parent() if s_op.parent() != op('/') and s_op.parent() != parent else None
    elif s_op.family == 'COMP':
        comp_op = s_op
        top_op = None
        for cname in ('out1', 'null_final', 'out_visual', 'render1', 'bg'):
            cand = s_op.op(cname)
            if cand and cand.family == 'TOP':
                top_op = cand
                break
        if not top_op:
            tops = [c for c in s_op.children if c.family == 'TOP']
            if tops:
                top_op = tops[-1]
    else:
        continue
    if top_op:
        resolved_scenes.append({"input_path": s_op.path, "comp_path": comp_op.path if comp_op else None, "top_path": top_op.path})

if len(resolved_scenes) < 2:
    print('<<JSON>>' + json.dumps({"ok": False, "error": f"se requieren al menos 2 escenas con TOP de salida válido; resueltas={len(resolved_scenes)}"}))
else:
    sw_name = spec['name']
    comp = parent.op(sw_name)
    if comp and getattr(comp, 'OPType', comp.type) != 'baseCOMP':
        comp.destroy()
        comp = None
    if not comp:
        comp = parent.create(td.baseCOMP, sw_name)

    # Custom Parameters en el switcher
    page = None
    for pg in comp.customPages:
        if pg.name == 'Switcher':
            page = pg
            break
    if not page:
        page = comp.appendCustomPage('Switcher')

    def ensure_cpar(method, pname, label):
        existing = getattr(comp.par, pname, None)
        if existing is not None and existing.isCustom:
            return existing
        return getattr(page, method)(pname, label=label)[0]

    n_scenes = len(resolved_scenes)
    act_idx = min(max(int(spec.get('active_scene', 0)), 0), n_scenes - 1)
    p_scene = ensure_cpar('appendInt', 'Scene', 'Active Scene')
    p_scene.min, p_scene.max = 0, n_scenes - 1
    p_scene.clampMin, p_scene.clampMax = True, True
    p_scene.normMin, p_scene.normMax = 0, n_scenes - 1
    p_scene.val = act_idx

    p_trans = ensure_cpar('appendFloat', 'Transitiontime', 'Transition Time (s)')
    p_trans.min, p_trans.max = 0.0, 10.0
    p_trans.clampMin = True
    p_trans.normMin, p_trans.normMax = 0.0, 4.0
    p_trans.val = float(spec.get('transition_seconds', 1.0))

    p_smart = ensure_cpar('appendToggle', 'Smartcooking', 'Smart Cooking Gate')
    p_smart.val = bool(spec.get('smart_cooking', True))

    def ensure_child(cls_name, cname):
        c = comp.op(cname)
        if c and getattr(c, 'OPType', c.type) != cls_name:
            c.destroy()
            c = None
        return c or comp.create(getattr(td, cls_name), cname)

    sw_top = ensure_child('switchTOP', 'sw_visual')
    sw_top.par.blend = True
    for conn in sw_top.inputConnectors:
        conn.disconnect()

    for idx, sc in enumerate(resolved_scenes):
        sel = ensure_child('selectTOP', f'in_scene_{idx}')
        sel.par.top = sc['top_path']
        sel.nodeX, sel.nodeY = 0, -idx * 130
        sw_top.inputConnectors[idx].connect(sel)

    sw_top.nodeX, sw_top.nodeY = 240, -60

    idx_c = ensure_child('constantCHOP', 'idx_target')
    idx_c.par.name0 = 'scene_idx'
    idx_c.par.value0.expr = "parent().par.Scene"
    idx_c.nodeX, idx_c.nodeY = 0, 160

    idx_f = ensure_child('filterCHOP', 'idx_smooth')
    idx_f.inputConnectors[0].connect(idx_c)
    idx_f.par.width.expr = "parent().par.Transitiontime"
    idx_f.nodeX, idx_f.nodeY = 200, 160

    sw_top.par.index.expr = "op('idx_smooth')['scene_idx']"

    out_null = ensure_child('nullTOP', 'out_visual')
    out_null.inputConnectors[0].connect(sw_top)
    out_null.nodeX, out_null.nodeY = 440, -60

    out_port = ensure_child('outTOP', 'out1')
    out_port.inputConnectors[0].connect(out_null)
    out_port.nodeX, out_port.nodeY = 620, -60

    # Tabla de escenas para Smart Cooking
    sc_tbl = ensure_child('tableDAT', 'scenes_table')
    sc_tbl.clear()
    sc_tbl.appendRow(['index', 'comp_path', 'top_path'])
    for idx, sc in enumerate(resolved_scenes):
        sc_tbl.appendRow([str(idx), sc['comp_path'] or '', sc['top_path']])
    sc_tbl.nodeX, sc_tbl.nodeY = 0, 300

    # chopexecuteDAT que apaga allowCooking en escenas fuera del crossfade actual
    ce = ensure_child('chopexecuteDAT', 'smart_cook_exec')
    ce.par.active = True
    ce.par.chop = 'idx_smooth'
    ce.par.valuechange = True
    ce.nodeX, ce.nodeY = 400, 160
    ce.text = (
        "def onValueChange(channel, sampleIndex, val, prev):\n"
        "    if not parent().par.Smartcooking.eval():\n"
        "        return\n"
        "    tbl = op('scenes_table')\n"
        "    for r in range(1, tbl.numRows):\n"
        "        idx = int(tbl[r, 'index'].val)\n"
        "        cpath = tbl[r, 'comp_path'].val\n"
        "        if cpath:\n"
        "            c = op(cpath)\n"
        "            if c:\n"
        "                c.allowCooking = (abs(val - idx) < 0.999)\n"
        "    return\n"
    )

    # Aplicar estado inicial de Smart Cooking para active_scene
    if bool(spec.get('smart_cooking', True)):
        for idx, sc in enumerate(resolved_scenes):
            if sc['comp_path']:
                c_node = op(sc['comp_path'])
                if c_node:
                    c_node.allowCooking = (idx == act_idx)

    for c in comp.children:
        try:
            c.cook(force=True)
        except Exception:
            pass

    for idx, sc in enumerate(resolved_scenes):
        c_node = op(sc['comp_path']) if sc['comp_path'] else None
        sc['index'] = idx
        sc['allow_cooking'] = bool(c_node.allowCooking) if c_node else True

    print('<<JSON>>' + json.dumps({
        "ok": True,
        "switcher_comp": comp.path,
        "output_top": out_null.path,
        "out_top": out_port.path,
        "active_scene": act_idx,
        "transition_seconds": float(p_trans.eval()),
        "smart_cooking": bool(p_smart.eval()),
        "scenes": resolved_scenes,
    }))
'''


def t_setup_scene_switcher(a: dict) -> dict:
    """Pilar 14 — Construye un switcher maestro de escenas con crossfade suave (switchTOP blend=True + filterCHOP) y Smart Cooking automático (chopexecuteDAT que desactiva allowCooking en los contenedores de escenas inactivas fuera de la transición)."""
    raw_scenes = a.get("scene_paths") or ""
    if isinstance(raw_scenes, str):
        scene_paths = [x.strip() for x in raw_scenes.split(",") if x.strip()]
    elif isinstance(raw_scenes, list):
        scene_paths = [str(x).strip() for x in raw_scenes if str(x).strip()]
    else:
        scene_paths = []
    if len(scene_paths) < 2:
        return {"ok": False, "error": "hacen falta al menos 2 rutas en 'scene_paths' (separadas por coma o lista)"}

    spec = {
        "parent_path": str(a.get("parent_path") or "/project1").strip(),
        "name": str(a.get("name") or "scene_switcher").strip(),
        "scene_paths": scene_paths,
        "active_scene": int(a.get("active_scene") if a.get("active_scene") is not None else 0),
        "transition_seconds": float(a.get("transition_seconds") if a.get("transition_seconds") is not None else 1.0),
        "smart_cooking": False if str(a.get("smart_cooking") or "").lower() in ("0", "false", "no") else True,
    }
    code = _SETUP_SCENE_SWITCHER.replace("__SPEC__", repr(spec))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    return res


# ── 29. td_preset_manager — Pilar 15: Gestor e interpolador de Presets ──────

_PRESET_MANAGER = r'''
import json
spec = __SPEC__
comp = op(spec['comp_path'])
if not comp or comp.family != 'COMP':
    print('<<JSON>>' + json.dumps({"ok": False, "error": f"COMP no encontrado: {spec['comp_path']}"}))
else:
    pdat = comp.op('_mcp_presets')
    if not pdat or getattr(pdat, 'OPType', pdat.type) != 'textDAT':
        if pdat:
            pdat.destroy()
        pdat = comp.create(td.textDAT, '_mcp_presets')
        pdat.nodeX, pdat.nodeY = -320, 260

    store = {"presets": {}}
    if (pdat.text or '').strip():
        try:
            store = json.loads(pdat.text)
            if "presets" not in store or not isinstance(store["presets"], dict):
                store = {"presets": {}}
        except Exception:
            store = {"presets": {}}

    if spec.get('imported_presets'):
        store["presets"].update(spec['imported_presets'])

    action = spec.get('action', 'list').lower()
    pname = spec.get('preset_name')
    inc_children = bool(spec.get('include_children', True))
    changes = []

    def is_orable_par(p):
        st = str(getattr(p, 'style', ''))
        if st in ('Pulse', 'Header', 'Momentary'):
            return False
        if p.readOnly or str(p.mode).endswith(('EXPRESSION', 'BIND', 'EXPORT')):
            return False
        return True

    if action == 'capture':
        if not pname:
            print('<<JSON>>' + json.dumps({"ok": False, "error": "falta 'preset_name' para action='capture'"}))
        else:
            cp_dict = {}
            for p in getattr(comp, 'customPars', []):
                if is_orable_par(p):
                    v = p.eval()
                    if isinstance(v, (int, float, bool, str)):
                        cp_dict[p.name] = v
            ch_dict = {}
            if inc_children:
                for c in comp.children:
                    if c.name.startswith(('.', '_mcp_')):
                        continue
                    for p in c.pars():
                        try:
                            if p.isDefault or not is_orable_par(p):
                                continue
                            v = p.eval()
                            if isinstance(v, (int, float, bool, str)):
                                ch_dict[f"{c.name}.{p.name}"] = v
                        except Exception:
                            pass
            store["presets"][pname] = {"custom_pars": cp_dict, "child_pars": ch_dict}
            pdat.text = json.dumps(store, indent=2)
            print('<<JSON>>' + json.dumps({
                "ok": True,
                "comp_path": comp.path,
                "action": "capture",
                "preset_name": pname,
                "custom_pars_saved": len(cp_dict),
                "child_pars_saved": len(ch_dict),
                "presets_available": list(store["presets"].keys()),
                "store": store,
            }))

    elif action == 'apply':
        if not pname or pname not in store["presets"]:
            print('<<JSON>>' + json.dumps({"ok": False, "error": f"preset '{pname}' no existe en {comp.path}; disponibles={list(store['presets'].keys())}"}))
        else:
            pr = store["presets"][pname]
            for k, v in (pr.get("custom_pars") or {}).items():
                if hasattr(comp.par, k):
                    try:
                        getattr(comp.par, k).val = v
                        changes.append({"target": f"par.{k}", "value": v})
                    except Exception:
                        pass
            for k, v in (pr.get("child_pars") or {}).items():
                if '.' in k:
                    cname, parname = k.split('.', 1)
                    cnode = comp.op(cname)
                    if cnode and hasattr(cnode.par, parname):
                        try:
                            getattr(cnode.par, parname).val = v
                            changes.append({"target": k, "value": v})
                        except Exception:
                            pass
            print('<<JSON>>' + json.dumps({
                "ok": True,
                "comp_path": comp.path,
                "action": "apply",
                "preset_name": pname,
                "parameters_affected": len(changes),
                "sample_changes": changes[:25],
                "presets_available": list(store["presets"].keys()),
            }))

    elif action == 'blend':
        pa_name = spec.get('preset_a')
        pb_name = spec.get('preset_b')
        alpha = min(max(float(spec.get('alpha', 0.5)), 0.0), 1.0)
        if pa_name not in store["presets"] or pb_name not in store["presets"]:
            print('<<JSON>>' + json.dumps({"ok": False, "error": f"preset_a='{pa_name}' o preset_b='{pb_name}' no existen; disponibles={list(store['presets'].keys())}"}))
        else:
            pra = store["presets"][pa_name]
            prb = store["presets"][pb_name]

            def blend_val(va, vb, p_obj):
                if isinstance(va, bool) or isinstance(vb, bool):
                    return va if alpha < 0.5 else vb
                if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                    v = (1.0 - alpha) * float(va) + alpha * float(vb)
                    if str(getattr(p_obj, 'style', '')) == 'Int':
                        return int(round(v))
                    return round(v, 6)
                return va if alpha < 0.5 else vb

            all_cp = set(pra.get("custom_pars", {}).keys()) | set(prb.get("custom_pars", {}).keys())
            for k in all_cp:
                if hasattr(comp.par, k):
                    p_obj = getattr(comp.par, k)
                    va = pra.get("custom_pars", {}).get(k, p_obj.eval())
                    vb = prb.get("custom_pars", {}).get(k, p_obj.eval())
                    bv = blend_val(va, vb, p_obj)
                    try:
                        p_obj.val = bv
                        changes.append({"target": f"par.{k}", "from": va, "to": vb, "blended": bv})
                    except Exception:
                        pass

            all_ch = set(pra.get("child_pars", {}).keys()) | set(prb.get("child_pars", {}).keys())
            for k in all_ch:
                if '.' in k:
                    cname, parname = k.split('.', 1)
                    cnode = comp.op(cname)
                    if cnode and hasattr(cnode.par, parname):
                        p_obj = getattr(cnode.par, parname)
                        va = pra.get("child_pars", {}).get(k, p_obj.eval())
                        vb = prb.get("child_pars", {}).get(k, p_obj.eval())
                        bv = blend_val(va, vb, p_obj)
                        try:
                            p_obj.val = bv
                            changes.append({"target": k, "from": va, "to": vb, "blended": bv})
                        except Exception:
                            pass

            print('<<JSON>>' + json.dumps({
                "ok": True,
                "comp_path": comp.path,
                "action": "blend",
                "preset_a": pa_name,
                "preset_b": pb_name,
                "alpha": alpha,
                "parameters_affected": len(changes),
                "sample_changes": changes[:25],
                "presets_available": list(store["presets"].keys()),
            }))

    elif action == 'delete':
        if pname in store["presets"]:
            del store["presets"][pname]
            pdat.text = json.dumps(store, indent=2)
        print('<<JSON>>' + json.dumps({
            "ok": True,
            "comp_path": comp.path,
            "action": "delete",
            "deleted": pname,
            "presets_available": list(store["presets"].keys()),
        }))

    else:
        summary = {
            k: {"custom_pars": len(v.get("custom_pars", {})), "child_pars": len(v.get("child_pars", {}))}
            for k, v in store["presets"].items()
        }
        print('<<JSON>>' + json.dumps({
            "ok": True,
            "comp_path": comp.path,
            "action": "list",
            "presets_available": list(store["presets"].keys()),
            "presets_summary": summary,
        }))
'''


def t_preset_manager(a: dict) -> dict:
    """Pilar 15 — Gestor de estados/presets e interpolador (morphing) para cualquier COMP: captura (capture), lista (list), aplica (apply), borra (delete) o interpola linealmente (blend con alpha 0.0..1.0) entre dos presets de Custom Parameters y parámetros de hijos."""
    comp_path = str(a.get("comp_path") or "").strip()
    if not comp_path:
        return {"ok": False, "error": "falta 'comp_path' (ruta del COMP cuyos presets se gestionan)"}
    action = str(a.get("action") or "list").strip().lower()
    file_path = str(a.get("file_path") or "").strip() or None

    imported_presets = None
    if file_path and action in ("apply", "blend", "list") and os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
                imported_presets = doc.get("presets", doc) if isinstance(doc, dict) else None
        except Exception as e:
            return {"ok": False, "error": f"no se pudo leer file_path '{file_path}': {e}"}

    spec = {
        "comp_path": comp_path,
        "action": action,
        "preset_name": str(a.get("preset_name") or "").strip() or None,
        "preset_a": str(a.get("preset_a") or "").strip() or None,
        "preset_b": str(a.get("preset_b") or "").strip() or None,
        "alpha": float(a.get("alpha") if a.get("alpha") is not None else 0.5),
        "include_children": False if str(a.get("include_children") or "").lower() in ("0", "false", "no") else True,
        "imported_presets": imported_presets,
    }
    code = _PRESET_MANAGER.replace("__SPEC__", repr(spec))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    if ok and isinstance(res, dict) and action == "capture" and file_path and "store" in res:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as fh:
                json.dump(res["store"], fh, ensure_ascii=False, indent=2)
            res["saved_file"] = file_path
        except Exception as e:
            res["file_warning"] = str(e)
    if isinstance(res, dict) and "store" in res:
        del res["store"]
    return res


# ── 30. td_setup_gpu_instancing — Pilar 16: Hardware Instancing en GPU ───────

_SETUP_GPU_INSTANCING = r'''
import json
spec = __SPEC__
parent = op(spec['parent_path']) or op('/')
src = op(spec['instance_source']) or parent.op(spec['instance_source'])
if not src:
    print('<<JSON>>' + json.dumps({"ok": False, "error": f"instance_source no encontrado: {spec['instance_source']}"}))
else:
    g_name = spec['name']
    geo = parent.op(g_name)
    if geo and getattr(geo, 'OPType', geo.type) != 'geometryCOMP':
        geo.destroy()
        geo = None
    if not geo:
        geo = parent.create(td.geometryCOMP, g_name)

    # Eliminar torus1 por defecto
    t_def = geo.op('torus1')
    if t_def:
        try: t_def.destroy()
        except: pass

    # Crear geometría base por instancia dentro de geometryCOMP
    base_geom = spec.get('base_geometry', 'box').lower()
    base_op = None
    for cand in ('inst_base', 'base_geo'):
        c = geo.op(cand)
        if c: base_op = c; break

    if not base_op:
        if base_geom == 'sphere':
            base_op = geo.create(td.spherePOP, 'inst_base')
        elif base_geom == 'grid':
            base_op = geo.create(td.gridPOP, 'inst_base')
        elif base_geom == 'torus':
            base_op = geo.create(td.torusPOP, 'inst_base')
        else:
            base_op = geo.create(td.boxPOP, 'inst_base')

    if hasattr(base_op, 'display'): base_op.display = True
    if hasattr(base_op, 'render'): base_op.render = True

    # Configurar instancing en GPU
    geo.par.instancing = 1
    geo.par.instanceop = src.path

    mapped_attrs = {}
    fam = src.family
    try: src.cook(force=True)
    except: pass

    if fam == 'POP':
        # Coordenadas de posición
        geo.par.instancetx = 'P(0)'
        geo.par.instancety = 'P(1)'
        geo.par.instancetz = 'P(2)'
        mapped_attrs['translate'] = ['P(0)', 'P(1)', 'P(2)']

        # Color
        has_color = False
        try:
            has_color = any(a.name.lower() in ('color', 'cd', 'c') for a in getattr(src, 'attributes', []))
        except:
            has_color = hasattr(src, 'hasAttribute') and src.hasAttribute('Color')
        if has_color and spec.get('color_mode', 'auto') != 'none':
            geo.par.instancer = 'Color(0)'
            geo.par.instanceg = 'Color(1)'
            geo.par.instanceb = 'Color(2)'
            geo.par.instancea = 'Color(3)'
            mapped_attrs['color'] = ['Color(0)', 'Color(1)', 'Color(2)', 'Color(3)']

        # Escala
        has_scale = False
        try:
            has_scale = any(a.name.lower() == 'scale' for a in getattr(src, 'attributes', []))
        except:
            has_scale = hasattr(src, 'hasAttribute') and src.hasAttribute('Scale')
        if has_scale and spec.get('scale_mode', 'auto') != 'none':
            geo.par.instancesx = 'Scale(0)'
            geo.par.instancesy = 'Scale(1)'
            geo.par.instancesz = 'Scale(2)'
            mapped_attrs['scale'] = ['Scale(0)', 'Scale(1)', 'Scale(2)']

        # Orientación / Rotación hacia vector
        has_n = False
        try:
            has_n = any(a.name.lower() in ('n', 'normal') for a in getattr(src, 'attributes', []))
        except:
            has_n = hasattr(src, 'hasAttribute') and src.hasAttribute('N')
        if has_n and spec.get('orient_mode', 'auto') != 'none':
            geo.par.instancerottoforward = 'z'
            geo.par.instancerottox = 'N(0)'
            geo.par.instancerottoy = 'N(1)'
            geo.par.instancerottoz = 'N(2)'
            mapped_attrs['rotate_to'] = ['N(0)', 'N(1)', 'N(2)']

    elif fam == 'CHOP':
        cnames = [c.name for c in src.chans()]
        tx = next((c for c in cnames if c in ('tx', 'x', 'P[0]', 'P(0)')), cnames[0] if cnames else '')
        ty = next((c for c in cnames if c in ('ty', 'y', 'P[1]', 'P(1)')), cnames[1] if len(cnames) > 1 else '')
        tz = next((c for c in cnames if c in ('tz', 'z', 'P[2]', 'P(2)')), cnames[2] if len(cnames) > 2 else '')
        if tx: geo.par.instancetx = tx
        if ty: geo.par.instancety = ty
        if tz: geo.par.instancetz = tz
        mapped_attrs['translate'] = [tx, ty, tz]

        # Color si existen r, g, b
        if all(k in cnames for k in ('r', 'g', 'b')):
            geo.par.instancer = 'r'
            geo.par.instanceg = 'g'
            geo.par.instanceb = 'b'
            if 'a' in cnames: geo.par.instancea = 'a'
            mapped_attrs['color'] = ['r', 'g', 'b']

        # Escala si existen sx, sy, sz o scale
        if 'scale' in cnames:
            geo.par.instancesx = 'scale'
            geo.par.instancesy = 'scale'
            geo.par.instancesz = 'scale'
            mapped_attrs['scale'] = ['scale']
        elif all(k in cnames for k in ('sx', 'sy', 'sz')):
            geo.par.instancesx = 'sx'
            geo.par.instancesy = 'sy'
            geo.par.instancesz = 'sz'
            mapped_attrs['scale'] = ['sx', 'sy', 'sz']

    # Render pipeline opcional
    ren_info = None
    if spec.get('create_render_pipeline', True):
        cam = parent.op('cam_inst') or parent.create(td.cameraCOMP, 'cam_inst')
        cam.par.tz = 5.0
        cam.nodeX, cam.nodeY = geo.nodeX, geo.nodeY + 160

        mat = parent.op('mat_inst') or parent.create(td.constantMAT, 'mat_inst')
        mat.nodeX, mat.nodeY = geo.nodeX - 160, geo.nodeY
        geo.par.material = mat.path

        ren = parent.op('ren_inst') or parent.create(td.renderTOP, 'ren_inst')
        ren.par.camera = cam.path
        ren.par.geometry = geo.path
        ren.nodeX, ren.nodeY = geo.nodeX + 180, geo.nodeY

        out_top = parent.op('out_inst') or parent.create(td.nullTOP, 'out_inst')
        out_top.inputConnectors[0].connect(ren)
        out_top.nodeX, out_top.nodeY = ren.nodeX + 160, ren.nodeY
        ren_info = {"render_top": ren.path, "output_top": out_top.path, "camera": cam.path, "material": mat.path}

    try: geo.cook(force=True)
    except: pass

    print('<<JSON>>' + json.dumps({
        "ok": True,
        "geometry_comp": geo.path,
        "instance_source": src.path,
        "source_family": fam,
        "base_geometry": base_op.path if base_op else None,
        "instancing_enabled": bool(geo.par.instancing.eval()),
        "mapped_attributes": mapped_attrs,
        "render_pipeline": ren_info,
    }))
'''


def t_setup_gpu_instancing(a: dict) -> dict:
    """Pilar 16 — Pipeline de Hardware Instancing en GPU: toma un operador fuente (POP/CHOP/TOP/SOP), auto-mapea atributos (P, Color, Scale, N) en las páginas de instancing del geometryCOMP y monta opcionalmente cámara, material y renderTOP."""
    src = str(a.get("instance_source") or "").strip()
    if not src:
        return {"ok": False, "error": "falta 'instance_source' (ruta del operador con puntos/datos de instancia)"}
    spec = {
        "parent_path": str(a.get("parent_path") or "/project1").strip(),
        "name": str(a.get("name") or "instanced_geo").strip(),
        "instance_source": src,
        "base_geometry": str(a.get("base_geometry") or "box").strip().lower(),
        "color_mode": str(a.get("color_mode") or "auto").strip().lower(),
        "scale_mode": str(a.get("scale_mode") or "auto").strip().lower(),
        "orient_mode": str(a.get("orient_mode") or "auto").strip().lower(),
        "create_render_pipeline": False if str(a.get("create_render_pipeline") or "").lower() in ("0", "false", "no") else True,
    }
    code = _SETUP_GPU_INSTANCING.replace("__SPEC__", repr(spec))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    return res


# ── 31. td_setup_postfx_chain — Pilar 17: Rack Modular de Post-Procesado ─────

_SETUP_POSTFX_CHAIN = r'''
import json
spec = __SPEC__
parent = op(spec['parent_path']) or op('/')
src_top = op(spec['input_top']) or parent.op(spec['input_top'])
if not src_top or src_top.family != 'TOP':
    print('<<JSON>>' + json.dumps({"ok": False, "error": f"input_top no encontrado o no es TOP: {spec['input_top']}"}))
else:
    r_name = spec['name']
    comp = parent.op(r_name)
    if comp and getattr(comp, 'OPType', comp.type) != 'baseCOMP':
        comp.destroy()
        comp = None
    if not comp:
        comp = parent.create(td.baseCOMP, r_name)

    # Custom Parameters de Mastering
    page = None
    for pg in comp.customPages:
        if pg.name == 'PostFX':
            page = pg; break
    if not page:
        page = comp.appendCustomPage('PostFX')

    def ensure_cpar(method, pname, label, v_default, v_min=0.0, v_max=1.0):
        existing = getattr(comp.par, pname, None)
        if existing is not None and existing.isCustom:
            return existing
        p = getattr(page, method)(pname, label=label)[0]
        p.val = v_default
        p.normMin, p.normMax = v_min, v_max
        return p

    p_bloom = ensure_cpar('appendToggle', 'Bloom', 'Enable Bloom', True)
    p_b_int = ensure_cpar('appendFloat', 'Bloomintensity', 'Bloom Intensity', 0.6, 0.0, 2.0)
    p_b_rad = ensure_cpar('appendFloat', 'Bloomradius', 'Bloom Radius', 15.0, 1.0, 50.0)

    p_trail = ensure_cpar('appendToggle', 'Feedbacktrail', 'Enable Feedback Trail', False)
    p_fb_op = ensure_cpar('appendFloat', 'Trailopacity', 'Trail Opacity', 0.85, 0.0, 0.98)

    p_bri = ensure_cpar('appendFloat', 'Brightness', 'Brightness', 1.0, 0.0, 2.0)
    p_con = ensure_cpar('appendFloat', 'Contrast', 'Contrast', 1.1, 0.2, 2.5)
    p_gam = ensure_cpar('appendFloat', 'Gamma', 'Gamma', 1.0, 0.2, 2.5)
    p_sat = ensure_cpar('appendFloat', 'Saturation', 'Saturation', 1.15, 0.0, 3.0)

    def ensure_child(cls_name, cname):
        c = comp.op(cname)
        if c and getattr(c, 'OPType', c.type) != cls_name:
            c.destroy()
            c = None
        return c or comp.create(getattr(td, cls_name), cname)

    in1 = ensure_child('inTOP', 'in1')
    in1.nodeX, in1.nodeY = -240, 0

    # Feedback loop opcional
    fb_comp = ensure_child('compositeTOP', 'fb_over')
    fb_comp.par.operand = 'over'
    fb_decay = ensure_child('levelTOP', 'fb_decay')
    fb_decay.par.opacity.expr = "parent().par.Trailopacity if parent().par.Feedbacktrail else 0.0"
    fb_top = ensure_child('feedbackTOP', 'fb1')
    fb_top.par.top = fb_comp.path
    fb_decay.inputConnectors[0].connect(fb_top)
    fb_comp.inputConnectors[0].connect(in1)
    fb_comp.inputConnectors[1].connect(fb_decay)
    fb_comp.nodeX, fb_comp.nodeY = 0, 0

    # Rama Bloom
    blm_thresh = ensure_child('levelTOP', 'bloom_thresh')
    blm_thresh.inputConnectors[0].connect(fb_comp)
    blm_thresh.par.threshold = 0.55
    blm_thresh.nodeX, blm_thresh.nodeY = 160, 120

    blm_blur = ensure_child('blurTOP', 'bloom_blur')
    blm_blur.inputConnectors[0].connect(blm_thresh)
    blm_blur.par.size.expr = "parent().par.Bloomradius"
    blm_blur.nodeX, blm_blur.nodeY = 320, 120

    blm_gain = ensure_child('levelTOP', 'bloom_gain')
    blm_gain.inputConnectors[0].connect(blm_blur)
    blm_gain.par.brightness1.expr = "parent().par.Bloomintensity if parent().par.Bloom else 0.0"
    blm_gain.nodeX, blm_gain.nodeY = 480, 120

    blm_add = ensure_child('compositeTOP', 'bloom_add')
    blm_add.par.operand = 'add'
    blm_add.inputConnectors[0].connect(fb_comp)
    blm_add.inputConnectors[1].connect(blm_gain)
    blm_add.nodeX, blm_add.nodeY = 320, 0

    # Mastering / Color Grade
    grade = ensure_child('levelTOP', 'grade')
    grade.inputConnectors[0].connect(blm_add)
    grade.par.brightness1.expr = "parent().par.Brightness"
    grade.par.contrast.expr = "parent().par.Contrast"
    grade.par.gamma1.expr = "parent().par.Gamma"
    if hasattr(grade.par, 'saturation'):
        grade.par.saturation.expr = "parent().par.Saturation"
    grade.nodeX, grade.nodeY = 500, 0

    out1 = ensure_child('outTOP', 'out1')
    out1.inputConnectors[0].connect(grade)
    out1.nodeX, out1.nodeY = 680, 0

    # Conectar entrada del rack al source TOP
    comp.inputConnectors[0].connect(src_top)

    try: comp.cook(force=True)
    except: pass

    print('<<JSON>>' + json.dumps({
        "ok": True,
        "rack_comp": comp.path,
        "input_top": src_top.path,
        "output_top": out1.path,
        "stages": ["feedback_trail", "bloom_glow", "color_mastering"],
        "custom_parameters": ["Bloom", "Bloomintensity", "Bloomradius", "Feedbacktrail", "Trailopacity", "Brightness", "Contrast", "Gamma", "Saturation"],
    }))
'''


def t_setup_postfx_chain(a: dict) -> dict:
    """Pilar 17 — Rack Modular de Post-Procesado y Mastering (baseCOMP en GPU con Bloom/Glow multicapa, Feedback Trail estelar, Color Grading y Custom Parameters listos para controlar desde UI/audio)."""
    inp = str(a.get("input_top") or "").strip()
    if not inp:
        return {"ok": False, "error": "falta 'input_top' (ruta del TOP a procesar)"}
    spec = {
        "parent_path": str(a.get("parent_path") or "/project1").strip(),
        "name": str(a.get("name") or "postfx_rack").strip(),
        "input_top": inp,
    }
    code = _SETUP_POSTFX_CHAIN.replace("__SPEC__", repr(spec))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    return res


# ── 32. td_setup_io_bridge — Pilar 18: Hub de Protocolos OSC / MIDI / DMX / UDP ─

_SETUP_IO_BRIDGE = r'''
import json
spec = __SPEC__
parent = op(spec['parent_path']) or op('/')
proto = spec.get('protocol', 'osc').lower()
b_name = spec['name']
comp = parent.op(b_name)
if comp and getattr(comp, 'OPType', comp.type) != 'baseCOMP':
    comp.destroy()
    comp = None
if not comp:
    comp = parent.create(td.baseCOMP, b_name)

def ensure_child(cls_name, cname):
    c = comp.op(cname)
    if c and getattr(c, 'OPType', c.type) != cls_name:
        c.destroy()
        c = None
    return c or comp.create(getattr(td, cls_name), cname)

port = int(spec.get('port', 7000))
addr = spec.get('target_address', '127.0.0.1')
loopback = bool(spec.get('loopback_test', True))
created_ops = []

if proto == 'osc':
    oin = ensure_child('oscinCHOP', 'osc_in')
    oin.par.port = port
    oin.nodeX, oin.nodeY = 0, 0
    created_ops.append(oin.path)

    out_null = ensure_child('nullCHOP', 'out_io')
    out_null.inputConnectors[0].connect(oin)
    out_null.nodeX, out_null.nodeY = 240, 0
    created_ops.append(out_null.path)

    if loopback:
        oout = ensure_child('oscoutCHOP', 'osc_out_sim')
        oout.par.port = port
        oout.par.netaddress = addr
        lfo = ensure_child('lfoCHOP', 'sim_signal')
        lfo.par.frequency = 1.0
        lfo.par.channelname = 'osc_ch1 osc_ch2'
        oout.inputConnectors[0].connect(lfo)
        lfo.nodeX, lfo.nodeY = -240, 140
        oout.nodeX, oout.nodeY = 0, 140
        created_ops.extend([lfo.path, oout.path])

elif proto == 'dmx':
    dout = ensure_child('dmxoutCHOP', 'dmx_out')
    dout.par.netaddress = addr
    dout.nodeX, dout.nodeY = 0, 0
    created_ops.append(dout.path)

    sig = ensure_child('waveCHOP', 'dmx_channels')
    sig.par.channelname = 'chan[1-12]'
    dout.inputConnectors[0].connect(sig)
    sig.nodeX, sig.nodeY = -200, 0
    created_ops.append(sig.path)

elif proto == 'midi':
    min_op = ensure_child('midiinCHOP', 'midi_in')
    min_op.nodeX, min_op.nodeY = 0, 0
    created_ops.append(min_op.path)

    out_null = ensure_child('nullCHOP', 'out_io')
    out_null.inputConnectors[0].connect(min_op)
    out_null.nodeX, out_null.nodeY = 200, 0
    created_ops.append(out_null.path)

else:
    # UDP dat
    uin = ensure_child('udpinDAT', 'udp_in')
    uin.par.port = port
    uin.nodeX, uin.nodeY = 0, 0
    created_ops.append(uin.path)

try: comp.cook(force=True)
except: pass

print('<<JSON>>' + json.dumps({
    "ok": True,
    "io_hub": comp.path,
    "protocol": proto,
    "port": port,
    "target_address": addr,
    "loopback_test": loopback,
    "nodes_created": created_ops,
    "out_channel_path": comp.op('out_io').path if comp.op('out_io') else None,
}))
'''


def t_setup_io_bridge(a: dict) -> dict:
    """Pilar 18 — Hub Universal de Protocolos e I/O Externo: crea módulos listos para OSC, MIDI, DMX/Art-Net o UDP con generadores de loopback/simulación integrados para probar transmisiones y recepciones en vivo."""
    spec = {
        "parent_path": str(a.get("parent_path") or "/project1").strip(),
        "name": str(a.get("name") or "io_hub").strip(),
        "protocol": str(a.get("protocol") or "osc").strip().lower(),
        "port": int(a.get("port") if a.get("port") is not None else 7000),
        "target_address": str(a.get("target_address") or "127.0.0.1").strip(),
        "loopback_test": False if str(a.get("loopback_test") or "").lower() in ("0", "false", "no") else True,
    }
    code = _SETUP_IO_BRIDGE.replace("__SPEC__", repr(spec))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    return res


# ── 33. td_record_movie — Pilar 19: Grabador determinista de video/animaciones ─

def t_record_movie(a: dict) -> dict:
    """Pilar 19 — Grabador determinista de video/loops y secuencias: avanza paso a paso N frames a FPS constante cocinando al 100%, genera una animación limpia (GIF animado universal con PIL o frames) y verifica el archivo resultante en disco."""
    import tempfile
    import time
    from pathlib import Path
    from PIL import Image

    top_path = str(a.get("top_path") or "").strip()
    if not top_path:
        return {"ok": False, "error": "falta 'top_path' (ruta del TOP a grabar)"}

    num_frames = min(max(int(a.get("num_frames") if a.get("num_frames") is not None else 24), 2), 240)
    fps = max(float(a.get("fps") if a.get("fps") is not None else 30.0), 1.0)
    reset_first = str(a.get("reset_first") or "").lower() in ("1", "true", "yes", "si", "sí") or a.get("reset_first") is True

    if reset_first:
        parent_guess = top_path.rsplit("/", 1)[0] or "/"
        t_control_simulation({"container_path": parent_guess, "action": "reset_only"})

    tmp_files: list[Path] = []
    try:
        step_code = r'''
import json
spec = __SPEC__
t = op(spec['top_path'])
if not t:
    print('<<JSON>>' + json.dumps({"ok": False, "error": f"TOP no encontrado: {spec['top_path']}"}))
else:
    try:
        op('/').time.frame += 1
    except: pass
    if t.parent():
        for c in t.parent().children:
            try: c.cook(force=True)
            except: pass
    try: t.cook(force=True)
    except: pass
    t.save(spec['save_path'])
    print('<<JSON>>' + json.dumps({"ok": True, "w": int(t.width), "h": int(t.height)}))
'''
        for i in range(num_frames):
            tmp_p = Path(tempfile.gettempdir()) / f"tdmcp_rec_{os.getpid()}_{i}.png"
            tmp_files.append(tmp_p)
            spec = {"top_path": top_path, "save_path": str(tmp_p)}
            ok, r = exec_code(step_code.replace("__SPEC__", repr(spec)))
            if not ok or not isinstance(r, dict) or not r.get("ok"):
                return {"ok": False, "error": f"falló captura de frame {i}: {r}"}

        # Cargar frames y armar GIF animado determinista
        loaded_imgs = [Image.open(p).convert("RGBA") for p in tmp_files]
        first = loaded_imgs[0]
        out_path = str(a.get("out_path") or "").strip()
        if not out_path:
            slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", top_path.strip("/")) or "rec"
            out_path = str(Path(tempfile.gettempdir()) / f"td_loop_{slug}.gif")

        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        frame_dur_ms = int(round(1000.0 / fps))
        first.save(out_path, save_all=True, append_images=loaded_imgs[1:], duration=frame_dur_ms, loop=0)

        fsize = os.path.getsize(out_path) if os.path.exists(out_path) else 0
        return {
            "ok": True,
            "top_path": top_path,
            "file_path": out_path,
            "format": "gif",
            "num_frames": num_frames,
            "fps": fps,
            "duration_seconds": round(num_frames / fps, 3),
            "resolution": f"{first.width}x{first.height}",
            "file_size_bytes": fsize,
        }
    except Exception as e:
        return {"ok": False, "error": f"error en td_record_movie: {e}"}
    finally:
        for tf in tmp_files:
            try:
                if tf.exists(): tf.unlink()
            except: pass


# ── 34. td_heal_network — Pilar 20: Auto-healer y doctor de redes ────────────

_HEAL_NETWORK = r'''
import json
spec = __SPEC__
root = op(spec['container_path']) or op('/')
dry_run = bool(spec.get('dry_run', False))

if not root:
    print('<<JSON>>' + json.dumps({"ok": False, "error": f"contenedor no encontrado: {spec['container_path']}"}))
else:
    all_ops = []
    def collect(comp, depth):
        for c in comp.children:
            if c.name.startswith('.'): continue
            all_ops.append(c)
            if c.family == 'COMP' and depth < 4:
                collect(c, depth + 1)
    collect(root, 0)

    fixes = []

    # 1. Torus trap en geometryCOMPs
    for c in all_ops:
        if not getattr(c, 'valid', False): continue
        if getattr(c, 'OPType', c.type) == 'geometryCOMP':
            tor = c.op('torus1')
            other_geos = [ch for ch in c.children if ch.family in ('POP', 'SOP') and ch.name != 'torus1']
            if tor and other_geos:
                fixes.append({"type": "destroy_residual_torus", "target": tor.path, "action": "destroy"})
                if not dry_run:
                    try: tor.destroy()
                    except: pass

            # 2. Flags display/render apagadas
            pop_sop_children = [ch for ch in c.children if ch.family in ('POP', 'SOP')]
            active_render = [ch for ch in pop_sop_children if getattr(ch, 'render', False)]
            if pop_sop_children and not active_render:
                term = next((ch for ch in pop_sop_children if ch.name.startswith(('out', 'null'))), pop_sop_children[-1])
                fixes.append({"type": "enable_render_display_flags", "target": term.path, "action": "set display=True, render=True"})
                if not dry_run:
                    try:
                        term.display = True
                        term.render = True
                    except: pass

    # 3. TOPs con resolution custom no fijada
    for c in all_ops:
        if not getattr(c, 'valid', False): continue
        if c.family == 'TOP' and hasattr(c.par, 'outputresolution'):
            rw = getattr(c.par, 'resolutionw', None)
            rh = getattr(c.par, 'resolutionh', None)
            if rw and rh and (not rw.isDefault or not rh.isDefault) and str(c.par.outputresolution.eval()) != 'custom':
                fixes.append({"type": "set_outputresolution_custom", "target": c.path, "action": "set outputresolution='custom'"})
                if not dry_run:
                    try: c.par.outputresolution = 'custom'
                    except: pass

    # 4. renderTOP sin cámara válida
    all_cams = [c for c in all_ops if getattr(c, 'valid', False) and getattr(c, 'OPType', c.type) == 'cameraCOMP']
    for c in all_ops:
        if not getattr(c, 'valid', False): continue
        if getattr(c, 'OPType', c.type) == 'renderTOP' and hasattr(c.par, 'camera'):
            cam_val = str(c.par.camera.eval() or '').strip()
            cam_node = op(cam_val) or c.parent().op(cam_val)
            if not cam_node and all_cams:
                target_cam = all_cams[0].path
                fixes.append({"type": "bind_missing_camera", "target": c.path, "action": f"set camera='{target_cam}'"})
                if not dry_run:
                    try: c.par.camera = target_cam
                    except: pass

    # 5. Nan/Inf en simulaciones
    has_nan = False
    for c in all_ops:
        if not getattr(c, 'valid', False): continue
        if c.family in ('POP', 'CHOP'):
            try:
                b = c.bounds() if callable(getattr(c, 'bounds', None)) else getattr(c, 'bounds', None)
                if b and any(str(v).lower() in ('nan', 'inf') for v in list(b.center) + list(b.size)):
                    has_nan = True
                    break
            except: pass

    if has_nan:
        for c in all_ops:
            if not getattr(c, 'valid', False): continue
            if getattr(c, 'OPType', c.type) in ('feedbackPOP', 'particlePOP', 'feedbackTOP', 'speedCHOP'):
                for rp in ('resetpulse', 'reset'):
                    p = getattr(c.par, rp, None)
                    if p:
                        fixes.append({"type": "reset_nan_simulation", "target": f"{c.path}.par.{rp}", "action": "pulse"})
                        if not dry_run:
                            try: p.pulse()
                            except: pass

    # Cook settle
    if not dry_run:
        for _ in range(3):
            for c in all_ops:
                if not getattr(c, 'valid', False): continue
                try: c.cook(force=True)
                except: pass

    print('<<JSON>>' + json.dumps({
        "ok": True,
        "container_path": root.path,
        "dry_run": dry_run,
        "fixes_count": len(fixes),
        "fixes": fixes,
    }))
'''


def t_heal_network(a: dict) -> dict:
    """Pilar 20 — Doctor Autónomo de Redes (Self-Healing): detecta y repara automáticamente fallas estructurales (torus1 residual, flags display/render ausentes, outputresolution='custom' no fijado, cámaras de renderTOP desvinculadas y NaNs en simulaciones)."""
    container_path = str(a.get("container_path") or "/project1").strip()
    dry_run = str(a.get("dry_run") or "").lower() in ("1", "true", "yes", "si", "sí") or a.get("dry_run") is True
    spec = {"container_path": container_path, "dry_run": dry_run}
    code = _HEAL_NETWORK.replace("__SPEC__", repr(spec))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    if ok and isinstance(res, dict) and not dry_run:
        ver = t_verify_network({"container_path": container_path})
        res["post_healing_verification"] = {
            "verdict": ver.get("verdict"),
            "issues_count": len(ver.get("issues", [])),
        }
    return res




# ── 31. td_setup_display_canvas — Canvas Multi-Display & Edge Blending ────────

_SETUP_DISPLAY_CANVAS = r"""
import json
spec = __SPEC__
parent = op(spec['parent_path']) or op('/')
c_name = spec['name']
comp = parent.op(c_name)
if comp and getattr(comp, 'OPType', comp.type) != 'baseCOMP':
    comp.destroy()
    comp = None
if not comp:
    comp = parent.create(td.baseCOMP, c_name)

num_disp = max(1, min(8, int(spec.get('num_displays', 2))))
disp_w = int(spec.get('display_width', 1920))
disp_h = int(spec.get('display_height', 1080))
layout = spec.get('layout', 'horizontal').lower()
is_horiz = layout == 'horizontal'
overlap = max(0, int(spec.get('overlap_pixels', 120))) if num_disp > 1 else 0
test_pattern = bool(spec.get('test_pattern', True))
create_window = bool(spec.get('create_window', False))

if is_horiz:
    canvas_w = (disp_w * num_disp) - (overlap * (num_disp - 1))
    canvas_h = disp_h
else:
    canvas_w = disp_w
    canvas_h = (disp_h * num_disp) - (overlap * (num_disp - 1))

# Content source
src_top_path = spec.get('input_top')
src_top = op(src_top_path) if src_top_path else None
content_in = comp.op('content_in')
if not content_in:
    content_in = comp.create(td.nullTOP, 'content_in')

if src_top:
    sel = comp.op('sel_input') or comp.create(td.selectTOP, 'sel_input')
    sel.par.top = src_top.path
    if not content_in.inputConnectors[0].connections:
        content_in.inputConnectors[0].connect(sel)
else:
    gen = comp.op('test_content') or comp.create(td.noiseTOP, 'test_content')
    gen.par.outputresolution = 'custom'
    gen.par.resolutionw = canvas_w
    gen.par.resolutionh = canvas_h
    gen.par.mono = 0
    if not content_in.inputConnectors[0].connections:
        content_in.inputConnectors[0].connect(gen)

displays_meta = []
for i in range(num_disp):
    crop_name = f'crop_disp{i}'
    cr = comp.op(crop_name) or comp.create(td.cropTOP, crop_name)
    if not cr.inputConnectors[0].connections:
        cr.inputConnectors[0].connect(content_in)
    cr.par.cropleftunit = 'pixels'
    cr.par.croprightunit = 'pixels'
    cr.par.croptopunit = 'pixels'
    cr.par.cropbottomunit = 'pixels'

    if is_horiz:
        x0 = i * (disp_w - overlap)
        x1 = x0 + disp_w
        cr.par.cropleft = x0
        cr.par.cropright = x1
        cr.par.cropbottom = 0
        cr.par.croptop = disp_h
        crop_bounds = {"x0": x0, "x1": x1, "y0": 0, "y1": disp_h}
    else:
        y0 = (num_disp - 1 - i) * (disp_h - overlap)
        y1 = y0 + disp_h
        cr.par.cropleft = 0
        cr.par.cropright = disp_w
        cr.par.cropbottom = y0
        cr.par.croptop = y1
        crop_bounds = {"x0": 0, "x1": disp_w, "y0": y0, "y1": y1}

    last_op = cr
    if test_pattern:
        lbl_name = f'lbl_disp{i}'
        lbl = comp.op(lbl_name) or comp.create(td.textTOP, lbl_name)
        lbl.par.text = f'DISPLAY {i+1}/{num_disp}\n{disp_w}x{disp_h}\n[X: {crop_bounds["x0"]}..{crop_bounds["x1"]}]'
        lbl.par.outputresolution = 'custom'
        lbl.par.resolutionw = disp_w
        lbl.par.resolutionh = disp_h
        if hasattr(lbl.par, 'fontsizex'):
            lbl.par.fontsizex = 28
        elif hasattr(lbl.par, 'fontsize'):
            lbl.par.fontsize = 28
        lbl.par.alignx = 'center'
        lbl.par.aligny = 'center'

        ov_name = f'overlay_disp{i}'
        ov = comp.op(ov_name) or comp.create(td.compositeTOP, ov_name)
        ov.par.operand = 'over'
        if len(ov.inputConnectors[0].connections) == 0:
            ov.inputConnectors[0].connect(cr)
        if len(ov.inputConnectors[1].connections) == 0:
            ov.inputConnectors[1].connect(lbl)
        last_op = ov

    out_name = f'out_disp{i}'
    out_node = comp.op(out_name) or comp.create(td.outTOP, out_name)
    if not out_node.inputConnectors[0].connections:
        out_node.inputConnectors[0].connect(last_op)
    try:
        out_node.cook(force=True)
    except:
        pass

    displays_meta.append({
        "display_index": i,
        "resolution": [disp_w, disp_h],
        "crop_bounds": crop_bounds,
        "out_op": out_node.path,
    })

out_canvas = comp.op('out_canvas') or comp.create(td.nullTOP, 'out_canvas')
if not out_canvas.inputConnectors[0].connections:
    out_canvas.inputConnectors[0].connect(content_in)
try:
    out_canvas.cook(force=True)
except:
    pass

win_path = None
if create_window:
    win = comp.op('canvas_window') or comp.create(td.windowCOMP, 'canvas_window')
    win.par.winop = out_canvas.path
    win.par.winw = canvas_w
    win.par.winh = canvas_h
    win.par.borders = False
    win_path = win.path

print('<<JSON>>' + json.dumps({
    "ok": True,
    "canvas_comp": comp.path,
    "canvas_resolution": [canvas_w, canvas_h],
    "num_displays": num_disp,
    "layout": layout,
    "overlap_pixels": overlap,
    "total_overlap_pixels": overlap * (num_disp - 1) if num_disp > 1 else 0,
    "test_pattern_active": test_pattern,
    "displays": displays_meta,
    "out_canvas": out_canvas.path,
    "window_comp": win_path,
}))
"""


def t_setup_display_canvas(a: dict) -> dict:
    """Pilar 21 — Multi-Display Canvas & Edge Blending: genera canvas multi-pantalla / multi-proyector con cálculo exacto de solapamientos (overlap), crops individuales por proyector, generador de patrones de test y windowCOMP de span opcional."""
    spec = {
        "parent_path": str(a.get("parent_path") or "/project1").strip(),
        "name": str(a.get("name") or "display_canvas").strip(),
        "num_displays": int(a.get("num_displays") or 2),
        "display_width": int(a.get("display_width") or 1920),
        "display_height": int(a.get("display_height") or 1080),
        "layout": str(a.get("layout") or "horizontal").strip().lower(),
        "overlap_pixels": int(a.get("overlap_pixels") if a.get("overlap_pixels") is not None else 120),
        "test_pattern": False if str(a.get("test_pattern") or "").lower() in ("0", "false", "no") else True,
        "input_top": str(a.get("input_top") or "").strip() or None,
        "create_window": str(a.get("create_window") or "").lower() in ("1", "true", "yes", "si", "sí") or a.get("create_window") is True,
    }
    code = _SETUP_DISPLAY_CANVAS.replace("__SPEC__", repr(spec))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    return res


# ── 32. td_setup_pbr_stage — High-End PBR Staging & Environment Lighting ──────

_SETUP_PBR_STAGE = r"""
import json
spec = __SPEC__
parent = op(spec['parent_path']) or op('/')
s_name = spec['name']
comp = parent.op(s_name)
if comp and getattr(comp, 'OPType', comp.type) != 'baseCOMP':
    comp.destroy()
    comp = None
if not comp:
    comp = parent.create(td.baseCOMP, s_name)

# 1. Environment Sky & Lighting
env_map_path = spec.get('env_map')
env_top = op(env_map_path) if env_map_path else None
if not env_top:
    sky = comp.op('sky_env') or comp.create(td.noiseTOP, 'sky_env')
    sky.par.outputresolution = 'custom'
    sky.par.resolutionw = 512
    sky.par.resolutionh = 256
    sky.par.mono = 0
    env_top = sky

env_light = comp.op('env_light') or comp.create(td.environmentlightCOMP, 'env_light')
env_light.par.envlightmap = env_top.name
env_light.par.dimmer = float(spec.get('env_dimmer', 0.8))

# 2. Three-Point Lighting Rig
key = comp.op('light_key') or comp.create(td.lightCOMP, 'light_key')
key.par.tx = 4.0
key.par.ty = 5.0
key.par.tz = 4.0
key.par.rx = -35.0
key.par.ry = 45.0
key.par.dimmer = float(spec.get('key_dimmer', 1.0))

fill = comp.op('light_fill') or comp.create(td.lightCOMP, 'light_fill')
fill.par.tx = -4.0
fill.par.ty = 2.0
fill.par.tz = 3.0
fill.par.rx = -20.0
fill.par.ry = -35.0
fill.par.dimmer = float(spec.get('fill_dimmer', 0.35))

rim = comp.op('light_rim') or comp.create(td.lightCOMP, 'light_rim')
rim.par.tx = 0.0
rim.par.ty = 4.0
rim.par.tz = -5.0
rim.par.rx = -25.0
rim.par.ry = 180.0
rim.par.dimmer = float(spec.get('rim_dimmer', 0.65))

# 3. Ground plane / Shadow catcher
include_ground = bool(spec.get('include_ground', True))
ground_path = None
if include_ground:
    ground_geo = comp.op('ground_geo') or comp.create(td.geometryCOMP, 'ground_geo')
    for c in list(ground_geo.children):
        if c.name == 'torus1':
            c.destroy()
    grid = ground_geo.op('grid') or ground_geo.create(td.gridSOP, 'grid')
    g_size = float(spec.get('ground_size', 30.0))
    grid.par.sizex = g_size
    grid.par.sizey = g_size
    grid.par.orient = 'zx'

    null_g = ground_geo.op('null_ground') or ground_geo.create(td.nullSOP, 'null_ground')
    if not null_g.inputConnectors[0].connections:
        null_g.inputConnectors[0].connect(grid)
    null_g.display = True
    null_g.render = True

    ground_mat = comp.op('ground_mat') or comp.create(td.pbrMAT, 'ground_mat')
    ground_mat.par.roughness = float(spec.get('ground_roughness', 0.8))
    ground_mat.par.metallic = 0.05
    ground_geo.par.material = ground_mat.name
    ground_path = ground_geo.path

# 4. Subject material ready for geometry
subject_mat = comp.op('subject_mat') or comp.create(td.pbrMAT, 'subject_mat')
subject_mat.par.roughness = 0.25
subject_mat.par.metallic = 0.15

# 5. Camera & Render pipeline
cam = comp.op('cam') or comp.create(td.cameraCOMP, 'cam')
cam.par.tx = 0.0
cam.par.ty = 1.2
cam.par.tz = float(spec.get('camera_tz', 4.5))

ren = comp.op('render_stage') or comp.create(td.renderTOP, 'render_stage')
ren.par.camera = cam.name
ren.par.lights = '*'
ren.par.geometry = '*'

res_str = spec.get('resolution', '1280x720')
try:
    rw, rh = [int(x.strip()) for x in res_str.lower().split('x')]
except:
    rw, rh = 1280, 720
ren.par.outputresolution = 'custom'
ren.par.resolutionw = rw
ren.par.resolutionh = rh

out = comp.op('out_stage') or comp.create(td.nullTOP, 'out_stage')
if not out.inputConnectors[0].connections:
    out.inputConnectors[0].connect(ren)

for _ in range(4):
    ren.cook(force=True)
    out.cook(force=True)

print('<<JSON>>' + json.dumps({
    "ok": True,
    "stage_comp": comp.path,
    "lights": [env_light.path, key.path, fill.path, rim.path],
    "ground_geo": ground_path,
    "subject_mat": subject_mat.path,
    "camera": cam.path,
    "render_top": ren.path,
    "out_top": out.path,
    "resolution": [rw, rh],
}))
"""


def t_setup_pbr_stage(a: dict) -> dict:
    """Pilar 22 — PBR Staging & Environment Lighting: monta un set de iluminación cinematográfica 3D (Key/Fill/Rim lights + environmentlightCOMP con mapa HDRI o procedural), plano de suelo PBR receptor de sombras, material PBR para sujetos, cámara calibrada y renderTOP libre de trampas."""
    spec = {
        "parent_path": str(a.get("parent_path") or "/project1").strip(),
        "name": str(a.get("name") or "pbr_stage").strip(),
        "env_map": str(a.get("env_map") or "").strip() or None,
        "env_dimmer": float(a.get("env_dimmer") or 0.8),
        "key_dimmer": float(a.get("key_dimmer") or 1.0),
        "fill_dimmer": float(a.get("fill_dimmer") or 0.35),
        "rim_dimmer": float(a.get("rim_dimmer") or 0.65),
        "include_ground": False if str(a.get("include_ground") or "").lower() in ("0", "false", "no") else True,
        "ground_size": float(a.get("ground_size") or 30.0),
        "ground_roughness": float(a.get("ground_roughness") or 0.8),
        "camera_tz": float(a.get("camera_tz") or 4.5),
        "resolution": str(a.get("resolution") or "1280x720").strip(),
    }
    code = _SETUP_PBR_STAGE.replace("__SPEC__", repr(spec))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    return res


# ── 33. td_sync_external_tox — Sincronización y Hot-Reload de Componentes TOX ──

_SYNC_EXTERNAL_TOX = r"""
import json, os
spec = __SPEC__
target = op(spec['comp_path']) or op('/')
action = spec.get('action', 'inspect').lower()
custom_tox = spec.get('tox_path')

if not target:
    print('<<JSON>>' + json.dumps({"ok": False, "error": f"comp_path no encontrado: {spec['comp_path']}"}))
else:
    if action == 'export':
        dest = custom_tox or (target.par.externaltox.eval() if hasattr(target.par, 'externaltox') else '')
        if not dest:
            folder = project.folder.replace('\\', '/')
            dest = f"{folder}/{target.name}.tox"
        dest = os.path.abspath(dest).replace('\\', '/')
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        target.save(dest)
        if bool(spec.get('bind_external', True)) and hasattr(target.par, 'externaltox'):
            target.par.externaltox = dest
        exists = os.path.exists(dest)
        sz = os.path.getsize(dest) if exists else 0
        print('<<JSON>>' + json.dumps({
            "ok": True,
            "action": "export",
            "comp_path": target.path,
            "saved_file": dest,
            "size_bytes": sz,
            "externaltox_bound": target.par.externaltox.eval() if hasattr(target.par, 'externaltox') else '',
        }))

    elif action == 'reload':
        src = custom_tox or (target.par.externaltox.eval() if hasattr(target.par, 'externaltox') else '')
        if not src or not os.path.exists(src):
            print('<<JSON>>' + json.dumps({"ok": False, "error": f"archivo tox no existe para recarga: {src}"}))
        else:
            if custom_tox and hasattr(target.par, 'externaltox'):
                target.par.externaltox = custom_tox
            if hasattr(target.par, 'reinitnet'):
                target.par.reinitnet.pulse()
            elif hasattr(target, 'loadTox'):
                target.loadTox(src)
            print('<<JSON>>' + json.dumps({
                "ok": True,
                "action": "reload",
                "comp_path": target.path,
                "reloaded_file": src,
                "mtime": os.path.getmtime(src),
            }))

    elif action == 'bind':
        if not custom_tox:
            print('<<JSON>>' + json.dumps({"ok": False, "error": "falta 'tox_path' para acción 'bind'"}))
        else:
            if hasattr(target.par, 'externaltox'):
                target.par.externaltox = custom_tox
            print('<<JSON>>' + json.dumps({
                "ok": True,
                "action": "bind",
                "comp_path": target.path,
                "externaltox": target.par.externaltox.eval() if hasattr(target.par, 'externaltox') else '',
                "file_exists": os.path.exists(custom_tox),
            }))

    else:
        recurse = bool(spec.get('recurse', True))
        candidates = [target] if target.isCOMP else []
        if recurse and hasattr(target, 'findChildren'):
            candidates.extend(target.findChildren(type=COMP))

        audited = []
        for c in candidates:
            if c.path.startswith(('/ui', '/sys', '/TDMCP')):
                continue
            ext = c.par.externaltox.eval() if hasattr(c.par, 'externaltox') else ''
            status = "NOT_EXTERNAL"
            file_info = None
            if ext:
                if os.path.exists(ext):
                    status = "SYNCED"
                    file_info = {
                        "path": ext,
                        "size_bytes": os.path.getsize(ext),
                        "mtime": os.path.getmtime(ext),
                    }
                else:
                    status = "FILE_MISSING_ON_DISK"
                    file_info = {"path": ext, "missing": True}
            audited.append({
                "comp_path": c.path,
                "type": getattr(c, 'OPType', c.type),
                "status": status,
                "externaltox": ext,
                "file_info": file_info,
            })

        ext_count = sum(1 for a in audited if a['externaltox'])
        missing_count = sum(1 for a in audited if a['status'] == 'FILE_MISSING_ON_DISK')
        print('<<JSON>>' + json.dumps({
            "ok": True,
            "action": "inspect",
            "root_path": target.path,
            "total_comps_audited": len(audited),
            "external_comps_count": ext_count,
            "missing_files_count": missing_count,
            "components": audited[:60],
        }))
"""


def t_sync_external_tox(a: dict) -> dict:
    """Pilar 23 — Sincronización y Hot-Reload de Componentes TOX: inspecciona dependencias externas en disco, audita drifts, exporta componentes a .tox de forma atómica y ejecuta Hot-Reload en memoria sin perder Custom Parameters."""
    spec = {
        "comp_path": str(a.get("comp_path") or "/project1").strip(),
        "action": str(a.get("action") or "inspect").strip().lower(),
        "tox_path": str(a.get("tox_path") or "").strip() or None,
        "recurse": False if str(a.get("recurse") or "").lower() in ("0", "false", "no") else True,
        "bind_external": False if str(a.get("bind_external") or "").lower() in ("0", "false", "no") else True,
    }
    code = _SYNC_EXTERNAL_TOX.replace("__SPEC__", repr(spec))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    return res


# ── 34. td_setup_ai_stream — Conector Streaming GenAI & ComfyUI ───────────────

_SETUP_AI_STREAM = r"""
import json
spec = __SPEC__
parent = op(spec['parent_path']) or op('/')
b_name = spec['name']
comp = parent.op(b_name)
if comp and getattr(comp, 'OPType', comp.type) != 'baseCOMP':
    comp.destroy()
    comp = None
if not comp:
    comp = parent.create(td.baseCOMP, b_name)

backend = spec.get('backend', 'comfyui').lower()
server_url = str(spec.get('server_url') or 'http://127.0.0.1:8188').rstrip('/')
default_prompt = str(spec.get('default_prompt') or 'masterpiece, abstract generative procedural geometry')
neg_prompt = str(spec.get('negative_prompt') or 'low quality, blurry, distorted')

# 1. Input image conditioning
in_src_path = spec.get('input_top')
in_src = op(in_src_path) if in_src_path else None
input_frame = comp.op('input_frame') or comp.create(td.nullTOP, 'input_frame')
if in_src:
    sel = comp.op('sel_in') or comp.create(td.selectTOP, 'sel_in')
    sel.par.top = in_src.path
    if not input_frame.inputConnectors[0].connections:
        input_frame.inputConnectors[0].connect(sel)
else:
    c_gen = comp.op('default_in') or comp.create(td.constantTOP, 'default_in')
    c_gen.par.outputresolution = 'custom'
    c_gen.par.resolutionw = 512
    c_gen.par.resolutionh = 512
    c_gen.par.colorr = 0.1
    c_gen.par.colorg = 0.12
    c_gen.par.colorb = 0.15
    if not input_frame.inputConnectors[0].connections:
        input_frame.inputConnectors[0].connect(c_gen)

# 2. Web Client for API communication
wc = comp.op('api_client') or comp.create(td.webclientDAT, 'api_client')
wc.par.url = server_url + ('/prompt' if backend == 'comfyui' else '')
wc.par.reqmethod = 'POST'

# 3. Prompt queue table
tab = comp.op('prompt_queue') or comp.create(td.tableDAT, 'prompt_queue')
tab.clear()
tab.appendRow(['id', 'prompt', 'negative_prompt', 'status', 'backend'])
tab.appendRow(['prompt_1', default_prompt, neg_prompt, 'READY', backend])

# 4. Status and telemetry CHOP
metrics = comp.op('stream_metrics') or comp.create(td.constantCHOP, 'stream_metrics')
metrics.par.name0 = 'connected'
metrics.par.value0 = 0.0
metrics.par.name1 = 'latency_ms'
metrics.par.value1 = 0.0
metrics.par.name2 = 'active_requests'
metrics.par.value2 = 1.0

# 5. Output node
out_ai = comp.op('out_ai') or comp.create(td.nullTOP, 'out_ai')
if not out_ai.inputConnectors[0].connections:
    out_ai.inputConnectors[0].connect(input_frame)

# 6. Custom Parameters on ai_bridge baseCOMP
page = comp.appendCustomPage('AI Stream') if 'AI Stream' not in [p.name for p in comp.customPages] else comp.customPages['AI Stream']
existing_pnames = [p.name for p in comp.customPars]

def ensure_cpar(name, style, default=None):
    if name not in existing_pnames:
        p = page.appendStr(name, label=name) if style == 'Str' else (
            page.appendPulse(name, label=name) if style == 'Pulse' else
            page.appendToggle(name, label=name)
        )
        if default is not None:
            p.val = default

ensure_cpar('Serverurl', 'Str', server_url)
ensure_cpar('Prompt', 'Str', default_prompt)
ensure_cpar('Negativeprompt', 'Str', neg_prompt)
ensure_cpar('Submitprompt', 'Pulse')
ensure_cpar('Autostream', 'Toggle', False)

print('<<JSON>>' + json.dumps({
    "ok": True,
    "bridge_comp": comp.path,
    "backend": backend,
    "server_url": server_url,
    "api_client": wc.path,
    "queue_table": tab.path,
    "metrics_chop": metrics.path,
    "out_top": out_ai.path,
    "custom_pars": ['Serverurl', 'Prompt', 'Negativeprompt', 'Submitprompt', 'Autostream'],
}))
"""


def t_setup_ai_stream(a: dict) -> dict:
    """Pilar 24 — Conector Streaming GenAI & ComfyUI: arquitectura puente llave en mano para IA generativa en tiempo real (webclientDAT/websocketDAT, cola de prompts tableDAT, métricas de latencia CHOP, Custom Parameters y texture outTOP)."""
    spec = {
        "parent_path": str(a.get("parent_path") or "/project1").strip(),
        "name": str(a.get("name") or "ai_bridge").strip(),
        "backend": str(a.get("backend") or "comfyui").strip().lower(),
        "server_url": str(a.get("server_url") or "http://127.0.0.1:8188").strip(),
        "input_top": str(a.get("input_top") or "").strip() or None,
        "default_prompt": str(a.get("default_prompt") or "masterpiece, abstract generative procedural geometry").strip(),
        "negative_prompt": str(a.get("negative_prompt") or "low quality, blurry, distorted").strip(),
    }
    code = _SETUP_AI_STREAM.replace("__SPEC__", repr(spec))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    return res


# ── 35. td_benchmark_longevity — Benchmark de Resiliencia y Longevidad 24/7 ────

_BENCHMARK_LONGEVITY = r"""
import json, time
spec = __SPEC__
root = op(spec['container_path']) or op('/')
dur = max(10, min(300, int(spec.get('duration_frames', 60))))
audit_buffers = bool(spec.get('audit_buffers', True))
step = max(1, int(spec.get('sample_interval', 10)))

# 1. Structural Buffer & Memory Growth Risk Audit
risks = []
if audit_buffers and hasattr(root, 'findChildren'):
    nodes = [root] + list(root.findChildren())
    for c in nodes:
        t = getattr(c, 'OPType', c.type)
        if t == 'feedbackTOP':
            is_huge = (getattr(c, 'width', 0) > 2560 or getattr(c, 'height', 0) > 1440)
            risks.append({
                "op": c.path,
                "type": t,
                "risk_level": "HIGH" if is_huge else "MEDIUM",
                "issue": f"feedbackTOP activo {'(resolución alta > 2K)' if is_huge else ''} sin ciclo de reset documentado",
                "recommendation": "Agregar pulso periódico de reset o acotar resolución con fitTOP."
            })
        elif t in ('trailCHOP', 'recordCHOP'):
            l_par = getattr(c.par, 'length', None)
            l_val = l_par.eval() if l_par else None
            if l_val is None or l_val > 1000:
                risks.append({
                    "op": c.path,
                    "type": t,
                    "risk_level": "MEDIUM",
                    "issue": f"{t} con longitud de buffer prolongada (length={l_val})",
                    "recommendation": "Reducir par.length a los frames estrictamente necesarios para la visual."
                })
        elif t in ('tableDAT', 'textDAT'):
            if c.numRows > 1500:
                risks.append({
                    "op": c.path,
                    "type": t,
                    "risk_level": "HIGH",
                    "issue": f"DAT con {c.numRows} filas acumuladas en memoria",
                    "recommendation": "Purgar filas obsoletas con scriptDAT o limitar appendRow."
                })

# 2. Performance & Memory Sampling via performCHOP
perf_probe = op('/').create(td.performCHOP, '_mcp_perf_soak')
perf_probe.par.gpumemused = 1
perf_probe.par.cpumemused = 1
perf_probe.par.cpumsec = 1
perf_probe.cook(force=True)

def _read_pchan(name):
    c = perf_probe.chan(name)
    return float(c.eval()) if c else 0.0

gpu_start = _read_pchan('gpu_mem_used')
cpu_start = _read_pchan('cpu_mem_used')
msec_samples = []

outputs = [c for c in root.children if c.family == 'TOP' and (c.name.startswith('out') or getattr(c, 'OPType', c.type) == 'outTOP')]
if not outputs:
    outputs = [c for c in root.children if c.family == 'TOP'][:3]

for i in range(0, dur, step):
    for o in outputs:
        try:
            o.cook(force=True)
        except Exception:
            pass
    perf_probe.cook(force=True)
    msec_samples.append(round(_read_pchan('cpumsec'), 2))

gpu_end = _read_pchan('gpu_mem_used')
cpu_end = _read_pchan('cpu_mem_used')
perf_probe.destroy()
perf_probe = None

gpu_delta = round(gpu_end - gpu_start, 2)
cpu_delta = round(cpu_end - cpu_start, 2)
avg_msec = round(sum(msec_samples) / max(1, len(msec_samples)), 2) if msec_samples else 0.0

high_risks = sum(1 for r in risks if r['risk_level'] == 'HIGH')
med_risks = sum(1 for r in risks if r['risk_level'] == 'MEDIUM')

score = 100
score -= high_risks * 25
score -= med_risks * 10
if gpu_delta > 40.0:
    score -= 30
if cpu_delta > 50.0:
    score -= 25
score = max(0, min(100, score))

if score >= 85 and high_risks == 0 and gpu_delta < 25.0:
    verdict = "EXHIBITION_READY"
elif score >= 60:
    verdict = "MONITOR_RECOMMENDED"
else:
    verdict = "MEMORY_LEAK_RISK"

print('<<JSON>>' + json.dumps({
    "ok": True,
    "container_path": root.path,
    "duration_frames": dur,
    "verdict": verdict,
    "longevity_score": score,
    "gpu_mem_start_mb": round(gpu_start, 2),
    "gpu_mem_end_mb": round(gpu_end, 2),
    "gpu_mem_delta_mb": gpu_delta,
    "cpu_mem_start_mb": round(cpu_start, 2),
    "cpu_mem_end_mb": round(cpu_end, 2),
    "cpu_mem_delta_mb": cpu_delta,
    "avg_cpu_cook_msec": avg_msec,
    "identified_risks_count": len(risks),
    "identified_risks": risks,
    "recommendations": [r['recommendation'] for r in risks[:5]],
}))
"""


def t_benchmark_longevity(a: dict) -> dict:
    """Pilar 25 — Longevity & 24/7 Resilience Benchmark: auditoría de estabilidad para instalaciones desatendidas; muestrea deltas de memoria VRAM GPU y CPU a lo largo del tiempo, audita nodos con riesgo de acumulación ilimitada y emite veredicto EXHIBITION_READY vs MEMORY_LEAK_RISK."""
    spec = {
        "container_path": str(a.get("container_path") or "/project1").strip(),
        "duration_frames": int(a.get("duration_frames") or 60),
        "audit_buffers": False if str(a.get("audit_buffers") or "").lower() in ("0", "false", "no") else True,
        "sample_interval": int(a.get("sample_interval") or 10),
    }
    code = _BENCHMARK_LONGEVITY.replace("__SPEC__", repr(spec))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    return res


_NETWORK_TIDY = r'''
import json, os

spec = __SPEC__

tidy_comp_path = spec.get('tidy_comp_path')
tox_path = spec.get('tox_path') or r'C:/Users/Tolch/Desktop/tox/NetworkTidy.tox'
network_path = str(spec.get('network_path') or '/project1').strip()
action = str(spec.get('action') or 'tidy').lower().strip()
scope = str(spec.get('scope') or 'all').lower().strip()
column_gap = int(spec.get('column_gap') if spec.get('column_gap') is not None else 60)
row_gap = int(spec.get('row_gap') if spec.get('row_gap') is not None else 30)
straighten_wires = bool(spec.get('straighten_wires', True))
grid_loose = bool(spec.get('grid_loose', True))
fit_annotations = bool(spec.get('fit_annotations', True))
animate = bool(spec.get('animate', False))
duration = float(spec.get('animation_duration') or 0.6)
frame_result = bool(spec.get('frame_result', True))

# Localizar o cargar el componente tidy
tidy = None
if tidy_comp_path:
    tidy = op(tidy_comp_path)
if tidy is None:
    tidy = op('/network_tidy')
if tidy is None and hasattr(op, 'network_tidy'):
    tidy = op.network_tidy
if tidy is None:
    candidates = op('/').findChildren(name='*network_tidy*', type=baseCOMP)
    if candidates:
        tidy = candidates[0]
if tidy is None and tox_path:
    if os.path.exists(tox_path):
        loaded = op('/').loadTox(tox_path)
        if loaded:
            loaded.name = 'network_tidy'
            tidy = loaded

if tidy is None or not hasattr(tidy.ext, 'TidyExt'):
    print('<<JSON>>' + json.dumps({
        'ok': False,
        'error': f"NetworkTidy COMP no encontrado en el proyecto y no se pudo cargar desde: {tox_path}",
    }))
else:
    # Contenedor objetivo
    net = op(network_path)
    if net is None and network_path == '/project1':
        net = op('/')
        network_path = '/'

    if net is None:
        print('<<JSON>>' + json.dumps({
            'ok': False,
            'error': f"Contenedor '{network_path}' no existe en TouchDesigner.",
        }))
    else:
        # Configurar parámetros en NetworkTidy
        tidy.par.Network = net
        if hasattr(tidy.par, 'Scope'):
            tidy.par.Scope = scope
        if hasattr(tidy.par, 'Gapx'):
            tidy.par.Gapx = column_gap
        if hasattr(tidy.par, 'Gapy'):
            tidy.par.Gapy = row_gap
        if hasattr(tidy.par, 'Straighten'):
            tidy.par.Straighten = straighten_wires
        if hasattr(tidy.par, 'Gridloose'):
            tidy.par.Gridloose = grid_loose
        if hasattr(tidy.par, 'Annotations'):
            tidy.par.Annotations = fit_annotations
        if hasattr(tidy.par, 'Animate'):
            tidy.par.Animate = animate
        if hasattr(tidy.par, 'Duration'):
            tidy.par.Duration = duration
        if hasattr(tidy.par, 'Frame'):
            tidy.par.Frame = frame_result

        before_pos = {o.name: [round(o.nodeX), round(o.nodeY)] for o in net.children if o != tidy}

        if action == 'undo':
            had_moves = bool(getattr(tidy.ext.TidyExt, 'lastMoves', {}))
            tidy.ext.TidyExt.Undo()
            status_msg = str(tidy.par.Status.eval()) if hasattr(tidy.par, 'Status') else 'Undo ejecutado'
            after_pos = {o.name: [round(o.nodeX), round(o.nodeY)] for o in net.children if o != tidy}
            moved = [name for name, pos in after_pos.items() if before_pos.get(name) != pos]
            print('<<JSON>>' + json.dumps({
                'ok': True,
                'action': 'undo',
                'network_path': net.path,
                'tidy_comp': tidy.path,
                'status': status_msg,
                'had_moves_to_undo': had_moves,
                'nodes_total': len(after_pos),
                'restored_nodes_count': len(moved),
                'restored_nodes': moved,
                'positions': after_pos,
                'can_undo': bool(getattr(tidy.ext.TidyExt, 'lastMoves', {})),
            }))
        else:
            tidy.ext.TidyExt.Tidy()
            status_msg = str(tidy.par.Status.eval()) if hasattr(tidy.par, 'Status') else 'Tidy ejecutado'
            after_pos = {o.name: [round(o.nodeX), round(o.nodeY)] for o in net.children if o != tidy}
            moved = [name for name, pos in after_pos.items() if before_pos.get(name) != pos]
            print('<<JSON>>' + json.dumps({
                'ok': True,
                'action': 'tidy',
                'network_path': net.path,
                'tidy_comp': tidy.path,
                'status': status_msg,
                'nodes_total': len(after_pos),
                'moved_count': len(moved),
                'moved_nodes': moved,
                'positions': after_pos,
                'before_positions': before_pos,
                'can_undo': bool(getattr(tidy.ext.TidyExt, 'lastMoves', {})),
                'settings': {
                    'scope': scope,
                    'column_gap': column_gap,
                    'row_gap': row_gap,
                    'straighten_wires': straighten_wires,
                    'grid_loose': grid_loose,
                    'fit_annotations': fit_annotations,
                    'animate': animate,
                    'duration': duration,
                    'frame_result': frame_result,
                }
            }))
'''


def t_network_tidy(a: dict) -> dict:
    """Ordena y embellece redes de TouchDesigner usando la extensión NetworkTidy (layout izquierda-a-derecha por flujo de datos, columnas alineadas, desenredo de cables cruzados, grilla de nodos sueltos, adaptación de annotations y docked ops). Soporta acciones 'tidy' y 'undo', scope 'all' o 'selected', y carga automática desde disco si no está en la red."""
    spec = {
        "network_path": str(a.get("network_path") or "/project1").strip(),
        "action": str(a.get("action") or "tidy").strip().lower(),
        "scope": str(a.get("scope") or "all").strip().lower(),
        "column_gap": int(a.get("column_gap") if a.get("column_gap") is not None else 60),
        "row_gap": int(a.get("row_gap") if a.get("row_gap") is not None else 30),
        "straighten_wires": False if str(a.get("straighten_wires") or "").lower() in ("0", "false", "no") else True,
        "grid_loose": False if str(a.get("grid_loose") or "").lower() in ("0", "false", "no") else True,
        "fit_annotations": False if str(a.get("fit_annotations") or "").lower() in ("0", "false", "no") else True,
        "animate": True if str(a.get("animate") or "").lower() in ("1", "true", "yes") else False,
        "animation_duration": float(a.get("animation_duration") or 0.6),
        "frame_result": False if str(a.get("frame_result") or "").lower() in ("0", "false", "no") else True,
        "tidy_comp_path": a.get("tidy_comp_path"),
        "tox_path": a.get("tox_path") or r"C:/Users/Tolch/Desktop/tox/NetworkTidy.tox",
    }
    code = _NETWORK_TIDY.replace("__SPEC__", repr(spec))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or TIMEOUT))
    return res


# ── Pilar 26: PathTracer 3.0.1 (Josef Pelz PT_FAM) Builder ──────────────────

_SETUP_PATHTRACER3 = r'''
import json, os, re
spec = __SPEC__
root = op(spec['parent_path'])
if not root:
    print('<<JSON>>' + json.dumps({'ok': False, 'error': 'Contenedor no encontrado: ' + spec['parent_path']}))
else:
    fam = root.op('PT_FAM') or op('/project1/PT_FAM')
    if fam is None:
        tox_path = spec.get('tox_path') or 'C:/Users/Tolch/Documents/AI_Code/PachTracer_POPs/PT_FAM_32460_patched.tox'
        if os.path.exists(tox_path):
            fam = root.loadTox(tox_path)
            fam.name = 'PT_FAM'
    if fam is None:
        print('<<JSON>>' + json.dumps({'ok': False, 'error': 'PT_FAM no encontrado en la red ni en tox_path'}))
    else:
        def _fix_geo(g):
            if g is None:
                return
            was_ck = g.allowCooking
            g.allowCooking = True
            tri, hf, xf = g.op('tri'), g.op('has_faces'), g.op('xf')
            if tri is not None and tri.OPType == 'baseCOMP':
                pos = (tri.nodeX, tri.nodeY)
                tri.destroy()
                tri = g.create(triangulatePOP, 'tri')
                tri.nodeX, tri.nodeY = pos
            if tri is not None and tri.OPType == 'triangulatePOP':
                tri.par.triangulatequads = True
                if hf and (not tri.inputConnectors[0].connections or tri.inputConnectors[0].connections[0].owner != hf):
                    hf.outputConnectors[0].connect(tri.inputConnectors[0])
                if xf and (not xf.inputConnectors[0].connections or xf.inputConnectors[0].connections[0].owner != tri):
                    tri.outputConnectors[0].connect(xf.inputConnectors[0])
            for c in g.children:
                for p in c.pars():
                    if p.mode == ParMode.EXPRESSION and ('primType=' in p.expr or 'lineStrips=True' in p.expr) and 'max(op(' not in p.expr:
                        e = re.sub(r"(op\('src'\)\.numPrims\(max=True,\s*primType='[^']+'\))", r"max(\1, 0)", p.expr)
                        e = re.sub(r"(op\('src'\)\.numVerts\(max=True,\s*lineStrips=True\))", r"max(\1, 0)", e)
                        p.expr = e
            g.allowCooking = was_ck

        def _enable_cooking_recursive(comp_op):
            if comp_op is None:
                return
            comp_op.allowCooking = True
            for c in comp_op.findChildren(type=COMP):
                c.allowCooking = True

        def _fix_pt(pt_comp):
            if pt_comp is None:
                return
            _enable_cooking_recursive(pt_comp)
            _fix_geo(pt_comp.op('scene/td_geo'))
            if pt_comp.op('scene') is not None:
                pt_comp.op('scene').par.Software = 1
            sc = pt_comp.op('py/scene')
            if sc is not None and "any(src.numPrims(max=True, primType=t) for t in types)" in sc.text:
                sc.text = sc.text.replace(
                    "any(src.numPrims(max=True, primType=t) for t in types)",
                    "any((src.cook() or src).numPrims(max=True, primType=t) > 0 for t in types)"
                )

        _fix_geo(fam.op('PT_OPs/PT_GEO'))
        _fix_geo(fam.op('PT_OPs/PT_LIGHT/mesh'))
        _fix_pt(fam.op('PT_OPs/Pathtracer'))

        m_pt = fam.op('PT_OPs/Pathtracer')
        m_geo = fam.op('PT_OPs/PT_GEO')
        m_mat = fam.op('PT_OPs/PT_MAT')
        m_light = fam.op('PT_OPs/PT_LIGHT')

        pt = root.op('Pathtracer1') or root.copy(m_pt, name='Pathtracer1')
        pt.allowCooking = True
        _fix_pt(pt)
        pt.par.Optimizedfor = ''
        pt.par.Panelresolution = False
        pt.par.Resolutionw = spec['width']
        pt.par.Resolutionh = spec['height']
        pt.par.Method = spec['denoise_method']
        pt.par.Quality = spec['dlss_quality']
        pt.par.Samples = spec['samples']
        pt.par.Bounces = spec['bounces']
        pt.par.Glassshadows = spec['glass_shadows']
        pt.par.Hazedensity = spec['haze_density']

        cam = root.op('cam1') or root.create(cameraCOMP, 'cam1')
        cam.par.tx, cam.par.ty, cam.par.tz = 0.0, 1.45, 4.85
        cam.par.rx, cam.par.ry, cam.par.rz = -7.0, 0.0, 0.0
        pt.par.Camera = 'cam1'

        null_out = root.op('null1') or root.create(nullTOP, 'null1')
        if not null_out.inputConnectors[0].connections:
            pt.outputConnectors[0].connect(null_out.inputConnectors[0])

        # Piso base optimizado (2x2 = 2 triángulos, 45x45 sin línea de corte de horizonte — C23)
        flr = root.op('floor_pop') or root.create(gridPOP, 'floor_pop')
        flr.par.rows, flr.par.cols = 2, 2
        flr.par.sizex, flr.par.sizey = 45.0, 45.0
        g_flr = root.op('pt_geo_floor') or root.copy(m_geo, name='pt_geo_floor')
        g_flr.allowCooking = True
        g_flr.render = True
        g_flr.par.rx = -90.0
        if not g_flr.inputConnectors[0].connections:
            flr.outputConnectors[0].connect(g_flr.inputConnectors[0])
        m_flr = root.op('pt_mat_floor') or root.copy(m_mat, name='pt_mat_floor')
        m_flr.allowCooking = True
        m_flr.par.Basecolorr, m_flr.par.Basecolorg, m_flr.par.Basecolorb = 0.75, 0.75, 0.78
        m_flr.par.Roughness = 0.6
        g_flr.par.Material = m_flr

        created_comps = [g_flr, m_flr]
        preset = spec.get('preset', 'studio')

        if 'vortex' in preset:
            import math
            # Vórtice 60 FPS de 64 esferas analíticas traslúcidas + humo volumétrico turbulento (C23)
            seed = root.op('pop_vortex_seed') or root.create(gridPOP, 'pop_vortex_seed')
            seed.par.rows, seed.par.cols = 8, 8
            seed.par.surftype = 'points'

            s_dat = root.op('pop_vortex_solver_code') or root.create(textDAT, 'pop_vortex_solver_code')
            s_dat.text = (
                "uniform float uTime;\n"
                "float hash11(uint n){n=(n<<13U)^n;n=n*(n*n*15731U+789221U)+1376312589U;return float(n&uint(0x7fffffffU))/float(0x7fffffff);}\n"
                "vec3 glassPalette(float t){return clamp(vec3(0.58,0.76,0.94)+vec3(0.38,0.28,0.24)*cos(6.2831853*(t+vec3(0.05,0.22,0.52))),0.22,1.0);}\n"
                "void main(){\n"
                "  const uint id=TDIndex(); if(id>=TDNumElements())return;\n"
                "  float t=mod(uTime,3600.0); uint numRings=8U, perRing=8U;\n"
                "  uint ringIdx=id/perRing, slotIdx=id%perRing;\n"
                "  float h1=hash11(id*3U+7U), h2=hash11(id*5U+11U), h3=hash11(id*9U+19U);\n"
                "  float ringNorm=clamp((float(ringIdx)+0.35*(h1-0.5))/float(numRings-1U),0.0,1.0);\n"
                "  float baseY=mix(0.26,2.15,ringNorm);\n"
                "  float baseR=mix(0.48,2.02,pow(ringNorm,0.78))+0.07*(h2-0.5);\n"
                "  float omega=0.65/pow(baseR,0.55);\n"
                "  float theta=(float(slotIdx)/float(perRing))*6.2831853+float(ringIdx)*0.85+0.14*(h3-0.5)+t*omega;\n"
                "  float sp=theta*2.0-ringNorm*5.0;\n"
                "  float r=baseR+0.06*sin(sp), y=baseY+0.045*cos(sp+h1*3.14159);\n"
                "  P[id]=vec3(r*cos(theta),y,r*sin(theta));\n"
                "  PartVel[id]=vec3(-r*sin(theta)*omega,0.0,r*cos(theta)*omega);\n"
                "  PointScale[id]=mix(0.075,0.138,ringNorm)*mix(0.82,1.24,h2);\n"
                "  Color[id]=vec4(glassPalette(fract(ringNorm*0.75+float(slotIdx)/float(perRing)*0.5+0.1*h1)),1.0);\n"
                "  Transmission[id]=mix(0.90,0.99,h1); Roughness[id]=mix(0.015,0.09,pow(h3,2.2)); Emit[id]=0.0;\n"
                "}\n"
            )
            solver = root.op('pop_vortex_solver') or root.create(glslPOP, 'pop_vortex_solver')
            solver.par.dat = s_dat.name
            if not solver.inputConnectors[0].connections:
                seed.outputConnectors[0].connect(solver.inputConnectors[0])
            solver.par.vec0name = 'uTime'
            solver.par.vec0valuex.expr = 'absTime.seconds'
            solver.seq.attr.numBlocks = 6
            for idx, (aname, comps) in enumerate([('PartVel', 3), ('PointScale', 1), ('Color', 4), ('Transmission', 1), ('Roughness', 1), ('Emit', 1)]):
                setattr(solver.par, f'attr{idx}name', 'custom')
                setattr(solver.par, f'attr{idx}customname', aname)
                setattr(solver.par, f'attr{idx}type', 'float')
                setattr(solver.par, f'attr{idx}numcomps', comps)
            solver.par.outputattrs = 'P PartVel PointScale Color Transmission Roughness Emit'

            g_vtx = root.op('pt_geo_vortex_spheres') or root.copy(m_geo, name='pt_geo_vortex_spheres')
            g_vtx.allowCooking = True
            g_vtx.render = True
            g_vtx.par.Velocity = ''
            if not g_vtx.inputConnectors[0].connections:
                solver.outputConnectors[0].connect(g_vtx.inputConnectors[0])
            m_vtx = root.op('pt_mat_translucent_spheres') or root.copy(m_mat, name='pt_mat_translucent_spheres')
            m_vtx.allowCooking = True
            m_vtx.par.Transmission = 0.96
            m_vtx.par.Ior = 1.49
            m_vtx.par.Roughness = 0.03
            m_vtx.par.Dispersion = 0.12
            m_vtx.par.Clearcoat = 0.85
            g_vtx.par.Material = m_vtx

            # Iluminación volumétrica selectiva (C23): Rect fill con Haze=False + Eye Sphere y Gobo Spot con Haze=True
            lt_key = root.op('pt_light_key') or root.copy(m_light, name='pt_light_key')
            lt_key.allowCooking = True
            lt_key.render = True
            lt_key.par.Type = 'Rect'
            lt_key.par.tx, lt_key.par.ty, lt_key.par.tz = -2.2, 3.2, 1.5
            lt_key.par.rx, lt_key.par.ry = -55.0, -32.0
            lt_key.par.Sizew, lt_key.par.Sizeh = 1.8, 1.8
            lt_key.par.Strength = 48.0
            lt_key.par.Haze = False

            lt_eye = root.op('pt_light_vortex_eye') or root.copy(m_light, name='pt_light_vortex_eye')
            lt_eye.allowCooking = True
            lt_eye.render = True
            lt_eye.par.Type = 'Sphere'
            lt_eye.par.tx, lt_eye.par.ty, lt_eye.par.tz = 0.0, 0.45, 0.0
            lt_eye.par.Radius = 0.16
            lt_eye.par.Colorr, lt_eye.par.Colorg, lt_eye.par.Colorb = 0.95, 0.35, 1.0
            lt_eye.par.Strength = 55.0
            lt_eye.par.Haze = True

            gobo = root.op('top_smoke_gobo') or root.create(noiseTOP, 'top_smoke_gobo')
            gobo.par.outputresolution = 'custom'
            gobo.par.resolutionw, gobo.par.resolutionh = 256, 256
            gobo.par.period = 2.2
            gobo.par.amp = 0.55
            gobo.par.offset = 0.5
            gobo.par.tz.expr = '(absTime.seconds % 3600.0) * 0.35'

            lt_spot = root.op('pt_light_smoke_spot') or root.copy(m_light, name='pt_light_smoke_spot')
            lt_spot.allowCooking = True
            lt_spot.render = True
            lt_spot.par.Type = 'Spot'
            lt_spot.par.tx, lt_spot.par.ty, lt_spot.par.tz = 0.0, 3.8, 0.0
            lt_spot.par.rx = -90.0
            lt_spot.par.Coneangle = 48.0
            lt_spot.par.Conedelta = 18.0
            lt_spot.par.Colorr, lt_spot.par.Colorg, lt_spot.par.Colorb = 0.30, 0.85, 1.0
            lt_spot.par.Strength = 165.0
            lt_spot.par.Projectormap = gobo.path
            lt_spot.par.Haze = True

            pt.par.Hazedensity = spec['haze_density'] if spec['haze_density'] > 0 else 0.14
            pt.par.Hazecolorr, pt.par.Hazecolorg, pt.par.Hazecolorb = 0.82, 0.90, 1.0
            pt.par.Hazeanisotropy = 0.68
            pt.par.Hazesamples = 4
            pt.par.Hazevariation = 1.0
            pt.par.Hazescale = 2.6
            pt.par.Hazemultiple = False
            pt.par.Hazedriftx.expr = '0.35 * math.sin((absTime.seconds % 3600.0) * 0.4)'
            pt.par.Hazedrifty.expr = '-0.38 * (absTime.seconds % 3600.0)'
            pt.par.Hazedriftz.expr = '0.35 * math.cos((absTime.seconds % 3600.0) * 0.4)'

            created_comps.extend([g_vtx, m_vtx, lt_key, lt_eye, lt_spot])
        else:
            # Esfera principal
            sph = root.op('sph_pop') or root.create(spherePOP, 'sph_pop')
            sph.par.radx = sph.par.rady = sph.par.radz = 0.5
            g_sph = root.op('pt_geo_sphere') or root.copy(m_geo, name='pt_geo_sphere')
            g_sph.allowCooking = True
            g_sph.render = True
            g_sph.par.ty = 0.5
            if not g_sph.inputConnectors[0].connections:
                sph.outputConnectors[0].connect(g_sph.inputConnectors[0])
            m_sph = root.op('pt_mat_sphere') or root.copy(m_mat, name='pt_mat_sphere')
            m_sph.allowCooking = True
            m_sph.par.Basecolorr, m_sph.par.Basecolorg, m_sph.par.Basecolorb = 0.9, 0.25, 0.15
            m_sph.par.Roughness = 0.18
            m_sph.par.Clearcoat = 1.0
            g_sph.par.Material = m_sph

            # Luz Rect principal
            lt = root.op('pt_light_rect') or root.copy(m_light, name='pt_light_rect')
            lt.allowCooking = True
            lt.render = True
            lt.par.Type = 'Rect'
            lt.par.tx, lt.par.ty, lt.par.tz = 0.0, 3.0, 0.0
            lt.par.rx, lt.par.ry, lt.par.rz = -90.0, 0.0, 0.0
            lt.par.Sizew, lt.par.Sizeh = 1.5, 1.5
            lt.par.Strength = 80.0
            created_comps.extend([g_sph, m_sph, lt])

        for comp_node in created_comps:
            _enable_cooking_recursive(comp_node)
        pt.par.Reset.pulse()
        print('<<JSON>>' + json.dumps({
            'ok': True,
            'preset': preset,
            'pathtracer': pt.path,
            'out_top': pt.op('out1').path,
            'geos': [g.path for g in pt.op('py/scene').module.geos(pt)],
            'lights': [l.path for l in pt.op('py/scene').module.lights(pt)],
            'errors': pt.errors(recurse=True)
        }))
'''


def t_setup_pathtracer3(a: dict) -> dict:
    """Pilar 26 — Monta y verifica desde cero un sistema PathTracer 3.0.1 (Josef Pelz PT_FAM) sobre POPs: carga/parchea automáticamente PT_FAM para compatibilidad 2025.32460 (triangulatePOP + max(numPrims, 0) + LBVH síncrono Software=1), instancia Pathtracer, PT_GEO, PT_MAT y PT_LIGHT con allowCooking=True recursivo, soporta presets 'studio' y 'vortex_haze_60fps' (64 esferas traslúcidas en vórtice + humo volumétrico FBM 3D + Gobo Spot a 60 FPS), espera frames reales y evalúa la imagen."""
    res_str = str(a.get("resolution") or "1280x720").lower().split("x")
    w = int(res_str[0]) if len(res_str) == 2 and res_str[0].isdigit() else 1280
    h = int(res_str[1]) if len(res_str) == 2 and res_str[1].isdigit() else 720
    preset = str(a.get("preset") or "studio").strip().lower()
    is_acc = str(a.get("denoise_method") or "").lower().startswith("acc")
    default_q = "Dlaa" if is_acc else ("Balanced" if "vortex" in preset else "Quality")
    spec = {
        "parent_path": str(a.get("parent_path") or "/project1").strip(),
        "preset": preset,
        "width": w,
        "height": h,
        "denoise_method": "Accumulate" if is_acc else "Dlss",
        "dlss_quality": str(a.get("dlss_quality") or default_q).capitalize(),
        "samples": int(a.get("samples") if a.get("samples") is not None else (1 if not is_acc else 2)),
        "bounces": int(a.get("bounces") if a.get("bounces") is not None else (4 if not is_acc else 8)),
        "glass_shadows": False if str(a.get("glass_shadows") or "").lower() in ("0", "false", "no") else True,
        "haze_density": float(a.get("haze_density") if a.get("haze_density") is not None else (0.14 if "vortex" in preset else 0.0)),
        "tox_path": a.get("tox_path") or "C:/Users/Tolch/Documents/AI_Code/PachTracer_POPs/PT_FAM_32460_patched.tox",
    }
    code = _SETUP_PATHTRACER3.replace("__SPEC__", repr(spec))
    ok, res = exec_code(code, timeout=float(a.get("timeout") or 60))
    if not ok or not res.get("ok"):
        return res
    import time
    time.sleep(0.8)
    eval_res = t_eval_render_frame({"op_path": res["out_top"]})
    res["render_evaluation"] = eval_res
    return res


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
    ("td_glsl_apply", "Pipeline GLSL atómico en vivo: valida estáticamente el código (POP/TOP), crea el textDAT + glslPOP/glslcopyPOP/glslTOP + infoDAT, auto-extrae y configura uniforms (incluyendo '=expr'), Create Attributes / outputattrs / outputaccess, conecta inputs y verifica la compilación con líneas de error.",
     {"name": "string (requerido: nombre del nodo GLSL)", "code": "string (requerido: código GLSL)",
      "parent_path": "string (default /project1)", "family": "pop|top|copy (default pop)",
      "source_path": "string (opcional: input 0)", "extra_inputs": "string (opcional: inputs 1,2… separados por coma)",
      "write_attrs": "string (opcional: ej. 'Color:4, PartVel:3')", "uniforms": "string (opcional: JSON dict de uniforms, soporta '=expr')",
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
    ("td_verify_network", "Verificación integral en 1 llamada (Gauntlet vivo): fuerza 4 pasadas de cook (settle), audita ownership de geometryCOMPs (torus1 borrado, display/render activos, numPoints/numPrims > 0), detecta NaN/Inf en POPs/CHOPs, corre get_op_errors_deep y eval_render_frame, y valida/ordena los nodos por defecto con NetworkTidy (tidy=true), devolviendo veredicto PASS/FAIL con actionable_fixes.",
     {"container_path": "string (default /project1)", "render_top": "string (opcional: ruta del TOP a evaluar visualmente)",
      "check_temporal": "bool (default true)", "tidy": "bool (default true: ejecuta NetworkTidy para ordenar y validar la disposición de los nodos)"}, t_verify_network),
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
    ("td_build_control_panel", "Pilar 11 — Construye un panel UI de control y monitoreo Perform-ready (containerCOMP con cabecera, visor opviewerCOMP conectado al TOP de salida y dock de parameterCOMPs interactivos vinculados a los Custom Parameters de cada operador objetivo).",
     {"target_ops": "string (requerido: ruta o rutas separadas por coma de los COMPs/operadores a controlar)",
      "parent_path": "string (default /project1)", "name": "string (default control_panel)",
      "preview_top": "string (opcional: ruta del TOP a mostrar en el visor)", "title": "string (opcional)",
      "include_builtin": "bool (default false)", "width": "int (default 1280)", "height": "int (default 720)",
      "create_window": "bool (default false: crea también un windowCOMP)"}, t_build_control_panel),
    ("td_render_contact_sheet", "Pilar 12 — Visión temporal multi-frame: avanza la red/simulación durante N muestras espaciadas por step_frames, captura cada frame del TOP objetivo, compone una hoja de contacto PNG (grilla R x C con barra de progreso temporal) y calcula métricas de movimiento inter-frame (ANIMATING / STATIC / BLANK).",
     {"top_path": "string (requerido: ruta del TOP a muestrear)", "out_path": "string (opcional: ruta del PNG de salida)",
      "num_frames": "int (default 6, rango 2..16)", "step_frames": "int (default 4)", "cols": "int (default 3)",
      "tile_width": "int (default 320)", "reset_first": "bool (default false)"}, t_render_contact_sheet),
    ("td_setup_audio_analyzer", "Pilar 13 — Analizador de audio multi-banda llave en mano: construye un baseCOMP con fuente (test_oscillator/file/device/op), filtros por banda (bass, mid, high), envolventes RMS, normalización y lag hacia un nullCHOP maestro (canales bass, mid, high, rms, kick) y vincula bindings opcionales.",
     {"parent_path": "string (default /project1)", "name": "string (default audio_analyzer)",
      "source_type": "test_oscillator|file|device|op (default test_oscillator)", "source_path": "string (opcional: archivo u operador CHOP)",
      "gain": "float (default 1.0)", "lag_attack": "float (default 0.04)", "lag_release": "float (default 0.18)",
      "bindings": "string (opcional: JSON list de bindings {band, target_op, target_par, scale, offset})"}, t_setup_audio_analyzer),
    ("td_setup_scene_switcher", "Pilar 14 — Switcher maestro de escenas con crossfade suave (switchTOP blend=True + filterCHOP) y Smart Cooking automático (chopexecuteDAT que apaga allowCooking en los contenedores de escenas inactivas fuera de la transición).",
     {"scene_paths": "string (requerido: rutas separadas por coma de 2+ escenas COMP o TOP)",
      "parent_path": "string (default /project1)", "name": "string (default scene_switcher)",
      "active_scene": "int (default 0)", "transition_seconds": "float (default 1.0)",
      "smart_cooking": "bool (default true)"}, t_setup_scene_switcher),
    ("td_preset_manager", "Pilar 15 — Gestor e interpolador de presets de estado para cualquier COMP: captura (capture), lista (list), aplica (apply), borra (delete) o interpola linealmente (blend con alpha 0.0..1.0) entre dos presets de Custom Parameters y parámetros de hijos.",
     {"comp_path": "string (requerido: ruta del COMP)", "action": "capture|apply|blend|list|delete (default list)",
      "preset_name": "string (opcional: nombre para capture/apply/delete)",
      "preset_a": "string (opcional: preset inicial para blend)", "preset_b": "string (opcional: preset final para blend)",
      "alpha": "float (default 0.5: factor 0.0..1.0 para blend)", "include_children": "bool (default true)",
      "file_path": "string (opcional: archivo JSON en disco para exportar/importar presets)"}, t_preset_manager),
    ("td_setup_gpu_instancing", "Pilar 16 — Pipeline de Hardware Instancing en GPU: toma un operador fuente (POP/CHOP/TOP/SOP), auto-mapea atributos (P, Color, Scale, N) en las páginas de instancing del geometryCOMP y monta opcionalmente cámara, material y renderTOP.",
     {"instance_source": "string (requerido: ruta del operador con instancias)",
      "parent_path": "string (default /project1)", "name": "string (default instanced_geo)",
      "base_geometry": "box|sphere|grid|torus (default box)", "color_mode": "auto|none (default auto)",
      "scale_mode": "auto|none (default auto)", "orient_mode": "auto|none (default auto)",
      "create_render_pipeline": "bool (default true)"}, t_setup_gpu_instancing),
    ("td_setup_postfx_chain", "Pilar 17 — Rack Modular de Post-Procesado y Mastering (baseCOMP en GPU con Bloom/Glow multicapa, Feedback Trail estelar, Color Grading y Custom Parameters listos para controlar desde UI/audio).",
     {"input_top": "string (requerido: ruta del TOP a procesar)", "parent_path": "string (default /project1)",
      "name": "string (default postfx_rack)"}, t_setup_postfx_chain),
    ("td_setup_io_bridge", "Pilar 18 — Hub Universal de Protocolos e I/O Externo: crea módulos listos para OSC, MIDI, DMX/Art-Net o UDP con generadores de loopback/simulación integrados para probar transmisiones y recepciones en vivo.",
     {"parent_path": "string (default /project1)", "name": "string (default io_hub)",
      "protocol": "osc|midi|dmx|udp (default osc)", "port": "int (default 7000)",
      "target_address": "string (default 127.0.0.1)", "loopback_test": "bool (default true)"}, t_setup_io_bridge),
    ("td_record_movie", "Pilar 19 — Grabador determinista de video/loops y secuencias: avanza paso a paso N frames a FPS constante cocinando al 100%, genera una animación limpia (GIF animado universal con PIL o frames) y verifica el archivo resultante en disco.",
     {"top_path": "string (requerido: ruta del TOP a grabar)", "out_path": "string (opcional: ruta del archivo final)",
      "num_frames": "int (default 24, rango 2..240)", "fps": "float (default 30.0)", "reset_first": "bool (default true)"}, t_record_movie),
    ("td_heal_network", "Pilar 20 — Doctor Autónomo de Redes (Self-Healing): detecta y repara automáticamente fallas estructurales (torus1 residual, flags display/render ausentes, outputresolution='custom' no fijado, cámaras de renderTOP desvinculadas y NaNs en simulaciones).",
     {"container_path": "string (default /project1)", "dry_run": "bool (default false: solo diagnostica si true)"}, t_heal_network),
    ("td_setup_display_canvas", "Pilar 21 — Multi-Display Canvas & Edge Blending: genera canvas multi-pantalla / multi-proyector con cálculo exacto de solapamientos (overlap), crops individuales por proyector, generador de patrones de test y windowCOMP de span opcional.",
     {"parent_path": "string (default /project1)", "name": "string (default display_canvas)",
      "num_displays": "int (default 2, rango 1..8)", "display_width": "int (default 1920)",
      "display_height": "int (default 1080)", "layout": "horizontal|vertical (default horizontal)",
      "overlap_pixels": "int (default 120)", "test_pattern": "bool (default true)",
      "input_top": "string (opcional)", "create_window": "bool (default false)"}, t_setup_display_canvas),
    ("td_setup_pbr_stage", "Pilar 22 — PBR Staging & Environment Lighting: monta un set de iluminación cinematográfica 3D (Key/Fill/Rim lights + environmentlightCOMP con mapa HDRI o procedural), plano de suelo PBR receptor de sombras, material PBR para sujetos, cámara calibrada y renderTOP libre de trampas.",
     {"parent_path": "string (default /project1)", "name": "string (default pbr_stage)",
      "env_map": "string (opcional: ruta a TOP HDRI/sky)", "env_dimmer": "float (default 0.8)",
      "key_dimmer": "float (default 1.0)", "fill_dimmer": "float (default 0.35)", "rim_dimmer": "float (default 0.65)",
      "include_ground": "bool (default true)", "ground_size": "float (default 30.0)", "ground_roughness": "float (default 0.8)",
      "camera_tz": "float (default 4.5)", "resolution": "string (default 1280x720)"}, t_setup_pbr_stage),
    ("td_sync_external_tox", "Pilar 23 — Sincronización y Hot-Reload de Componentes TOX: inspecciona dependencias externas en disco, audita drifts, exporta componentes a .tox de forma atómica y ejecuta Hot-Reload en memoria sin perder Custom Parameters.",
     {"comp_path": "string (default /project1)", "action": "inspect|export|reload|bind (default inspect)",
      "tox_path": "string (opcional)", "recurse": "bool (default true)", "bind_external": "bool (default true)"}, t_sync_external_tox),
    ("td_setup_ai_stream", "Pilar 24 — Conector Streaming GenAI & ComfyUI: arquitectura puente llave en mano para IA generativa en tiempo real (webclientDAT/websocketDAT, cola de prompts tableDAT, métricas de latencia CHOP, Custom Parameters y texture outTOP).",
     {"parent_path": "string (default /project1)", "name": "string (default ai_bridge)",
      "backend": "comfyui|websocket|rest (default comfyui)", "server_url": "string (default http://127.0.0.1:8188)",
      "input_top": "string (opcional)", "default_prompt": "string (opcional)", "negative_prompt": "string (opcional)"}, t_setup_ai_stream),
    ("td_benchmark_longevity", "Pilar 25 — Longevity & 24/7 Resilience Benchmark: auditoría de estabilidad para instalaciones desatendidas; muestrea deltas de memoria VRAM GPU y CPU a lo largo del tiempo, audita nodos con riesgo de acumulación ilimitada y emite veredicto EXHIBITION_READY vs MEMORY_LEAK_RISK.",
     {"container_path": "string (default /project1)", "duration_frames": "int (default 60, rango 10..300)",
      "audit_buffers": "bool (default true)", "sample_interval": "int (default 10)"}, t_benchmark_longevity),
    ("td_network_tidy", "Ordena y embellece redes de TouchDesigner usando la extensión NetworkTidy (layout izquierda-a-derecha por flujo de datos, columnas alineadas, desenredo de cables cruzados, grilla de nodos sueltos, adaptación de annotations y docked ops). Soporta acciones 'tidy' y 'undo', scope 'all' o 'selected', y carga automática desde disco si no está en la red.",
     {"network_path": "string (default /project1: contenedor COMP a ordenar)",
      "action": "tidy|undo (default tidy)",
      "scope": "all|selected (default all)",
      "column_gap": "int (default 60)",
      "row_gap": "int (default 30)",
      "straighten_wires": "bool (default true)",
      "grid_loose": "bool (default true)",
      "fit_annotations": "bool (default true)",
      "animate": "bool (default false: false para ejecución instantánea vía MCP)",
      "animation_duration": "float (default 0.6)",
      "frame_result": "bool (default true)",
      "tidy_comp_path": "string (opcional: ruta a /network_tidy si se renombró)",
      "tox_path": "string (opcional: ruta a NetworkTidy.tox en disco si no está cargado)"}, t_network_tidy),
    ("td_setup_pathtracer3", "Pilar 26 — Monta y verifica desde cero un sistema PathTracer 3.0.1 (Josef Pelz PT_FAM) sobre POPs: carga y parchea automáticamente PT_FAM para compatibilidad 2025.32460 (triangulatePOP + max(numPrims, 0) + LBVH síncrono Software=1), instancia Pathtracer, PT_GEO, PT_MAT y PT_LIGHT con allowCooking=True recursivo, soporta presets 'studio' y 'vortex_haze_60fps' (64 esferas analíticas traslúcidas en vórtice + humo volumétrico FBM 3D + Gobo Spot a 60 FPS), avanza frames reales y evalúa la salida visual.",
     {"parent_path": "string (default /project1)",
      "preset": "studio|vortex_haze_60fps|minimal (default studio)",
      "resolution": "string (default 1280x720)",
      "denoise_method": "Dlss|Accumulate (default Dlss)",
      "dlss_quality": "Dlaa|Quality|Balanced|Performance|Ultraperformance (default Quality o Balanced en vortex)",
      "samples": "int (default 1 en Dlss para 60fps, 2 en Accumulate)",
      "bounces": "int (default 4 en Dlss para 60fps, 8 en Accumulate)",
      "glass_shadows": "bool (default true)",
      "haze_density": "float (default 0.0 en studio, 0.14 en vortex_haze_60fps)",
      "tox_path": "string (opcional: ruta a PT_FAM_32460_patched.tox)"}, t_setup_pathtracer3),
]


LIVE_NAMES = [n for n, _d, _s, _f in LIVE_TOOLS]
# Tools de lectura que no modifican la red de TouchDesigner
LIVE_READONLY = {
    "td_status", "find_in_ops", "tdn_diff", "eval_render_frame", "get_op_errors_deep",
    "td_measure", "td_explore_project", "td_compare_networks", "td_spatial_context",
    "td_verify_network", "td_profile_network", "td_visual_diff", "td_render_contact_sheet", "td_benchmark_longevity",
}



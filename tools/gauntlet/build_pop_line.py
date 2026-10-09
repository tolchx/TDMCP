#!/usr/bin/env python3
"""build_pop_line.py — cobertura POP 1/6 (5d): linePOP.

Red /pop_line: t (linePOP) renderizado directo. Medido (probe_5d_scout + micro-line):
  * default: 2 ctrl pts (0,0,0)->(1,1,0), linear, subdivlines divs=20 -> EXACTO 21 pts /
    1 linestrip; P_i = (i/20, i/20, 0) exacto (err < 1e-6).
  * divs escala exacto: 10 -> 11 pts (divs+1).
  * closed=on con 2 ctrl pts -> 40 pts (2x divs, verbatim) / 1 prim.
  * output='ctrlpoints' -> 2 pts / 1 prim.
  * 3 ctrl pts linear -> 41 = 2*divs+1; P_last = pt2 exacto.
  * cardinal -> mismos 21 pts (el conteo no cambia con el interpolante).
  * render: camara con `lookat` al geometryCOMP y posicion iso (2,2,2) (C17).
"""
from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gauntlet_client import Gauntlet  # noqa: E402
from td_probe import chain_source, png_stats, set_and_verify  # noqa: E402

RUN = os.environ.get("GAUNTLET_RUN_ID") or time.strftime("%Y%m%d-%H%M%S")
g = Gauntlet(phase="build-pop-line", run_id=RUN)
g.init()

ROOT = "/pop_line"
CHAIN = chain_source(ROOT)

report = {"run_id": RUN,
          "objetivo": "linePOP: subdiv de curva por ctrl points, conteos exactos (divs+1), "
                      "closed 2x, ctrlpoints passthrough, 3 ctrl = 2*divs+1, cardinal mismo conteo",
          "ok": False, "cheks": []}


def chek(name, ok, detail=""):
    report["cheks"].append((name, bool(ok)))
    g.check(name, ok, str(detail)[:240])


# ── 0. entorno limpio + estructura ──
g.call("project_info", {}, note="TD vivo")
ok, d = g.exec_code("import json\ntry:\n op(%r).destroy()\nexcept Exception:\n pass\n"
                    "print('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
chek("limpieza previa", ok)

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_line",
                              "nodeX": 4000, "nodeY": 2600, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"}, {"type": "cameraCOMP", "name": "cam"},
    {"type": "renderTOP", "name": "ren"}, {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True}, note="estructura")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 1. linePOP: conteos y geometria exacta ──
ok, d = g.exec_code(CHAIN + """
import json
import time
geo = op(ROOT + '/geo')
for c in list(geo.children):
    if c.name.lower().startswith('torus'):
        c.destroy()
t = geo.create(linePOP, 't')
t.display = False
t.render = False
chk = op(ROOT + '/check')

def cook():
    settle(2)
    t.cook(force=True)
    time.sleep(0.12)
    t.cook(force=True)
    time.sleep(0.06)

def state():
    return dict(pts=t.numPoints(), prims=t.numPrims())

def pvals():
    chk.par.pop = t
    settle(2)
    chk.cook(force=True)
    time.sleep(0.12)
    chk.cook(force=True)
    time.sleep(0.06)
    out = {}
    for nm in ('P_0', 'P_1', 'P_2'):
        out[nm] = list(next(c.vals for c in chk.chans() if c.name == nm))
    return out

cook()
sal = {}
sal['default'] = state()
pv = pvals()
sal['p0'] = [round(v, 6) for v in (pv['P_0'][0], pv['P_1'][0], pv['P_2'][0])]
sal['pmid'] = [round(v, 6) for v in (pv['P_0'][10], pv['P_1'][10], pv['P_2'][10])]
sal['plast'] = [round(v, 6) for v in (pv['P_0'][20], pv['P_1'][20], pv['P_2'][20])]
t.par.divs = 10
cook()
sal['divs10'] = state()
t.par.divs = 20
t.par.closed = True
cook()
sal['closed'] = state()
t.par.closed = False
t.par.output = 'ctrlpoints'
cook()
sal['ctrlpts'] = state()
t.par.output = 'subdivlines'
t.par.interpmethod = 'cardinal'
cook()
sal['cardinal'] = state()
t.par.interpmethod = 'linear'
seq = t.par.pt.sequence
sal['pt_blocks_default'] = seq.numBlocks
seq.numBlocks = 3
t.par.pt2posx = 1.0
t.par.pt2posy = 0.0
t.par.pt2posz = 0.0
cook()
sal['pt3'] = state()
pv3 = pvals()
sal['p3_last'] = [round(v, 6) for v in (pv3['P_0'][40], pv3['P_1'][40], pv3['P_2'][40])]
sal['err'] = t.errors()[:60]
print('<<JSON>>' + json.dumps(sal))
""")
res = d or {}
report["line"] = res
p0, pmid, plast = res.get("p0") or [9]*3, res.get("pmid") or [9]*3, res.get("plast") or [9]*3
p3last = res.get("p3_last") or [9]*3
chek("linePOP default: EXACTO 21 pts / 1 linestrip (divs=20, 2 ctrl pts, linear)",
     ok and (res.get("default") or {}).get("pts") == 21 and (res.get("default") or {}).get("prims") == 1, res)
chek("geometria linear exacta: P_0=(0,0,0), P_10=(0.5,0.5,0), P_20=(1,1,0) err<1e-6",
     ok and all(abs(a - b) < 1e-6 for a, b in zip(p0, (0, 0, 0)))
     and all(abs(a - b) < 1e-6 for a, b in zip(pmid, (0.5, 0.5, 0)))
     and all(abs(a - b) < 1e-6 for a, b in zip(plast, (1, 1, 0))), {"p0": p0, "pmid": pmid, "plast": plast})
chek("divs escala exacto: 10 -> 11 pts (divs+1)",
     ok and (res.get("divs10") or {}).get("pts") == 11 and (res.get("divs10") or {}).get("prims") == 1, res)
chek("closed=on con 2 ctrl pts: 40 pts verbatim (2x divs) / 1 prim",
     ok and (res.get("closed") or {}).get("pts") == 40 and (res.get("closed") or {}).get("prims") == 1, res)
chek("output='ctrlpoints': 2 pts / 1 prim (passthrough de los ctrl points)",
     ok and (res.get("ctrlpts") or {}).get("pts") == 2, res)
chek("cardinal: mismos 21 pts (el conteo no depende del interpolante)",
     ok and (res.get("cardinal") or {}).get("pts") == 21, res)
chek("3 ctrl pts linear: EXACTO 41 = 2*divs+1 y P_last = pt2 (1,0,0)",
     ok and (res.get("pt3") or {}).get("pts") == 41
     and all(abs(a - b) < 1e-6 for a, b in zip(p3last, (1, 0, 0))), {"pt3": res.get("pt3"), "p3_last": p3last})
chek("sin errores en el op", ok and res.get("err") == "", res)

# ── 2. estado canonico + material + camara + PNG + guardia ──

def call_retry(tool, args, note, tries=4, wait=1.5):
    r = {}
    for i in range(tries):
        r = g.call(tool, args, note)
        if not g.is_err(r):
            return r
        time.sleep(wait)
    g.fail("fallo la tool %s (%s) tras %d intentos" % (tool, note, tries))
    return r


time.sleep(1.5)
g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "pointspriteMAT", "name": "mat"},
          note="material")
bad, got = set_and_verify(g, ROOT + "/geo/mat", {"pointsize": 5.0, "colorr": 0.2, "colorg": 0.8, "colorb": 1.0},
                          "material celeste", call=call_retry)
chek("pars del material aplicados (C4)", not bad, got)
ok, d = g.exec_code(CHAIN + """
import json
import time
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
t = op(ROOT + '/geo/t')
t.par.interpmethod = 'linear'
t.display = True
t.render = True
t.cook(force=True)
geo.par.material = geo.op('mat')
cam.par.lookat = geo
cam.par.tx, cam.par.ty, cam.par.tz = 2.0, 2.0, 2.0
ren.par.geometry = geo
ren.par.camera = cam
settle(3)
print('<<JSON>>' + json.dumps(dict(mat=str(geo.par.material.eval()),
                                   lookat=str(cam.par.lookat.eval()), n=t.numPoints())))
""")
d = d or {}
chek("estado canonico: material + camara lookat=geo iso(2,2,2) + terminal renderizando",
     ok and "mat" in str(d.get("mat", "")) and "geo" in str(d.get("lookat", "")) and d.get("n") == 41, d)
g.call_retry = call_retry
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_line.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

ok, d = g.exec_code(CHAIN + """
import json
import time
t = op(ROOT + '/geo/t')
settle(3)
time.sleep(1.0)
antes = px()
print('<<JSON>>' + json.dumps(dict(px_antes=antes, guardia=list(render_is_ours(t)))))
""")
d = d or {}
guardia = d.get("guardia") or []
chek("el render subio la geometria (px > 0 antes de la guardia)", (d.get("px_antes") or 0) > 0,
     {"px": d.get("px_antes")})
chek("los px son del line chain (guardia: apagar el terminal -> 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-line-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_line ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| fallos:", g.failures)
print("line:", json.dumps(report.get("line", {}), ensure_ascii=False))
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

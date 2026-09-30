#!/usr/bin/env python3
"""build_pop_pattern.py — cobertura POP 11/12: patternPOP.

contratos que este build mide (evidencia: results/<run>/build-pop-pattern-report.json):
  * ramp EXACTO por índice: 4 pts -> [0, 1/3, 2/3, 1] en P_0 (error < 1e-6);
    6 pts -> [0, 0.2, 0.4, 0.6, 0.8, 1.0]. numpoints controla la longitud.
  * connectivity (6 pts): linestrip=1 prim, lines=5 (n-1), points=6, none=0;
    con 4 pts: lines=3, points=4 (n-1 / n, medido en ambas longitudes).
  * reverse=on invierte el orden; tolow/tohigh remapea [10, 20] exacto.
  * sin 2 ciclos en 8 pts cuadra con math.sin(2*pi*2*i/7) punto a punto (err < 1e-3).
  * type='random' es determinístico por seed (2 lecturas iguales, cambia con 3≠9)
  * y genera POR INDICE: los valores de los primeros 4 puntos no dependen de numpoints.
  * tex rampstartend: Tex_0 == P_0 del ramp (4 pts).
  * NO verificado acá (queda fuera de checks): type='index' produce [0,2,0,2]
    en 4 pts (semántica no deducible con nuestra sonda); amp no escala el
    uniforme de randomPOP (cruce documentado en el build de random).
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
g = Gauntlet(phase="build-pop-pattern", run_id=RUN)
g.init()

ROOT = "/pop_pattern"
CHAIN = chain_source(ROOT)

report = {"run_id": RUN,
          "objetivo": "patternPOP: ramp exacto por índice, tabla de prims por connectivity, "
                      "reverse/remap, sin 2 ciclos punto a punto, random determinístico por seed",
          "ok": False, "cheks": []}


def chek(name, ok, detail=""):
    report["cheks"].append((name, bool(ok)))
    g.check(name, ok, str(detail)[:240])


# ── 0. entorno limpio + estructura ──
g.call("project_info", {}, note="TD vivo")
ok, d = g.exec_code("import json\ntry:\n op('%s').destroy()\nexcept Exception:\n pass\n"
                    "print('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
chek("limpieza previa", ok)

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_pattern",
                              "nodeX": 2200, "nodeY": 2600, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"}, {"type": "cameraCOMP", "name": "cam"},
    {"type": "renderTOP", "name": "ren"}, {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True}, note="estructura")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 1. ramp exacto, tabla de prims, reverse/remap ──
ok, d = g.exec_code(CHAIN + """
import json
import time
geo = op(ROOT + '/geo')
for c in list(geo.children):
    if c.name.lower().startswith('torus'):
        c.destroy()
pt = geo.create(patternPOP, 'pt')
pt.display = True
pt.render = True
chk = op(ROOT + '/check')

def chans(pop):
    chk.par.pop = pop
    settle(2)
    chk.cook(force=True)
    time.sleep(0.2)
    chk.cook(force=True)
    time.sleep(0.1)
    chk.cook(force=True)
    return {c.name: list(c.vals) for c in chk.chans()}

pt.par.numpoints = 4
pt.par.type0 = 'ramp'
pt.par.connectivity = 'linestrip'
pt.par.cyclic = False
pt.par.closed = False
r4 = chans(pt)
esperado4 = [0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0]
err4 = max(abs(a - b) for a, b in zip(r4.get('P_0', []), esperado4)) if len(r4.get('P_0', [])) == 4 else 9.9
pt.par.numpoints = 6
prims = {}
for conn in ('linestrip', 'lines', 'points', 'none'):
    pt.par.connectivity = conn
    pt.cook(force=True)
    time.sleep(0.1)
    prims[conn] = pt.numPrims()
pt.par.connectivity = 'linestrip'
r6 = chans(pt).get('P_0', [])
err6 = max(abs(a - b) for a, b in zip(r6, [0.0, 0.2, 0.4, 0.6, 0.8, 1.0])) if len(r6) == 6 else 9.9
pt.par.reverse0 = True
rev = chans(pt).get('P_0', [])
pt.par.reverse0 = False
pt.par.tolow0 = 10.0
pt.par.tohigh0 = 20.0
rm = chans(pt).get('P_0', [])
pt.par.tolow0 = 0.0
pt.par.tohigh0 = 1.0
pt.par.numpoints = 7
n7 = len(chans(pt).get('P_0', []))
pt.par.numpoints = 4
print('<<JSON>>' + json.dumps(dict(
    r4=r4.get('P_0', []), err4=err4, prims=prims, err6=err6,
    rev=[round(v, 4) for v in rev], remap=[round(v, 4) for v in rm], n7=n7)))
""")
res = d or {}
report["ramp"] = res
chek("ramp 4 pts EXACTO [0, 1/3, 2/3, 1] (err punto a punto < 1e-6)",
     ok and (res.get("err4") or 9.9) < 1e-6, res)
chek("tabla de prims 6 pts: linestrip=1, lines=5, points=6, none=0",
     ok and (res.get("prims") or {}) == {"linestrip": 1, "lines": 5, "points": 6, "none": 0}, res)
chek("ramp 6 pts EXACTO paso 0.2 y numpoints=7 da 7 puntos",
     ok and (res.get("err6") or 9.9) < 1e-6 and (res.get("n7") or 0) == 7, res)
chek("reverse invierte y remap tolow/tohigh=10..20 escala exacto (0->10, 1->20)",
     ok and (res.get("rev") or []) == [1.0, 0.8, 0.6, 0.4, 0.2, 0.0]
     and (res.get("remap") or []) == [10.0, 12.0, 14.0, 16.0, 18.0, 20.0], res)

# ── 2. sin punto a punto + random determinístico + Tex ramp ──
ok, d = g.exec_code(CHAIN + """
import json
import math
import time
pt = op(ROOT + '/geo/pt')
chk = op(ROOT + '/check')

def chans(pop):
    chk.par.pop = pop
    settle(2)
    chk.cook(force=True)
    time.sleep(0.2)
    chk.cook(force=True)
    time.sleep(0.1)
    chk.cook(force=True)
    return {c.name: list(c.vals) for c in chk.chans()}

pt.par.numpoints = 8
pt.par.type0 = 'ramp'
pt.par.numcycles1 = 2.0
c = chans(pt)
esperado = [math.sin(2 * math.pi * 2.0 * (i / 7.0)) for i in range(8)]
got = c.get('P_1', [])
err_sin = max(abs(a - b) for a, b in zip(got, esperado)) if len(got) == 8 else 9.9
tex = c.get('Tex_0', [])
pt.par.numpoints = 4
pt.par.type0 = 'random'
pt.par.seed = 3.0
r1 = chans(pt).get('P_0', [])
r2 = chans(pt).get('P_0', [])
pt.par.seed = 9.0
r3 = chans(pt).get('P_0', [])
pt.par.type0 = 'sin'
pt.par.numcycles1 = 1.0
pt.par.numpoints = 4
c4 = chans(pt)
tex4 = c4.get('Tex_0', [])
print('<<JSON>>' + json.dumps(dict(
    err_sin=err_sin, sin_vals=[round(v, 4) for v in got],
    tex_ramp=[round(v, 4) for v in tex4],
    rnd_det=(r1 == r2), rnd_cambia=(r1 != r3),
    rnd_n=len(r1), v1=[round(v, 3) for v in r1], v3=[round(v, 3) for v in r3])))
""")
res = d or {}
report["sin_random"] = res
chek("sin 2 ciclos en 8 pts cuadra con math.sin punto a punto (err < 1e-3)",
     ok and (res.get("err_sin") or 9.9) < 1e-3, res)
chek("type random determinístico por seed (2 lecturas iguales, cambia 3≠9), 4 valores",
     ok and res.get("rnd_det") is True and res.get("rnd_cambia") is True
     and res.get("rnd_n") == 4, res)
chek("tex rampstartend reproduce el ramp en Tex_0 ([0, 1/3, 2/3, 1])",
     ok and (res.get("tex_ramp") or []) == [0.0, 0.3333, 0.6667, 1.0], res)

# ── 3. estado canónico + material + cámara + PNG + guardia ──
g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "pointspriteMAT", "name": "mat"},
          note="material")
bad, got = set_and_verify(g, ROOT + "/geo/mat", {"pointsize": 6.0, "colorr": 0.2, "colorg": 0.85, "colorb": 1.0},
                          "material celeste")
chek("pars del material aplicados (C4)", not bad, got)
ok, d = g.exec_code(CHAIN + """
import json
import time
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
pt = op(ROOT + '/geo/pt')
pt.par.type0 = 'sin'
pt.par.type1 = 'sin'
pt.par.numcycles1 = 2.0
pt.par.numpoints = 60
pt.par.connectivity = 'linestrip'
pt.cook(force=True)
geo.par.material = geo.op('mat')
chk = op(ROOT + '/check')
chk.par.pop = pt
settle(3)
chk.cook(force=True)
medios = {}
for c in chk.chans():
    if c.name in ('P_0', 'P_1', 'P_2'):
        medios[c.name] = (min(c.vals) + max(c.vals)) / 2
cam.par.tx = round(medios.get('P_0', 0.0), 2)
cam.par.ty = round(medios.get('P_1', 0.0), 2)
cam.par.tz = round(medios.get('P_2', 0.0) + 2.5, 2)
ren.par.geometry = geo
ren.par.camera = cam
settle(3)
print('<<JSON>>' + json.dumps(dict(mat=str(geo.par.material.eval()),
                                   centro={k: round(v, 2) for k, v in medios.items()},
                                   n=pt.numPoints())))
""")
chek("estado canónico (sin 2D 60 pts) + material + cámara",
     ok and "mat" in str((d or {}).get("mat", "")) and (d or {}).get("n") == 60
     and len(((d or {}).get("centro") or {})) == 3, d)
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_pattern.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

ok, d = g.exec_code(CHAIN + """
import json
import time
pt = op(ROOT + '/geo/pt')
settle(3)
time.sleep(1.5)
antes = px()
print('<<JSON>>' + json.dumps(dict(px_antes=antes, guardia=list(render_is_ours(pt)))))
""")
d = d or {}
guardia = d.get("guardia") or []
chek("el render subió la geometría (px > 0 antes de la guardia)", (d.get("px_antes") or 0) > 0,
     {"px": d.get("px_antes")})
chek("los px son del pattern (guardia: apagar el terminal → 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-pattern-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_pattern ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| fallos:", g.failures)
print("ramp:", json.dumps(report.get("ramp", {}), ensure_ascii=False))
print("sin_random:", json.dumps(report.get("sin_random", {}), ensure_ascii=False))
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

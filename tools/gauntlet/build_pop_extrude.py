#!/usr/bin/env python3
"""build_pop_extrude.py — cobertura POP 10/12: extrudePOP.

contratos que este build mide (evidencia: results/<run>/build-pop-extrude-report.json):
  * LA JAULA SE CREA SIEMPRE: grid 3x3 (9 pts, 4 quads) -> 25 pts / 20 prims
    INCLUSO con distance=0; grid 4x4 (16/9) -> 52/45. Los 20 prims de 3x3 son
    8 caras copiadas + 12 quads laterales.
  * distance ESCALA la altura de la jaula: rango P_2 = [0, distance] con axis z
    (medido 1.0 -> [0,1], 2.0 -> [0,2]) y la base queda en P_2=0.
  * axis='y' mueve el rango al eje elegido (P_1 = [-0.5, 2.5] con distance 2
    sobre la grilla; P_2 plano en 0).
  * taper=0.5 no cambia el conteo (25/20): solo deforma.
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
g = Gauntlet(phase="build-pop-extrude", run_id=RUN)
g.init()

ROOT = "/pop_extrude"
CHAIN = chain_source(ROOT)

report = {"run_id": RUN,
          "objetivo": "extrudePOP: jaula siempre (9/4 -> 25/20 incluso con d=0; 16/9 -> 52/45), "
                      "P_2 = [0, distance], axis=y mueve el rango, taper no cambia conteo",
          "ok": False, "cheks": []}


def chek(name, ok, detail=""):
    report["cheks"].append((name, bool(ok)))
    g.check(name, ok, str(detail)[:240])


# ── 0. entorno limpio + estructura ──
g.call("project_info", {}, note="TD vivo")
ok, d = g.exec_code("import json\ntry:\n op('%s').destroy()\nexcept Exception:\n pass\n"
                    "print('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
chek("limpieza previa", ok)

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_extrude",
                              "nodeX": 1800, "nodeY": 2600, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"}, {"type": "cameraCOMP", "name": "cam"},
    {"type": "renderTOP", "name": "ren"}, {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True}, note="estructura")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 1. jaula: conteos con d0 y d1 en 3x3, y 4x4 ──
ok, d = g.exec_code(CHAIN + """
import json
import time
geo = op(ROOT + '/geo')
for c in list(geo.children):
    if c.name.lower().startswith('torus'):
        c.destroy()
gr = geo.create(gridPOP, 'gr')
gr.par.cols = 3
gr.par.rows = 3
ex = geo.create(extrudePOP, 'ex')
ex.inputConnectors[0].connect(gr.outputConnectors[0])
ex.display = True
ex.render = True
ex.par.axis = 'z'
ex.par.taper = 0.0
res = {}
ex.par.distance = 0.0
settle(2)
ex.cook(force=True)
time.sleep(0.2)
ex.cook(force=True)
res['d0'] = dict(pts=ex.numPoints(), prims=ex.numPrims())
ex.par.distance = 1.0
settle(2)
ex.cook(force=True)
time.sleep(0.2)
ex.cook(force=True)
res['d1'] = dict(pts=ex.numPoints(), prims=ex.numPrims())
gr4 = geo.create(gridPOP, 'gr4')
gr4.par.cols = 4
gr4.par.rows = 4
ex2 = geo.create(extrudePOP, 'ex2')
ex2.inputConnectors[0].connect(gr4.outputConnectors[0])
ex2.par.axis = 'z'
ex2.par.distance = 1.0
settle(2)
ex2.cook(force=True)
time.sleep(0.2)
ex2.cook(force=True)
res['grid4_d1'] = dict(pts=ex2.numPoints(), prims=ex2.numPrims())
print('<<JSON>>' + json.dumps(res))
""")
res = d or {}
report["jaula"] = res
chek("grid 3x3: la jaula se crea incluso con distance=0 (9/4 -> 25 pts, 20 prims)",
     ok and (res.get("d0") or {}) == {"pts": 25, "prims": 20}, res)
chek("grid 3x3 con d=1 mantiene 25/20 (la jaula existe, la altura cambia)",
     ok and (res.get("d1") or {}) == {"pts": 25, "prims": 20}, res)
chek("grid 4x4 con d=1: 52 pts y 45 prims (escalado del mismo patrón)",
     ok and (res.get("grid4_d1") or {}) == {"pts": 52, "prims": 45}, res)

# ── 2. distance y axis: rango de P medido por canal ──
ok, d = g.exec_code(CHAIN + """
import json
import time
ex = op(ROOT + '/geo/ex')
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

ex.par.axis = 'z'
ex.par.distance = 1.0
ex.par.taper = 0.0
settle(2)
ex.cook(force=True)
time.sleep(0.2)
ex.cook(force=True)
c = chans(ex)
p2 = c.get('P_2', [])
ex.par.distance = 2.0
settle(2)
ex.cook(force=True)
time.sleep(0.2)
ex.cook(force=True)
c2 = chans(ex)
p2b = c2.get('P_2', [])
ex.par.axis = 'y'
settle(2)
ex.cook(force=True)
time.sleep(0.2)
ex.cook(force=True)
c3 = chans(ex)
p1c, p2c = c3.get('P_1', []), c3.get('P_2', [])
ex.par.axis = 'z'
ex.par.distance = 1.0
ex.par.taper = 0.5
settle(2)
ex.cook(force=True)
time.sleep(0.2)
ex.cook(force=True)
res = dict(
    d1=[round(min(p2), 4), round(max(p2), 4)],
    d2=[round(min(p2b), 4), round(max(p2b), 4)],
    axisY_P1=[round(min(p1c), 4), round(max(p1c), 4)],
    axisY_P2=[round(min(p2c), 4), round(max(p2c), 4)],
    taper_pts=ex.numPoints(), taper_prims=ex.numPrims())
print('<<JSON>>' + json.dumps(res))
""")
res = d or {}
report["dist_axis"] = res
chek("axis z: rango P_2 = [0, 1.0] con d=1 y [0, 2.0] con d=2",
     ok and res.get("d1") == [0.0, 1.0] and res.get("d2") == [0.0, 2.0], res)
chek("axis y: el rango se mueve a P_1 ([-0.5, 2.5]) y P_2 queda plano en 0",
     ok and res.get("axisY_P1") == [-0.5, 2.5] and res.get("axisY_P2") == [0.0, 0.0], res)
chek("taper=0.5 mantiene 25 pts y 20 prims (deforma, no agrega)",
     ok and res.get("taper_pts") == 25 and res.get("taper_prims") == 20, res)

# ── 3. estado canónico + material + cámara + PNG + guardia ──
g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "pointspriteMAT", "name": "mat"},
          note="material")
bad, got = set_and_verify(g, ROOT + "/geo/mat", {"pointsize": 3.0, "colorr": 0.95, "colorg": 0.4, "colorb": 0.95},
                          "material violeta")
chek("pars del material aplicados (C4)", not bad, got)
ok, d = g.exec_code(CHAIN + """
import json
import time
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
ex = op(ROOT + '/geo/ex')
ex.par.axis = 'z'
ex.par.distance = 1.0
ex.par.taper = 0.0
ex.cook(force=True)
geo.par.material = geo.op('mat')
chk = op(ROOT + '/check')
chk.par.pop = ex
settle(3)
chk.cook(force=True)
medios = {}
for c in chk.chans():
    if c.name in ('P_0', 'P_1', 'P_2'):
        medios[c.name] = (min(c.vals) + max(c.vals)) / 2
cam.par.tx = round(medios.get('P_0', 0.0), 2)
cam.par.ty = round(medios.get('P_1', 0.0), 2)
cam.par.tz = round(medios.get('P_2', 0.0) + 3.0, 2)
ren.par.geometry = geo
ren.par.camera = cam
settle(3)
print('<<JSON>>' + json.dumps(dict(mat=str(geo.par.material.eval()),
                                   centro={k: round(v, 2) for k, v in medios.items()},
                                   prims=ex.numPrims())))
""")
chek("estado canónico (20 prims) + material + cámara",
     ok and "mat" in str((d or {}).get("mat", "")) and (d or {}).get("prims") == 20
     and len(((d or {}).get("centro") or {})) == 3, d)
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_extrude.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

ok, d = g.exec_code(CHAIN + """
import json
import time
ex = op(ROOT + '/geo/ex')
settle(3)
time.sleep(1.5)
antes = px()
print('<<JSON>>' + json.dumps(dict(px_antes=antes, guardia=list(render_is_ours(ex)))))
""")
d = d or {}
guardia = d.get("guardia") or []
chek("el render subió la geometría (px > 0 antes de la guardia)", (d.get("px_antes") or 0) > 0,
     {"px": d.get("px_antes")})
chek("los px son del extrude (guardia: apagar el terminal → 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-extrude-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_extrude ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| fallos:", g.failures)
print("jaula:", json.dumps(report.get("jaula", {}), ensure_ascii=False))
print("dist_axis:", json.dumps(report.get("dist_axis", {}), ensure_ascii=False))
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

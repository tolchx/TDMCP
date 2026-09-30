#!/usr/bin/env python3
"""build_pop_triangulate.py — cobertura POP 9/12: triangulatePOP.

contratos que este build mide (evidencia: results/<run>/build-pop-triangulate-report.json):
  * grid 4x4 (16 pts, 9 quads) con triangulatequads=off pasa INTACTA (9 quads);
    con on la parte en 18 tris. Los PUNTOS no cambian en ningun caso (16/16).
  * mode='concave' sobre la grilla convexa da el mismo 18 (los quads son convexos).
  * escala sobre superficie curva: toro 800 quads -> 1600 tris con los 800 pts
    intactos (x2 exacto, igual que la grilla).
  * triangulatequads es TOGGLE (default false en el build vivo 2025.32460): sin
    prenderlo, triangulatePOP NO triangula quads.
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
g = Gauntlet(phase="build-pop-triangulate", run_id=RUN)
g.init()

ROOT = "/pop_triangulate"
CHAIN = chain_source(ROOT)

report = {"run_id": RUN,
          "objetivo": "triangulatePOP: toggle triangulatequads (off=pasamanos, on=9->18 en "
                      "grid 4x4 y 800->1600 en toro), puntos intactos, concave==convex en quads convexos",
          "ok": False, "cheks": []}


def chek(name, ok, detail=""):
    report["cheks"].append((name, bool(ok)))
    g.check(name, ok, str(detail)[:240])


# ── 0. entorno limpio + estructura ──
g.call("project_info", {}, note="TD vivo")
ok, d = g.exec_code("import json\ntry:\n op('%s').destroy()\nexcept Exception:\n pass\n"
                    "print('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
chek("limpieza previa", ok)

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_triangulate",
                              "nodeX": 1400, "nodeY": 2600, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"}, {"type": "cameraCOMP", "name": "cam"},
    {"type": "renderTOP", "name": "ren"}, {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True}, note="estructura")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 1. grilla: off intacta, on 9->18, concave igual ──
ok, d = g.exec_code(CHAIN + """
import json
import time
geo = op(ROOT + '/geo')
for c in list(geo.children):
    if c.name.lower().startswith('torus'):
        c.destroy()
gr = geo.create(gridPOP, 'gr')
gr.par.cols = 4
gr.par.rows = 4
tri = geo.create(triangulatePOP, 'tri')
tri.inputConnectors[0].connect(gr.outputConnectors[0])
tri.display = True
tri.render = True
res = {}
tri.par.triangulatequads = False
tri.par.mode = 'convex'
settle(2)
tri.cook(force=True)
time.sleep(0.2)
tri.cook(force=True)
res['tq_off'] = dict(pts=tri.numPoints(), prims=tri.numPrims())
tri.par.triangulatequads = True
settle(2)
tri.cook(force=True)
time.sleep(0.2)
tri.cook(force=True)
res['tq_on'] = dict(pts=tri.numPoints(), prims=tri.numPrims())
tri.par.mode = 'concave'
settle(2)
tri.cook(force=True)
time.sleep(0.2)
tri.cook(force=True)
res['concave'] = dict(pts=tri.numPoints(), prims=tri.numPrims())
res['base'] = dict(pts=gr.numPoints(), prims=gr.numPrims())
print('<<JSON>>' + json.dumps(res))
""")
res = d or {}
report["grid"] = res
chek("tq OFF pasa la grilla intacta (16 pts, 9 quads): el toggle es necesario",
     ok and (res.get("tq_off") or {}) == {"pts": 16, "prims": 9}, res)
chek("tq ON parte en 18 tris con los 16 pts intactos",
     ok and (res.get("tq_on") or {}) == {"pts": 16, "prims": 18}, res)
chek("mode concave sobre quads convexos da el mismo 18",
     ok and (res.get("concave") or {}).get("prims") == 18
     and (res.get("concave") or {}).get("pts") == 16, res)

# ── 2. toro: 800 quads -> 1600 tris, pts intactos ──
ok, d = g.exec_code(CHAIN + """
import json
import time
geo = op(ROOT + '/geo')
toro = geo.create(torusPOP, 'toro')
toro.par.radx = 2.2
toro.par.rady = 2.2
toro.par.scale = 0.55
tri2 = geo.create(triangulatePOP, 'tri2')
tri2.inputConnectors[0].connect(toro.outputConnectors[0])
tri2.par.triangulatequads = True
tri2.par.mode = 'convex'
settle(2)
tri2.cook(force=True)
time.sleep(0.2)
tri2.cook(force=True)
print('<<JSON>>' + json.dumps(dict(pts=tri2.numPoints(), prims=tri2.numPrims(),
                                   base=toro.numPrims())))
""")
res = d or {}
report["toro"] = res
chek("toro: 800 quads -> 1600 tris (x2) con los 800 pts intactos",
     ok and (res.get("pts") or 0) == 800 and (res.get("prims") or 0) == 1600
     and (res.get("base") or 0) == 800, res)

# ── 3. estado canónico + material + cámara + PNG + guardia ──
g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "pointspriteMAT", "name": "mat"},
          note="material")
bad, got = set_and_verify(g, ROOT + "/geo/mat", {"pointsize": 3.0, "colorr": 0.9, "colorg": 0.9, "colorb": 1.0},
                          "material celeste")
chek("pars del material aplicados (C4)", not bad, got)
ok, d = g.exec_code(CHAIN + """
import json
import time
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
tri = op(ROOT + '/geo/tri')
tri.par.triangulatequads = True
tri.par.mode = 'convex'
tri.cook(force=True)
geo.par.material = geo.op('mat')
chk = op(ROOT + '/check')
chk.par.pop = tri
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
                                   prims=tri.numPrims())))
""")
chek("estado canónico (18 tris) + material + cámara",
     ok and "mat" in str((d or {}).get("mat", "")) and (d or {}).get("prims") == 18
     and len(((d or {}).get("centro") or {})) == 3, d)
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_triangulate.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

ok, d = g.exec_code(CHAIN + """
import json
import time
tri = op(ROOT + '/geo/tri')
settle(3)
time.sleep(1.5)
antes = px()
print('<<JSON>>' + json.dumps(dict(px_antes=antes, guardia=list(render_is_ours(tri)))))
""")
d = d or {}
guardia = d.get("guardia") or []
chek("el render subió la geometría (px > 0 antes de la guardia)", (d.get("px_antes") or 0) > 0,
     {"px": d.get("px_antes")})
chek("los px son del triangulate (guardia: apagar el terminal → 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-triangulate-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_triangulate ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| fallos:", g.failures)
print("grid:", json.dumps(report.get("grid", {}), ensure_ascii=False))
print("toro:", json.dumps(report.get("toro", {}), ensure_ascii=False))
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

#!/usr/bin/env python3
"""build_pop_facet.py — cobertura POP 7/12: facetPOP.

contratos que este build mide (evidencia: results/<run>/build-pop-facet-report.json):
  * unique des-duplica: grid 4x4 (16 pts, 9 quads) -> 36 pts y 9 prims intactos;
    toro (800 pts compartidos) -> 3200 pts = 800 quads x 4; los PRIMS nunca cambian.
  * cusp con angle=20 en el toro NO abre puntos (800->800): las normales continuas
    del toro no superan el umbral; con angle=1 SÍ (800->3200). El umbral es
    "menor angulo = mas cortes".
  * conspoints colapsa por distancia: grid 4x4 con dist=0.3 deja 16 pts (el
    espaciado 1/3 ~ 0.333 > 0.3) y con dist=0.5 colapsa TODO a 1 punto;
    prims intactas en ambos (reindexa, no borra).
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
g = Gauntlet(phase="build-pop-facet", run_id=RUN)
g.init()

ROOT = "/pop_facet"
CHAIN = chain_source(ROOT)

report = {"run_id": RUN,
          "objetivo": "facetPOP: unique des-duplica (16->36 grid, 800->3200 toro), cusp "
                      "depende del angulo (20 no corta el toro, 1 si), conspoints colapsa "
                      "por distancia (0.3 deja 16, 0.5 deja 1)",
          "ok": False, "cheks": []}


def chek(name, ok, detail=""):
    report["cheks"].append((name, bool(ok)))
    g.check(name, ok, str(detail)[:240])


def cook2(pop):
    return ("settle(2)\n%s.cook(force=True)\ntime.sleep(0.2)\n%s.cook(force=True)\n"
            % (pop, pop))


# ── 0. entorno limpio + estructura ──
g.call("project_info", {}, note="TD vivo")
ok, d = g.exec_code("import json\ntry:\n op('%s').destroy()\nexcept Exception:\n pass\n"
                    "print('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
chek("limpieza previa", ok)

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_facet",
                              "nodeX": 600, "nodeY": 2600, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"}, {"type": "cameraCOMP", "name": "cam"},
    {"type": "renderTOP", "name": "ren"}, {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True}, note="estructura")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 1. unique sobre grid 4x4 y toro: puntos se abren, prims intactas ──
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
fc = geo.create(facetPOP, 'fc')
fc.inputConnectors[0].connect(gr.outputConnectors[0])
fc.par.operation = 'none'
fc.display = False
fc.render = False
""" + cook2("fc") + """
res = dict(none=dict(pts=fc.numPoints(), prims=fc.numPrims()))
fc.par.operation = 'unique'
""" + cook2("fc") + """
res['unique'] = dict(pts=fc.numPoints(), prims=fc.numPrims())
fc.par.operation = 'none'
toro = geo.create(torusPOP, 'toro')
toro.par.radx = 2.2
toro.par.rady = 2.2
toro.par.scale = 0.55
fc2 = geo.create(facetPOP, 'fc2')
fc2.inputConnectors[0].connect(toro.outputConnectors[0])
fc2.par.operation = 'none'
fc2.display = True
fc2.render = True
""" + cook2("fc2") + """
res['toro_none'] = dict(pts=fc2.numPoints(), prims=fc2.numPrims())
fc2.par.operation = 'unique'
""" + cook2("fc2") + """
res['toro_unique'] = dict(pts=fc2.numPoints(), prims=fc2.numPrims())
fc2.par.operation = 'cusp'
fc2.par.angle = 20.0
""" + cook2("fc2") + """
res['toro_cusp20'] = dict(pts=fc2.numPoints(), prims=fc2.numPrims())
fc2.par.angle = 1.0
""" + cook2("fc2") + """
res['toro_cusp1'] = dict(pts=fc2.numPoints(), prims=fc2.numPrims())
print('<<JSON>>' + json.dumps(res))
""")
res = d or {}
report["unique_cusp"] = res
chek("grid 4x4: unique abre 16 -> 36 puntos con 9 prims intactas",
     ok and (res.get("none") or {}).get("pts") == 16
     and (res.get("unique") or {}).get("pts") == 36
     and (res.get("unique") or {}).get("prims") == 9, res)
chek("toro: unique abre 800 -> 3200 (= 800 quads x 4) con 800 prims intactas",
     ok and (res.get("toro_none") or {}).get("pts") == 800
     and (res.get("toro_unique") or {}).get("pts") == 3200
     and (res.get("toro_unique") or {}).get("prims") == 800, res)
chek("cusp angle=20 NO corta el toro continuo (800 -> 800); angle=1 si (-> 3200)",
     ok and (res.get("toro_cusp20") or {}).get("pts") == 800
     and (res.get("toro_cusp1") or {}).get("pts") == 3200, res)

# ── 2. conspoints: colapso por distancia con prims intactas ──
ok, d = g.exec_code(CHAIN + """
import json
import time
fc = op(ROOT + '/geo/fc')
fc.par.operation = 'conspoints'
""" + cook2("fc") + """
res = {}
fc.par.dist = 0.3
""" + cook2("fc") + """
res['d03'] = dict(pts=fc.numPoints(), prims=fc.numPrims())
fc.par.dist = 0.5
""" + cook2("fc") + """
res['d05'] = dict(pts=fc.numPoints(), prims=fc.numPrims())
fc.par.dist = 0.0001
""" + cook2("fc") + """
res['d1e4'] = dict(pts=fc.numPoints(), prims=fc.numPrims())
print('<<JSON>>' + json.dumps(res))
""")
res = d or {}
report["cons"] = res
chek("conspoints dist=0.3 deja 16 pts (espaciado 1/3 > 0.3) y dist=0.5 colapsa a 1",
     ok and (res.get("d03") or {}).get("pts") == 16
     and (res.get("d05") or {}).get("pts") == 1, res)
chek("conspoints reindexa sin borrar prims (9 quads en los tres umbrales)",
     ok and all((res.get(k) or {}).get("prims") == 9 for k in ("d03", "d05", "d1e4")), res)

# ── 3. estado canónico + material + cámara + PNG + guardia ──
g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "pointspriteMAT", "name": "mat"},
          note="material")
bad, got = set_and_verify(g, ROOT + "/geo/mat", {"pointsize": 3.0, "colorr": 0.3, "colorg": 1.0, "colorb": 0.5},
                          "material verde")
chek("pars del material aplicados (C4)", not bad, got)
ok, d = g.exec_code(CHAIN + """
import json
import time
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
fc2 = op(ROOT + '/geo/fc2')
fc2.par.operation = 'unique'
fc2.par.angle = 20.0
fc2.cook(force=True)
geo.par.material = geo.op('mat')
chk = op(ROOT + '/check')
chk.par.pop = fc2
settle(3)
chk.cook(force=True)
medios = {}
for c in chk.chans():
    if c.name in ('P_0', 'P_1', 'P_2'):
        medios[c.name] = (min(c.vals) + max(c.vals)) / 2
cam.par.tx = round(medios.get('P_0', 0.0), 2)
cam.par.ty = round(medios.get('P_1', 0.0), 2)
cam.par.tz = round(medios.get('P_2', 0.0) + 8.0, 2)
ren.par.geometry = geo
ren.par.camera = cam
settle(3)
print('<<JSON>>' + json.dumps(dict(mat=str(geo.par.material.eval()),
                                   centro={k: round(v, 2) for k, v in medios.items()},
                                   pts=fc2.numPoints())))
""")
chek("estado canónico (unique 3200 pts) + material + cámara",
     ok and "mat" in str((d or {}).get("mat", "")) and (d or {}).get("pts") == 3200
     and len(((d or {}).get("centro") or {})) == 3, d)
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_facet.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

ok, d = g.exec_code(CHAIN + """
import json
import time
fc2 = op(ROOT + '/geo/fc2')
settle(3)
time.sleep(1.5)
antes = px()
print('<<JSON>>' + json.dumps(dict(px_antes=antes, guardia=list(render_is_ours(fc2)))))
""")
d = d or {}
guardia = d.get("guardia") or []
chek("el render subió la geometría (px > 0 antes de la guardia)", (d.get("px_antes") or 0) > 0,
     {"px": d.get("px_antes")})
chek("los px son del facet (guardia: apagar el terminal → 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-facet-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_facet ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| fallos:", g.failures)
print("unique/cusp:", json.dumps(report.get("unique_cusp", {}), ensure_ascii=False))
print("cons:", json.dumps(report.get("cons", {}), ensure_ascii=False))
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

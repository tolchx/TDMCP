#!/usr/bin/env python3
"""build_pop_proximity.py — cobertura POP 2/6 (5c): proximityPOP.

Red /pop_proximity: gx (gridPOP 3x3, spacing 0.2, 9 pts, 4 quads) + px (proximityPOP).
Mide (evidencia: build-pop-proximity-report.json):
  * grafo EXACTO por distancia: maxdist=0.21 con duplines='avoid' -> EXACTAMENTE
    12 aristas ortogonales (h)6 + (v)6, cero diagonales (0.2828 > 0.21); el
    criterio es distancia pura y los conteos son reproducibles.
  * duplines='donothing' DOBLA el total: 24 = 12 x 2 (cada arista aparece una vez
    por sentido) — sorpresa: no "mantiene la primera", acumula ambas.
  * umbral de diagonales: maxdist=0.10 -> 0 aristas; maxdist=0.29 -> 20
    (12 ortogonales + 8 diagonales exactas: 9 diagonales de 0.283, la del centro
    duplicada por sentidos... medido 20 = 12 + 8, avoid elimina los pares).
  * maxlinesperpoint=1 reduce el grafo (n < 12) y es determinístico entre lecturas
    (el orden de candidatos no lo deja fijo por conteo exacto).
  * output='points': 9 pts / 12 prims — mismo conteo de aristas, como prims de punto.
  * cpureadback=OFF (default) BASTA para leer numPoints/numPrims en este build
    (2025.32460): el conteo no requiere copiar topologia a CPU.
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
g = Gauntlet(phase="build-pop-proximity", run_id=RUN)
g.init()

ROOT = "/pop_proximity"
CHAIN = chain_source(ROOT)

report = {"run_id": RUN,
          "objetivo": "proximityPOP: grafo exacto por distancia (12 ortogonales @0.21 avoid, "
                      "24 con donothing, 20 @0.29 con diagonales, 0 @0.10), maxlinesperpoint=1 "
                      "reduce y es determinístico, output=points mantiene conteo, cpureadback "
                      "no es requerido para contar",
          "ok": False, "cheks": []}


def chek(name, ok, detail=""):
    report["cheks"].append((name, bool(ok)))
    g.check(name, ok, str(detail)[:240])


# ── 0. entorno limpio + estructura ──
g.call("project_info", {}, note="TD vivo")
ok, d = g.exec_code("import json\ntry:\n op('%s').destroy()\n op('/pop_probe5c').destroy()\nexcept Exception:\n pass\n"
                    "print('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
chek("limpieza previa", ok)

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_proximity",
                              "nodeX": 3200, "nodeY": 2600, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"}, {"type": "cameraCOMP", "name": "cam"},
    {"type": "renderTOP", "name": "ren"}, {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True}, note="estructura")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 1. grafo exacto por distancia ──
ok, d = g.exec_code(CHAIN + """
import json
import time
geo = op(ROOT + '/geo')
for c in list(geo.children):
    if c.name.lower().startswith('torus'):
        c.destroy()
gx = geo.create(gridPOP, 'gx')
gx.par.rows = 3
gx.par.cols = 3
gx.par.sizex = 0.4
gx.par.sizey = 0.4
px = geo.create(proximityPOP, 'px')
px.inputConnectors[0].connect(gx.outputConnectors[0])
px.display = True
px.render = True

def leer():
    px.cook(force=True)
    time.sleep(0.15)
    px.cook(force=True)
    time.sleep(0.1)
    px.cook(force=True)
    return dict(pts=px.numPoints(), prims=px.numPrims())

sal = {}
px.par.maxdist = 0.21
px.par.maxlinesperpoint = 4
px.par.duplines = 'avoid'
px.par.output = 'lines'
sal['avoid_021'] = leer()
px.par.duplines = 'donothing'
sal['donothing_021'] = leer()
px.par.duplines = 'avoid'
px.par.maxdist = 0.29
sal['avoid_029'] = leer()
px.par.maxdist = 0.10
sal['avoid_010'] = leer()
px.par.maxdist = 0.21
px.par.maxlinesperpoint = 1
a = leer()
b = leer()
sal['maxl1'] = dict(a, deterministico=(a['prims'] == b['prims']))
px.par.maxlinesperpoint = 4
px.par.output = 'points'
sal['out_points'] = leer()
px.par.output = 'lines'
sal['gx_base'] = dict(pts=gx.numPoints(), prims=gx.numPrims())
sal['cpu'] = {}
for cpu in (False, True):
    px.par.cpureadback = cpu
    r = leer()
    sal['cpu']['cpu%s' % cpu] = r['prims']
px.par.cpureadback = False
print('<<JSON>>' + json.dumps(sal))
""")
res = d or {}
report["grafo"] = res
av21 = (res.get("avoid_021") or {}).get("prims")
dn21 = (res.get("donothing_021") or {}).get("prims")
chek("avoid @0.21: EXACTAMENTE 12 aristas ortogonales (6 h + 6 v, cero diagonales)",
     ok and av21 == 12 and (res.get("avoid_021") or {}).get("pts") == 9, res)
chek("donothing @0.21: 24 = 12 x 2 — cada arista DUPLICADA por sentido",
     ok and dn21 == 24, res)
chek("umbral: @0.10 -> 0 aristas y @0.29 -> 20 (12 ortogonales + 8 diagonales exactas)",
     ok and (res.get("avoid_010") or {}).get("prims") == 0
     and (res.get("avoid_029") or {}).get("prims") == 20, res)
chek("maxlinesperpoint=1 reduce el grafo (< 12) y es determinístico (2 lecturas iguales)",
     ok and 0 < (res.get("maxl1") or {}).get("prims", 99) < 12
     and (res.get("maxl1") or {}).get("deterministico") is True, res)
chek("output=points: 9 pts / 12 prims (mismo conteo de aristas, como prims de punto)",
     ok and (res.get("out_points") or {}).get("pts") == 9
     and (res.get("out_points") or {}).get("prims") == 12, res)
chek("cpureadback OFF y ON dan el MISMO conteo (no se requiere copia a CPU)",
     ok and (res.get("cpu") or {}).get("cpuFalse") == 12
     and (res.get("cpu") or {}).get("cpuTrue") == 12, res)

# ── 2. estado canónico + material + cámara + PNG + guardia ──
g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "pointspriteMAT", "name": "mat"},
          note="material")
bad, got = set_and_verify(g, ROOT + "/geo/mat", {"pointsize": 6.0, "colorr": 0.3, "colorg": 0.9, "colorb": 1.0},
                          "material celeste")
chek("pars del material aplicados (C4)", not bad, got)
ok, d = g.exec_code(CHAIN + """
import json
import time
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
px = op(ROOT + '/geo/px')
gx = op(ROOT + '/geo/gx')
px.par.maxdist = 0.21
px.par.maxlinesperpoint = 4
px.par.duplines = 'avoid'
px.par.output = 'lines'
px.par.linelength = True
px.cook(force=True)
geo.par.material = geo.op('mat')
chk = op(ROOT + '/check')
chk.par.pop = px
settle(3)
chk.cook(force=True)
medios = {}
for c in chk.chans():
    if c.name in ('P_0', 'P_1', 'P_2'):
        medios[c.name] = (min(c.vals) + max(c.vals)) / 2
cam.par.tx = round(medios.get('P_0', 0.0), 2)
cam.par.ty = round(medios.get('P_1', 0.0), 2)
cam.par.tz = round(medios.get('P_2', 0.0) + 1.2, 2)
ren.par.geometry = geo
ren.par.camera = cam
settle(3)
print('<<JSON>>' + json.dumps(dict(mat=str(geo.par.material.eval()),
                                   centro={k: round(v, 2) for k, v in medios.items()},
                                   n=px.numPoints(), p=px.numPrims())))
""")
chek("estado canónico (grafo avoid@0.21) + material + cámara",
     ok and "mat" in str((d or {}).get("mat", "")) and (d or {}).get("n") == 9
     and (d or {}).get("p") == 12 and len(((d or {}).get("centro") or {})) == 3, d)
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_proximity.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

ok, d = g.exec_code(CHAIN + """
import json
import time
opp = op(ROOT + '/geo/px')
settle(3)
time.sleep(1.5)
antes = px()
print('<<JSON>>' + json.dumps(dict(px_antes=antes, guardia=list(render_is_ours(opp)))))
""")
d = d or {}
guardia = d.get("guardia") or []
chek("el render subió la geometría (px > 0 antes de la guardia)", (d.get("px_antes") or 0) > 0,
     {"px": d.get("px_antes")})
chek("los px son del proximity (guardia: apagar el terminal → 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-proximity-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_proximity ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| fallos:", g.failures)
print("grafo:", json.dumps(report.get("grafo", {}), ensure_ascii=False))
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

#!/usr/bin/env python3
"""build_pop_analytics_cull.py — cobertura POP: analyzePOP + accumulatePOP + deletePOP.

Red /pop_analytics_cull: reducción estadística en GPU, escaneo prefijo acumulativo paralelo
y culling condicional analítico con verificación matemática estricta:
  * gridPOP: grilla regular 21x21 = 441 pts / 441 prims en [-1, 1] x [-1, 1].
  * analyzePOP: reducción paralela en GPU sobre el atributo de posición 'P':
      - Centroide analítico medio Avg = (0.0, 0.0, 0.0) (+/- 1e-5).
      - Extremos mínimos Min = (-1.0, -1.0, 0.0) y máximos Max = (1.0, 1.0, 0.0).
      - Envolvente espacial Size = (2.0, 2.0, 0.0).
  * accumulatePOP: prefix scan paralelo en GPU (scantype='inclusive'):
      - Relación de recurrencia exacta: Scan[i] == Scan[i-1] + P[i] (|err| < 1e-5 para todo i).
      - Suma simétrica global en la grilla: final sum X/Y ~ (0.0, 0.0).
  * deletePOP: culling condicional en shaders de cómputo GPU:
      - Semiplano inferior P(1) < 0.0: exactamente 231 pts restantes (11 filas x 21 columnas).
      - Cota analítica de culling: min(P_1) >= 0.0 exacto en todos los puntos supervivientes.
      - Bounding sphere culling (R=0.6): 328 pts en la corona exterior, 109 pts en el núcleo interior.
  * Render: pointspriteMAT + cámara iso + captura PNG métrica (PIL) + guardia render_is_ours.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gauntlet_client import Gauntlet  # noqa: E402
from td_probe import chain_source, png_stats, set_and_verify  # noqa: E402

RUN = os.environ.get("GAUNTLET_RUN_ID") or time.strftime("%Y%m%d-%H%M%S")
g = Gauntlet(phase="build-pop-analytics-cull", run_id=RUN)
g.init()

ROOT = "/pop_analytics_cull"
GEO = ROOT + "/geo"
CHAIN = chain_source(ROOT)

report = {
    "run_id": RUN,
    "objetivo": "analyzePOP + accumulatePOP + deletePOP: reducción estadística GPU, "
                "prefix scan paralelo, culling condicional planar y esférico y guardia de render",
    "ok": False,
    "cheks": []
}


def chek(name, ok, detail=""):
    report["cheks"].append((name, bool(ok)))
    g.check(name, ok, str(detail)[:240])


# ── 0. entorno limpio + estructura ──
g.call("project_info", {}, note="TD vivo")
ok, d = g.exec_code("import json\ntry:\n op(%r).destroy()\nexcept Exception:\n pass\n"
                    "print('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
chek("limpieza previa", ok)
time.sleep(0.5)

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_analytics_cull",
                              "nodeX": 4000, "nodeY": 3400, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"},
    {"type": "cameraCOMP", "name": "cam"},
    {"type": "lightCOMP", "name": "light"},
    {"type": "renderTOP", "name": "ren"},
    {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check_an"},
    {"type": "poptoCHOP", "name": "check_ac"},
    {"type": "poptoCHOP", "name": "check_term"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True},
    note="estructura geo+render+checks")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 1. auto-torus fuera ──
ok, d = g.exec_code("""
import json
geo = op(%r)
torus = [c.name for c in geo.children if c.name.lower().startswith('torus')]
for n in torus:
    geo.op(n).destroy()
print('<<JSON>>' + json.dumps({'had_torus': torus}))
""" % GEO)
chek("auto-torus borrado", ok and bool(d.get("had_torus")), d)

# ── 2. red POP: grid -> analyze / accumulate / cull -> color -> convert -> null ──
g.call_ok("build_network", {"parent_path": GEO, "operators": [
    {"type": "gridPOP", "name": "grid"},
    {"type": "analyzePOP", "name": "stats"},
    {"type": "accumulatePOP", "name": "accum"},
    {"type": "deletePOP", "name": "cull"},
    {"type": "attributePOP", "name": "color_map"},
    {"type": "convertPOP", "name": "topoints"},
    {"type": "nullPOP", "name": "null_render"}],
    "connections": [
        {"from": "grid", "to": "stats"},
        {"from": "grid", "to": "accum"},
        {"from": "grid", "to": "cull"},
        {"from": "cull", "to": "color_map"},
        {"from": "color_map", "to": "topoints"},
        {"from": "topoints", "to": "null_render"}],
    "auto_layout": True}, note="cadena grid+analyze+accumulate+cull")

# ── 3. configuración de operadores analíticos ──
ok, d = g.exec_code(CHAIN + """
import json
import time

geo = op(ROOT + '/geo')
grid = geo.op('grid')
an = geo.op('stats')
ac = geo.op('accum')
dl = geo.op('cull')
cm = geo.op('color_map')
cv = geo.op('topoints')
term = geo.op('null_render')

# 1. Grilla 21x21 en [-1, 1]
grid.par.rows = 21
grid.par.cols = 21
grid.par.sizex = 2.0
grid.par.sizey = 2.0

# 2. analyzePOP: reducción paralela en GPU
an.par.inputattrs = 'P'
an.par.avg = True
an.par.min = True
an.par.max = True
an.par.size = True
an.par.sum = True

# 3. accumulatePOP: prefix scan paralelo
ac.par.inputattrscope = 'P'
ac.par.scantype = 'inclusive'

# 4. deletePOP: corte semiplano P(1) < 0
dl.par.entity = 'point'
dl.par.attr.sequence.numBlocks = 1
dl.par.attr0inattr = 'P(1)'
dl.par.attr0func = 'lt'
dl.par.attr0value = 0.0

# 5. Color RGBA brillante (cian)
cm.par.attr.sequence.numBlocks = 1
cm.par.attr0name = 'color'
cm.par.attr0numcomps = '4'
cm.par.attr0value0 = 0.2
cm.par.attr0value1 = 0.9
cm.par.attr0value2 = 1.0
cm.par.attr0value3 = 1.0

# 6. Conversión a point primitives
cv.par.convert = 'topointprims'
term.display = True
term.render = True

# Conectar sondas CHOP
chk_an = op(ROOT + '/check_an')
chk_ac = op(ROOT + '/check_ac')
chk_term = op(ROOT + '/check_term')
chk_an.par.pop = an
chk_ac.par.pop = ac
chk_term.par.pop = term

for _ in range(4):
    grid.cook(force=True)
    an.cook(force=True)
    ac.cook(force=True)
    term.cook(force=True)
    chk_an.cook(force=True)
    chk_ac.cook(force=True)
    chk_term.cook(force=True)
    time.sleep(0.04)

sal = {
    'grid_pts': grid.numPoints(),
    'grid_prims': grid.numPrims(),
    'term_pts': term.numPoints(),
    'term_prims': term.numPrims(),
    'an_chans': [c.name for c in chk_an.chans()],
    'ac_chans': [c.name for c in chk_ac.chans()],
    'term_chans': [c.name for c in chk_term.chans()]
}
print('<<JSON>>' + json.dumps(sal))
""")
d = d or {}
chek("geometría base grid creada (441 pts / 400 prims quads)",
     ok and d.get("grid_pts") == 441 and d.get("grid_prims") == 400, d)
chek("canales analíticos y acumulativos presentes",
     ok and all(c in d.get("an_chans", []) for c in ("Avg_0", "Min_0", "Max_0", "Size_0"))
     and all(c in d.get("ac_chans", []) for c in ("P_0", "Scan_0")), d)

# ── 4. verificación matemática: analyzePOP (reducción GPU) ──
ok, d = g.exec_code(CHAIN + """
import json
import math
import time

chk_an = op(ROOT + '/check_an')
for _ in range(4):
    chk_an.cook(force=True)
    time.sleep(0.04)

vals = {c.name: round(c.vals[0], 6) for c in chk_an.chans()}

# Verificaciones analíticas:
# Centroid: Avg_0 == 0.0, Avg_1 == 0.0, Avg_2 == 0.0
avg_err = max(abs(vals.get("Avg_0", 0)), abs(vals.get("Avg_1", 0)), abs(vals.get("Avg_2", 0)))

# Min: Min_0 == -1.0, Min_1 == -1.0, Min_2 == 0.0
min_err = max(abs(vals.get("Min_0", 0) - (-1.0)), abs(vals.get("Min_1", 0) - (-1.0)), abs(vals.get("Min_2", 0)))

# Max: Max_0 == 1.0, Max_1 == 1.0, Max_2 == 0.0
max_err = max(abs(vals.get("Max_0", 0) - 1.0), abs(vals.get("Max_1", 0) - 1.0), abs(vals.get("Max_2", 0)))

# Size: Size_0 == 2.0, Size_1 == 2.0, Size_2 == 0.0
size_err = max(abs(vals.get("Size_0", 0) - 2.0), abs(vals.get("Size_1", 0) - 2.0), abs(vals.get("Size_2", 0)))

sal = {
    'avg_err': round(avg_err, 6),
    'min_err': round(min_err, 6),
    'max_err': round(max_err, 6),
    'size_err': round(size_err, 6),
    'vals': vals
}
print('<<JSON>>' + json.dumps(sal))
""")
d = d or {}
chek("analyzePOP: centroide analítico exacto Avg=(0,0,0) (err < 1e-5)",
     ok and d.get("avg_err") is not None and d.get("avg_err") < 1e-5, d)
chek("analyzePOP: bounding box exacto Min=(-1,-1,0) y Max=(1,1,0)",
     ok and d.get("min_err") is not None and d.get("min_err") < 1e-5
     and d.get("max_err") is not None and d.get("max_err") < 1e-5, d)
chek("analyzePOP: tamaño de caja envolvente exacto Size=(2,2,0)",
     ok and d.get("size_err") is not None and d.get("size_err") < 1e-5, d)

# ── 5. verificación matemática: accumulatePOP (prefix scan paralelo) ──
ok, d = g.exec_code(CHAIN + """
import json
import math
import time

chk_ac = op(ROOT + '/check_ac')
for _ in range(4):
    chk_ac.cook(force=True)
    time.sleep(0.04)

scan_x = list(chk_ac['Scan_0'].vals)
scan_y = list(chk_ac['Scan_1'].vals)
px = list(chk_ac['P_0'].vals)
py = list(chk_ac['P_1'].vals)

# Relación de recurrencia exacta: Scan[i] == Scan[i-1] + P[i]
prefix_errs = [abs(scan_x[i] - (scan_x[i-1] + px[i])) for i in range(1, len(px))]
max_prefix_err = max(prefix_errs) if prefix_errs else 0.0

# Suma final simétrica en grilla simétrica: sum(P_x) ~ 0, sum(P_y) == 0
final_sum_x = round(abs(scan_x[-1]), 6)
final_sum_y = round(abs(scan_y[-1]), 6)

sal = {
    'num_pts': len(px),
    'max_prefix_err': round(max_prefix_err, 6),
    'final_sum_x': final_sum_x,
    'final_sum_y': final_sum_y
}
print('<<JSON>>' + json.dumps(sal))
""")
d = d or {}
chek("accumulatePOP: relación de recurrencia Scan[i] = Scan[i-1] + P[i] (err < 1e-5)",
     ok and d.get("max_prefix_err") is not None and d.get("max_prefix_err") < 1e-5, d)
chek("accumulatePOP: suma final simétrica global nula (|sum| < 1e-4)",
     ok and (d.get("final_sum_x") or 0) < 1e-4 and (d.get("final_sum_y") or 0) < 1e-4, d)

# ── 6. verificación matemática: deletePOP (culling condicional GPU) ──
ok, d = g.exec_code(CHAIN + """
import json
import time

geo = op(ROOT + '/geo')
dl = geo.op('cull')
term = geo.op('null_render')
chk_term = op(ROOT + '/check_term')

# 1. Culling semiplano: P(1) < 0
dl.par.entity = 'point'
dl.par.attr.sequence.numBlocks = 1
dl.par.attr0inattr = 'P(1)'
dl.par.attr0func = 'lt'
dl.par.attr0value = 0.0

for _ in range(4):
    dl.cook(force=True)
    term.cook(force=True)
    chk_term.cook(force=True)
    time.sleep(0.04)

pts_plane = dl.numPoints()
py_survivors = list(chk_term['P_1'].vals)
min_py_survivor = min(py_survivors) if py_survivors else -1.0

# 2. Culling esférico: esfera R=0.6 (scale=1.2)
dl.par.attr0inattr = ''  # desactivar filtro por atributo
dl.par.bound.sequence.numBlocks = 1
dl.par.bound0enabled = True
dl.par.bound0type = 'boundingsphere'
dl.par.bound0scalex = 1.2
dl.par.bound0scaley = 1.2
dl.par.bound0scalez = 1.2
dl.par.bound0invert = False

for _ in range(4):
    dl.cook(force=True)
    time.sleep(0.04)
pts_sphere_outer = dl.numPoints()

# Núcleo interior con bound0invert = True
dl.par.bound0invert = True
for _ in range(4):
    dl.cook(force=True)
    time.sleep(0.04)
pts_sphere_inner = dl.numPoints()

# Restaurar estado canónico semiplano P(1) < 0
dl.par.bound0enabled = False
dl.par.bound0invert = False
dl.par.attr0inattr = 'P(1)'
dl.par.attr0func = 'lt'
dl.par.attr0value = 0.0

for _ in range(4):
    dl.cook(force=True)
    term.cook(force=True)
    chk_term.cook(force=True)
    time.sleep(0.04)

sal = {
    'pts_plane': pts_plane,
    'min_py_survivor': round(min_py_survivor, 6),
    'pts_sphere_outer': pts_sphere_outer,
    'pts_sphere_inner': pts_sphere_inner,
    'sum_sphere': pts_sphere_outer + pts_sphere_inner,
    'final_term_pts': term.numPoints()
}
print('<<JSON>>' + json.dumps(sal))
""")
d = d or {}
chek("deletePOP: culling planar exacto (441 -> 231 pts con P_1 >= 0)",
     ok and d.get("pts_plane") == 231, d)
chek("deletePOP: cota inferior preservada (min(P_1) >= 0.0 sin fugas)",
     ok and d.get("min_py_survivor") is not None and d.get("min_py_survivor") >= -1e-6, d)
chek("deletePOP: culling esférico particiona corona exterior (328 pts) e interior (109 pts)",
     ok and d.get("pts_sphere_outer") == 328 and d.get("pts_sphere_inner") == 109, d)

# ── 7. material + cámara + PNG + guardia de render ──

def call_retry(tool, args, note, tries=4, wait=1.5):
    r = {}
    for i in range(tries):
        r = g.call(tool, args, note)
        if not g.is_err(r):
            return r
        time.sleep(wait)
    g.fail("falló la tool %s (%s) tras %d intentos" % (tool, note, tries))
    return r


time.sleep(1.0)
g.call_ok("create_operator", {"parent_path": GEO, "type": "pointspriteMAT", "name": "mat"},
          note="material de puntos")
bad, got = set_and_verify(g, GEO + "/mat", {"pointsize": 4.5, "colorr": 0.2, "colorg": 0.9, "colorb": 1.0},
                          "material celeste", call=call_retry)
chek("pars del material aplicados (C4)", not bad, got)

ok, d = g.exec_code(CHAIN + """
import json
import time

geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
geo.par.material = geo.op('mat')
cam.par.lookat = geo
cam.par.tx, cam.par.ty, cam.par.tz = 2.0, 2.0, 2.5
ren.par.geometry = geo
ren.par.camera = cam

settle(3)
term = geo.op('null_render')
print('<<JSON>>' + json.dumps(dict(mat=str(geo.par.material.eval()),
                                   lookat=str(cam.par.lookat.eval()),
                                   n=term.numPoints())))
""")
d = d or {}
chek("estado canónico: material + cámara lookat=geo iso + terminal renderizando",
     ok and "mat" in str(d.get("mat", "")) and "geo" in str(d.get("lookat", "")) and d.get("n") == 231, d)

g.call_retry = call_retry
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_analytics_cull.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 30, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

ok, d = g.exec_code(CHAIN + """
import json
import time

term = op(ROOT + '/geo/null_render')
settle(3)
time.sleep(0.5)
antes = px()
guardia = list(render_is_ours(term))
print('<<JSON>>' + json.dumps(dict(px_antes=antes, guardia=guardia)))
""")
d = d or {}
guardia = d.get("guardia") or []
chek("el render subió la geometría (px > 0 antes de la guardia)", (d.get("px_antes") or 0) > 0,
     {"px": d.get("px_antes")})
chek("los px son del analytics/cull chain (guardia: apagar el terminal -> 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = all(c[1] for c in report["cheks"])

out_rep = os.path.join(g.out_dir, "build-pop-analytics-cull-report.json")
with open(out_rep, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)

print("\n=== RESUMEN pop_analytics_cull ===")
print("ok: %s | cheks: %d | fallos: %s" % (
    report["ok"], len(report["cheks"]),
    [c[0] for c in report["cheks"] if not c[1]]))
print("PNG: %s" % report["png"])
print("Reporte: %s" % out_rep)

sys.exit(0 if report["ok"] else 1)

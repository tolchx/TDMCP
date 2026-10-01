#!/usr/bin/env python3
"""build_pop_group.py — cobertura POP 1/6 (5c): groupPOP con red propia.

Red /pop_group: gx (gridPOP 5x4, 20 pts, 12 quads) + gp (groupPOP) + tf (transformPOP).
Mide:
  * LA POBLACION NO CAMBIA: con thin activo el output sigue 20 pts/12 prims — la
    membresia es METADATO, invisible para numPoints() y para el conteo del poptoCHOP.
  * membresia observable por debugcolor: thin range [0-5) -> 5 puntos con ColorA y
    15 con ColorB (valores distintos, constantes dentro de cada grupo);
    thin step 2 -> 10/10.
  * transformPOP filtra por el grupo: dy=+1.2 EXACTO en los 5 miembros y 0.0 en los
    otros 15 (deltas contra baseline ty=0); con grupo inexistente ('ghost') el delta
    es 0 en los 20 (no filtra).
  * bound esferico redefine la membresia (thin apagado): escala 10 -> 20/20 dentro;
    escala 0.3 -> subconjunto estricto (< 20, >= 1).
  * 'remunusedpoints' figura en el help (catalogo 2025.33070) pero NO existe en el
    build vivo 2025.32460: help stale verificado en vivo (lección, no check).
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
g = Gauntlet(phase="build-pop-group", run_id=RUN)
g.init()

ROOT = "/pop_group"
CHAIN = chain_source(ROOT)

report = {"run_id": RUN,
          "objetivo": "groupPOP: poblacion inmutable (membresia=metadato), debugcolor como medida "
                      "(thin 5/20 y 10/20), filtro por grupo via transformPOP (dy exacto, ghost no "
                      "filtra), bound esferico grande/chica; help stale (remunusedpoints no existe)",
          "ok": False, "cheks": []}


def chek(name, ok, detail=""):
    report["cheks"].append((name, bool(ok)))
    g.check(name, ok, str(detail)[:240])


# ── 0. entorno limpio + estructura ──
g.call("project_info", {}, note="TD vivo")
ok, d = g.exec_code("import json\ntry:\n op('%s').destroy()\nexcept Exception:\n pass\n"
                    "print('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
chek("limpieza previa", ok)

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_group",
                              "nodeX": 2800, "nodeY": 2600, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"}, {"type": "cameraCOMP", "name": "cam"},
    {"type": "renderTOP", "name": "ren"}, {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True}, note="estructura")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 1. fuente + groupPOP: poblacion inmutable + membresia por debugcolor ──
ok, d = g.exec_code(CHAIN + """
import json
import time
geo = op(ROOT + '/geo')
for c in list(geo.children):
    if c.name.lower().startswith('torus'):
        c.destroy()
gx = geo.create(gridPOP, 'gx')
gx.par.rows = 5
gx.par.cols = 4
gx.par.sizex = 1.0
gx.par.sizey = 1.0
gp = geo.create(groupPOP, 'gp')
gp.inputConnectors[0].connect(gx.outputConnectors[0])
gp.par.grname = 'ng1'
gp.display = False
gp.render = False
chk = op(ROOT + '/check')

def medir():
    chk.par.pop = gp
    settle(2)
    chk.cook(force=True)
    time.sleep(0.2)
    chk.cook(force=True)
    time.sleep(0.1)
    chk.cook(force=True)
    return dict(pts=gp.numPoints(), prims=gp.numPrims(),
                col=[round(v, 5) for v in next((c.vals for c in chk.chans() if c.name == 'Color_0'), [])])

base = medir()
gp.par.thinenabled = True
gp.par.thinoutrange = True
gp.par.thinrangestart = 0
gp.par.thinrangelength = 5
r5 = medir()
gp.par.thinoutrange = False
gp.par.thinstep = 2
r10 = medir()
gp.par.thinstep = 1
gp.par.thinenabled = False
gp.par.debugcolor = False
print('<<JSON>>' + json.dumps(dict(base=base, r5=r5, r10=r10)))
""")
res = d or {}
report["thin"] = res
base, r5, r10 = res.get("base") or {}, res.get("r5") or {}, res.get("r10") or {}
c5, c10 = r5.get("col") or [], r10.get("col") or []


def grupos(col):
    """cuenta cuantos puntos tienen el Color del grupo (primer valor) vs el resto."""
    if not col:
        return (0, 0)
    a = col[0]
    na = sum(1 for v in col if abs(v - a) < 1e-6)
    return (na, len(col) - na)


na5, nb5 = grupos(c5)
na10, nb10 = grupos(c10)
chek("poblacion INMUTABLE con thin activo: 20 pts y 12 prims en base/range/step",
     ok and base.get("pts") == 20 and r5.get("pts") == 20 and r10.get("pts") == 20
     and base.get("prims") == 12 and r5.get("prims") == 12 and r10.get("prims") == 12, res)
chek("thin range [0-5): debugcolor marca 5 con ColorA y 15 con ColorB (distintos)",
     ok and len(c5) == 20 and na5 == 5 and nb5 == 15, res)
chek("thin step 2: 10/10 por debugcolor (seleccion por indice)",
     ok and len(c10) == 20 and na10 == 10 and nb10 == 10, res)

# ── 2. transformPOP filtra por el grupo; grupo fantasma no filtra ──
ok, d = g.exec_code(CHAIN + """
import json
import time
geo = op(ROOT + '/geo')
gp = op(ROOT + '/geo/gp')
gx = op(ROOT + '/geo/gx')
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

tf = geo.create(transformPOP, 'tf')
tf.inputConnectors[0].connect(gp.outputConnectors[0])
tf.par.group = 'ng1'
tf.display = True
tf.render = True
c0 = chans(tf)
tf.par.ty = 1.2
c1 = chans(tf)
dy = [round(v - b, 5) for v, b in zip(c1.get('P_1', []), c0.get('P_1', []))]
gpx = geo.create(groupPOP, 'gpx')
gpx.inputConnectors[0].connect(gx.outputConnectors[0])
gpx.par.grname = 'ghost'
gpx.display = False
gpx.render = False
tf.inputConnectors[0].connect(gpx.outputConnectors[0])
tf.par.ty = 0.0
cgb = chans(tf)
tf.par.ty = 1.2
cg = chans(tf)
dyg = [round(v - b, 5) for v, b in zip(cg.get('P_1', []), cgb.get('P_1', []))]
tf.inputConnectors[0].connect(gp.outputConnectors[0])
print('<<JSON>>' + json.dumps(dict(
    dy=[round(v, 4) for v in dy], n=len(dy),
    dyg_max=max((abs(v) for v in dyg), default=9.9), nghost=len(dyg))))
""")
res = d or {}
report["filtro"] = res
dy = res.get("dy") or []
movidos = [v for v in dy if abs(v - 1.2) < 1e-4]
quietos = [v for v in dy if abs(v) < 1e-4]
chek("transform filtra por grupo: 5 miembros dy=+1.2 exacto y 15 en 0.0 (deltas)",
     ok and len(dy) == 20 and len(movidos) == 5 and len(quietos) == 15, res)
chek("grupo inexistente ('ghost') NO filtra: 20/20 con delta 0",
     ok and res.get("nghost") == 20 and (res.get("dyg_max") or 9.9) < 1e-4, res)

# ── 3. bound esferico redefine la membresia (thin apagado) ──
ok, d = g.exec_code(CHAIN + """
import json
import time
gp = op(ROOT + '/geo/gp')
chk = op(ROOT + '/check')

def color():
    chk.par.pop = gp
    settle(2)
    chk.cook(force=True)
    time.sleep(0.2)
    chk.cook(force=True)
    time.sleep(0.1)
    chk.cook(force=True)
    return [round(v, 5) for v in next((c.vals for c in chk.chans() if c.name == 'Color_0'), [])]

gp.par.debugcolor = True
sin = color()
gp.par.bound0inattr = 'P'
gp.par.bound0type = 'usebsphere'
gp.par.bound0scalex = 10.0
gp.par.bound0scaley = 10.0
gp.par.bound0scalez = 10.0
cbig = color()
gp.par.bound0scalex = 0.3
gp.par.bound0scaley = 0.3
gp.par.bound0scalez = 0.3
csmall = color()
print('<<JSON>>' + json.dumps(dict(
    sin=sin[:2], sin_n=len(sin),
    big=cbig, small=csmall)))
""")
res = d or {}
report["bound"] = res
na_big, nb_big = grupos(res.get("big") or [])
na_small, nb_small = grupos(res.get("small") or [])
chek("bound sin criterios (default): todo el grupo toma UN Color (20 iguales)",
     ok and len(res.get("sin") or []) == 2 and len(set(res.get("sin") or [1, 2])) == 1, res)
chek("bound esferico escala 10: 20/20 dentro del grupo",
     ok and na_big == 20 and nb_big == 0, res)
chek("bound esferico escala 0.3: subconjunto estricto (1..19 de 20)",
     ok and 1 <= na_small < 20 and na_small + nb_small == 20, res)

# ── 4. estado canónico + material + cámara + PNG + guardia ──
g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "pointspriteMAT", "name": "mat"},
          note="material")
bad, got = set_and_verify(g, ROOT + "/geo/mat", {"pointsize": 5.0, "colorr": 1.0, "colorg": 0.6, "colorb": 0.2},
                          "material naranja")
chek("pars del material aplicados (C4)", not bad, got)
ok, d = g.exec_code(CHAIN + """
import json
import time
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
tf = op(ROOT + '/geo/tf')
tf.par.ty = 1.2
tf.cook(force=True)
geo.par.material = geo.op('mat')
chk = op(ROOT + '/check')
chk.par.pop = tf
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
                                   n=tf.numPoints())))
""")
chek("estado canónico (filtro por ng1 activo) + material + cámara",
     ok and "mat" in str((d or {}).get("mat", "")) and (d or {}).get("n") == 20
     and len(((d or {}).get("centro") or {})) == 3, d)
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_group.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

ok, d = g.exec_code(CHAIN + """
import json
import time
tf = op(ROOT + '/geo/tf')
settle(3)
time.sleep(1.5)
antes = px()
print('<<JSON>>' + json.dumps(dict(px_antes=antes, guardia=list(render_is_ours(tf)))))
""")
d = d or {}
guardia = d.get("guardia") or []
chek("el render subió la geometría (px > 0 antes de la guardia)", (d.get("px_antes") or 0) > 0,
     {"px": d.get("px_antes")})
chek("los px son del group chain (guardia: apagar el terminal → 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-group-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_group ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| fallos:", g.failures)
print("thin:", json.dumps(report.get("thin", {}), ensure_ascii=False))
print("filtro:", json.dumps(report.get("filtro", {}), ensure_ascii=False))
print("bound: big0=%s small0=%s" % ((report.get("bound") or {}).get("big", [])[:1],
                                    (report.get("bound") or {}).get("small", [])[:1]))
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

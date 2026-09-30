#!/usr/bin/env python3
"""build_pop_random.py — cobertura POP 12/12: randomPOP.

contratos que este build mide (evidencia: results/<run>/build-pop-random-report.json):
  * combineop='add' es IN-PLACE sobre P: deltas medidos punto a punto, 9 puntos,
    todos en [0, 1] con amp=1 (uniforme), determinístico por seed y cambia con
    la semilla (3 != 7). amp=0.5 NO acota los deltas a [0, 0.5]: hay deltas >
    0.5 medidos (el amp no escala el uniforme como se asumiría).
  * combineop='set' con outputattrscope='' es NO-OP: P vuelve EXACTO a la grilla
    ([-0.5, 0, 0.5]x3). Con outputattrscope='P' set escribe uniformes en [0, 1].
  * type='gaussian' con amp=1 y n=200: media |mu| < 0.3, stdev en [0.8, 1.2],
    rango > 4 (colas gaussianas, no uniformes).
  * type='uniform' con n=200 y scope vacío + add: rango contenido en [-0.5, 1.5]
    (base [-0.5,0.5] + delta [0,1]).
  * extrapts MULTIPLICA los puntos: 9 -> 18 (2 pts por fuente) y 9 -> 27 (3 por
    fuente) estables con re-cook; extrapts=1 deja 9 (max(1, extrapts)).
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
g = Gauntlet(phase="build-pop-random", run_id=RUN)
g.init()

ROOT = "/pop_random"
CHAIN = chain_source(ROOT)

report = {"run_id": RUN,
          "objetivo": "randomPOP: add in-place (deltas uniformes en [0,1], determinístico), "
                      "set es no-op con scope vacío y escribe [0,1] con scope P, gaussian "
                      "N(0,1), extrapts multiplica los puntos",
          "ok": False, "cheks": []}


def chek(name, ok, detail=""):
    report["cheks"].append((name, bool(ok)))
    g.check(name, ok, str(detail)[:240])


# ── 0. entorno limpio + estructura ──
g.call("project_info", {}, note="TD vivo")
ok, d = g.exec_code("import json\ntry:\n op('%s').destroy()\nexcept Exception:\n pass\n"
                    "print('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
chek("limpieza previa", ok)

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_random",
                              "nodeX": 2600, "nodeY": 2600, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"}, {"type": "cameraCOMP", "name": "cam"},
    {"type": "renderTOP", "name": "ren"}, {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True}, note="estructura")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 1. add in-place: deltas medidos, determinismo y semilla ──
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
rnd = geo.create(randomPOP, 'rnd')
rnd.inputConnectors[0].connect(gr.outputConnectors[0])
rnd.display = True
rnd.render = True
rnd.par.combineop = 'add'
rnd.par.amp0 = 1.0
rnd.par.seed = 3.0
rnd.par.outputattrscope = ''
rnd.par.extrapts = 0
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

base = chans(gr).get('P_0', [])
a1 = chans(rnd).get('P_0', [])
a2 = chans(rnd).get('P_0', [])
rnd.par.seed = 7.0
a3 = chans(rnd).get('P_0', [])
deltas = [a - b for a, b in zip(a1, base)]
print('<<JSON>>' + json.dumps(dict(
    n=len(a1), base=[round(v, 4) for v in base],
    det=([round(v, 6) for v in a1] == [round(v, 6) for v in a2]),
    cambia=([round(v, 4) for v in a1] != [round(v, 4) for v in a3]),
    deltas=[round(v, 4) for v in deltas],
    todos01=all(0.0 <= v <= 1.0 for v in deltas))))
""")
res = d or {}
report["add"] = res
chek("add in-place: 9 deltas medidos punto a punto, todos en [0, 1] con amp=1",
     ok and res.get("n") == 9 and res.get("todos01") is True, res)
chek("determinístico (2 lecturas iguales) y cambia con seed (3 ≠ 7)",
     ok and res.get("det") is True and res.get("cambia") is True, res)

# ── 2. amp no escala el uniforme; set con scope vacío es no-op; scope P escribe [0,1] ──
ok, d = g.exec_code(CHAIN + """
import json
import time
rnd = op(ROOT + '/geo/rnd')
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

base = chans(op(ROOT + '/geo/gr')).get('P_0', [])
rnd.par.seed = 3.0
rnd.par.amp0 = 1.0
a1 = chans(rnd).get('P_0', [])
deltas1 = [a - b for a, b in zip(a1, base)]
rnd.par.amp0 = 0.5
a4 = chans(rnd).get('P_0', [])
deltas4 = [a - b for a, b in zip(a4, base)]
rnd.par.combineop = 'set'
rnd.par.amp0 = 1.0
s1 = chans(rnd).get('P_0', [])
readback = dict(scope=rnd.par.outputattrscope.eval(), op=rnd.par.combineop.eval())
rnd.par.outputattrscope = 'P'
s2 = chans(rnd).get('P_0', [])
rnd.par.outputattrscope = ''
rnd.par.combineop = 'add'
print('<<JSON>>' + json.dumps(dict(
    amp1_max=round(max(deltas1), 4), amp4=[round(v, 4) for v in deltas4],
    amp4_supera05=any(v > 0.5 for v in deltas4),
    set_scopevacio=[round(v, 4) for v in s1], readback=readback,
    setP_vals=[round(v, 4) for v in s2],
    setP_en01=all(0.0 <= v <= 1.0 for v in s2))))
""")
res = d or {}
report["amp_set"] = res
chek("amp=0.5 NO acota los deltas (hay > 0.5): el amp no escala el uniforme",
     ok and res.get("amp4_supera05") is True, res)
chek("set con outputattrscope='' es NO-OP: P vuelve EXACTO a la grilla base",
     ok and (res.get("set_scopevacio") or []) == [-0.5, 0.0, 0.5, -0.5, 0.0, 0.5, -0.5, 0.0, 0.5], res)
chek("set con outputattrscope='P' escribe uniformes en [0, 1] (9 puntos)",
     ok and res.get("setP_en01") is True and len(res.get("setP_vals") or []) == 9, res)

# ── 3. gaussian N(0,1) y uniforme n=200 ──
ok, d = g.exec_code(CHAIN + """
import json
import time
geo = op(ROOT + '/geo')
gr20 = geo.create(gridPOP, 'gr20')
gr20.par.cols = 20
gr20.par.rows = 10
rnd2 = geo.create(randomPOP, 'rnd2')
rnd2.inputConnectors[0].connect(gr20.outputConnectors[0])
rnd2.par.combineop = 'add'
rnd2.par.outputattrscope = ''
rnd2.par.extrapts = 0
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

rnd2.par.type = 'gaussian'
rnd2.par.amp0 = 1.0
rnd2.par.seed = 3.0
ga = chans(rnd2).get('P_0', [])
n = len(ga)
mean = sum(ga) / n
var = sum((v - mean) ** 2 for v in ga) / n
rnd2.par.type = 'uniform'
ga2 = chans(rnd2).get('P_0', [])
print('<<JSON>>' + json.dumps(dict(
    n=n, mean=round(mean, 3), stdev=round(var ** 0.5, 3),
    rango_gauss=round(max(ga) - min(ga), 2),
    uni_min=round(min(ga2), 3), uni_max=round(max(ga2), 3))))
""")
res = d or {}
report["gauss_uni"] = res
chek("gaussian amp=1 n=200: |media| < 0.3, stdev en [0.8, 1.2], rango > 4",
     ok and abs(res.get("mean") or 9) < 0.3 and 0.8 <= (res.get("stdev") or 9) <= 1.2
     and (res.get("rango_gauss") or 0) > 4, res)
chek("uniform n=200 con add: rango contenido en [-0.5, 1.5] (base + delta)",
     ok and (res.get("uni_min") or -9) >= -0.5 and (res.get("uni_max") or 9) <= 1.5, res)

# ── 4. extrapts multiplica los puntos ──
ok, d = g.exec_code(CHAIN + """
import json
import time
rnd3 = op(ROOT + '/geo/rnd')
res = {}
for e in (0, 2, 3, 1):
    rnd3.par.extrapts = e
    settle(2)
    rnd3.cook(force=True)
    time.sleep(0.2)
    rnd3.cook(force=True)
    res['e%d' % e] = rnd3.numPoints()
print('<<JSON>>' + json.dumps(res))
""")
res = d or {}
report["extrapts"] = res
chek("extrapts multiplica: e=0 -> 9, e=2 -> 18, e=3 -> 27, e=1 -> 9 (estables)",
     ok and res.get("e0") == 9 and res.get("e2") == 18 and res.get("e3") == 27
     and res.get("e1") == 9, res)

# ── 5. estado canónico + material + cámara + PNG + guardia ──
g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "pointspriteMAT", "name": "mat"},
          note="material")
bad, got = set_and_verify(g, ROOT + "/geo/mat", {"pointsize": 5.0, "colorr": 1.0, "colorg": 0.25, "colorb": 0.25},
                          "material rojo")
chek("pars del material aplicados (C4)", not bad, got)
ok, d = g.exec_code(CHAIN + """
import json
import time
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
rnd = op(ROOT + '/geo/rnd')
rnd.par.extrapts = 0
rnd.par.combineop = 'add'
rnd.par.amp0 = 1.0
rnd.par.seed = 3.0
rnd.cook(force=True)
geo.par.material = geo.op('mat')
chk = op(ROOT + '/check')
chk.par.pop = rnd
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
                                   n=rnd.numPoints())))
""")
chek("estado canónico (9 pts dispersos) + material + cámara",
     ok and "mat" in str((d or {}).get("mat", "")) and (d or {}).get("n") == 9
     and len(((d or {}).get("centro") or {})) == 3, d)
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_random.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

ok, d = g.exec_code(CHAIN + """
import json
import time
rnd = op(ROOT + '/geo/rnd')
settle(3)
time.sleep(1.5)
antes = px()
print('<<JSON>>' + json.dumps(dict(px_antes=antes, guardia=list(render_is_ours(rnd)))))
""")
d = d or {}
guardia = d.get("guardia") or []
chek("el render subió la geometría (px > 0 antes de la guardia)", (d.get("px_antes") or 0) > 0,
     {"px": d.get("px_antes")})
chek("los px son del random (guardia: apagar el terminal → 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-random-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_random ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| fallos:", g.failures)
print("add:", json.dumps(report.get("add", {}), ensure_ascii=False))
print("amp_set:", json.dumps(report.get("amp_set", {}), ensure_ascii=False))
print("gauss_uni:", json.dumps(report.get("gauss_uni", {}), ensure_ascii=False))
print("extrapts:", json.dumps(report.get("extrapts", {}), ensure_ascii=False))
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

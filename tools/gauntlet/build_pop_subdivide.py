#!/usr/bin/env python3
"""build_pop_subdivide.py — cobertura POP 8/12: subdividePOP.

contratos que este build mide (evidencia: results/<run>/build-pop-subdivide-report.json):
  * iterations es ESCALADO EXACTO de topologia sobre grid 4x4 (16 pts, 9 quads):
    it0=16/9 (identidad), it1=49/72, it2=169/288; los quads se multiplican x4
    por nivel (9->36->144) y los tris que crea en el medio se quedan en 0 al
    final (72 y 288 son quads: (2^n-1+1)^2-1 ... medido: 72 = 8x9, 288 = 16x18).
  * el bounding box NO cambia: P_0/P_1 en [-0.5, 0.5] y P_2 max abs = 0
    (subdividir no deforma la superficie plana).
  * creaseweight=1 mantiene conteos (49/72) pero DESPLAZA los puntos
    (la nube ya no coincide con la de crease=0).
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
g = Gauntlet(phase="build-pop-subdivide", run_id=RUN)
g.init()

ROOT = "/pop_subdivide"
CHAIN = chain_source(ROOT)

report = {"run_id": RUN,
          "objetivo": "subdividePOP: escalado exacto 16/9 -> 49/72 -> 169/288, bb y "
                      "planaridad preservados, creaseweight desplaza sin cambiar conteos",
          "ok": False, "cheks": []}


def chek(name, ok, detail=""):
    report["cheks"].append((name, bool(ok)))
    g.check(name, ok, str(detail)[:240])


# ── 0. entorno limpio + estructura ──
g.call("project_info", {}, note="TD vivo")
ok, d = g.exec_code("import json\ntry:\n op('%s').destroy()\nexcept Exception:\n pass\n"
                    "print('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
chek("limpieza previa", ok)

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_subdivide",
                              "nodeX": 1000, "nodeY": 2600, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"}, {"type": "cameraCOMP", "name": "cam"},
    {"type": "renderTOP", "name": "ren"}, {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True}, note="estructura")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 1. escalado exacto por iterations ──
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
sb = geo.create(subdividePOP, 'sb')
sb.inputConnectors[0].connect(gr.outputConnectors[0])
sb.display = True
sb.render = True
res = {}
for it in (0, 1, 2):
    sb.par.iterations = it
    settle(2)
    sb.cook(force=True)
    time.sleep(0.2)
    sb.cook(force=True)
    res['it%d' % it] = dict(pts=sb.numPoints(), prims=sb.numPrims())
print('<<JSON>>' + json.dumps(res))
""")
res = d or {}
report["escalado"] = res
chek("it0 es identidad (16 pts, 9 quads)",
     ok and (res.get("it0") or {}).get("pts") == 16 and (res.get("it0") or {}).get("prims") == 9, res)
chek("it1 EXACTO: 49 pts y 72 prims", ok and (res.get("it1") or {}).get("pts") == 49
     and (res.get("it1") or {}).get("prims") == 72, res)
chek("it2 EXACTO: 169 pts y 288 prims (quads x4 por nivel: 36->144)",
     ok and (res.get("it2") or {}).get("pts") == 169
     and (res.get("it2") or {}).get("prims") == 288, res)

# ── 2. bb preservado + planaridad + creaseweight ──
ok, d = g.exec_code(CHAIN + """
import json
import time
sb = op(ROOT + '/geo/sb')
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

sb.par.iterations = 1
sb.par.creaseweight = 0.0
settle(2)
sb.cook(force=True)
time.sleep(0.2)
sb.cook(force=True)
c = chans(sb)
p0, p1, p2 = c.get('P_0', []), c.get('P_1', []), c.get('P_2', [])
base = [round(v, 5) for v in p0]
sb.par.creaseweight = 1.0
settle(2)
sb.cook(force=True)
time.sleep(0.2)
sb.cook(force=True)
c2 = chans(sb)
p0b, p2b = c2.get('P_0', []), c2.get('P_2', [])
print('<<JSON>>' + json.dumps(dict(
    n=len(p0),
    P0=[round(min(p0), 4), round(max(p0), 4)], P1=[round(min(p1), 4), round(max(p1), 4)],
    P2_maxabs=round(max(abs(v) for v in p2), 6),
    n_crease=len(p0b), P2_crease_maxabs=round(max(abs(v) for v in p2b), 6),
    crease_desplaza=([round(v, 5) for v in p0b] != base))))
""")
res = d or {}
report["bb_crease"] = res
chek("it1 preserva el bb de la grilla (P0 y P1 en [-0.5, 0.5])",
     ok and res.get("P0") == [-0.5, 0.5] and res.get("P1") == [-0.5, 0.5], res)
chek("la superficie subdividida sigue PLANA (P_2 max abs = 0, medido en it1 y crease)",
     ok and res.get("P2_maxabs") == 0.0 and res.get("P2_crease_maxabs") == 0.0, res)
chek("creaseweight=1 desplaza los puntos sin cambiar el conteo (49)",
     ok and res.get("n") == 49 and res.get("n_crease") == 49
     and res.get("crease_desplaza") is True, res)

# ── 3. estado canónico + material + cámara + PNG + guardia ──
g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "pointspriteMAT", "name": "mat"},
          note="material")
bad, got = set_and_verify(g, ROOT + "/geo/mat", {"pointsize": 3.0, "colorr": 1.0, "colorg": 0.6, "colorb": 0.1},
                          "material naranja")
chek("pars del material aplicados (C4)", not bad, got)
ok, d = g.exec_code(CHAIN + """
import json
import time
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
sb = op(ROOT + '/geo/sb')
sb.par.iterations = 2
sb.par.creaseweight = 0.0
sb.cook(force=True)
geo.par.material = geo.op('mat')
chk = op(ROOT + '/check')
chk.par.pop = sb
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
                                   pts=sb.numPoints())))
""")
chek("estado canónico (it2: 169 pts) + material + cámara",
     ok and "mat" in str((d or {}).get("mat", "")) and (d or {}).get("pts") == 169
     and len(((d or {}).get("centro") or {})) == 3, d)
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_subdivide.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

ok, d = g.exec_code(CHAIN + """
import json
import time
sb = op(ROOT + '/geo/sb')
settle(3)
time.sleep(1.5)
antes = px()
print('<<JSON>>' + json.dumps(dict(px_antes=antes, guardia=list(render_is_ours(sb)))))
""")
d = d or {}
guardia = d.get("guardia") or []
chek("el render subió la geometría (px > 0 antes de la guardia)", (d.get("px_antes") or 0) > 0,
     {"px": d.get("px_antes")})
chek("los px son del subdivide (guardia: apagar el terminal → 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-subdivide-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_subdivide ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| fallos:", g.failures)
print("escalado:", json.dumps(report.get("escalado", {}), ensure_ascii=False))
print("bb_crease:", json.dumps(report.get("bb_crease", {}), ensure_ascii=False))
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

#!/usr/bin/env python3
"""build_pop_connectivity.py — cobertura POP 6/6: connectivityPOP.

contratos que este build mide (evidencia: results/<run>/build-pop-connectivity-report.json):
  * grilla 4x4 (16 pts, 9 quads nativos) re-conectada por surftype (medido, prims):
    points=16, lines=12, linestrips=4, triangles=18, alttriangles=18, quads=9, none=0.
  * lines + firstdimclosed en 4x4: 12 → 16 (+1 cerrojo por FILA, 4 filas);
    seconddimclosed NO agrega prims (16→16, medido dos veces) y linestrips
    cerradas tampoco (4→4): el cerrojo extra sólo entra por firstdim.
  * el número de PUNTOS no cambia en ningún modo (re-conecta, no re-muestrea).
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
g = Gauntlet(phase="build-pop-connectivity", run_id=RUN)
g.init()

ROOT = "/pop_connectivity"
CHAIN = chain_source(ROOT)

report = {"run_id": RUN,
          "objetivo": "connectivityPOP: tabla exacta de prims por surftype sobre grilla 4x4, "
                      "firstdimclosed agrega cerrojos, los puntos no cambian",
          "ok": False, "cheks": []}


def chek(name, ok, detail=""):
    report["cheks"].append((name, bool(ok)))
    g.check(name, ok, str(detail)[:240])


# ── 0. entorno limpio + estructura ──
g.call("project_info", {}, note="TD vivo")
ok, d = g.exec_code("import json\ntry:\n op('%s').destroy()\nexcept Exception:\n pass\n"
                    "print('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
chek("limpieza previa", ok)

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_connectivity",
                              "nodeX": -400, "nodeY": 2600, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"}, {"type": "cameraCOMP", "name": "cam"},
    {"type": "renderTOP", "name": "ren"}, {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True}, note="estructura")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 1. grilla 4x4 + connectivity: tabla por surftype ──
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
gr.par.sizex = 1.0
gr.par.sizey = 1.0
cx = geo.create(connectivityPOP, 'cx')
cx.inputConnectors[0].connect(gr.outputConnectors[0])
cx.display = True
cx.render = True
chk = op(ROOT + '/check')
res = {}
for st in ('points', 'lines', 'linestrips', 'triangles', 'alttriangles', 'quads', 'none'):
    cx.par.surftype = st
    settle(2)
    cx.cook(force=True)
    time.sleep(0.2)
    cx.cook(force=True)
    res[st] = dict(prims=cx.numPrims(), pts=cx.numPoints())
gr_num = dict(prims=gr.numPrims(), pts=gr.numPoints())
print('<<JSON>>' + json.dumps(dict(grilla=gr_num, cx=res,
                                   re_st=str(cx.par.surftype.eval()))))
""")
tabla = (d or {}).get("cx") or {}
esperado = {"points": 16, "lines": 12, "linestrips": 4, "triangles": 18,
            "alttriangles": 18, "quads": 9, "none": 0}
report["tabla"] = d
chek("tabla de prims EXACTA por surftype (grilla 4x4): %s" % esperado,
     ok and all((tabla.get(k) or {}).get("prims") == v for k, v in esperado.items())
     and all((tabla.get(k) or {}).get("pts") == 16 for k in esperado), d)
chek("la grilla nativa entra con 9 quads y 16 puntos",
     ok and ((d or {}).get("grilla") or {}).get("prims") == 9
     and ((d or {}).get("grilla") or {}).get("pts") == 16, d)

# ── 2. firstdimclosed: lines 12→36 en 2D (cerrojos por fila y columna) ──
ok, d = g.exec_code(CHAIN + """
import json
import time
cx = op(ROOT + '/geo/cx')
chk = op(ROOT + '/check')
res = {}
cx.par.surftype = 'lines'
cx.par.firstdimclosed = False
cx.par.seconddimclosed = False
settle(2)
cx.cook(force=True)
time.sleep(0.2)
cx.cook(force=True)
res['lines_abiertas'] = cx.numPrims()
cx.par.firstdimclosed = True
settle(2)
cx.cook(force=True)
time.sleep(0.2)
cx.cook(force=True)
res['lines_fd_closed'] = cx.numPrims()
cx.par.seconddimclosed = True
settle(2)
cx.cook(force=True)
time.sleep(0.2)
cx.cook(force=True)
res['lines_ambas_closed'] = cx.numPrims()
cx.par.surftype = 'linestrips'
cx.par.firstdimclosed = True
cx.par.seconddimclosed = False
settle(2)
cx.cook(force=True)
time.sleep(0.2)
cx.cook(force=True)
res['strips_fd_closed'] = cx.numPrims()
print('<<JSON>>' + json.dumps(res))
""")
chek("lines: 12 abiertas → 16 con fd closed (+1 cerrojo por FILA, 4 filas)",
     ok and (d.get("lines_abiertas") or 0) == 12 and (d.get("lines_fd_closed") or 0) == 16, d)
chek("CONTRATO medido: seconddimclosed NO agrega prims (16→16) y strips cerradas tampoco (4→4)",
     ok and (d.get("lines_ambas_closed") or 0) == 16 and (d.get("strips_fd_closed") or 0) == 4, d)
report["closed"] = d

# ── 3. estado canónico + material + cámara + PNG + guardia ──
g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "pointspriteMAT", "name": "mat"},
          note="material")
bad, got = set_and_verify(g, ROOT + "/geo/mat", {"pointsize": 8.0, "colorr": 1.0, "colorg": 0.4, "colorb": 0.9},
                          "material magenta")
chek("pars del material aplicados (C4)", not bad, got)
ok, d = g.exec_code(CHAIN + """
import json
import time
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
cx = op(ROOT + '/geo/cx')
cx.par.surftype = 'quads'
cx.par.firstdimclosed = False
cx.par.seconddimclosed = False
geo.par.material = geo.op('mat')
chk = op(ROOT + '/check')
chk.par.pop = cx
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
                                   prims=cx.numPrims())))
""")
chek("estado canónico (quads=9) + material + cámara", ok and "mat" in str(d.get("mat", ""))
     and (d.get("prims") or 0) == 9 and len((d.get("centro") or {})) == 3, d)
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_connectivity.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

ok, d = g.exec_code(CHAIN + """
import json
import time
cx = op(ROOT + '/geo/cx')
settle(3)
time.sleep(1.5)
antes = px()
print('<<JSON>>' + json.dumps(dict(px_antes=antes, guardia=list(render_is_ours(cx)))))
""")
d = d or {}
guardia = d.get("guardia") or []
chek("el render subió la geometría (px > 0 antes de la guardia)", (d.get("px_antes") or 0) > 0,
     {"px": d.get("px_antes")})
chek("los px son del connectivity (guardia: apagar el terminal → 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-connectivity-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_connectivity ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| fallos:", g.failures)
print("tabla:", json.dumps((report.get("tabla") or {}).get("cx", {}), ensure_ascii=False))
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

#!/usr/bin/env python3
"""build_pop_revolve.py — cobertura POP 3/6 (5c): revolvePOP.

Red /pop_revolve: pt (patternPOP ramp 2 pts, radios 0.2..0.5, linestrip) + rv (revolvePOP).
Mide (evidencia: build-pop-revolve-report.json):
  * topologia EXACTA: perfil de 2 pts barrido con divs=20 -> 40 pts (= 2 filas x
    20 columnas) y 20 quads (= divs). El seam DUPLICA la columna 0: hay 20
    columnas logicas pero 2 filas de 20 puntos.
  * radios XZ conservados EXACTOS: el conjunto de sqrt(x^2+z^2) es {0.2, 0.5}
    (err < 1e-3) — cada circunferencia hereda el radio del punto del perfil.
  * tabla surftype (2x20): quads=20, rows=2 (las 2 circunferencias como
    linestrips), cols=20 (una linea vertical por columna), points=40, none=0,
    triangles=40 (2 tris por quad).
  * divs escala EXACTO: divs=4 -> 8 pts / 4 prims; divs=8 -> 16 pts / 8 prims.
  * autopivot ON vs OFF con perfil COLINEAL al eje: misma topologia (20/40) y
    mismos radios {0.2, 0.5} — el pivote automatico (linea 1er-ultimo punto)
    coincide con el eje Y en este caso.
  * atributos de superficie: N (3 canales) y Tex (2) creados con los defaults
    (normal=pointNormals, texture=vertNormals).
  * render: camara con `lookat` al geometryCOMP y posicion iso (2,2,2). Apuntar a
    mano con rx/ry NO apunta donde uno espera (render negro en toda config; el
    auto-torus tampoco dibuja) y mirar el anillo desde el eje Y con up=+Y es
    singular (0 px) — el mecanismo canonico del repo es lookat + traslacion.
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
g = Gauntlet(phase="build-pop-revolve", run_id=RUN)
g.init()

ROOT = "/pop_revolve"
CHAIN = chain_source(ROOT)

report = {"run_id": RUN,
          "objetivo": "revolvePOP: 2·divs pts / divs quads exactos, radios XZ conservados {0.2,0.5}, "
                      "tabla surftype completa, escalado divs 4/8, autopivot colineal igual a manual, "
                      "N y Tex de serie",
          "ok": False, "cheks": []}


def chek(name, ok, detail=""):
    report["cheks"].append((name, bool(ok)))
    g.check(name, ok, str(detail)[:240])


# ── 0. entorno limpio + estructura ──
g.call("project_info", {}, note="TD vivo")
ok, d = g.exec_code("import json\ntry:\n op('%s').destroy()\n op('/pop_probe5c').destroy()\nexcept Exception:\n pass\n"
                    "print('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
chek("limpieza previa", ok)

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_revolve",
                              "nodeX": 3600, "nodeY": 2600, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"}, {"type": "cameraCOMP", "name": "cam"},
    {"type": "renderTOP", "name": "ren"}, {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True}, note="estructura")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 1. topologia + radios + surftype + divs ──
ok, d = g.exec_code(CHAIN + """
import json
import math
import time
geo = op(ROOT + '/geo')
for c in list(geo.children):
    if c.name.lower().startswith('torus'):
        c.destroy()
pt = geo.create(patternPOP, 'pt')
pt.par.numpoints = 2
pt.par.type0 = 'ramp'
pt.par.tolow0 = 0.2
pt.par.tohigh0 = 0.5
pt.par.connectivity = 'linestrip'
pt.par.closed = False
rv = geo.create(revolvePOP, 'rv')
rv.inputConnectors[0].connect(pt.outputConnectors[0])
rv.display = True
rv.render = True
chk = op(ROOT + '/check')

def leer(pop):
    chk.par.pop = pop
    settle(2)
    chk.cook(force=True)
    time.sleep(0.2)
    chk.cook(force=True)
    time.sleep(0.1)
    chk.cook(force=True)
    return {c.name: list(c.vals) for c in chk.chans()}

def topo(pop):
    return dict(pts=pop.numPoints(), prims=pop.numPrims())

sal = {}
cp = leer(pt)
sal['perfil'] = dict(topo=topo(pt), P0=[round(v, 3) for v in cp.get('P_0', [])])
rv.par.autopivot = True
ch = leer(rv)
radios = sorted(set(round(math.sqrt(a * a + b * b), 3) for a, b in zip(ch.get('P_0', []), ch.get('P_2', []))))
sal['quads'] = dict(topo=topo(rv), radios=radios, n_can=len(ch.get('P_0', [])),
                    tiene_n=('N_0' in ch), tiene_tex=('Tex_0' in ch))
tabla = {}
for st in ('quads', 'rows', 'cols', 'points', 'none', 'triangles'):
    rv.par.surftype = st
    rv.cook(force=True)
    time.sleep(0.15)
    rv.cook(force=True)
    time.sleep(0.1)
    tabla[st] = topo(rv)
sal['surftype'] = tabla
rv.par.surftype = 'quads'
d2 = {}
for dv in (4, 8):
    rv.par.divs = dv
    rv.cook(force=True)
    time.sleep(0.15)
    rv.cook(force=True)
    time.sleep(0.1)
    d2['divs%s' % dv] = topo(rv)
sal['divs'] = d2
rv.par.divs = 20
rv.par.autopivot = False
rv.par.axis = 'y'
ch2 = leer(rv)
radios2 = sorted(set(round(math.sqrt(a * a + b * b), 3) for a, b in zip(ch2.get('P_0', []), ch2.get('P_2', []))))
sal['auto_off'] = dict(topo=topo(rv), radios=radios2)
rv.par.autopivot = True
print('<<JSON>>' + json.dumps(sal))
""")
res = d or {}
report["revolve"] = res
q = res.get("quads") or {}
chek("perfil 2 pts -> 40 pts (=2 filas x 20 col) y 20 quads (=divs)",
     ok and q.get("topo") == {"pts": 40, "prims": 20}, res)
chek("radios XZ EXACTOS {0.2, 0.5} (cada circunferencia conserva el radio del perfil)",
     ok and q.get("radios") == [0.2, 0.5], res)
chek("tabla surftype 2x20: quads 20, rows 2, cols 20, points 40, none 0, triangles 40",
     ok and (res.get("surftype") or {}) == {"quads": {"pts": 40, "prims": 20},
                                            "rows": {"pts": 40, "prims": 2},
                                            "cols": {"pts": 40, "prims": 20},
                                            "points": {"pts": 40, "prims": 40},
                                            "none": {"pts": 40, "prims": 0},
                                            "triangles": {"pts": 40, "prims": 40}}, res)
chek("divs escala EXACTO: 4 -> 8/4 y 8 -> 16/8",
     ok and (res.get("divs") or {}) == {"divs4": {"pts": 8, "prims": 4}, "divs8": {"pts": 16, "prims": 8}}, res)
chek("autopivot ON vs OFF (perfil colineal): misma topologia y mismos radios",
     ok and (res.get("auto_off") or {}).get("topo") == {"pts": 40, "prims": 20}
     and (res.get("auto_off") or {}).get("radios") == [0.2, 0.5], res)
chek("N y Tex creados de serie (normal=pointNormals, texture=vertNormals)",
     ok and q.get("tiene_n") is True and q.get("tiene_tex") is True, res)

# ── 2. estado canónico + material + cámara + PNG + guardia ──
g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "pointspriteMAT", "name": "mat"},
          note="material")
bad, got = set_and_verify(g, ROOT + "/geo/mat", {"pointsize": 5.0, "colorr": 0.4, "colorg": 1.0, "colorb": 0.55},
                          "material verde")
chek("pars del material aplicados (C4)", not bad, got)
ok, d = g.exec_code(CHAIN + """
import json
import time
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
rv = op(ROOT + '/geo/rv')
rv.par.surftype = 'quads'
rv.par.divs = 20
rv.par.autopivot = True
rv.cook(force=True)
geo.par.material = geo.op('mat')
# camara canonica del gauntlet: lookat al geometryCOMP + posicion iso (2,2,2).
# Apuntar a mano con rx/ry da render negro (ni el auto-torus dibuja); y mirar el
# anillo desde el eje Y con up=+Y es singular (0 px).
cam.par.lookat = geo
cam.par.tx, cam.par.ty, cam.par.tz = 2.0, 2.0, 2.0
ren.par.geometry = geo
ren.par.camera = cam
settle(4)
print('<<JSON>>' + json.dumps(dict(mat=str(geo.par.material.eval()),
                                   lookat=str(cam.par.lookat.eval()),
                                   pos=[round(cam.par.tx.eval(), 2), round(cam.par.ty.eval(), 2),
                                        round(cam.par.tz.eval(), 2)],
                                   n=rv.numPoints(), p=rv.numPrims())))
""")
chek("estado canónico (vaso 0.2-0.5, divs=20, quads) + material + cámara lookat iso",
     ok and "mat" in str((d or {}).get("mat", "")) and (d or {}).get("n") == 40
     and (d or {}).get("p") == 20 and str((d or {}).get("lookat", "")).endswith("/geo")
     and (d or {}).get("pos") == [2.0, 2.0, 2.0], d)
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_revolve.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

ok, d = g.exec_code(CHAIN + """
import json
import time
rvp = op(ROOT + '/geo/rv')
settle(3)
time.sleep(1.5)
antes = px()
print('<<JSON>>' + json.dumps(dict(px_antes=antes, guardia=list(render_is_ours(rvp)))))
""")
d = d or {}
guardia = d.get("guardia") or []
chek("el render subió la geometría (px > 0 antes de la guardia)", (d.get("px_antes") or 0) > 0,
     {"px": d.get("px_antes")})
chek("los px son del revolve (guardia: apagar el terminal → 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-revolve-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_revolve ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| fallos:", g.failures)
print("revolve:", json.dumps(report.get("revolve", {}), ensure_ascii=False))
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

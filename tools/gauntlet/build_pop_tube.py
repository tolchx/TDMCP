#!/usr/bin/env python3
"""build_pop_tube.py — cobertura POP 4/6 (5c): tubePOP.

Red /pop_tube: tb (tubePOP autonomo, sin input).
Mide (evidencia: build-pop-tube-report.json):
  * default cols=40 rows=10 surftype=quads -> 400 pts / 360 prims (= (rows-1)*cols).
  * cols=8 rows=4 quads -> EXACTO 32 pts / 24 prims; la malla es una rejilla
    (rows x cols) sin puntos duplicados y con U cerrada.
  * radx/rady son los RADIOS DE LOS EXTREMOS (cono): radx=0.2 en y=-1 y rady=1.0
    en y=+1, con interpolacion lineal EXACTA en las filas intermedias
    (y=-1/3 -> 0.467, y=+1/3 -> 0.733). radz/radw del help NO existen en el build
    vivo (2025.32460): help stale.
  * height escala el eje del tubo: height=4 -> bbox Y=[-2,2] manteniendo XZ.
  * orient x/y/z mueve el eje del cono: el mismo perfil de radios aparece medido
    sobre X, Y o Z respectivamente.
  * closedu=False Duplica la columna del seam: +rows pts (36 vs 32) con las mismas
    24 prims (el anillo se abre, la topologia de quads no cambia).
  * endcaps (Toggle on) agrega EXACTAMENTE cols-2 = 6 prims (abanico de
    triangulos, una tapa) sin crear puntos nuevos.
  * tabla surftype (8x4): rows=4, cols=8, triangles=60, points=32, quads=24.
  * atributos: default SOLO P (aun con normal=vertNormals/texture=vert de serie:
    los attrs de clase vert no llegan al poptoCHOP); normal=pointNormals crea N y
    texture=point crea Tex.
  * render: camara con lookat al geometryCOMP + posicion iso (2,2,2) (mecanismo
    canonico del gauntlet; apuntar a mano con rx/ry da render negro).
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
g = Gauntlet(phase="build-pop-tube", run_id=RUN)
g.init()

ROOT = "/pop_tube"
CHAIN = chain_source(ROOT)

report = {"run_id": RUN,
          "objetivo": "tubePOP: malla exacta (rows x cols), radx/rady radios de extremos (cono) "
                      "con interpolacion lineal, height, orient x/y/z, seam closedu, endcaps "
                      "+cols-2, tabla surftype, attrs P/N/Tex, render con camara lookat",
          "ok": False, "cheks": []}


def chek(name, ok, detail=""):
    report["cheks"].append((name, bool(ok)))
    g.check(name, ok, str(detail)[:240])


# ── 0. entorno limpio + estructura ──
g.call("project_info", {}, note="TD vivo")
ok, d = g.exec_code("import json\ntry:\n op('%s').destroy()\n op('/pop_probe5c').destroy()\nexcept Exception:\n pass\n"
                    "print('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
chek("limpieza previa", ok)

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_tube",
                              "nodeX": 4000, "nodeY": 2600, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"}, {"type": "cameraCOMP", "name": "cam"},
    {"type": "renderTOP", "name": "ren"}, {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True}, note="estructura")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 1. malla exacta + cono + orient + seam + caps + surftype + attrs ──
ok, d = g.exec_code(CHAIN + """
import json
import time
geo = op(ROOT + '/geo')
for c in list(geo.children):
    if c.name.lower().startswith('torus'):
        c.destroy()
tb = geo.create(tubePOP, 'tb')
tb.display = True
tb.render = True
chk = op(ROOT + '/check')

def topo():
    tb.cook(force=True)
    time.sleep(0.12)
    tb.cook(force=True)
    time.sleep(0.08)
    return dict(pts=tb.numPoints(), prims=tb.numPrims())

def canales():
    chk.par.pop = tb
    tb.cook(force=True)
    time.sleep(0.1)
    chk.cook(force=True)
    time.sleep(0.08)
    chk.cook(force=True)
    return {c.name: list(c.vals) for c in chk.chans()}

def bbox_y_eje(eje):
    ch = canales()
    idx = {'x': 'P_0', 'y': 'P_1', 'z': 'P_2'}[eje]
    return (round(min(ch[idx]), 3), round(max(ch[idx]), 3)) if idx in ch else None

def radios_por(eje):
    ch = canales()
    idx = {'x': 'P_0', 'y': 'P_1', 'z': 'P_2'}[eje]
    otros = [n for n in ('P_0', 'P_1', 'P_2') if n != idx]
    filas = {}
    for a, b, c in zip(ch.get(otros[0], []), ch.get(otros[1], []), ch.get(idx, [])):
        filas.setdefault(round(c, 2), []).append((a * a + b * b) ** 0.5)
    return {k: (round(min(v), 3), round(max(v), 3)) for k, v in filas.items()}

def attrs():
    tb.cook(force=True)
    time.sleep(0.1)
    chk.par.pop = tb
    chk.cook(force=True)
    time.sleep(0.08)
    chk.cook(force=True)
    return sorted(set(c.name.split('_')[0] for c in chk.chans()))

sal = {}
sal['default'] = dict(topo=topo(), pars=dict(cols=tb.par.cols.eval(), rows=tb.par.rows.eval(),
                                             surftype=str(tb.par.surftype.eval()),
                                             closedu=str(tb.par.closedu.eval()),
                                             endcaps=str(tb.par.endcaps.eval()),
                                             orient=str(tb.par.orient.eval())))
tb.par.cols = 8
tb.par.rows = 4
tb.par.surftype = 'quads'
tb.par.endcaps = False
sal['c8r4'] = topo()
# cono: radx extremo negativo, rady extremo positivo, interpolacion lineal
tb.par.radx = 0.2
tb.par.rady = 1.0
tb.par.height = 2.0
sal['cono'] = dict(radios=radios_por('y'), bbox_y=bbox_y_eje('y'))
# height escala el eje
tb.par.radx = 0.5
tb.par.rady = 0.5
tb.par.height = 4.0
sal['height4'] = dict(bbox=dict(P_0=bbox_y_eje('x'), P_1=bbox_y_eje('y'), P_2=bbox_y_eje('z')))
tb.par.height = 2.0
# orient mueve el eje del cono (mismo perfil de radios sobre otro eje)
tb.par.radx = 0.2
tb.par.rady = 1.0
rx = {}
for o in ('x', 'z'):
    tb.par.orient = o
    rx['orient_%s' % o] = radios_por(o)
tb.par.orient = 'y'
sal['orient'] = rx
# seam: U abierta duplica la ultima columna
tb.par.closedu = False
sal['u_abierta'] = topo()
tb.par.closedu = True
# endcaps: abanico de cols-2 triangulos
tb.par.endcaps = True
sal['caps_on'] = topo()
tb.par.endcaps = False
# tabla surftype
tabla = {}
for st in ('rows', 'cols', 'triangles', 'points', 'quads'):
    tb.par.surftype = st
    tabla[st] = topo()
sal['surftype'] = tabla
tb.par.surftype = 'quads'
# atributos: default solo P; normal point -> N; texture point -> Tex
sal['attrs_default'] = dict(normal=str(tb.par.normal.eval()), texture=str(tb.par.texture.eval()),
                            attrs=attrs())
tb.par.normal = 'pointNormals'
sal['attrs_n'] = attrs()
tb.par.texture = 'point'
sal['attrs_tex'] = attrs()
print('<<JSON>>' + json.dumps(sal))
""")
res = d or {}
report["tube"] = res
chek("default cols=40 rows=10 quads -> 400 pts / 360 prims (= (rows-1)*cols)",
     ok and (res.get("default") or {}).get("topo") == {"pts": 400, "prims": 360}
     and (res.get("default") or {}).get("pars", {}).get("cols") == 40
     and (res.get("default") or {}).get("pars", {}).get("rows") == 10, res)
chek("cols=8 rows=4 quads -> EXACTO 32 pts / 24 prims", ok and res.get("c8r4") == {"pts": 32, "prims": 24}, res)
cono = (res.get("cono") or {}).get("radios") or {}
chek("radx/rady son radios de EXTREMOS (cono 0.2->1.0) con interpolacion lineal exacta",
     ok and cono == {"-1.0": [0.2, 0.2], "-0.33": [0.467, 0.467],
                     "0.33": [0.733, 0.733], "1.0": [1.0, 1.0]}, res)
hb = ((res.get("height4") or {}).get("bbox") or {})
chek("height escala el eje: height=4 -> Y=[-2,2] con XZ en [-0.5,0.5]",
     ok and hb.get("P_1") == [-2.0, 2.0] and hb.get("P_0") == [-0.5, 0.5]
     and hb.get("P_2") == [-0.5, 0.5], res)
ori = res.get("orient") or {}
chek("orient x/z mueven el eje: mismo perfil de radios {0.2..1.0} sobre X y sobre Z",
     ok and (ori.get("orient_x") or {}) == {"1.0": [0.2, 0.2], "0.33": [0.467, 0.467],
                                            "-0.33": [0.733, 0.733], "-1.0": [1.0, 1.0]}
     and (ori.get("orient_z") or {}) == {"-1.0": [0.2, 0.2], "-0.33": [0.467, 0.467],
                                         "0.33": [0.733, 0.733], "1.0": [1.0, 1.0]}, res)
chek("closedu=False abre el seam: +4 pts (=rows) con las MISMAS 24 prims",
     ok and res.get("u_abierta") == {"pts": 36, "prims": 24}, res)
chek("endcaps agrega EXACTAMENTE cols-2 = 6 prims (una tapa) sin puntos nuevos",
     ok and res.get("caps_on") == {"pts": 32, "prims": 30}, res)
chek("tabla surftype 8x4 (sin caps): rows=4, cols=8, triangles=48, points=32, quads=24",
     ok and (res.get("surftype") or {}) == {"rows": {"pts": 32, "prims": 4},
                                            "cols": {"pts": 32, "prims": 8},
                                            "triangles": {"pts": 32, "prims": 48},
                                            "points": {"pts": 32, "prims": 32},
                                            "quads": {"pts": 32, "prims": 24}}, res)
ad = res.get("attrs_default") or {}
chek("attrs default SOLO P (los de clase vert no llegan al poptoCHOP); "
     "normal=pointNormals crea N y texture=point crea Tex",
     ok and ad.get("attrs") == ["P"] and res.get("attrs_n") == ["N", "P"]
     and res.get("attrs_tex") == ["N", "P", "Tex"], res)

# ── 2. estado canónico + material + cámara + PNG + guardia ──
g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "pointspriteMAT", "name": "mat"},
          note="material")
bad, got = set_and_verify(g, ROOT + "/geo/mat", {"pointsize": 6.0, "colorr": 0.4, "colorg": 1.0, "colorb": 0.55},
                          "material verde")
chek("pars del material aplicados (C4)", not bad, got)
ok, d = g.exec_code(CHAIN + """
import json
import time
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
tb = op(ROOT + '/geo/tb')
tb.par.cols = 8
tb.par.rows = 4
tb.par.surftype = 'quads'
tb.par.endcaps = False
tb.par.closedu = True
tb.par.orient = 'y'
tb.par.radx = 0.2
tb.par.rady = 1.0
tb.par.height = 2.0
tb.cook(force=True)
geo.par.material = geo.op('mat')
# camara canonica del gauntlet: lookat al geometryCOMP + posicion iso (2,2,2)
cam.par.lookat = geo
cam.par.tx, cam.par.ty, cam.par.tz = 2.0, 2.0, 2.0
ren.par.geometry = geo
ren.par.camera = cam
settle(4)
print('<<JSON>>' + json.dumps(dict(mat=str(geo.par.material.eval()),
                                   lookat=str(cam.par.lookat.eval()),
                                   pos=[round(cam.par.tx.eval(), 2), round(cam.par.ty.eval(), 2),
                                        round(cam.par.tz.eval(), 2)],
                                   n=tb.numPoints(), p=tb.numPrims())))
""")
chek("estado canónico (cono 8x4 quads) + material + cámara lookat iso",
     ok and "mat" in str((d or {}).get("mat", "")) and (d or {}).get("n") == 32
     and (d or {}).get("p") == 24 and str((d or {}).get("lookat", "")).endswith("/geo")
     and (d or {}).get("pos") == [2.0, 2.0, 2.0], d)
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_tube.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

ok, d = g.exec_code(CHAIN + """
import json
import time
tbp = op(ROOT + '/geo/tb')
settle(3)
time.sleep(1.5)
antes = px()
print('<<JSON>>' + json.dumps(dict(px_antes=antes, guardia=list(render_is_ours(tbp)))))
""")
d = d or {}
guardia = d.get("guardia") or []
chek("el render subió la geometría (px > 0 antes de la guardia)", (d.get("px_antes") or 0) > 0,
     {"px": d.get("px_antes")})
chek("los px son del tube (guardia: apagar el terminal → 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-tube-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_tube ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| fallos:", g.failures)
print("tube:", json.dumps(report.get("tube", {}), ensure_ascii=False))
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

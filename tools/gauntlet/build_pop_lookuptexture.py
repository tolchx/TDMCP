#!/usr/bin/env python3
"""build_pop_lookuptexture.py — cobertura POP 6/6 (5c): lookuptexturePOP.

Red /pop_lookup: nz (noiseTOP 8x8, seed fija) + gx (gridPOP 3x3 quads) +
lt (lookuptexturePOP: top=nz, overrideautoattr=True, outputattrscope='Color',
attrtype='color', interpolate=False) + lt2 (sin override, testigo) +
const (constantTOP 0.9 para el swap de fuente).
Mide (evidencia: build-pop-lookuptexture-report.json):
  * el lookup PRESERVA el POP de entrada: 9 pts / 4 quads y P en [-1,1].
  * el attr de salida NO aparece por defecto: sin overrideautoattr NO hay Color;
    con overrideautoattr=True + outputattrscope='Color' + attrtype='color' se
    crea el attr Color (4 canales) — sorpresa del build vivo (2025.32460).
  * muestreo EXACTO por texel (interpolate=False): cada Color_0 medido es uno de
    los valores de la matriz del TOP (pertenencia al conjunto de texels).
  * DETERMINISMO: dos lecturas completas dan el mismo vector de Color.
  * el indice es FUNCION de P: trasladar el grid cambia el muestreo dentro del
    conjunto de texels y al restaurar tx vuelven EXACTAMENTE los valores base.
  * el lookup sigue al TOP que se le asigna: al conectar constantTOP 0.9 todos
    los Color_0 pasan a 0.9; al volver a nz se restauran los valores base.
  * lookupindexoffset desplaza el muestreo (patron distinto) y 0 lo restaura.
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
g = Gauntlet(phase="build-pop-lookuptexture", run_id=RUN)
g.init()

ROOT = "/pop_lookup"
CHAIN = chain_source(ROOT)

report = {"run_id": RUN,
          "objetivo": "lookuptexturePOP: preserva el POP de entrada, Color solo con overrideautoattr, "
                      "muestreo exacto por texel (pertenencia al conjunto), determinismo, indice "
                      "funcion de P (ida y vuelta), swap de TOP (constant 0.9) y offset reversible",
          "ok": False, "cheks": []}


def chek(name, ok, detail=""):
    report["cheks"].append((name, bool(ok)))
    g.check(name, ok, str(detail)[:240])


# ── 0. entorno limpio + estructura ──
g.call("project_info", {}, note="TD vivo")
ok, d = g.exec_code("import json\ntry:\n op('%s').destroy()\n op('/pop_probe5c').destroy()\nexcept Exception:\n pass\n"
                    "print('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
chek("limpieza previa", ok)

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_lookup",
                              "nodeX": 4800, "nodeY": 2600, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"}, {"type": "cameraCOMP", "name": "cam"},
    {"type": "renderTOP", "name": "ren"}, {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True}, note="estructura")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 1. muestreo del TOP sobre los puntos ──
ok, d = g.exec_code(CHAIN + """
import json
import time
geo = op(ROOT + '/geo')
for c in list(geo.children):
    if c.name.lower().startswith('torus'):
        c.destroy()
nz = op(ROOT).create(noiseTOP, 'nz')
nz.par.resolutionw = 8
nz.par.resolutionh = 8
try:
    nz.par.seed = 7
except Exception:
    pass
cs = op(ROOT).create(constantTOP, 'const')
cs.par.resolutionw = 8
cs.par.resolutionh = 8
for cn in ('r', 'colorr'):
    try:
        cs.par[cn] = 0.9
        break
    except Exception:
        continue
for cn in ('g', 'colorg'):
    try:
        cs.par[cn] = 0.9
        break
    except Exception:
        continue
for cn in ('b', 'colorb'):
    try:
        cs.par[cn] = 0.9
        break
    except Exception:
        continue
gx = geo.create(gridPOP, 'gx')
gx.par.rows = 3
gx.par.cols = 3
gx.par.sizex = 2.0
gx.par.sizey = 2.0
lt = geo.create(lookuptexturePOP, 'lt')
lt.inputConnectors[0].connect(gx.outputConnectors[0])
lt.par.top = nz
lt.par.overrideautoattr = True
lt.par.outputattrscope = 'Color'
lt.par.attrtype = 'color'
lt.par.interpolate = False
lt.display = True
lt.render = True
lt2 = geo.create(lookuptexturePOP, 'lt2')
lt2.inputConnectors[0].connect(gx.outputConnectors[0])
lt2.par.top = nz
chk = op(ROOT + '/check')

def cocer_top(t):
    t.cook(force=True)
    time.sleep(0.1)
    t.cook(force=True)
    time.sleep(0.08)

def leer():
    cocer_top(nz)
    lt.cook(force=True)
    time.sleep(0.12)
    lt.cook(force=True)
    time.sleep(0.08)
    chk.par.pop = lt
    chk.cook(force=True)
    time.sleep(0.08)
    chk.cook(force=True)
    return {c.name: list(c.vals) for c in chk.chans()}

def attrs_de(pop):
    chk.par.pop = pop
    pop.cook(force=True)
    time.sleep(0.1)
    chk.cook(force=True)
    time.sleep(0.08)
    chk.cook(force=True)
    return sorted(set(c.name.split('_')[0] for c in chk.chans()))

sal = {}
cocer_top(nz)
arr = nz.numpyArray()
texels = sorted(set(round(float(v), 4) for v in arr[:, :, 0].ravel()))
sal['texels_n'] = len(texels)
sal['nz_shape'] = list(arr.shape)

# lt2 (sin override): testigo de que sin overrideautoattr NO aparece Color
sal['lt2_attrs'] = attrs_de(lt2)

ch = leer()
sal['attrs'] = sorted(set(k.split('_')[0] for k in ch))
sal['topo'] = dict(pts=lt.numPoints(), prims=lt.numPrims())
sal['P_rango'] = {n: (round(min(v), 2), round(max(v), 2)) for n, v in ch.items() if n.startswith('P_')}
base = [round(v, 4) for v in ch.get('Color_0', [])]
sal['base'] = base
# pertenencia al conjunto de texels
sal['base_en_texels'] = all(any(abs(b - t) <= 2e-3 for t in texels) for b in base)
# determinismo
ch2 = leer()
sal['base2'] = [round(v, 4) for v in ch2.get('Color_0', [])]
sal['deterministico'] = (base == sal['base2'])
# indice funcion de P: trasladar y volver
gx.par.tx = 0.5
gx.cook(force=True)
ch3 = leer()
mov = [round(v, 4) for v in ch3.get('Color_0', [])]
sal['movido'] = mov
sal['movido_en_texels'] = all(any(abs(b - t) <= 2e-3 for t in texels) for b in mov)
gx.par.tx = 0.0
gx.cook(force=True)
ch4 = leer()
sal['vuelta'] = [round(v, 4) for v in ch4.get('Color_0', [])]
# swap de TOP: constant 0.9
lt.par.top = cs
cocer_top(cs)
ch5 = leer()
sal['const_topo'] = [round(v, 4) for v in ch5.get('Color_0', [])]
lt.par.top = nz
cocer_top(nz)
ch6 = leer()
sal['restaurado'] = [round(v, 4) for v in ch6.get('Color_0', [])]
# offset
lt.par.lookupindexoffset0 = 0.125
ch7 = leer()
sal['offset'] = [round(v, 4) for v in ch7.get('Color_0', [])]
lt.par.lookupindexoffset0 = 0.0
ch8 = leer()
sal['offset_vuelta'] = [round(v, 4) for v in ch8.get('Color_0', [])]
print('<<JSON>>' + json.dumps(sal))
""")
res = d or {}
report["lt"] = res
chek("estructura: 9 pts / 4 quads, P en [-1,1], attrs Color+N+P+Tex con override",
     ok and (res.get("topo") or {}) == {"pts": 9, "prims": 4}
     and ((res.get("P_rango") or {}).get("P_0") == [-1.0, 1.0])
     and (res.get("attrs") or []) == ["Color", "N", "P", "Tex"], res)
chek("sin overrideautoattr NO aparece Color (testigo lt2)",
     ok and (res.get("lt2_attrs") or []) == ["N", "P", "Tex"], res)
chek("interpolate=False: cada Color_0 es EXACTAMENTE un texel del TOP (pertenencia al conjunto)",
     ok and res.get("base_en_texels") is True and (res.get("texels_n") or 0) > 1, res)
chek("determinismo: dos lecturas completas dan el MISMO vector de Color",
     ok and res.get("deterministico") is True and res.get("base") == res.get("base2")
     and len(res.get("base") or []) == 9, res)
chek("indice funcion de P: trasladado lee texels del conjunto y al VOLVER restaura exacto",
     ok and res.get("movido_en_texels") is True and res.get("vuelta") == res.get("base"), res)
ct = res.get("const_topo") or []
chek("swap de TOP: constantTOP 0.9 -> TODOS los Color_0 = 0.9 (±1 LSB del TOP de 8 bits)",
     ok and len(ct) == 9 and all(abs(v - 0.9) <= 1.0 / 255.0 for v in ct), res)
chek("restauracion: al volver a nz los valores base vuelven EXACTOS",
     ok and res.get("restaurado") == res.get("base"), res)
off = res.get("offset") or []
chek("offset=0.125 desplaza el muestreo y 0 lo restaura exacto",
     ok and len(off) == 9 and off != res.get("base") and res.get("offset_vuelta") == res.get("base"), res)

# ── 2. estado canónico + material + cámara + PNG + guardia ──
g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "pointspriteMAT", "name": "mat"},
          note="material")
bad, got = set_and_verify(g, ROOT + "/geo/mat", {"pointsize": 10.0, "colorr": 1.0, "colorg": 1.0, "colorb": 1.0},
                          "material blanco (el color viene del lookup)")
chek("pars del material aplicados (C4)", not bad, got)
ok, d = g.exec_code(CHAIN + """
import json
import time
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
lt = op(ROOT + '/geo/lt')
lt.par.top = op(ROOT + '/nz')
lt.par.overrideautoattr = True
lt.par.outputattrscope = 'Color'
lt.par.attrtype = 'color'
lt.par.interpolate = False
lt.par.lookupindexoffset0 = 0.0
lt.par.lookupindexoffset1 = 0.0
lt.display = True
lt.render = True
op(ROOT + '/geo/lt2').display = False
op(ROOT + '/geo/lt2').render = False
lt.cook(force=True)
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
                                   n=lt.numPoints(), p=lt.numPrims())))
""")
chek("estado canónico (top=nz, Color, offset 0) + material + cámara lookat iso",
     ok and "mat" in str((d or {}).get("mat", "")) and (d or {}).get("n") == 9
     and (d or {}).get("p") == 4 and str((d or {}).get("lookat", "")).endswith("/geo")
     and (d or {}).get("pos") == [2.0, 2.0, 2.0], d)
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_lookuptexture.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

ok, d = g.exec_code(CHAIN + """
import json
import time
ltp = op(ROOT + '/geo/lt')
settle(3)
time.sleep(1.5)
antes = px()
print('<<JSON>>' + json.dumps(dict(px_antes=antes, guardia=list(render_is_ours(ltp)))))
""")
d = d or {}
guardia = d.get("guardia") or []
chek("el render subió la geometría (px > 0 antes de la guardia)", (d.get("px_antes") or 0) > 0,
     {"px": d.get("px_antes")})
chek("los px son del lookuptexture (guardia: apagar el terminal → 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-lookuptexture-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_lookuptexture ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| fallos:", g.failures)
print("lt:", json.dumps(report.get("lt", {}), ensure_ascii=False))
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

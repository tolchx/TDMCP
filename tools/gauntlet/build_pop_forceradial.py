#!/usr/bin/env python3
"""build_pop_forceradial.py — cobertura POP 5d-2: forceradialPOP.

Red /pop_forceradial: gridPOP 3x3 (escala de medicion) -> forceradialPOP -> poptoCHOP,
mas un mathcombinePOP que calcula un escalar por punto (Dist2 = dot(P,P)) para medir la
pagina `map` (escalar de otro POP -> parametro de fuerza).

Medido en TD 2025.32460 (MCP oficial 1.1.55):
  * El tipo se llama `forceradialPOP` (minuscula). El nombre de la doc/indice KB
    `forceRadialPOP` NO existe en este build: create_operator devuelve isError.
  * Defaults: radial=True, radialstrength=1.0, direction=(0,1,0), falloff='scurve',
    falloffradius=2.0, globforce=(0,-0.1,0), globforcemult=0, spiral=False.
  * Pasa los puntos tal cual (npts 9 -> 9) y AGREGA el atributo `PartForce`
    (attrs de salida: P, N, Tex, PartForce).
  * radial con strength 1: en r=1 el modulo es 1.0 exacto y la direccion es la radial
    unitaria; en r=sqrt(2) cada eje vale 0.44769 (|F|=0.6331). La curva del falloff
    NO es la smoothstep clasica con plateau 0.5 (esa predeciria 0.6274): el modelo
    queda abierto y se documenta la tabla medida.
  * Singularidad del centro: en r=0 la direccion radial no existe y la fuerza cae a
    `direction` normalizado con strength pleno -> (0,1,0) con strength 1, (0,2,0) con 2.
  * strength es LINEAL: 2.0 duplica exacto (2.0 y 0.89538).
  * spiral gira la fuerza +90 grados en el plano perpendicular a `direction`.
    GOTCHA del tutorial CONFIRMADA: con direction=(0,0,0) la salida es PartForce=0 en
    TODOS los puntos (no hay eje). Con direction=(0,0,1) gira en XY. En el centro la
    espiral da 0 (a diferencia de la radial).
  * globforce se multiplica por globforcemult y NO pasa por el falloff: con mult=0
    (default) globforce no hace nada; con globforcez=2 y mult=1 da (0,-0.1,2) constante.
  * Pagina `map`: map0op + map0element (el menu se vuelve dinamico y lista los atributos
    del op: aparece `Dist2`) + map0parm + map0combineop='set' reemplaza el parametro
    POR PUNTO: con globforcez=2 y Dist2=dot(P,P) sale PartForce.z = 2*Dist2 (4/2/0).
    El par `globforcemult` sigue leyendose 1.0 (el map no escribe el par, lo pisa por
    punto) y el toggle `map` se lee 0 aunque el mapeo funciona: no hace falta prenderlo.
  * layout: nodos separados por profundidad (base + geo), auditado sin solapamientos.
  * render: grilla densa + pointspriteMAT; camara iso (4,4,4) con lookat al geo.
"""
from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gauntlet_client import Gauntlet  # noqa: E402
from td_layout import tidy  # noqa: E402
from td_probe import chain_source, png_stats, set_and_verify  # noqa: E402

RUN = os.environ.get("GAUNTLET_RUN_ID") or time.strftime("%Y%m%d-%H%M%S")
g = Gauntlet(phase="build-pop-forceradial", run_id=RUN)
g.init()

ROOT = "/pop_forceradial"
CHAIN = chain_source(ROOT)

report = {"run_id": RUN,
          "objetivo": "forceradialPOP: radial/spiral/global, gotcha direction=000, "
                      "falloff medido, singularity del centro y pagina map (escalar -> fuerza)",
          "ok": False, "cheks": []}


def chek(name, ok, detail=""):
    report["cheks"].append((name, bool(ok)))
    g.check(name, ok, str(detail)[:240])


def call_retry(tool, args, note, tries=4, wait=1.5):
    r = {}
    for _ in range(tries):
        r = g.call(tool, args, note)
        if not g.is_err(r):
            return r
        time.sleep(wait)
    g.fail("fallo la tool %s (%s) tras %d intentos" % (tool, note, tries))
    return r


# ── 0. entorno limpio + estructura ──
g.call("project_info", {}, note="TD vivo")
ok, d = g.exec_code("import json\ntry:\n op(%r).destroy()\nexcept Exception:\n pass\n"
                    "print('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
chek("limpieza previa", ok)

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_forceradial",
                              "nodeX": 6000, "nodeY": 2600, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"}, {"type": "cameraCOMP", "name": "cam"},
    {"type": "renderTOP", "name": "ren"}, {"type": "nullTOP", "name": "null_view"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True}, note="estructura")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 1. contrato del NOMBRE del tipo ──
r_bad = g.call("create_operator", {"parent_path": ROOT + "/geo", "type": "forceRadialPOP",
                                   "name": "nombre_doc"}, note="forceRadialPOP (nombre de la doc)")
chek("el nombre de la doc `forceRadialPOP` NO existe en este build (isError)", g.is_err(r_bad),
     g.text_of(r_bad)[:160])
g.call("delete_operator", {"path": ROOT + "/geo/nombre_doc"}, note="limpieza del intento invalido")

g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "forceradialPOP", "name": "fr"},
          note="forceradialPOP (nombre real)")
# C2: el geometryCOMP auto-crea un torusPOP que DIBUJA y enmascara el render.
ok, d = g.exec_code(CHAIN + """
import json
geo = op(ROOT + '/geo')
borrados = []
for c in list(geo.children):
    if c.OPType == 'torusPOP' or c.name.lower().startswith('torus'):
        borrados.append(c.name)
        c.destroy()
print('<<JSON>>' + json.dumps({'borrados': borrados,
                              'quedan': [c.name for c in geo.children if c.OPType == 'torusPOP']}))
""")
d = d or {}
chek("geo sin el torusPOP auto-creado (C2: enmascara el render)",
     ok and not d.get("quedan"), d)
g.call_ok("build_network", {"parent_path": ROOT + "/geo", "operators": [
    {"type": "gridPOP", "name": "src"}, {"type": "poptoCHOP", "name": "chk"},
    {"type": "mathcombinePOP", "name": "mc"}, {"type": "poptoCHOP", "name": "chk2"},
    {"type": "convertPOP", "name": "topoints"}],
    "connections": [], "auto_layout": True}, note="cadena de medicion")

# ── 2. medicion numerica por configuracion ──
ok, d = g.exec_code(CHAIN + """
import json, time
geo = op(ROOT + '/geo')
src, fr, chk, mc, chk2 = (geo.op('src'), geo.op('fr'), geo.op('chk'),
                          geo.op('mc'), geo.op('chk2'))
src.par.rows = 3
src.par.cols = 3
src.par.sizex = 2.0
src.par.sizey = 2.0
src.par.tz = 0.0
src.outputConnectors[0].connect(fr.inputConnectors[0])
src.outputConnectors[0].connect(mc.inputConnectors[0])
chk.par.pop = fr
chk2.par.pop = mc

# escalar por punto para la pagina map: Dist2 = dot(P,P)
mc.par.comb.sequence.numBlocks = 1
mc.par.comb0oper = 'dot'
mc.par.comb0scopea = 'P'
mc.par.comb0scopeb = 'P'
mc.par.comb0result = 'Dist2'

def v(name):
    try:
        return fr.par[name].eval()
    except Exception as e:
        return 'ERR:' + str(e)

out = {'defaults': {n: v(n) for n in ('radial', 'radialstrength', 'spiral', 'spiralstrength',
                                     'directionx', 'directiony', 'directionz', 'falloff',
                                     'falloffradius', 'globforcex', 'globforcey', 'globforcez',
                                     'globforcemult', 'posx', 'posy', 'posz')},
       'falloff_menu': list(fr.par['falloff'].menuLabels),
       'src_npts': src.numPoints()}

def snap(tag, extra=None):
    fr.cook(force=True)
    mc.cook(force=True)
    time.sleep(0.1)
    chk.cook(force=True)
    chk2.cook(force=True)
    time.sleep(0.05)
    chk.cook(force=True)
    chk2.cook(force=True)
    r = {'tag': tag,
         'err': fr.errors(), 'mc_err': mc.errors(), 'npts': fr.numPoints(),
         'attrs': [a.name for a in fr.pointAttributes],
         'force': {c.name: [round(float(x), 5) for x in c.vals]
                   for c in chk.chans() if c.name.startswith('PartForce')},
         'pos': {c.name: [round(float(x), 5) for x in c.vals]
                 for c in chk.chans() if c.name.startswith('P_')},
         'dist2': {c.name: [round(float(x), 5) for x in c.vals]
                   for c in chk2.chans() if c.name.startswith('Dist2')}}
    if extra:
        r.update(extra)
    return r

S = {}
# A: default (radial ON, strength 1)
S['A_default'] = snap('A')
# B: strength 2 -> linealidad
fr.par.radialstrength = 2.0
S['B_radial2'] = snap('B')
# C: todas las fuerzas apagadas
fr.par.radial = False
fr.par.radialstrength = 1.0
S['C_all_off'] = snap('C')
# D: spiral con direction=(0,0,0) -> gotcha del tutorial
fr.par.spiral = True
fr.par.spiralstrength = 1.0
fr.par.directionx, fr.par.directiony, fr.par.directionz = 0.0, 0.0, 0.0
S['D_spiral_dir000'] = snap('D')
# E: spiral con direction=(0,0,1)
fr.par.directionz = 1.0
S['E_spiral_dir001'] = snap('E')
# F: globforce z=2 con globforcemult default 0 (gate)
fr.par.spiral = False
fr.par.globforcez = 2.0
S['F_global_mult0'] = snap('F')
# G: globforce z=2 con globforcemult 1
fr.par.globforcemult = 1.0
S['G_global_mult1'] = snap('G')
# H: pagina map -> globforcemult desde Dist2
fr.par.map0op = mc
fr.par.map0combineop = 'set'
out['map_menu_dinamico'] = list(fr.par['map0element'].menuLabels)
fr.par.map0element = 'Dist2'
fr.par.map0parm = 'globforcemult'
out['map_pars'] = {'op': str(fr.par.map0op.eval()), 'element': str(fr.par.map0element.eval()),
                   'parm': str(fr.par.map0parm.eval()),
                   'combine': str(fr.par.map0combineop.eval()),
                   'map_toggle': int(fr.par.map.eval())}
S['H_map_dist2'] = snap('H', {'mult_leido': float(fr.par['globforcemult'].eval())})
out['snaps'] = S
print('<<JSON>>' + json.dumps(out))
""")
res = d or {}
report["medicion"] = res
snaps = res.get("snaps") or {}
defaults = res.get("defaults") or {}


def force(tag, axis=0):
    s = snaps.get(tag) or {}
    return ((s.get("force") or {}).get("PartForce_%d" % axis)) or []


def pos(tag, axis=0):
    s = snaps.get(tag) or {}
    return ((s.get("pos") or {}).get("P_%d" % axis)) or []


def near(a, b, tol=1e-3):
    return len(a) == len(b) and all(abs(float(x) - float(y)) <= tol for x, y in zip(a, b))


# orden de la grilla 3x3 medida: (x,-1) -> (1,-1) -> ... x varia primero
def val(tag, i_axis, idx):
    return force(tag, i_axis)[idx] if len(force(tag, i_axis)) > idx else None


fx, fy, fz = force("A_default", 0), force("A_default", 1), force("A_default", 2)

chek("defaults medidos: radial ON, strength 1, direction (0,1,0), falloff scurve radius 2, "
     "globforce (0,-0.1,0), globforcemult 0",
     defaults.get("radial") is True and abs(float(defaults.get("radialstrength")) - 1.0) < 1e-6
     and (defaults.get("directionx"), defaults.get("directiony"), defaults.get("directionz")) == (0.0, 1.0, 0.0)
     and defaults.get("falloff") == "scurve" and abs(float(defaults.get("falloffradius")) - 2.0) < 1e-6
     and abs(float(defaults.get("globforcey")) + 0.1) < 1e-6
     and abs(float(defaults.get("globforcemult"))) < 1e-6,
     defaults)

chek("parte el input sin crear puntos (3x3=9) y AGREGA el atributo PartForce",
     ok and res.get("src_npts") == 9 and (snaps.get("A_default") or {}).get("npts") == 9
     and "PartForce" in ((snaps.get("A_default") or {}).get("attrs") or []),
     {"src": res.get("src_npts"), "fr": (snaps.get("A_default") or {}).get("npts"),
      "attrs": (snaps.get("A_default") or {}).get("attrs")})

# indices: 0=(-1,-1) 1=(0,-1) 2=(1,-1) 3=(-1,0) 4=(0,0) 5=(1,0) 6=(-1,1) 7=(0,1) 8=(1,1)
chek("radial en r=1 (puntos cardinales): fuerza radial unitaria exacta",
     ok and near([fx[5], fy[7], fx[3], fy[1]], [1.0, 1.0, -1.0, -1.0], 1e-4)
     and near([fy[5], fx[7], fy[3], fx[1]], [0.0, 0.0, 0.0, 0.0], 1e-4),
     {"x": fx, "y": fy})

chek("radial en r=sqrt(2): cada eje 0.44769 (|F| 0.6331) y direccion radial conservada",
     ok and near([fx[0], fy[0]], [-0.44769, -0.44769], 1e-4)
     and near([fx[2], fy[2]], [0.44769, -0.44769], 1e-4)
     and near([fx[6], fy[6]], [-0.44769, 0.44769], 1e-4)
     and near([fx[8], fy[8]], [0.44769, 0.44769], 1e-4),
     {"esq": [fx[0], fy[0], fx[8], fy[8]]})

mod_r2 = (fx[0] ** 2 + fy[0] ** 2) ** 0.5 if len(fx) > 0 and len(fy) > 0 else 0.0
chek("falloff: |F| en r=sqrt(2) = 0.6331 y NO coincide con la smoothstep clasica con plateau "
     "0.5 (0.6274) ni con un falloff lineal (0.2929) -> curva propia, tabla medida",
     ok and abs(mod_r2 - 0.6331) < 2e-3 and abs(mod_r2 - 0.6274) > 3e-3
     and abs(mod_r2 - 0.29289) > 3e-3,
     {"modulo_r2": round(mod_r2, 5), "smoothstep_predeciria": 0.6274, "lineal_predeciria": 0.29289})

chek("GOTCHA singularidad: en el centro r=0 la radial cae a `direction` normalizado con "
     "strength pleno -> (0,1,0)",
     ok and near([fx[4], fy[4], fz[4]], [0.0, 1.0, 0.0], 1e-4), {"centro": [fx[4], fy[4], fz[4]]})

bx, by = force("B_radial2", 0), force("B_radial2", 1)
chek("radialstrength es LINEAL: strength 2 duplica exacto (2.0 y 0.89538)",
     ok and near([bx[5], bx[0], by[4]], [2.0, -0.89538, 2.0], 1e-4),
     {"x": bx[:2], "y_centro": by[4]})

gx, gy, gz = force("C_all_off", 0), force("C_all_off", 1), force("C_all_off", 2)
chek("con todas las fuerzas apagadas PartForce = 0 en los 9 puntos",
     ok and len(gx) == 9 and all(abs(v) < 1e-6 for v in gx + gy + gz), {"x": gx, "z": gz})

dx, dy, dz = force("D_spiral_dir000", 0), force("D_spiral_dir000", 1), force("D_spiral_dir000", 2)
chek("GOTCHA del tutorial CONFIRMADA: spiral con direction=(0,0,0) -> PartForce=0 en TODOS "
     "los puntos", ok and len(dx) == 9 and all(abs(v) < 1e-6 for v in dx + dy + dz),
     {"x": dx})

ex_, ey = force("E_spiral_dir001", 0), force("E_spiral_dir001", 1)
chek("spiral con direction=(0,0,1) gira la fuerza +90 grados: (1,0)->(0,1) y (0,1)->(-1,0)",
     ok and near([ex_[5], ey[5], ex_[7], ey[7]], [0.0, 1.0, -1.0, 0.0], 1e-4),
     {"x": ex_, "y": ey})

chek("spiral en el centro da 0 (a diferencia de la radial, que cae a `direction`)",
     ok and near([ex_[4], ey[4]], [0.0, 0.0], 1e-4), {"centro": [ex_[4], ey[4]]})

fz0 = force("F_global_mult0", 2)
chek("globforce con globforcemult=0 (default) NO hace nada: z=2 con mult 0 -> 0",
     ok and len(fz0) == 9 and all(abs(v) < 1e-6 for v in fz0), {"z": fz0})

gx1, gy1, gz1 = force("G_global_mult1", 0), force("G_global_mult1", 1), force("G_global_mult1", 2)
chek("globforce con mult=1 es constante y NO pasa por el falloff: (0,-0.1,2) en los 9 puntos",
     ok and near(gz1, [2.0] * 9, 1e-4) and near(gy1, [-0.1] * 9, 1e-4)
     and near(gx1, [0.0] * 9, 1e-4), {"y": gy1, "z": gz1})

menu = res.get("map_menu_dinamico") or []
chek("pagina map: el menu de map0element se vuelve dinamico y lista el atributo Dist2 del op",
     ok and "Dist2" in menu, {"menu": menu[:8]})

hv = (snaps.get("H_map_dist2") or {})
d2 = ((hv.get("dist2") or {}).get("Dist2")) or []
hz, hy2 = force("H_map_dist2", 2), force("H_map_dist2", 1)
chek("pagina map: PartForce.z = 2*Dist2 exacto por punto (4/2/0)",
     ok and near(hz, [2.0 * v for v in d2], 1e-4) and near(d2, [2.0, 1.0, 2.0, 1.0, 0.0, 1.0, 2.0, 1.0, 2.0], 1e-4),
     {"z": hz, "dist2": d2})

chek("pagina map: el par globforcemult sigue leyendose 1.0 y el toggle `map` se lee 0 "
     "(el map pisa por punto, no escribe el par)",
     ok and abs(float(hv.get("mult_leido") or 0) - 1.0) < 1e-6
     and (res.get("map_pars") or {}).get("map_toggle") == 0, res.get("map_pars"))

chek("sin errores de cocinado en la medicion",
     ok and not (snaps.get("A_default") or {}).get("err") and not (snaps.get("H_map_dist2") or {}).get("err"),
     {"A": (snaps.get("A_default") or {}).get("err"), "H": (snaps.get("H_map_dist2") or {}).get("err")})

# ── 3. estado canonico + material + camara + PNG + guardia ──
time.sleep(1.5)
g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "pointspriteMAT", "name": "mat"},
          note="material")
bad, got = set_and_verify(g, ROOT + "/geo/mat",
                          {"pointsize": 4.0, "colorr": 0.95, "colorg": 0.45, "colorb": 1.0},
                          "material violeta", call=call_retry)
chek("pars del material aplicados (C4)", not bad, got)

layout_ok, layout_data = tidy(g, roots=[ROOT])
bad_layout = [(p.get("parent"), p.get("overlaps"))
              for p in layout_data.get("parents", []) if p.get("overlaps")]
chek("red sin nodos solapados (layout por profundidad, base + geo)",
     layout_ok and layout_data.get("total") == 0,
     {"total": layout_data.get("total"), "bad": bad_layout})
report["layout"] = {"ok": layout_ok, "total": layout_data.get("total"),
                    "parents": [{"parent": p.get("parent"), "n": p.get("n"),
                                 "overlaps": p.get("overlaps")}
                                for p in layout_data.get("parents", [])]}

ok, d = g.exec_code(CHAIN + """
import json
import time
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
src, fr, tp = geo.op('src'), geo.op('fr'), geo.op('topoints')
# grilla chica para el PNG: puntos separados y legibles
src.par.cols = 7
src.par.rows = 7
src.par.sizex = 3.0
src.par.sizey = 3.0
fr.par.spiral = True
fr.par.spiralstrength = 1.0
fr.par.directionx = 0.0
fr.par.directiony = 0.0
fr.par.directionz = 1.0
fr.par.radial = True
fr.par.radialstrength = 0.6
# C2: el gridPOP emite quads -> el material de puntos pinta una superficie.
# Se convierte a point prims para que el render muestre PUNTOS (no una cara).
tp.par.convert = 'topointprims'
fr.outputConnectors[0].connect(tp.inputConnectors[0])
for o in geo.children:
    o.display = False
    o.render = False
tp.display = True
tp.render = True
geo.par.material = geo.op('mat')
cam.par.lookat = geo
cam.par.tx, cam.par.ty, cam.par.tz = 4.0, 4.0, 4.0
ren.par.geometry = geo
ren.par.camera = cam
settle(3)
print('<<JSON>>' + json.dumps(dict(mat=str(geo.par.material.eval()),
                                   lookat=str(cam.par.lookat.eval()),
                                   convert=str(tp.par.convert.eval()), n=tp.numPoints())))
""")
d = d or {}
chek("estado canonico: material + camara lookat=geo iso(4,4,4) + convert a pointprims + 49 puntos",
     ok and "mat" in str(d.get("mat", "")) and "geo" in str(d.get("lookat", ""))
     and d.get("convert") == "topointprims" and d.get("n") == 49, d)
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "medium"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_forceradial.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real y en PUNTOS (49 pt -> ~46 px encendidos a 171x96; una "
     "superficie rellena daba 4.865)",
     bool(png) and 30 <= st.get("px_lit", 0) < 2000, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

ok, d = g.exec_code(CHAIN + """
import json
import time
tp = op(ROOT + '/geo/topoints')
settle(3)
time.sleep(1.0)
antes = px()
print('<<JSON>>' + json.dumps(dict(px_antes=antes, guardia=list(render_is_ours(tp)))))
""")
d = d or {}
guardia = d.get("guardia") or []
chek("el render subio los puntos (px > 0 antes de la guardia)", (d.get("px_antes") or 0) > 0,
     {"px": d.get("px_antes")})
chek("los px son del forceradial (guardia: apagar el terminal -> 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-forceradial-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_forceradial ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| fallos:", g.failures)
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

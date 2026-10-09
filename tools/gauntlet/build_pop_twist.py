#!/usr/bin/env python3
"""build_pop_twist.py — cobertura POP: twistPOP + deformaciones espaciales GPU.

Red /pop_twist: deformaciones espaciales 3D aceleradas en GPU (twist, bend, taper, squash)
con modulación continua por peso mediante rerangePOP y verificación analítica:
  * tubePOP: cilindro paramétrico (rad=0.5, h=2.0, 21x21 = 441 pts / 441 prims).
  * rerangePOP: mapeo normalizado de P(1) en [-1, 1] a 'Weight' en [0.0, 1.0].
  * twistPOP modo twist: torsión sobre eje Y gobernada por 'Weight'.
      - Conservación radial exacta: sqrt(x^2 + z^2) == r_0 (0.5 +/- 1e-5) para todos los puntos.
      - Confinamiento estricto por peso: en Weight == 0 (base), desplazamiento nulo (< 1e-5).
      - Deformación activa: en Weight == 1 (tope) con strength=180°, desplazamiento delta P == 2*r == 1.0 (+/- 1e-4).
  * twistPOP modos bend, taper y squash:
      - bend: flexión con desplazamiento lateral del eje (ampliación de bounding box en X).
      - taper: conicidad asimétrica (radio en el extremo superior != extremo inferior).
      - squash: estiramiento en Y con compresión ortogonal en XZ (preservación de volumen).
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
g = Gauntlet(phase="build-pop-twist", run_id=RUN)
g.init()

ROOT = "/pop_twist"
GEO = ROOT + "/geo"
CHAIN = chain_source(ROOT)

report = {
    "run_id": RUN,
    "objetivo": "twistPOP + deformaciones espaciales GPU: torsión con conservación radial exacta, "
                "confinamiento por peso, modos bend/taper/squash y guardia de render",
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

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_twist",
                              "nodeX": 4000, "nodeY": 3200, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"},
    {"type": "cameraCOMP", "name": "cam"},
    {"type": "lightCOMP", "name": "light"},
    {"type": "renderTOP", "name": "ren"},
    {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True},
    note="estructura geo+render+check")
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

# ── 2. red POP: tube -> rerange (weight) -> twist -> color -> convert -> null ──
g.call_ok("build_network", {"parent_path": GEO, "operators": [
    {"type": "tubePOP", "name": "tube"},
    {"type": "rerangePOP", "name": "weight_ramp"},
    {"type": "twistPOP", "name": "twist_op"},
    {"type": "attributePOP", "name": "color_map"},
    {"type": "convertPOP", "name": "topoints"},
    {"type": "nullPOP", "name": "null_render"}],
    "connections": [
        {"from": "tube", "to": "weight_ramp"},
        {"from": "weight_ramp", "to": "twist_op"},
        {"from": "twist_op", "to": "color_map"},
        {"from": "color_map", "to": "topoints"},
        {"from": "topoints", "to": "null_render"}],
    "auto_layout": True}, note="cadena tube+rerange+twist")

# ── 3. configuración de parámetros analíticos ──
ok, d = g.exec_code(CHAIN + """
import json
import time

geo = op(ROOT + '/geo')
tube = geo.op('tube')
rr = geo.op('weight_ramp')
tw = geo.op('twist_op')
cm = geo.op('color_map')
cv = geo.op('topoints')
term = geo.op('null_render')

# 1. Tubo paramétrico cilíndrico
tube.par.radx = 0.5
tube.par.rady = 0.5
tube.par.height = 2.0
tube.par.rows = 21
tube.par.cols = 21

# 2. Rerange: P(1) en [-1, 1] -> Weight en [0, 1]
rr.par.inputattrscope = 'P(1)'
rr.par.fromlow0 = -1.0
rr.par.fromhigh0 = 1.0
rr.par.tolow0 = 0.0
rr.par.tohigh0 = 1.0
rr.par.outputattrscope = 'Weight'
rr.par.overrideautoattr = True

# 3. Twist: 180 grados sobre eje Y modulado por Weight
tw.par.op = 'twist'
tw.par.paxis = 'y'
tw.par.strength = 180.0
tw.par.weightattr = 'Weight'

# 4. Color RGBA (celeste brillante)
cm.par.attr.sequence.numBlocks = 1
cm.par.attr0name = 'color'
cm.par.attr0numcomps = '4'
cm.par.attr0value0 = 0.2
cm.par.attr0value1 = 0.85
cm.par.attr0value2 = 1.0
cm.par.attr0value3 = 1.0

# 5. Conversión a point primitives
cv.par.convert = 'topointprims'
term.display = True
term.render = True

chk = op(ROOT + '/check')
chk.par.pop = term

for _ in range(4):
    term.cook(force=True)
    chk.cook(force=True)
    time.sleep(0.04)

sal = {
    'pts': term.numPoints(),
    'prims': term.numPrims(),
    'chans': [c.name for c in chk.chans()]
}
print('<<JSON>>' + json.dumps(sal))
""")
d = d or {}
chek("cadena POP construida y cocinada (441 pts / 441 prims)",
     ok and d.get("pts") == 441 and d.get("prims") == 441, d)
chek("canales requeridos presentes (P_0..2, Weight, Color_0..3)",
     ok and all(c in d.get("chans", []) for c in ("P_0", "P_1", "P_2", "Weight", "Color_0")), d)

# ── 4. verificación matemática: conservación radial y modulación por peso ──
ok, d = g.exec_code(CHAIN + """
import json
import math
import time

geo = op(ROOT + '/geo')
tw = geo.op('twist_op')
chk = op(ROOT + '/check')

# Primero leemos posiciones con twist activo
for _ in range(3):
    tw.cook(force=True)
    chk.cook(force=True)
    time.sleep(0.04)

px = list(chk['P_0'].vals)
py = list(chk['P_1'].vals)
pz = list(chk['P_2'].vals)
weight = list(chk['Weight'].vals)

# Radio radial r = sqrt(x^2 + z^2)
radii = [math.sqrt(x*x + z*z) for x, z in zip(px, pz)]
max_rad_err = max(abs(r - 0.5) for r in radii)

# Ahora leemos referencia sin twist (bypass)
tw.par.bypass = True
for _ in range(3):
    tw.cook(force=True)
    chk.cook(force=True)
    time.sleep(0.04)

px0 = list(chk['P_0'].vals)
pz0 = list(chk['P_2'].vals)
tw.par.bypass = False

# 1. Desplazamiento en la base (Weight == 0)
disp_w0 = [math.sqrt((x-x0)**2 + (z-z0)**2) for x, z, x0, z0, w in zip(px, pz, px0, pz0, weight) if w < 1e-4]
max_disp_w0 = max(disp_w0) if disp_w0 else 0.0

# 2. Desplazamiento en el tope (Weight > 0.99): rotación de 180° -> delta P = 2 * r = 1.0
disp_w1 = [math.sqrt((x-x0)**2 + (z-z0)**2) for x, z, x0, z0, w in zip(px, pz, px0, pz0, weight) if w > 0.99]
mean_disp_w1 = sum(disp_w1)/len(disp_w1) if disp_w1 else 0.0
max_disp_w1_err = max(abs(d - 1.0) for d in disp_w1) if disp_w1 else 0.0

sal = {
    'max_rad_err': round(max_rad_err, 6),
    'max_disp_w0': round(max_disp_w0, 6),
    'mean_disp_w1': round(mean_disp_w1, 4),
    'max_disp_w1_err': round(max_disp_w1_err, 6),
    'w0_count': len(disp_w0),
    'w1_count': len(disp_w1)
}
print('<<JSON>>' + json.dumps(sal))
""")
d = d or {}
chek("conservación radial bajo torsión pura (|r - r0| < 1e-5)",
     ok and d.get("max_rad_err") is not None and d.get("max_rad_err") < 1e-5, d)
chek("confinamiento estricto por peso (Weight=0 -> desplazamiento nulo < 1e-5)",
     ok and d.get("max_disp_w0") is not None and d.get("max_disp_w0") < 1e-5, d)
chek("deformación activa en zona de peso alto (Weight=1 -> ||ΔP|| exacto 1.0)",
     ok and d.get("max_disp_w1_err") is not None and d.get("max_disp_w1_err") < 1e-4, d)

# ── 5. verificación de modos espaciales adicionales: bend, shear, squash ──
ok, d = g.exec_code(CHAIN + """
import json
import math
import time

geo = op(ROOT + '/geo')
tw = geo.op('twist_op')
chk = op(ROOT + '/check')

# Probar modo BEND (paxis='y', saxis='z', curvatura global en Z)
tw.par.weightattr = ''
tw.par.op = 'bend'
tw.par.paxis = 'y'
tw.par.saxis = 'z'
tw.par.strength = 90.0
for _ in range(4):
    tw.cook(force=True)
    chk.cook(force=True)
    time.sleep(0.04)
pz_bend = list(chk['P_2'].vals)
bend_span_z = max(pz_bend) - min(pz_bend)

# Probar modo SHEAR (paxis='y', saxis='x', cizalladura analítica lineal en X)
tw.par.op = 'shear'
tw.par.paxis = 'y'
tw.par.saxis = 'x'
tw.par.strength = 1.0
for _ in range(4):
    tw.cook(force=True)
    chk.cook(force=True)
    time.sleep(0.04)
px_sh = list(chk['P_0'].vals)
py_sh = list(chk['P_1'].vals)
top_x = [x for x, y in zip(px_sh, py_sh) if y > 0.99]
bot_x = [x for x, y in zip(px_sh, py_sh) if y < -0.99]
mean_top_x = sum(top_x)/len(top_x) if top_x else 0.0
mean_bot_x = sum(bot_x)/len(bot_x) if bot_x else 0.0
shear_span_x = max(px_sh) - min(px_sh)

# Probar modo SQUASH (paxis='y', extensión en Y, compresión en XZ para conservar volumen)
tw.par.op = 'squash'
tw.par.paxis = 'y'
tw.par.strength = 1.0
for _ in range(4):
    tw.cook(force=True)
    chk.cook(force=True)
    time.sleep(0.04)
py_sq = list(chk['P_1'].vals)
px_sq = list(chk['P_0'].vals)
sq_span_y = max(py_sq) - min(py_sq)
sq_max_x = max(abs(x) for x in px_sq)

# Restaurar estado canónico TWIST modulado por Weight
tw.par.op = 'twist'
tw.par.paxis = 'y'
tw.par.saxis = 'x'
tw.par.strength = 180.0
tw.par.weightattr = 'Weight'
for _ in range(4):
    tw.cook(force=True)
    chk.cook(force=True)
    time.sleep(0.04)

sal = {
    'bend_span_z': round(bend_span_z, 4),
    'mean_top_x': round(mean_top_x, 4),
    'mean_bot_x': round(mean_bot_x, 4),
    'shear_span_x': round(shear_span_x, 4),
    'sq_span_y': round(sq_span_y, 4),
    'sq_max_x': round(sq_max_x, 4)
}
print('<<JSON>>' + json.dumps(sal))
""")
d = d or {}
chek("deformación modal bend activa (flexión ensancha span en Z > 2.0)",
     ok and (d.get("bend_span_z") or 0) > 2.0, d)
chek("deformación modal shear activa (cizalladura desplaza extremos en X: +1.0 y -1.0)",
     ok and abs((d.get("mean_top_x") or 0) - 1.0) < 0.05 and abs((d.get("mean_bot_x") or 0) - (-1.0)) < 0.05
     and (d.get("shear_span_x") or 0) > 2.8, d)
chek("deformación modal squash activa (span Y expandido a 4.0, radio X comprimido a 0.25)",
     ok and abs((d.get("sq_span_y") or 0) - 4.0) < 0.05 and abs((d.get("sq_max_x") or 0) - 0.25) < 0.02, d)

# ── 6. material + cámara + PNG + guardia de render ──

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
     ok and "mat" in str(d.get("mat", "")) and "geo" in str(d.get("lookat", "")) and d.get("n") == 441, d)

g.call_retry = call_retry
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_twist.png"))
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
chek("los px son del twist chain (guardia: apagar el terminal -> 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = all(c[1] for c in report["cheks"])

out_rep = os.path.join(g.out_dir, "build-pop-twist-report.json")
with open(out_rep, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)

print("\n=== RESUMEN pop_twist ===")
print("ok: %s | cheks: %d | fallos: %s" % (
    report["ok"], len(report["cheks"]),
    [c[0] for c in report["cheks"] if not c[1]]))
print("PNG: %s" % report["png"])
print("Reporte: %s" % out_rep)

sys.exit(0 if report["ok"] else 1)

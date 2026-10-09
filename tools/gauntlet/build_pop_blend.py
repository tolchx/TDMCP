#!/usr/bin/env python3
"""build_pop_blend.py — cobertura POP: blendPOP + cacheblendPOP (GPU Morphing e Interpolación).

Red /pop_blend: interpolación espacial multi-objetivo (shape morphing) en compute shaders GPU:
  * Geometrías base (441 pts / 441 prims cada una):
      - Fuente A: gridPOP plana (Z = 0.0).
      - Fuente B: transformPOP desplazada en Z (+4.0).
      - Fuente C: transformPOP desplazada en X (+6.0).
  * blendPOP (blendtype='proportional'):
      - Interpolación A puro (w=[1, 0, 0]): Z == 0.0 exacto (|err| < 1e-5).
      - Interpolación B puro (w=[0, 1, 0]): Z == 4.0 exacto (|err| < 1e-5).
      - Interpolación media (w=[0.5, 0.5, 0]): Z == 2.0 exacto (|err| < 1e-5).
      - Tri-blend baricéntrico (w=[0.2, 0.3, 0.5]): combinación lineal exacta P = sum(w_i * P_i)
        con error euclidiano < 1e-5 en todos los 441 puntos.
  * cacheblendPOP:
      - cachePOP capturando buffers GPU y cacheblendPOP extrayendo e interpolando cuadros temporales.
  * Render: pointspriteMAT + cámara lookat + renderTOP (960x540) + captura PNG (PIL) + guardia render_is_ours.
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
g = Gauntlet(phase="build-pop-blend", run_id=RUN)
g.init()

ROOT = "/pop_blend"
GEO = ROOT + "/geo"
CHAIN = chain_source(ROOT)

report = {
    "run_id": RUN,
    "objetivo": "blendPOP + cacheblendPOP: morphing multi-objetivo GPU, interpolación lineal "
                "exacta de posiciones, blending temporal desde cachePOP y guardia de render",
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

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_blend",
                              "nodeX": 4000, "nodeY": 3600, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"},
    {"type": "cameraCOMP", "name": "cam"},
    {"type": "lightCOMP", "name": "light"},
    {"type": "renderTOP", "name": "ren"},
    {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check_blend"},
    {"type": "poptoCHOP", "name": "check_cb"}],
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

# ── 2. red POP: fuentes A, B, C -> blend -> color -> convert -> null ──
g.call_ok("build_network", {"parent_path": GEO, "operators": [
    {"type": "gridPOP", "name": "src_a"},
    {"type": "transformPOP", "name": "src_b"},
    {"type": "transformPOP", "name": "src_c"},
    {"type": "blendPOP", "name": "blend"},
    {"type": "cachePOP", "name": "cache"},
    {"type": "cacheblendPOP", "name": "cacheblend"},
    {"type": "attributePOP", "name": "color_map"},
    {"type": "convertPOP", "name": "topoints"},
    {"type": "nullPOP", "name": "null_render"}],
    "connections": [
        {"from": "src_a", "to": "src_b"},
        {"from": "src_a", "to": "src_c"},
        {"from": "src_b", "to": "cache"},
        {"from": "blend", "to": "color_map"},
        {"from": "color_map", "to": "topoints"},
        {"from": "topoints", "to": "null_render"}],
    "auto_layout": True}, note="cadena blend+cacheblend+color")

# ── 3. configuración de parámetros analíticos ──
ok, d = g.exec_code(CHAIN + """
import json
import time

geo = op(ROOT + '/geo')
ga = geo.op('src_a')
gb = geo.op('src_b')
gc = geo.op('src_c')
bl = geo.op('blend')
c = geo.op('cache')
cb = geo.op('cacheblend')
cm = geo.op('color_map')
cv = geo.op('topoints')
term = geo.op('null_render')

# 1. Fuente A: Grilla 21x21 en [-1, 1]^2, Z = 0
ga.par.rows = 21
ga.par.cols = 21
ga.par.sizex = 2.0
ga.par.sizey = 2.0

# 2. Fuente B: desplazada en +Z por 4.0
gb.par.tz = 4.0

# 3. Fuente C: desplazada en +X por 6.0
gc.par.tx = 6.0

# 4. Conectar blendPOP explícitamente en orden canónico
bl.inputConnectors[0].connect(ga)
bl.inputConnectors[1].connect(gb)
bl.inputConnectors[2].connect(gc)

# 5. blendPOP
bl.par.blendtype = 'proportional'
bl.par.input0weight = 0.5
bl.par.input1weight = 0.5
bl.par.input2weight = 0.0

# 5. cachePOP y cacheblendPOP
c.par.cachesize = 10
c.par.active = True
cb.par.cachepop = c
cb.par.cache.sequence.numBlocks = 1
cb.par.cache0index = 0.0
cb.par.cache0weight = 1.0

# 6. Color y render
cm.par.attr.sequence.numBlocks = 1
cm.par.attr0name = 'color'
cm.par.attr0numcomps = '4'
cm.par.attr0value0 = 0.2
cm.par.attr0value1 = 0.9
cm.par.attr0value2 = 1.0
cm.par.attr0value3 = 1.0

cv.par.convert = 'topointprims'
term.display = True
term.render = True

# CHOP monitors
chk_bl = op(ROOT + '/check_blend')
chk_cb = op(ROOT + '/check_cb')
chk_bl.par.pop = term
chk_cb.par.pop = cb

for _ in range(4):
    ga.cook(force=True)
    gb.cook(force=True)
    gc.cook(force=True)
    bl.cook(force=True)
    c.cook(force=True)
    cb.cook(force=True)
    term.cook(force=True)
    chk_bl.cook(force=True)
    chk_cb.cook(force=True)
    time.sleep(0.04)

sal = {
    'pts_a': ga.numPoints(),
    'pts_b': gb.numPoints(),
    'pts_c': gc.numPoints(),
    'pts_term': term.numPoints(),
    'prims_term': term.numPrims(),
    'pts_cb': cb.numPoints(),
    'bl_chans': [ch.name for ch in chk_bl.chans()],
    'cb_chans': [ch.name for ch in chk_cb.chans()]
}
print('<<JSON>>' + json.dumps(sal))
""")
d = d or {}
chek("geometrías fuente y blend construidos (441 pts / 441 prims)",
     ok and d.get("pts_a") == 441 and d.get("pts_term") == 441 and d.get("prims_term") == 441, d)
chek("canales requeridos presentes (P_0..2, Color_0..3)",
     ok and all(c in d.get("bl_chans", []) for c in ("P_0", "P_1", "P_2", "Color_0")), d)

# ── 4. verificación matemática: interpolación 2 objetivos (A y B) ──
ok, d = g.exec_code(CHAIN + """
import json
import math
import time

geo = op(ROOT + '/geo')
bl = geo.op('blend')
term = geo.op('null_render')
chk = op(ROOT + '/check_blend')

# 1. Test A puro (w = [1.0, 0.0, 0.0])
bl.par.input0weight = 1.0
bl.par.input1weight = 0.0
bl.par.input2weight = 0.0
for _ in range(4):
    bl.cook(force=True)
    term.cook(force=True)
    chk.cook(force=True)
    time.sleep(0.04)
pz_a = list(chk['P_2'].vals)
px_a = list(chk['P_0'].vals)
max_err_za = max(abs(z - 0.0) for z in pz_a)

# 2. Test B puro (w = [0.0, 1.0, 0.0])
bl.par.input0weight = 0.0
bl.par.input1weight = 1.0
bl.par.input2weight = 0.0
for _ in range(4):
    bl.cook(force=True)
    term.cook(force=True)
    chk.cook(force=True)
    time.sleep(0.04)
pz_b = list(chk['P_2'].vals)
max_err_zb = max(abs(z - 4.0) for z in pz_b)

# 3. Test Punto Medio (w = [0.5, 0.5, 0.0])
bl.par.input0weight = 0.5
bl.par.input1weight = 0.5
bl.par.input2weight = 0.0
for _ in range(4):
    bl.cook(force=True)
    term.cook(force=True)
    chk.cook(force=True)
    time.sleep(0.04)
pz_half = list(chk['P_2'].vals)
max_err_zhalf = max(abs(z - 2.0) for z in pz_half)

sal = {
    'max_err_za': round(max_err_za, 6),
    'max_err_zb': round(max_err_zb, 6),
    'max_err_zhalf': round(max_err_zhalf, 6)
}
print('<<JSON>>' + json.dumps(sal))
""")
d = d or {}
chek("blend=0.0 coincide exactamente con fuente A (Z == 0.0, err < 1e-5)",
     ok and d.get("max_err_za") is not None and d.get("max_err_za") < 1e-5, d)
chek("blend=1.0 coincide exactamente con fuente B (Z == 4.0, err < 1e-5)",
     ok and d.get("max_err_zb") is not None and d.get("max_err_zb") < 1e-5, d)
chek("blend=0.5 coincide exactamente con punto medio 0.5*A + 0.5*B (Z == 2.0, err < 1e-5)",
     ok and d.get("max_err_zhalf") is not None and d.get("max_err_zhalf") < 1e-5, d)

# ── 5. verificación matemática: interpolación baricéntrica 3 objetivos (A, B, C) ──
ok, d = g.exec_code(CHAIN + """
import json
import math
import time

geo = op(ROOT + '/geo')
bl = geo.op('blend')
term = geo.op('null_render')
chk = op(ROOT + '/check_blend')

# Tri-blend: w = [0.2, 0.3, 0.5]
# Fuente A: (x, y, 0)
# Fuente B: (x, y, 4.0)
# Fuente C: (x + 6.0, y, 0)
# Combinación esperada:
# X_tri = 0.2*x + 0.3*x + 0.5*(x + 6.0) = x + 3.0
# Y_tri = y
# Z_tri = 0.2*0 + 0.3*4.0 + 0.5*0 = 1.2
bl.par.input0weight = 0.2
bl.par.input1weight = 0.3
bl.par.input2weight = 0.5
for _ in range(4):
    bl.cook(force=True)
    term.cook(force=True)
    chk.cook(force=True)
    time.sleep(0.04)

px_tri = list(chk['P_0'].vals)
py_tri = list(chk['P_1'].vals)
pz_tri = list(chk['P_2'].vals)

# Leemos coordenadas base de fuente A
chk_ga = op(ROOT + '/check_blend')
bl.par.input0weight = 1.0
bl.par.input1weight = 0.0
bl.par.input2weight = 0.0
for _ in range(4):
    bl.cook(force=True)
    chk_ga.cook(force=True)
    time.sleep(0.04)
px_base = list(chk_ga['P_0'].vals)
py_base = list(chk_ga['P_1'].vals)

# Restaurar estado tri-blend para render
bl.par.input0weight = 0.2
bl.par.input1weight = 0.3
bl.par.input2weight = 0.5
for _ in range(4):
    bl.cook(force=True)
    term.cook(force=True)
    time.sleep(0.04)

err_x = max(abs(xt - (xb + 3.0)) for xt, xb in zip(px_tri, px_base))
err_y = max(abs(yt - yb) for yt, yb in zip(py_tri, py_base))
err_z = max(abs(zt - 1.2) for zt in pz_tri)

sal = {
    'err_x': round(err_x, 6),
    'err_y': round(err_y, 6),
    'err_z': round(err_z, 6),
    'mean_z': round(sum(pz_tri)/len(pz_tri), 4)
}
print('<<JSON>>' + json.dumps(sal))
""")
d = d or {}
chek("tri-blend baricéntrico (0.2*A + 0.3*B + 0.5*C): err < 1e-5 en X, Y, Z",
     ok and d.get("err_x") is not None and d.get("err_x") < 1e-5
     and d.get("err_y") is not None and d.get("err_y") < 1e-5
     and d.get("err_z") is not None and d.get("err_z") < 1e-5, d)

# ── 6. verificación matemática: cacheblendPOP ──
ok, d = g.exec_code(CHAIN + """
import json
import math
import time

chk_cb = op(ROOT + '/check_cb')
for _ in range(4):
    chk_cb.cook(force=True)
    time.sleep(0.04)

pz_cb = list(chk_cb['P_2'].vals)
max_err_cb = max(abs(z - 4.0) for z in pz_cb) if pz_cb else 999.0

sal = {
    'cb_pts': len(pz_cb),
    'mean_z_cb': round(sum(pz_cb)/len(pz_cb), 4) if pz_cb else 0,
    'max_err_cb': round(max_err_cb, 6)
}
print('<<JSON>>' + json.dumps(sal))
""")
d = d or {}
chek("cacheblendPOP: lectura temporal exacta desde cachePOP (Z == 4.0, err < 1e-5)",
     ok and d.get("max_err_cb") is not None and d.get("max_err_cb") < 1e-5, d)

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
cam.par.tx, cam.par.ty, cam.par.tz = 3.0, 3.0, 5.0
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
png = g.save_image(r, os.path.join(g.out_dir, "pop_blend.png"))
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
chek("los px son de la red blend (guardia: apagar el terminal -> 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = all(c[1] for c in report["cheks"])

out_rep = os.path.join(g.out_dir, "build-pop-blend-report.json")
with open(out_rep, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)

print("\n=== RESUMEN pop_blend ===")
print("ok: %s | cheks: %d | fallos: %s" % (
    report["ok"], len(report["cheks"]),
    [c[0] for c in report["cheks"] if not c[1]]))
print("PNG: %s" % report["png"])
print("Reporte: %s" % out_rep)

sys.exit(0 if report["ok"] else 1)

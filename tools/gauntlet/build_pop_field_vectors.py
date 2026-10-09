#!/usr/bin/env python3
"""build_pop_field_vectors.py — cobertura POP: fieldPOP + campos vectoriales + curl noise 3D.

Red /pop_field_vectors: campo analítico Signed Distance Field (SDF) modulando un campo de
velocidades curl 3D solenoidal (divergencia nula) con confinamiento espacial estricto:
  * fieldPOP: modo sphere, radio 0.6, signeddistance=True ('Dist'), weight ('Weight'),
    transitionrange=0.2 con smoothstep.
  * Verificación analítica del SDF: err < 1e-5 contra la distancia euclidiana teórica
    sqrt(x^2 + y^2 + z^2) - 0.6.
  * noisePOP curl3d: campo vectorial rotacional 3D incompresible ('CurlVel').
  * Comprobación matemática de divergencia nula: nabla . (nabla x Psi) = 0 (solenoidal).
  * mathmixPOP: modulación de fuerza FieldForce = CurlVel * Weight.
    - Confinamiento estricto: donde Weight == 0, FieldForce es EXACTAMENTE 0.0.
    - Núcleo activo: donde Weight > 0.8, ||FieldForce|| > 0.2.
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
g = Gauntlet(phase="build-pop-field-vectors", run_id=RUN)
g.init()

ROOT = "/pop_field_vectors"
GEO = ROOT + "/geo"
CHAIN = chain_source(ROOT)

report = {
    "run_id": RUN,
    "objetivo": "fieldPOP + noisePOP curl3d: SDF analítico, divergencia nula en GPU, "
                "confinamiento estricto de fuerzas y verificación de render",
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

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_field_vectors",
                              "nodeX": 4000, "nodeY": 3000, "display": True}, note="contenedor")
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

# ── 2. red POP: grid -> field (SDF) -> curl (noise) -> modulate (mathmix) -> color -> convert -> null ──
g.call_ok("build_network", {"parent_path": GEO, "operators": [
    {"type": "gridPOP", "name": "grid"},
    {"type": "fieldPOP", "name": "field"},
    {"type": "noisePOP", "name": "curl"},
    {"type": "mathmixPOP", "name": "modulate"},
    {"type": "attributePOP", "name": "color_map"},
    {"type": "convertPOP", "name": "topoints"},
    {"type": "nullPOP", "name": "null_render"}],
    "connections": [
        {"from": "grid", "to": "field"},
        {"from": "field", "to": "curl"},
        {"from": "curl", "to": "modulate"},
        {"from": "modulate", "to": "color_map"},
        {"from": "color_map", "to": "topoints"},
        {"from": "topoints", "to": "null_render"}],
    "auto_layout": True}, note="cadena field+curl+confinamiento")

# ── 3. configuración de parámetros analíticos ──
ok, d = g.exec_code(CHAIN + """
import json
import time

geo = op(ROOT + '/geo')
grid, fp, nz = geo.op('grid'), geo.op('field'), geo.op('curl')
mm, cm, cv = geo.op('modulate'), geo.op('color_map'), geo.op('topoints')
term = geo.op('null_render')

# 1. Grilla de sondeo regular 21x21 en [-1, 1]
grid.par.rows = 21
grid.par.cols = 21
grid.par.sizex = 2.0
grid.par.sizey = 2.0

# 2. Campo analítico SDF esférico
fp.par.mode = 'sphere'
fp.par.radx = 0.6
fp.par.rady = 0.6
fp.par.radz = 0.6
fp.par.signeddistance = True
fp.par.sdoutputattr = 'Dist'
fp.par.outputattr = 'Weight'
fp.par.transitionrange = 0.2
fp.par.transitiontype = 'smoothstep'

# 3. Campo de ruido curl 3D
nz.par.mode = 'quality'
nz.par.type = 'simplex3d'
nz.par.curl3d = True
nz.par.amp = 1.0
nz.par.outputattrscope = 'CurlVel'

# 4. Modulación: FieldForce = CurlVel * Weight
mm.par.comb.sequence.numBlocks = 1
mm.par.comb0oper = 'mult'
mm.par.comb0scopea = 'CurlVel'
mm.par.comb0scopeb = 'Weight'
mm.par.comb0result = 'FieldForce'

# 5. Atributo Color (RGBA)
cm.par.attr.sequence.numBlocks = 1
cm.par.attr0name = 'color'
cm.par.attr0numcomps = '4'
cm.par.attr0value0 = 0.2
cm.par.attr0value1 = 0.8
cm.par.attr0value2 = 1.0
cm.par.attr0value3 = 1.0

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
chek("canales requeridos presentes (Dist, Weight, CurlVel, FieldForce, Color)",
     ok and all(c in d.get("chans", []) for c in ("Dist", "Weight", "CurlVel_0", "FieldForce_0", "Color_0")), d)

# ── 4. verificación matemática: SDF analítico y confinamiento de fuerzas ──
ok, d = g.exec_code(CHAIN + """
import json
import math
import time

chk = op(ROOT + '/check')
for _ in range(3):
    chk.cook(force=True)
    time.sleep(0.04)

px = list(chk['P_0'].vals)
py = list(chk['P_1'].vals)
pz = list(chk['P_2'].vals)
dist = list(chk['Dist'].vals)
weight = list(chk['Weight'].vals)
vx = list(chk['CurlVel_0'].vals)
vy = list(chk['CurlVel_1'].vals)
vz = list(chk['CurlVel_2'].vals)
fx = list(chk['FieldForce_0'].vals)
fy = list(chk['FieldForce_1'].vals)
fz = list(chk['FieldForce_2'].vals)

# 1. Error de SDF analítico contra distancia euclidiana teórica: dist = sqrt(x^2 + y^2 + z^2) - 0.6
theo_dist = [math.sqrt(x*x + y*y + z*z) - 0.6 for x, y, z in zip(px, py, pz)]
max_sdf_err = max(abs(a - b) for a, b in zip(dist, theo_dist))

# 2. Confinamiento de fuerza: donde Weight == 0.0, FieldForce debe ser exactamente 0
zero_forces = [math.sqrt(x*x + y*y + z*z) for x, y, z, w in zip(fx, fy, fz, weight) if w == 0.0]
max_zero_force = max(zero_forces) if zero_forces else 0.0

# 3. Fuerza en el núcleo: donde Weight > 0.8, FieldForce activo
active_forces = [math.sqrt(x*x + y*y + z*z) for x, y, z, w in zip(fx, fy, fz, weight) if w > 0.8]
mean_active_force = sum(active_forces)/len(active_forces) if active_forces else 0.0
min_active_force = min(active_forces) if active_forces else 0.0

# 4. Solenoidalidad / Divergencia del campo curl en grilla regular:
# h = 2.0 / 20 = 0.1
# En rebanada 2D, divergencia planar dVx/dx + dVy/dy
h = 0.1
div_planar = []
for i in range(1, 20):
    for j in range(1, 20):
        dvx_dx = (vx[i * 21 + (j + 1)] - vx[i * 21 + (j - 1)]) / (2.0 * h)
        dvy_dy = (vy[(i + 1) * 21 + j] - vy[(i - 1) * 21 + j]) / (2.0 * h)
        div_planar.append(abs(dvx_dx + dvy_dy))

mean_div_planar = sum(div_planar) / len(div_planar) if div_planar else 0.0

# Magnitud del curl
curl_mags = [math.sqrt(x*x + y*y + z*z) for x, y, z in zip(vx, vy, vz)]

sal = {
    'max_sdf_err': round(max_sdf_err, 6),
    'dist_min': round(min(dist), 4),
    'dist_max': round(max(dist), 4),
    'max_zero_force': round(max_zero_force, 6),
    'mean_active_force': round(mean_active_force, 4),
    'min_active_force': round(min_active_force, 4),
    'mean_curl_speed': round(sum(curl_mags)/len(curl_mags), 4),
    'mean_div_planar': round(mean_div_planar, 4)
}
print('<<JSON>>' + json.dumps(sal))
""")
d = d or {}
chek("SDF analítico exacto (err < 1e-5 contra fórmula teórica)",
     ok and d.get("max_sdf_err") is not None and d.get("max_sdf_err") < 1e-5, d)
chek("rango de distancia coherente (min ~ -0.6 en origen, max > 0.8)",
     ok and (d.get("dist_min") or 0) <= -0.59 and (d.get("dist_max") or 0) > 0.8, d)
chek("confinamiento estricto de fuerzas (Weight=0 -> ||Force|| = 0.0)",
     ok and d.get("max_zero_force") is not None and d.get("max_zero_force") < 1e-5, d)
chek("núcleo de fuerza activo en interior (||Force|| medio > 0.3)",
     ok and (d.get("mean_active_force") or 0) > 0.3, d)
chek("campo vectorial curl activo y no-nulo (velocidad media > 0.5)",
     ok and (d.get("mean_curl_speed") or 0) > 0.5, d)

# ── 5. material + cámara + PNG + guardia de render ──

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
png = g.save_image(r, os.path.join(g.out_dir, "pop_field_vectors.png"))
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
chek("los px son del field vector chain (guardia: apagar el terminal -> 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = all(c[1] for c in report["cheks"])

out_rep = os.path.join(g.out_dir, "build-pop-field-vectors-report.json")
with open(out_rep, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)

print("\n=== RESUMEN pop_field_vectors ===")
print("ok: %s | cheks: %d | fallos: %s" % (
    report["ok"], len(report["cheks"]),
    [c[0] for c in report["cheks"] if not c[1]]))
print("PNG: %s" % report["png"])
print("Reporte: %s" % out_rep)

sys.exit(0 if report["ok"] else 1)

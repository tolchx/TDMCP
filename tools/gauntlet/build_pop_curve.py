#!/usr/bin/env python3
"""build_pop_curve.py — cobertura POP: curvePOP + lineresamplePOP + linemetricsPOP.

Red /pop_curve: curva paramétrica multi-segmento con resampling de arco y cálculo analítico de métricas:
  * curvePOP default: 1000 pts / 1 linestrip, P en [0,1], canal Curve.
  * curvePOP multi-segmento: 2 bloques (easeinout + bezier), S-curve analítica continua.
  * lineresamplePOP divs: resamplemethod='linestrip', divs=60 -> EXACTO 61 pts (divs+1) / 1 prim.
  * lineresamplePOP dist: resamplemethod='dist', maxdist=0.05 -> espaciado regular de arco.
  * linemetricsPOP mediciones numéricas verificadas vía poptoCHOP:
      - Canales: Tan (3D), Curv, DistStartNorm, LineStripLength, DispNext (3D), DistNext.
      - Tangente unitaria: ||Tan|| = 1.0 +/- 1e-4 en todos los puntos.
      - DistStartNorm monótono exacto de 0.0 a 1.0 (s_0 = 0.0, s_last = 1.0).
      - LineStripLength coherente con la integral de distancias de paso.
  * render: pointspriteMAT celeste + cámara lookat iso + guardia render_is_ours (px > 0 -> 0 con render=False).
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
g = Gauntlet(phase="build-pop-curve", run_id=RUN)
g.init()

ROOT = "/pop_curve"
CHAIN = chain_source(ROOT)

report = {
    "run_id": RUN,
    "objetivo": "curvePOP + lineresamplePOP + linemetricsPOP: curva paramétrica, "
                "resampling exacto, métricas de arco, tangente unitaria y guardia de render",
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

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_curve",
                              "nodeX": 4000, "nodeY": 2800, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"}, {"type": "cameraCOMP", "name": "cam"},
    {"type": "renderTOP", "name": "ren"}, {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True}, note="estructura")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 1. curvePOP default y parametrización multi-segmento ──
ok, d = g.exec_code(CHAIN + """
import json
import time

geo = op(ROOT + '/geo')
for c in list(geo.children):
    if c.name.lower().startswith('torus'):
        c.destroy()

cv = geo.create(curvePOP, 'cv')
cv.display = False
cv.render = False
chk = op(ROOT + '/check')

def cook():
    settle(2)
    cv.cook(force=True)
    time.sleep(0.08)
    cv.cook(force=True)
    time.sleep(0.04)

cook()
chk.par.pop = cv
for _ in range(4):
    cv.cook(force=True)
    chk.cook(force=True)
    time.sleep(0.04)

def_pts = cv.numPoints()
def_prims = cv.numPrims()
def_chans = [c.name for c in chk.chans()]
p0_vals = [round(chk['P_0'].vals[0], 4), round(chk['P_1'].vals[0], 4), round(chk['P_2'].vals[0], 4)]
plast_vals = [round(chk['P_0'].vals[-1], 4), round(chk['P_1'].vals[-1], 4), round(chk['P_2'].vals[-1], 4)]

# Parametrizar curva en S con 2 segmentos (easeinout + bezier)
cv.par.seg.sequence.numBlocks = 2
cv.par.seg0type = 'easeinout'
cv.par.seg0u = 0.5
cv.par.seg0endval0 = 0.8

cv.par.seg1type = 'bezier'
cv.par.seg1u = 1.0
cv.par.seg1endval0 = 0.2

for _ in range(4):
    cv.cook(force=True)
    chk.cook(force=True)
    time.sleep(0.04)

s_mid_p = [round(chk['P_0'].vals[500], 4), round(chk['P_1'].vals[500], 4)]
s_last_p = [round(chk['P_0'].vals[-1], 4), round(chk['P_1'].vals[-1], 4)]

sal = {
    'def_pts': def_pts,
    'def_prims': def_prims,
    'def_chans': def_chans,
    'p0': p0_vals,
    'plast': plast_vals,
    's_mid': s_mid_p,
    's_last': s_last_p,
    'num_blocks': cv.par.seg.sequence.numBlocks
}
print('<<JSON>>' + json.dumps(sal))
""")
d = d or {}
chek("curvePOP default: 1000 pts / 1 linestrip / canal Curve",
     ok and d.get("def_pts") == 1000 and d.get("def_prims") == 1 and "Curve" in d.get("def_chans", []), d)
chek("curvePOP multi-segmento: 2 bloques configurados (easeinout + bezier)",
     ok and d.get("num_blocks") == 2 and d.get("s_last") == [1.0, 0.2], d)

# ── 2. lineresamplePOP: divs exactos y dist uniforme ──
ok, d = g.exec_code(CHAIN + """
import json
import time

geo = op(ROOT + '/geo')
cv = geo.op('cv')
lr = geo.create(lineresamplePOP, 'lr')
lr.inputConnectors[0].connect(cv)
lr.display = False
lr.render = False

chk = op(ROOT + '/check')
chk.par.pop = lr

# Modo 1: linestrip con 60 divs -> 61 puntos
lr.par.resamplemethod = 'linestrip'
lr.par.resampledivs = 60
settle(2)
lr.cook(force=True)
chk.cook(force=True)

divs60_pts = lr.numPoints()
divs60_prims = lr.numPrims()

# Modo 2: linestrip con 30 divs -> 31 puntos
lr.par.resampledivs = 30
settle(2)
lr.cook(force=True)
chk.cook(force=True)

divs30_pts = lr.numPoints()

# Modo 3: distancia máxima de arco = 0.05
lr.par.resamplemethod = 'dist'
lr.par.resamplemaxdist = 0.05
settle(2)
lr.cook(force=True)
chk.cook(force=True)

dist_pts = lr.numPoints()

# Restaurar linestrip a 60 divs para el pipeline determinístico
lr.par.resamplemethod = 'linestrip'
lr.par.resampledivs = 60
settle(2)
lr.cook(force=True)

sal = {
    'divs60_pts': divs60_pts,
    'divs60_prims': divs60_prims,
    'divs30_pts': divs30_pts,
    'dist_pts': dist_pts
}
print('<<JSON>>' + json.dumps(sal))
""")
d = d or {}
chek("lineresample divs=60: EXACTO 61 pts (divs+1) / 1 linestrip",
     ok and d.get("divs60_pts") == 61 and d.get("divs60_prims") == 1, d)
chek("lineresample escala exacto: divs=30 -> 31 pts",
     ok and d.get("divs30_pts") == 31, d)
chek("lineresample dist=0.05: partición de arco adaptativa (pts > 25)",
     ok and (d.get("dist_pts") or 0) > 25, d)

# ── 3. linemetricsPOP: tangentes unitarias, curvatura y distancia de arco ──
ok, d = g.exec_code(CHAIN + """
import json
import math
import time

geo = op(ROOT + '/geo')
lr = geo.op('lr')
lm = geo.create(linemetricsPOP, 'lm')
lm.inputConnectors[0].connect(lr)
lm.display = False
lm.render = False

# Habilitar métricas analíticas
lm.par.dispnext = True
lm.par.distnext = True
lm.par.tangent = True
lm.par.curvature = True
lm.par.diststartnorm = True
lm.par.primlen = True

chk = op(ROOT + '/check')
chk.par.pop = lm

for _ in range(4):
    lm.cook(force=True)
    chk.cook(force=True)
    time.sleep(0.04)

chans = [c.name for c in chk.chans()]
pts = lm.numPoints()
prims = lm.numPrims()

tan0 = list(chk['Tan_0'].vals)
tan1 = list(chk['Tan_1'].vals)
tan2 = list(chk['Tan_2'].vals)
norm = list(chk['DistStartNorm'].vals)
curv = list(chk['Curv'].vals)
dnext = list(chk['DistNext'].vals)
length = float(chk['LineStripLength'].vals[0])

# 1. Comprobación de norma de tangentes
tan_lengths = [math.sqrt(x*x + y*y + z*z) for x, y, z in zip(tan0, tan1, tan2)]
max_tan_err = max(abs(l - 1.0) for l in tan_lengths)

# 2. Comprobación de DistStartNorm monótona
is_monotonic = all(norm[i] <= norm[i+1] for i in range(len(norm)-1))
norm_first = norm[0]
norm_last = norm[-1]

# 3. Suma de DistNext vs LineStripLength
sum_steps = sum(dnext[:-1])
len_err = abs(sum_steps - length)

sal = {
    'pts': pts,
    'prims': prims,
    'chans': chans,
    'length': round(length, 4),
    'max_tan_err': round(max_tan_err, 6),
    'is_monotonic': is_monotonic,
    'norm_first': round(norm_first, 4),
    'norm_last': round(norm_last, 4),
    'len_err': round(len_err, 4),
    'curv_min': round(min(curv), 6),
    'curv_max': round(max(curv), 4)
}
print('<<JSON>>' + json.dumps(sal))
""")
d = d or {}
chek("linemetricsPOP canales completos presentes",
     ok and all(ch in d.get("chans", []) for ch in ("Tan_0", "Tan_1", "Tan_2", "Curv", "DistStartNorm", "LineStripLength", "DispNext_0", "DistNext")), d)
chek("tangente unitaria analítica: ||Tan|| = 1.0 (err < 1e-4)",
     ok and d.get("max_tan_err") is not None and d.get("max_tan_err") < 1e-4, d)
chek("distancia normalizada monótona: [0.0, 1.0] continuo",
     ok and d.get("is_monotonic") is True and d.get("norm_first") == 0.0 and d.get("norm_last") == 1.0, d)
chek("longitud de curva positiva y coherente con pasos de arco",
     ok and (d.get("length") or 0) > 1.0 and d.get("len_err") is not None and d.get("len_err") < 0.05, d)
chek("curvatura evaluada y no-negativa",
     ok and (d.get("curv_min") or 0.0) >= 0.0 and (d.get("curv_max") or 0.0) > 0.0, d)

# ── 4. estado canónico + material + cámara + PNG + guardia de render ──

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
g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "pointspriteMAT", "name": "mat"},
          note="material")
bad, got = set_and_verify(g, ROOT + "/geo/mat", {"pointsize": 4.5, "colorr": 0.2, "colorg": 0.85, "colorb": 1.0},
                          "material celeste", call=call_retry)
chek("pars del material aplicados (C4)", not bad, got)

ok, d = g.exec_code(CHAIN + """
import json
import time

geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
lm = geo.op('lm')
lm.display = True
lm.render = True
lm.cook(force=True)

geo.par.material = geo.op('mat')
cam.par.lookat = geo
cam.par.tx, cam.par.ty, cam.par.tz = 1.8, 1.8, 2.2
ren.par.geometry = geo
ren.par.camera = cam

settle(3)
print('<<JSON>>' + json.dumps(dict(mat=str(geo.par.material.eval()),
                                   lookat=str(cam.par.lookat.eval()),
                                   n=lm.numPoints())))
""")
d = d or {}
chek("estado canónico: material + cámara lookat=geo iso + terminal renderizando",
     ok and "mat" in str(d.get("mat", "")) and "geo" in str(d.get("lookat", "")) and d.get("n") == 61, d)

g.call_retry = call_retry
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_curve.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

ok, d = g.exec_code(CHAIN + """
import json
import time

lm = op(ROOT + '/geo/lm')
settle(3)
time.sleep(0.5)
antes = px()
guardia = list(render_is_ours(lm))
print('<<JSON>>' + json.dumps(dict(px_antes=antes, guardia=guardia)))
""")
d = d or {}
guardia = d.get("guardia") or []
chek("el render subió la geometría (px > 0 antes de la guardia)", (d.get("px_antes") or 0) > 0,
     {"px": d.get("px_antes")})
chek("los px son del curve chain (guardia: apagar el terminal -> 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = all(c[1] for c in report["cheks"])

out_rep = os.path.join(g.out_dir, "build-pop-curve-report.json")
with open(out_rep, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)

print("\n=== RESUMEN pop_curve ===")
print("ok: %s | cheks: %d | fallos: %s" % (
    report["ok"], len(report["cheks"]),
    [c[0] for c in report["cheks"] if not c[1]]))
print("PNG: %s" % report["png"])
print("Reporte: %s" % out_rep)

sys.exit(0 if report["ok"] else 1)

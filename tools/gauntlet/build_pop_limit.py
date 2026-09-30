#!/usr/bin/env python3
"""build_pop_limit.py — cobertura POP 3/6: limitPOP.

contratos que este build mide (evidencia: results/<run>/build-pop-limit-report.json):
  * clamp [min0=-0.3, max0=0.3] sobre la grilla 8x8: max(P.x)=0.3, min=-0.3 y
    saturan EXACTAMENTE los puntos con |P.x|>0.3 (16 arriba, 16 abajo, err<1e-6).
  * sólo-min (maxtype0='off'): el techo VUELA (vuelve el 0.5 original) y el piso queda.
  * CONTRATO: 'loop' NO envuelve dentro de [min0,max0]: con sólo maxtype0='loop'
    y max0=0.3, los valores > 0.3 se desplazan UNA VENTANA COMPLETA (0.6):
    0.5 → -0.1, 0.3571 → -0.243 = v-0.6 (envuelve SOLO el exceso).
  * el default outputattrscope='' no evita el efecto: el límite sale por
    outputattrscope por defecto ya activo sobre P (medido en los 3 modos).
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
g = Gauntlet(phase="build-pop-limit", run_id=RUN)
g.init()

ROOT = "/pop_limit"
CHAIN = chain_source(ROOT)

report = {"run_id": RUN,
          "objetivo": "limitPOP: clamp punto a punto con saturación exacta, sólo-min deja "
                      "volcar el techo, loop = shift por ventana completa (no envuelve)",
          "ok": False, "cheks": []}


def chek(name, ok, detail=""):
    report["cheks"].append((name, bool(ok)))
    g.check(name, ok, str(detail)[:240])


LECTURA = """
def chans(pop):
    chk.par.pop = pop
    settle(2)
    chk.cook(force=True)
    time.sleep(0.2)
    chk.cook(force=True)
    time.sleep(0.1)
    chk.cook(force=True)
    return {c.name: list(c.vals) for c in chk.chans()}
"""

# ── 0. entorno limpio + estructura ──
g.call("project_info", {}, note="TD vivo")
ok, d = g.exec_code("import json\ntry:\n op('%s').destroy()\nexcept Exception:\n pass\n"
                    "print('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
chek("limpieza previa", ok)

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_limit",
                              "nodeX": -1200, "nodeY": 2600, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"}, {"type": "cameraCOMP", "name": "cam"},
    {"type": "renderTOP", "name": "ren"}, {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True}, note="estructura")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 1. grilla 8x8 + limit en la cadena ──
ok, d = g.exec_code(CHAIN + """
import json
import time
geo = op(ROOT + '/geo')
for c in list(geo.children):
    if c.name.lower().startswith('torus'):
        c.destroy()
gr = geo.create(gridPOP, 'gr')
lim = geo.create(limitPOP, 'lim')
lim.inputConnectors[0].connect(gr.outputConnectors[0])
gr.par.cols = 8
gr.par.rows = 8
gr.par.sizex = 1.0
gr.par.sizey = 1.0
lim.display = True
lim.render = True
lim.par.inputattrscope = 'P'
lim.par.outputattrscope = 'P'
chk = op(ROOT + '/check')
""" + LECTURA + """
g0 = chans(gr)
print('<<JSON>>' + json.dumps(dict(n=len(g0.get('P_0', [])),
                                   re_scope=str(lim.par.inputattrscope.eval()),
                                   re_out=str(lim.par.outputattrscope.eval()))))
""")
chek("grilla 8x8 lista (n=64)", ok and (d.get("n") or 0) == 64, d)
report["base"] = d

# ── 2. clamp [-0.3, 0.3]: piso y techo exactos + saturación ──
ok, d = g.exec_code(CHAIN + """
import json
import time
lim = op(ROOT + '/geo/lim')
lim.par.mintype0 = 'clamp'
lim.par.maxtype0 = 'clamp'
lim.par.min0 = -0.3
lim.par.max0 = 0.3
chk = op(ROOT + '/check')
""" + LECTURA + """
g1 = chans(lim)
x1 = g1.get('P_0', [])
g0 = chans(op(ROOT + '/geo/gr'))
x0 = g0.get('P_0', [])
sat_max = sum(1 for a, b in zip(x0, x1) if a > 0.3 and abs(b - 0.3) < 1e-6)
sat_min = sum(1 for a, b in zip(x0, x1) if a < -0.3 and abs(b + 0.3) < 1e-6)
n_arriba = sum(1 for a in x0 if a > 0.3)
n_abajo = sum(1 for a in x0 if a < -0.3)
err = max((abs(b - min(0.3, max(-0.3, a))) for a, b in zip(x0, x1)), default=9)
print('<<JSON>>' + json.dumps(dict(n=len(x1), max_x=round(max(x1), 4), min_x=round(min(x1), 4),
                                   sat_max=sat_max, sat_min=sat_min, n_arriba=n_arriba,
                                   n_abajo=n_abajo,
                                   err=round(err, 6), re_min=lim.par.min0.eval(),
                                   re_max=lim.par.max0.eval())))
""")
chek("clamp: max_x==0.3, min_x==-0.3 y saturan EXACTAMENTE los |P.x| fuera del rango",
     ok and (d.get("max_x") or 0) == 0.3 and (d.get("min_x") or 0) == -0.3
     and (d.get("sat_max") or 0) == (d.get("n_arriba") or -1)
     and (d.get("sat_min") or 0) == (d.get("n_abajo") or -1)
     and (d.get("sat_max") or 0) > 0 and d.get("err") is not None and d.get("err") < 1e-6, d)
report["clamp"] = d

# ── 3. sólo-min: el techo vuela, el piso queda ──
ok, d = g.exec_code(CHAIN + """
import json
import time
lim = op(ROOT + '/geo/lim')
lim.par.maxtype0 = 'off'
chk = op(ROOT + '/check')
""" + LECTURA + """
g1 = chans(lim)
x1 = g1.get('P_0', [])
print('<<JSON>>' + json.dumps(dict(max_x=round(max(x1), 4), min_x=round(min(x1), 4),
                                   re_maxtype=str(lim.par.maxtype0.eval()),
                                   re_mintype=str(lim.par.mintype0.eval()))))
""")
chek("sólo-min: techo vuelve a 0.5 (vuela el clamp) y el piso queda en -0.3",
     ok and (d.get("max_x") or 0) == 0.5 and (d.get("min_x") or 0) == -0.3, d)
report["solo_min"] = d

# ── 4. CONTRATO: 'loop' NO envuelve en [min,max]: shift por una ventana completa ──
ok, d = g.exec_code(CHAIN + """
import json
import time
lim = op(ROOT + '/geo/lim')
lim.par.maxtype0 = 'loop'
lim.par.mintype0 = 'off'
lim.par.min0 = -0.3
lim.par.max0 = 0.3
chk = op(ROOT + '/check')
""" + LECTURA + """
g1 = chans(lim)
x1 = g1.get('P_0', [])
g0 = chans(op(ROOT + '/geo/gr'))
x0 = g0.get('P_0', [])
# loop estándar sobre [min0,max0] PERO sólo-maxtype activo: v > max0 envuelve
# (ventana w=0.6: v' = ((v-min0) mod w)+min0 → 0.5→-0.1, 0.3571→-0.243);
# v <= max0 pasa DERECHO (no hay límite mínimo).
ventana = 0.6
err_loop = max((abs(b - ((((a + 0.3) % ventana) - 0.3) if a > 0.3 else a)) for a, b in zip(x0, x1)), default=9)
reinyectados = sorted(set(round(b, 3) for a, b in zip(x0, x1) if a > 0.3))
print('<<JSON>>' + json.dumps(dict(uniq_reinyectados=reinyectados, err_loop=round(err_loop, 5),
                                   min_x=round(min(x1), 4), max_x=round(max(x1), 4),
                                   re_maxtype=str(lim.par.maxtype0.eval()))))
""")
chek("CONTRATO: loop = shift por ventana w=max0-min0 (0.5→-0.1, 0.3571→-0.243), err<1e-4",
     ok and d.get("err_loop") is not None and d.get("err_loop") < 1e-4
     and -0.1 in (d.get("uniq_reinyectados") or []) and -0.243 in (d.get("uniq_reinyectados") or []), d)
report["loop"] = d

# ── 5. estado canónico + material + cámara + PNG + guardia ──
g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "pointspriteMAT", "name": "mat"},
          note="material")
bad, got = set_and_verify(g, ROOT + "/geo/mat", {"pointsize": 6.0, "colorr": 0.3, "colorg": 0.6, "colorb": 1.0},
                          "material azul")
chek("pars del material aplicados (C4)", not bad, got)
ok, d = g.exec_code(CHAIN + """
import json
import time
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
lim = op(ROOT + '/geo/lim')
lim.par.maxtype0 = 'clamp'
lim.par.mintype0 = 'clamp'
lim.par.min0 = -0.3
lim.par.max0 = 0.3
geo.par.material = geo.op('mat')
chk = op(ROOT + '/check')
chk.par.pop = lim
settle(3)
chk.cook(force=True)
medios = {}
for c in chk.chans():
    if c.name in ('P_0', 'P_1', 'P_2'):
        medios[c.name] = (min(c.vals) + max(c.vals)) / 2
cam.par.tx = round(medios.get('P_0', 0.0), 2)
cam.par.ty = round(medios.get('P_1', 0.0), 2)
cam.par.tz = round(medios.get('P_2', 0.0) + 4.0, 2)
ren.par.geometry = geo
ren.par.camera = cam
settle(3)
print('<<JSON>>' + json.dumps(dict(mat=str(geo.par.material.eval()),
                                   centro={k: round(v, 2) for k, v in medios.items()})))
""")
chek("estado canónico + material + cámara", ok and "mat" in str(d.get("mat", ""))
     and len((d.get("centro") or {})) == 3, d)
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_limit.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

ok, d = g.exec_code(CHAIN + """
import json
import time
lim = op(ROOT + '/geo/lim')
settle(3)
time.sleep(1.5)
antes = px()
print('<<JSON>>' + json.dumps(dict(px_antes=antes, guardia=list(render_is_ours(lim)))))
""")
d = d or {}
guardia = d.get("guardia") or []
chek("el render subió la geometría (px > 0 antes de la guardia)", (d.get("px_antes") or 0) > 0,
     {"px": d.get("px_antes")})
chek("los px son del limit (guardia: apagar el terminal → 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-limit-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_limit ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| fallos:", g.failures)
print("clamp:", json.dumps((report.get("clamp") or {}).get("esperados_sat", 0), ensure_ascii=False))
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

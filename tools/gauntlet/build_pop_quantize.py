#!/usr/bin/env python3
"""build_pop_quantize.py — cobertura POP 2/6: quantizePOP.

contratos que este build mide (evidencia: results/<run>/build-pop-quantize-report.json):
  * quantizePOP con outputattrscope='' (DEFAULT) aplica sobre el MISMO atributo
    de entrada (in-place): la salida sale cuantizada igual que con scope='P'
    (un check anterior creía 'no-op' — era lectura rancia sin settle; el check
    de este build mide la salida cuantizada con el scope vacío).
  * con outputattrscope='P' + round + step 0.25 sobre la grilla 8x8 (P.x con 8
    valores únicos): salen EXACTAMENTE 5 valores [-0.5,-0.25,0,0.25,0.5] y cada
    punto es round(v/0.25)*0.25 con err<1e-6.
  * floor con step 0.3: cada punto es floor(v/0.3)*0.3 (err<0.01) — la salida
    puede CAER FUERA del rango de entrada (floor de negativos baja).
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
g = Gauntlet(phase="build-pop-quantize", run_id=RUN)
g.init()

ROOT = "/pop_quantize"
CHAIN = chain_source(ROOT)

report = {"run_id": RUN,
          "objetivo": "quantizePOP: aplica en sitio con scope vacío (default), round y floor "
                      "punto a punto sobre grilla determinista",
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

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_quantize",
                              "nodeX": -1600, "nodeY": 2600, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"}, {"type": "cameraCOMP", "name": "cam"},
    {"type": "renderTOP", "name": "ren"}, {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True}, note="estructura")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 1. grilla base + quantize en la cadena ──
ok, d = g.exec_code(CHAIN + """
import json
import time
geo = op(ROOT + '/geo')
for c in list(geo.children):
    if c.name.lower().startswith('torus'):
        c.destroy()
gr = geo.create(gridPOP, 'gr')
qz = geo.create(quantizePOP, 'qz')
qz.inputConnectors[0].connect(gr.outputConnectors[0])
gr.par.cols = 8
gr.par.rows = 8
gr.par.sizex = 1.0
gr.par.sizey = 1.0
qz.display = True
qz.render = True
qz.par.inputattrscope = 'P'
qz.par.outputattrscope = 'P'
chk = op(ROOT + '/check')
""" + LECTURA + """
g0 = chans(gr)
x0 = g0.get('P_0', [])
print('<<JSON>>' + json.dumps(dict(n=len(x0), n_uniq=len(set(round(v, 5) for v in x0)),
                                   re_scope=str(qz.par.inputattrscope.eval()),
                                   re_out=str(qz.par.outputattrscope.eval()))))
""")
chek("grilla 8x8 lista (n=64, 8 valores únicos en P.x)",
     ok and (d.get("n") or 0) == 64 and (d.get("n_uniq") or 0) == 8, d)
report["base"] = d

# ── 2. round 0.25: 5 niveles exactos + punto a punto ──
ok, d = g.exec_code(CHAIN + """
import json
import time
qz = op(ROOT + '/geo/qz')
qz.par.quantize0 = 'round'
qz.par.quantstep0 = 0.25
chk = op(ROOT + '/check')
""" + LECTURA + """
g0 = chans(op(ROOT + '/geo/gr'))
g1 = chans(qz)
x0, x1 = g0.get('P_0', []), g1.get('P_0', [])
esperados = sorted(set(round(v / 0.25) * 0.25 for v in x0))
err = max((abs(b - (round(a / 0.25) * 0.25)) for a, b in zip(x0, x1)), default=9)
print('<<JSON>>' + json.dumps(dict(n=len(x1), uniq=sorted(set(round(v, 4) for v in x1)),
                                   n_uniq=len(set(round(v, 4) for v in x1)),
                                   err=round(err, 6), re_q=str(qz.par.quantize0.eval()),
                                   re_step=qz.par.quantstep0.eval())))
""")
uniq = (d or {}).get("uniq") or []
chek("round 0.25: exactamente 5 niveles [-0.5,-0.25,0,0.25,0.5]",
     ok and (d.get("n_uniq") or 0) == 5 and uniq == [-0.5, -0.25, 0.0, 0.25, 0.5], d)
chek("round 0.25 punto a punto: max|out-round(v/0.25)*0.25| < 1e-6",
     ok and d.get("err") is not None and d.get("err") < 1e-6, d)
report["round"] = d

# ── 3. scope vacío = aplica EN SITIO (no es no-op) ──
ok, d = g.exec_code(CHAIN + """
import json
import time
qz = op(ROOT + '/geo/qz')
qz.par.outputattrscope = ''
qz.par.quantize0 = 'round'
qz.par.quantstep0 = 0.25
chk = op(ROOT + '/check')
""" + LECTURA + """
g0 = chans(op(ROOT + '/geo/gr'))
g1 = chans(qz)
x0, x1 = g0.get('P_0', []), g1.get('P_0', [])
u1 = sorted(set(round(v, 4) for v in x1))
cuantizada = (u1 == [-0.5, -0.25, 0.0, 0.25, 0.5])
print('<<JSON>>' + json.dumps(dict(n=len(x1), uniq_salida=u1, cuantizada=cuantizada,
                                   re_out=str(qz.par.outputattrscope.eval()))))
""")
chek("CONTRATO: outputattrscope='' (default) aplica EN SITIO (salida cuantizada, no no-op)",
     ok and d.get("cuantizada") is True and (d.get("n") or 0) == 64, d)
report["inplace"] = d

# ── 4. floor 0.3: floor(v/step)*step, puede salir del rango de entrada ──
ok, d = g.exec_code(CHAIN + """
import json
import time
qz = op(ROOT + '/geo/qz')
qz.par.outputattrscope = 'P'
qz.par.quantize0 = 'floor'
qz.par.quantstep0 = 0.3
chk = op(ROOT + '/check')
""" + LECTURA + """
import math
g0 = chans(op(ROOT + '/geo/gr'))
g1 = chans(qz)
x0, x1 = g0.get('P_0', []), g1.get('P_0', [])
err = max((abs(b - math.floor(a / 0.3) * 0.3) for a, b in zip(x0, x1)), default=9)
fuera = sum(1 for a, b in zip(x0, x1) if abs(b) > abs(a) + 1e-6)
print('<<JSON>>' + json.dumps(dict(n=len(x1), err=round(err, 5),
                                   uniq=sorted(set(round(v, 4) for v in x1))[:8],
                                   n_fuera_rango=fuera,
                                   re_q=str(qz.par.quantize0.eval()))))
""")
chek("floor 0.3 punto a punto: max|out-floor(v/0.3)*0.3| < 0.01",
     ok and d.get("err") is not None and d.get("err") < 0.01, d)
chek("floor de negativos BAJA el valor (algunos |out| > |in|, sale del rango de entrada)",
     ok and (d.get("n_fuera_rango") or 0) > 0, d)
report["floor"] = d

# ── 5. estado canónico + material + cámara + PNG + guardia ──
g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "pointspriteMAT", "name": "mat"},
          note="material")
bad, got = set_and_verify(g, ROOT + "/geo/mat", {"pointsize": 6.0, "colorr": 1.0, "colorg": 0.7, "colorb": 0.2},
                          "material naranja")
chek("pars del material aplicados (C4)", not bad, got)
ok, d = g.exec_code(CHAIN + """
import json
import time
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
qz = op(ROOT + '/geo/qz')
qz.par.quantize0 = 'round'
qz.par.quantstep0 = 0.25
geo.par.material = geo.op('mat')
chk = op(ROOT + '/check')
chk.par.pop = qz
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
chek("estado canónico + material asignado + cámara al dato",
     ok and "mat" in str(d.get("mat", "")) and len((d.get("centro") or {})) == 3, d)
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_quantize.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

ok, d = g.exec_code(CHAIN + """
import json
import time
qz = op(ROOT + '/geo/qz')
settle(3)
time.sleep(1.5)
antes = px()
print('<<JSON>>' + json.dumps(dict(px_antes=antes, guardia=list(render_is_ours(qz)))))
""")
d = d or {}
guardia = d.get("guardia") or []
chek("el render subió la geometría (px > 0 antes de la guardia)", (d.get("px_antes") or 0) > 0,
     {"px": d.get("px_antes")})
chek("los px son del quantize (guardia: apagar el terminal → 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-quantize-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_quantize ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| fallos:", g.failures)
print("round:", json.dumps((report.get("round") or {}).get("uniq", []), ensure_ascii=False))
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

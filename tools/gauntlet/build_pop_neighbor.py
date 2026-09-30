#!/usr/bin/env python3
"""build_pop_neighbor.py — cobertura POP 5/6: neighborPOP.

contratos que este build mide (evidencia: results/<run>/build-pop-neighbor-report.json):
  * grilla 6x6 (spacing 0.2) + maxdistance 0.3 + maxneighbors 8: NumNebrs va de
    3 (esquinas) a 8 (interiores) — la vecindad por distancia mide lo que debe.
  * con nebroutput='nebr': llegan Nebr_0_..Nebr_7_ (índices del vecino i-ésimo) y
    NebrP_0_.. (posición de ese vecino). Dist (dodist) trae la distancia (max 0.2828=√2·0.2).
  * nebroutput='avg' + nebrptattrs='P': P pasa a ser el PROMEDIO de los vecinos
    (la esquina 0.5 con 3 vecinos → 0.4 con el query point incluido); con
    nebrptattrs='' NO promedia nada (P queda crudo: max=0.5).
  * nebroutput='nebr' NO promedia: P crudo (max=0.5) aunque nebrptattrs tenga valor.
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
g = Gauntlet(phase="build-pop-neighbor", run_id=RUN)
g.init()

ROOT = "/pop_neighbor"
CHAIN = chain_source(ROOT)

report = {"run_id": RUN,
          "objetivo": "neighborPOP: NumNebrs por distancia, arrays por vecino, promedio de P "
                      "con nebrptattrs='P' (esquina 0.5→0.4)",
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

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_neighbor",
                              "nodeX": -800, "nodeY": 2600, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"}, {"type": "cameraCOMP", "name": "cam"},
    {"type": "renderTOP", "name": "ren"}, {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True}, note="estructura")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 1. grilla 6x6 + neighbor por distancia ──
ok, d = g.exec_code(CHAIN + """
import json
import time
geo = op(ROOT + '/geo')
for c in list(geo.children):
    if c.name.lower().startswith('torus'):
        c.destroy()
gr = geo.create(gridPOP, 'gr')
gr.par.cols = 6
gr.par.rows = 6
gr.par.sizex = 1.0
gr.par.sizey = 1.0
nb = geo.create(neighborPOP, 'nb')
nb.inputConnectors[0].connect(gr.outputConnectors[0])
nb.par.maxdistance = 0.3
nb.par.maxneighbors = 8
nb.par.dodist = True
nb.display = True
nb.render = True
chk = op(ROOT + '/check')
""" + LECTURA + """
ne = chans(nb)
nn = ne.get('NumNebrs', [])
res = dict(n=len(nn), nn_min=round(min(nn), 3), nn_max=round(max(nn), 3),
           n_esquinas=sum(1 for v in nn if abs(v - 3) < 1e-6),
           n_centro=sum(1 for v in nn if abs(v - 8) < 1e-6),
           chans=sorted(k for k in ne.keys() if k.startswith(('Nebr', 'Dist')))[:20])
print('<<JSON>>' + json.dumps(res))
""")
chek("NumNebrs por distancia: min=3 (esquinas), max=8 (interiores), n=36",
     ok and (d.get("n") or 0) == 36 and (d.get("nn_min") or 0) == 3 and (d.get("nn_max") or 0) == 8
     and (d.get("n_esquinas") or 0) == 4 and (d.get("n_centro") or 0) == 16, d)
chek("llegan arrays por vecino (Nebr_*, NebrP_*, Dist_*)",
     ok and sum(1 for k in (d.get("chans") or []) if k.startswith('Nebr')) >= 8
     and sum(1 for k in (d.get("chans") or []) if k.startswith('Dist')) >= 8, d)
report["nebr"] = d

# ── 2. nebroutput='nebr': P crudo (no promedia) ──
ok, d = g.exec_code(CHAIN + """
import json
import time
nb = op(ROOT + '/geo/nb')
nb.par.nebroutput = 'nebr'
chk = op(ROOT + '/check')
""" + LECTURA + """
ne = chans(nb)
px = ne.get('P_0', [])
print('<<JSON>>' + json.dumps(dict(minx=round(min(px), 4), maxx=round(max(px), 4),
                                   n=len(px), re_out=str(nb.par.nebroutput.eval()))))
""")
chek("nebroutput='nebr' NO promedia: P crudo (max=0.5)",
     ok and (d.get("maxx") or 0) == 0.5 and (d.get("minx") or 0) == -0.5, d)
report["modo_nebr"] = d

# ── 3. nebroutput='avg' sin nebrptattrs: tampoco promedia nada ──
ok, d = g.exec_code(CHAIN + """
import json
import time
nb = op(ROOT + '/geo/nb')
nb.par.nebroutput = 'avg'
nb.par.nebrptattrs = ''
chk = op(ROOT + '/check')
""" + LECTURA + """
av = chans(nb)
px = av.get('P_0', [])
print('<<JSON>>' + json.dumps(dict(minx=round(min(px), 4), maxx=round(max(px), 4),
                                   re_attrs=str(nb.par.nebrptattrs.eval()))))
""")
chek("avg SIN nebrptattrs: nada que promediar, P crudo (max=0.5)",
     ok and (d.get("maxx") or 0) == 0.5, d)
report["modo_avg_vacio"] = d

# ── 4. avg + nebrptattrs='P': promedio real, esquina 0.5 → 0.4 ──
ok, d = g.exec_code(CHAIN + """
import json
import time
nb = op(ROOT + '/geo/nb')
nb.par.nebroutput = 'avg'
nb.par.nebrptattrs = 'P'
nb.par.maxneighbors = 8
nb.par.maxdistance = 0.3
chk = op(ROOT + '/check')
""" + LECTURA + """
av = chans(nb)
px, py, nn = av.get('P_0', []), av.get('P_1', []), av.get('NumNebrs', [])
# en modo avg la esquina ya no vale 0.5: es el punto de |x| máximo (promedió a 0.4)
i_esq = max(range(len(px)), key=lambda i: abs(px[i]) + abs(py[i]))
esq = (round(px[i_esq], 4), round(py[i_esq], 4), round(nn[i_esq], 1))
interior = [(round(x, 4), round(y, 4), round(v, 1))
            for x, y, v in zip(px, py, nn) if abs(x - 0.1) < 1e-6 and abs(y - 0.1) < 1e-6]
print('<<JSON>>' + json.dumps(dict(minx=round(min(px), 4), maxx=round(max(px), 4),
                                   n=len(px),
                                   esquina=list(esq),
                                   interior=interior,
                                   nn_rango=[round(min(nn), 1), round(max(nn), 1)],
                                   re_attrs=str(nb.par.nebrptattrs.eval()))))
""")
chek("avg + nebrptattrs='P' promedia: esquina raw (±0.5,±0.5) → (0.4,∓0.4) con nn=3",
     ok and (d.get("esquina") or [])[0] == 0.4 and abs((d.get("esquina") or [0, 9])[1]) == 0.4
     and (d.get("esquina") or [0, 0, 0])[2] == 3.0, d)
chek("el interior (0.1,0.1) promedia a sí mismo (vecindad simétrica; NumNebrs también se promedia: 12.0)",
     ok and any(p[0] == 0.1 and p[1] == 0.1 and p[2] == 12.0 for p in (d.get("interior") or [])), d)
report["modo_avg"] = d

# ── 5. estado canónico + material + cámara + PNG + guardia ──
ok, d = g.exec_code(CHAIN + """
import json
import time
nb = op(ROOT + '/geo/nb')
nb.par.nebroutput = 'nebr'
nb.par.nebrptattrs = 'P'
nb.par.dodist = True
print('<<JSON>>' + json.dumps(dict(re_out=str(nb.par.nebroutput.eval()),
                                   re_attrs=str(nb.par.nebrptattrs.eval()))))
""")
g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "pointspriteMAT", "name": "mat"},
          note="material")
bad, got = set_and_verify(g, ROOT + "/geo/mat", {"pointsize": 7.0, "colorr": 0.2, "colorg": 0.9, "colorb": 1.0},
                          "material celeste")
chek("pars del material aplicados (C4)", not bad, got)
ok, d = g.exec_code(CHAIN + """
import json
import time
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
geo.par.material = geo.op('mat')
chk = op(ROOT + '/check')
chk.par.pop = op(ROOT + '/geo/nb')
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
chek("material + cámara al dato", ok and "mat" in str(d.get("mat", ""))
     and len((d.get("centro") or {})) == 3, d)
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_neighbor.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

ok, d = g.exec_code(CHAIN + """
import json
import time
nb = op(ROOT + '/geo/nb')
settle(3)
time.sleep(1.5)
antes = px()
print('<<JSON>>' + json.dumps(dict(px_antes=antes, guardia=list(render_is_ours(nb)))))
""")
d = d or {}
guardia = d.get("guardia") or []
chek("el render subió la geometría (px > 0 antes de la guardia)", (d.get("px_antes") or 0) > 0,
     {"px": d.get("px_antes")})
chek("los px son del neighbor (guardia: apagar el terminal → 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-neighbor-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_neighbor ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| fallos:", g.failures)
print("nebr:", json.dumps((report.get("nebr") or {}), ensure_ascii=False)[:220])
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

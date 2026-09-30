#!/usr/bin/env python3
"""build_pop_transform.py — cobertura POP 1/6: transformPOP (+ groupPOP como apoyo).

contratos que este build mide (evidencia: results/<run>/build-pop-transform-report.json):
  * groupPOP crea 'mitad' por condición P.x>=0; debugcolor lo vuelve medible
    (Color=0.8 dentro, 0.2 fuera) y transformPOP.group mueve EXACTAMENTE esos puntos.
  * CONTRATO PELIGROSO: nombre de grupo sin población o inexistente NO filtra:
    transformPOP mueve TODOS los puntos igual que group=''.
  * mapeo exacto por punto sobre grilla determinista: rz=90 → P' = (-y, x, z)
    (pivot en origen) y P' = (2.2-y, x-2.2, z) (pivot en 2.2,0,0), err<0.01.
  * la rotación Z intercambia la distribución de N_x ↔ N_y (swap de varianzas medido).
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
g = Gauntlet(phase="build-pop-transform", run_id=RUN)
g.init()

ROOT = "/pop_transform"
CHAIN = chain_source(ROOT)

report = {"run_id": RUN,
          "objetivo": "transformPOP: group scoping real vs grupo sin población, mapeo exacto "
                      "por punto (grilla determinista), swap de varianzas de N",
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

# ── 0. entorno limpio + estructura geo+render+check ──
g.call("project_info", {}, note="TD vivo")
ok, d = g.exec_code("import json\ntry:\n op('%s').destroy()\nexcept Exception:\n pass\n"
                    "print('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
chek("limpieza previa", ok)

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_transform",
                              "nodeX": -2400, "nodeY": 2600, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"}, {"type": "cameraCOMP", "name": "cam"},
    {"type": "renderTOP", "name": "ren"}, {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True}, note="estructura")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 1. cadena: toro(2.2/0.55)→sprinkle(400)→group(P.x>=0+debugcolor)→transform ──
ok, d = g.exec_code(CHAIN + """
import json
import time
geo = op(ROOT + '/geo')
for c in list(geo.children):
    if c.name.lower().startswith('torus'):
        c.destroy()
toro = geo.create(torusPOP, 'toro')
spr = geo.create(sprinklePOP, 'spr')
grp = geo.create(groupPOP, 'grp')
tr = geo.create(transformPOP, 'tr')
spr.inputConnectors[0].connect(toro.outputConnectors[0])
grp.inputConnectors[0].connect(spr.outputConnectors[0])
tr.inputConnectors[0].connect(grp.outputConnectors[0])
toro.par.radx = 2.2
toro.par.rady = 2.2
toro.par.scale = 0.55
spr.par.numpoints = 400
tr.display = True
tr.render = True
tr.par.group = 'mitad'
# groupPOP: condición P.x >= 0 + debugcolor como INSTRUMENTO de membresía
grp.par.grname = 'mitad'
grp.par.debugcolor = True
grp.par.attr0inattr = 'P.x'
grp.par.attr0func = 'gte'
grp.par.attr0value = 0.0
settle(3)
time.sleep(0.3)
toro.cook(force=True)
time.sleep(0.2)
toro.cook(force=True)
chk = op(ROOT + '/check')
""" + LECTURA + """
gc = chans(grp)
c0 = gc.get('Color_0', [])
n_dentro = sum(1 for v in c0 if abs(v - 0.8) < 1e-6)
n_fuera = sum(1 for v in c0 if abs(v - 0.2) < 1e-6)
n_total = len(c0)
n_esperado = sum(1 for v in gc.get('P_0', []) if v >= 0)
print('<<JSON>>' + json.dumps(dict(n_total=n_total, n_dentro=n_dentro, n_fuera=n_fuera,
                                   n_esperado=n_esperado,
                                   re_grname=str(grp.par.grname.eval()),
                                   re_inattr=str(grp.par.attr0inattr.eval()),
                                   re_func=str(grp.par.attr0func.eval()),
                                   re_val=grp.par.attr0value.eval())))
""")
chek("grupo poblado (n=400, dentro == puntos con P.x>=0, fuera el resto)",
     ok and (d.get("n_total") or 0) == 400 and (d.get("n_dentro") or 0) == (d.get("n_esperado") or 1)
     and 0 < (d.get("n_dentro") or 0) < d.get("n_total"), d)
report["grupo"] = d

# ── 2. transform con grupo poblado: mueve SÓLO los de adentro ──
ok, d = g.exec_code(CHAIN + """
import json
import time
tr = op(ROOT + '/geo/tr')
tr.par.group = 'mitad'
tr.par.tx = 10.0
chk = op(ROOT + '/check')
""" + LECTURA + """
tm = chans(tr)
px, co = tm.get('P_0', []), tm.get('Color_0', [])
out = dict(n_total=len(px),
           moved_08=sum(1 for v, c in zip(px, co) if v > 5 and abs(c - 0.8) < 1e-6),
           moved_02=sum(1 for v, c in zip(px, co) if v > 5 and abs(c - 0.2) < 1e-6),
           dentro=sum(1 for c in co if abs(c - 0.8) < 1e-6),
           re_group=str(tr.par.group.eval()), re_tx=tr.par.tx.eval())
print('<<JSON>>' + json.dumps(out))
""")
chek("transform.group mueve SÓLO los del grupo (moved_08 == dentro, moved_02 == 0)",
     ok and (d.get("n_total") or 0) == 400 and (d.get("dentro") or 0) > 0
     and d.get("moved_08") == d.get("dentro") and d.get("moved_02") == 0, d)
report["grupo_scoped"] = d

# ── 3. CONTRATO PELIGROSO: grupo inexistente / sin población NO filtra ──
ok, d = g.exec_code(CHAIN + """
import json
import time
tr = op(ROOT + '/geo/tr')
chk = op(ROOT + '/check')
""" + LECTURA + """
def moved():
    tm = chans(tr)
    px, co = tm.get('P_0', []), tm.get('Color_0', [])
    return dict(n_total=len(px),
                moved_08=sum(1 for v, c in zip(px, co) if v > 5 and abs(c - 0.8) < 1e-6),
                moved_02=sum(1 for v, c in zip(px, co) if v > 5 and abs(c - 0.2) < 1e-6))


tr.par.group = 'noexiste'
a = moved()
tr.par.group = ''
b = moved()
tr.par.group = 'mitad'
print('<<JSON>>' + json.dumps(dict(inexistente=a, vacio=b,
                                   re_group_restaurado=str(tr.par.group.eval()))))
""")
ine, vac = (d or {}).get("inexistente") or {}, (d or {}).get("vacio") or {}
tot_i = (ine.get("moved_08") or 0) + (ine.get("moved_02") or 0)
tot_v = (vac.get("moved_08") or 0) + (vac.get("moved_02") or 0)
chek("CONTRATO: grupo inexistente NO filtra (400/400 movidos, igual que vacío)",
     ok and tot_i == 400 and tot_v == 400 and (ine.get("n_total") or 0) == 400, d)
report["grupo_inexistente"] = d

# ── 4. mapeo exacto por punto (grilla determinista) + swap de varianzas de N ──
ok, d = g.exec_code(CHAIN + """
import json
import time
geo = op(ROOT + '/geo')
gri = geo.create(gridPOP, 'gri')
tr2 = geo.create(transformPOP, 'tr2')
tr2.inputConnectors[0].connect(gri.outputConnectors[0])
gri.par.cols = 6
gri.par.rows = 6
gri.par.sizex = 1.0
gri.par.sizey = 1.0
tr = op(ROOT + '/geo/tr')
tr.par.group = ''
tr.par.tx = 0.0
tr.par.rz = 0.0
tr.par.px = 0.0
chk = op(ROOT + '/check')
""" + LECTURA + """
# 4a. grilla determinista: P' punto a punto
g0 = chans(gri)
x0, y0, z0 = g0.get('P_0', []), g0.get('P_1', []), g0.get('P_2', [])
tr2.par.rz = 90.0
g1 = chans(tr2)
x1, y1, z1 = g1.get('P_0', []), g1.get('P_1', []), g1.get('P_2', [])
err_origen = 0.0
if x1:
    err_origen = max(max(abs(b - (-a)) for a, b in zip(y0, x1)),
                     max(abs(b - a) for a, b in zip(x0, y1)))
tr2.par.px = 2.2
g2 = chans(tr2)
x2 = g2.get('P_0', [])
y2 = g2.get('P_1', [])
err_pivot = 0.0
if x2:
    err_pivot = max(max(abs(b - (2.2 - a)) for a, b in zip(y0, x2)),
                    max(abs(b - (a - 2.2)) for a, b in zip(x0, y2)))
tr2.par.px = 0.0
tr2.par.rz = 0.0
# 4b. swap de varianzas de N sobre la nube del toro (transform principal, todos los puntos)
n0 = chans(tr)
import statistics as st
va = dict(v0=st.pstdev(n0.get('N_0', [0])), v1=st.pstdev(n0.get('N_1', [0])))
tr.par.rz = 90.0
tr.par.px = 2.2
n1 = chans(tr)
vb = dict(v0=st.pstdev(n1.get('N_0', [0])), v1=st.pstdev(n1.get('N_1', [0])))
tr.par.rz = 0.0
tr.par.px = 0.0
print('<<JSON>>' + json.dumps(dict(n=len(x0), err_origen=round(err_origen, 4),
                                   err_pivot=round(err_pivot, 4),
                                   var_antes={k: round(v, 4) for k, v in va.items()},
                                   var_despues={k: round(v, 4) for k, v in vb.items()},
                                   cx_pivot=round((min(x2) + max(x2)) / 2, 3) if x2 else None,
                                   rango_x2=[round(min(x2), 3), round(max(x2), 3)] if x2 else None)))
""")
ok = bool(ok)
eo, ep = (d or {}).get("err_origen"), (d or {}).get("err_pivot")
va, vb = (d or {}).get("var_antes") or {}, (d or {}).get("var_despues") or {}
chek("mapeo EXACTO sin pivot: max|P'-(-y,x,z)| < 0.01 (grilla 6x6, n=%s)" % (d or {}).get("n"),
     ok and eo is not None and eo < 0.01, d)
chek("mapeo EXACTO con pivot (2.2,0,0): max|P'-(2.2-y,x-2.2,z)| < 0.01",
     ok and ep is not None and ep < 0.01, d)
chek("rz=90 intercambia N_x<->N_y (swap de desvíos, Δ<0.05)",
     ok and va.get("v0") and vb.get("v0")
     and abs((vb.get("v0") or 0) - (va.get("v1") or 0)) < 0.05
     and abs((vb.get("v1") or 0) - (va.get("v0") or 0)) < 0.05, d)
report["mapeo"] = d

# ── 5. estado canónico + material + cámara + errores + PNG + guardia ──
g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "pointspriteMAT", "name": "mat"},
          note="material")
bad, got = set_and_verify(g, ROOT + "/geo/mat", {"pointsize": 4.0, "colorr": 0.2, "colorg": 1.0, "colorb": 0.4},
                          "material verde")
chek("pars del material aplicados (C4)", not bad, got)
ok, d = g.exec_code(CHAIN + """
import json
import time
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
tr = op(ROOT + '/geo/tr')
tr.par.rz = 0.0
tr.par.px = 0.0
tr.par.tx = 0.0
tr.par.group = 'mitad'
geo.par.material = geo.op('mat')     # ASIGNAR el material (par = OP directo)
chk = op(ROOT + '/check')
chk.par.pop = tr
settle(3)
chk.cook(force=True)
medios = {}
for c in chk.chans():
    if c.name in ('P_0', 'P_1', 'P_2'):
        medios[c.name] = (min(c.vals) + max(c.vals)) / 2
cam.par.tx = round(medios.get('P_0', 0.0), 2)
cam.par.ty = round(medios.get('P_1', 0.0), 2)
cam.par.tz = round(medios.get('P_2', 0.0) + 8.0, 2)
ren.par.geometry = geo
ren.par.camera = cam
settle(3)
print('<<JSON>>' + json.dumps(dict(mat=str(geo.par.material.eval()),
                                   centro={k: round(v, 2) for k, v in medios.items()})))
""")
chek("material asignado + cámara al dato", ok and "mat" in str(d.get("mat", ""))
     and len((d.get("centro") or {})) == 3, d)
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_transform.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

ok, d = g.exec_code(CHAIN + """
import json
import time
tr = op(ROOT + '/geo/tr')
settle(3)
time.sleep(1.5)
antes = px()
print('<<JSON>>' + json.dumps(dict(px_antes=antes, guardia=list(render_is_ours(tr)))))
""")
d = d or {}
guardia = d.get("guardia") or []
chek("el render subió la geometría (px > 0 antes de la guardia)", (d.get("px_antes") or 0) > 0,
     {"px": d.get("px_antes")})
chek("los px son del transform (guardia: apagar el terminal → 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-transform-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_transform ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| fallos:", g.failures)
print("grupo:", json.dumps(report.get("grupo", {}), ensure_ascii=False)[:220])
print("mapeo:", json.dumps((report.get("mapeo") or {}).get("err_origen", {}), ensure_ascii=False))
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

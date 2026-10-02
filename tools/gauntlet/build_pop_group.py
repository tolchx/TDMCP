#!/usr/bin/env python3
"""build_pop_group.py — cobertura POP 1/6 (5c): groupPOP con red propia.

Red /pop_group: gx (gridPOP 5x4, 20 pts, 12 quads) + gp (groupPOP, grupo 'ng1')
+ tf (transformPOP, filtra por 'ng1'). Medido (evidencia: build-pop-group-report.json):
  * LA POBLACION NO CAMBIA: con thin activo el output sigue 20 pts / 12 prims —
    la membresia es METADATO, invisible para numPoints() y poptoCHOP.
  * membresia observable: discriminador transform (dy=+1.2 contra baseline) —
    thin [0-5) deja un SUBCONJUNTO ESTRICTO bimodal ({1.2, 0}, sin valores
    intermedios) pero el N NO es reproducible entre corridas (5 y 3 medidos):
    el orden de indices de la nube no es estable entre cooks; step 2 SI
    (exactamente 10 de 20 en todas las corridas).
  * debugcolor cuantiza la membresia: 2 valores de Color exactos, y el valor
    A acompana SOLO a los puntos que se movieron (pairing por indice), el B a los quietos.
  * grupo SIN miembros ('ghost') mueve TODO (20/20 dy=1.2) — reproduce C15 en red propia.
  * bound (pagina Bounding): en TODAS las configs probadas (bsphere 0.01..5,
    bbox 0.1..20, trasladado tx=10, invert) el criterio NO excluye a nadie via
    API (20/20 en el discriminador) — sin efecto medible; queda ABIERTO si
    requiere algo mas alla de los pars.
  * API de secuencias: numBlocks=0 lanza tdError 'Minimum size is 1 block'
    (verbatim) y destroyBlock no baja de 1 — piso de 1 bloque por secuencia.
  * 'remunusedpoints' figura en get_help (catalogo 2025.33070) pero NO existe
    en el build vivo 2025.32460: help stale verificado en vivo (leccion).
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
g = Gauntlet(phase="build-pop-group", run_id=RUN)
g.init()

ROOT = "/pop_group"
CHAIN = chain_source(ROOT)

report = {"run_id": RUN,
          "objetivo": "groupPOP: poblacion inmutable (membresia=metadato), discriminador transform "
                      "(thin range subconjunto estricto bimodal, step 2 = 10/20 exacto), debugcolor "
                      "binario con pairing, ghost mueve todo (C15), bound sin efecto medible + piso "
                      "de 1 bloque en secuencias",
          "ok": False, "cheks": []}


def chek(name, ok, detail=""):
    report["cheks"].append((name, bool(ok)))
    g.check(name, ok, str(detail)[:240])


# ── 0. entorno limpio + estructura ──
g.call("project_info", {}, note="TD vivo")
ok, d = g.exec_code("import json\ntry:\n op('%s').destroy()\nexcept Exception:\n pass\n"
                    "print('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
chek("limpieza previa", ok)

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_group",
                              "nodeX": 2800, "nodeY": 2600, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"}, {"type": "cameraCOMP", "name": "cam"},
    {"type": "renderTOP", "name": "ren"}, {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True}, note="estructura")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 1. fuente + groupPOP: poblacion inmutable ──
ok, d = g.exec_code(CHAIN + """
import json
import time
geo = op(ROOT + '/geo')
for c in list(geo.children):
    if c.name.lower().startswith('torus'):
        c.destroy()
gx = geo.create(gridPOP, 'gx')
gx.par.rows = 5
gx.par.cols = 4
gp = geo.create(groupPOP, 'gp')
gp.inputConnectors[0].connect(gx.outputConnectors[0])
gp.par.grname = 'ng1'
gp.par.debugcolor = True
gp.display = False
gp.render = False
tf = geo.create(transformPOP, 'tf')
tf.inputConnectors[0].connect(gp.outputConnectors[0])
tf.par.group = 'ng1'
tf.display = True
tf.render = True
chk = op(ROOT + '/check')

def medir():
    chk.par.pop = gp
    settle(2)
    chk.cook(force=True)
    time.sleep(0.2)
    chk.cook(force=True)
    time.sleep(0.1)
    chk.cook(force=True)
    return dict(pts=gp.numPoints(), prims=gp.numPrims())

base = medir()
gp.par.thinenabled = True
gp.par.thinoutrange = True
gp.par.thinrangestart = 0
gp.par.thinrangelength = 5
r5 = medir()
gp.par.thinoutrange = False
gp.par.thinstep = 2
r10 = medir()
print('<<JSON>>' + json.dumps(dict(base=base, r5=r5, r10=r10)))
""")
res = d or {}
report["inmutable"] = res
base, r5, r10 = res.get("base") or {}, res.get("r5") or {}, res.get("r10") or {}
chek("poblacion INMUTABLE con thin activo: 20 pts y 12 prims en base/range/step",
     ok and base.get("pts") == 20 and r5.get("pts") == 20 and r10.get("pts") == 20
     and base.get("prims") == 12 and r5.get("prims") == 12 and r10.get("prims") == 12, res)

# ── 2. discriminador transform: membresia exacta + debugcolor con pairing ──
ok, d = g.exec_code(CHAIN + """
import json
import time
gp = op(ROOT + '/geo/gp')
tf = op(ROOT + '/geo/tf')
chk = op(ROOT + '/check')

def muestra(pop):
    chk.par.pop = pop
    settle(2)
    chk.cook(force=True)
    time.sleep(0.2)
    chk.cook(force=True)
    time.sleep(0.1)
    chk.cook(force=True)
    return {c.name: list(c.vals) for c in chk.chans()}

def deltas_tf():
    # el delta SIEMPRE se lee de tf (downstream del groupPOP); el color, de gp
    tf.par.ty = 0.0
    chk.par.pop = tf
    settle(2)
    chk.cook(force=True)
    time.sleep(0.2)
    chk.cook(force=True)
    time.sleep(0.1)
    chk.cook(force=True)
    b = list(next(c.vals for c in chk.chans() if c.name == 'P_1'))
    tf.par.ty = 1.2
    settle(2)
    chk.cook(force=True)
    time.sleep(0.2)
    chk.cook(force=True)
    time.sleep(0.1)
    chk.cook(force=True)
    m = list(next(c.vals for c in chk.chans() if c.name == 'P_1'))
    return [round(v - w, 5) for v, w in zip(m, b)]

gp.par.debugcolor = True
gp.par.thinenabled = True
gp.par.thinoutrange = True
gp.par.thinrangestart = 0
gp.par.thinrangelength = 5
dy5 = deltas_tf()
m5 = muestra(gp)
col5 = m5.get('Color_0', [])
gp.par.thinoutrange = False
gp.par.thinstep = 2
dy10 = deltas_tf()
gp.par.thinstep = 1
# pairing: el Color de los movidos vs el de los quietos (mismo cook)
mov_cols = [c for c, v in zip(col5, dy5) if abs(v - 1.2) < 1e-4]
quie_cols = [c for c, v in zip(col5, dy5) if abs(v) < 1e-4]
print('<<JSON>>' + json.dumps(dict(
    n5=len(dy5), mov5=sum(1 for v in dy5 if abs(v - 1.2) < 1e-4),
    qui5=sum(1 for v in dy5 if abs(v) < 1e-4),
    otros5=len(dy5) - sum(1 for v in dy5 if abs(v - 1.2) < 1e-4 or abs(v) < 1e-4),
    mov10=sum(1 for v in dy10 if abs(v - 1.2) < 1e-4),
    ncol=len(col5), vals=sorted(set(round(v, 4) for v in col5)),
    mov_col_unico=len(set(round(v, 5) for v in mov_cols)),
    quie_col_unico=len(set(round(v, 5) for v in quie_cols)),
    colA=round(mov_cols[0], 4) if mov_cols else None,
    colB=round(quie_cols[0], 4) if quie_cols else None)))
""")
res = d or {}
report["membresia"] = res
colA, colB = res.get("colA"), res.get("colB")
chek("thin [0-5): subconjunto ESTRICTO bimodal (dy exactamente {0, 1.2}, 1..19 movidos)",
     ok and res.get("n5") == 20 and res.get("otros5") == 0
     and 1 <= res.get("mov5", 0) <= 19, res)
chek("thin step 2: 10 movidos de 20",
     ok and res.get("mov10") == 10, res)
chek("debugcolor: Color cuantizado en 2 valores y el valor A acompana SOLO a los movidos",
     ok and res.get("ncol") == 20 and len(res.get("vals") or []) == 2
     and res.get("mov_col_unico") == 1 and res.get("quie_col_unico") == 1
     and colA is not None and colB is not None and abs(colA - colB) > 1e-3, res)

# ── 3. grupo fantasma mueve TODO (C15) + bound sin efecto + piso de secuencia ──
ok, d = g.exec_code(CHAIN + """
import json
import time
gp = op(ROOT + '/geo/gp')
tf = op(ROOT + '/geo/tf')
gx = op(ROOT + '/geo/gx')
chk = op(ROOT + '/check')

def muestra(pop):
    chk.par.pop = pop
    settle(2)
    chk.cook(force=True)
    time.sleep(0.2)
    chk.cook(force=True)
    time.sleep(0.1)
    chk.cook(force=True)
    return {c.name: list(c.vals) for c in chk.chans()}

def deltas_tf():
    tf.par.ty = 0.0
    chk.par.pop = tf
    settle(2)
    chk.cook(force=True)
    time.sleep(0.2)
    chk.cook(force=True)
    time.sleep(0.1)
    chk.cook(force=True)
    b = list(next(c.vals for c in chk.chans() if c.name == 'P_1'))
    tf.par.ty = 1.2
    settle(2)
    chk.cook(force=True)
    time.sleep(0.2)
    chk.cook(force=True)
    time.sleep(0.1)
    chk.cook(force=True)
    m = list(next(c.vals for c in chk.chans() if c.name == 'P_1'))
    return [round(v - w, 5) for v, w in zip(m, b)]

def n_mov(dy):
    return sum(1 for v in dy if abs(v - 1.2) < 1e-4)

sal = {}
geo = op(ROOT + '/geo')
# ghost: grupo sin miembros
gpx = geo.create(groupPOP, 'gpx')
gpx.inputConnectors[0].connect(gx.outputConnectors[0])
gpx.par.grname = 'ghost'
gpx.display = False
gpx.render = False
tf.inputConnectors[0].connect(gpx.outputConnectors[0])
dyg = deltas_tf()
sal['ghost_n'] = len(dyg)
sal['ghost_mov'] = n_mov(dyg)
tf.inputConnectors[0].connect(gp.outputConnectors[0])
gp.par.debugcolor = False
gp.par.thinenabled = False
# bound: bloque unico (piso 1) y barrido de configs
seq = gp.par.bound.sequence
sal['nb_inicial'] = seq.numBlocks
try:
    seq.numBlocks = 0
    sal['piso'] = 'sin error'
except Exception as e:
    sal['piso'] = str(e)[:90]
gp.par.bound0inattr = 'P'
gp.par.bound0invert = False
gp.par.bound0translatex = 0.0
for tag, t, sc, scz in (('bs03', 'usebsphere', 0.3, 0.3), ('bb20', 'usebbox', 20.0, 20.0)):
    gp.par.bound0type = t
    gp.par.bound0scalex = sc
    gp.par.bound0scaley = sc
    gp.par.bound0scalez = scz
    sal[tag] = n_mov(deltas_tf())
gp.par.bound0type = 'usebsphere'
gp.par.bound0scalex = 1.0
gp.par.bound0scaley = 1.0
gp.par.bound0scalez = 1.0
gp.par.bound0translatex = 10.0
sal['bs1_tx10'] = n_mov(deltas_tf())
gp.par.bound0translatex = 0.0
gp.par.bound0invert = True
sal['bs1_inv'] = n_mov(deltas_tf())
gp.par.bound0invert = False
sal['err_gp'] = gp.errors()[:60]
print('<<JSON>>' + json.dumps(sal))
""")
res = d or {}
report["ghost_bound"] = res
configs = [res.get(k) for k in ("bs03", "bb20", "bs1_tx10", "bs1_inv")]
chek("grupo 'ghost' SIN miembros mueve TODO: 20/20 dy=1.2 (C15 reproducido en red 5c)",
     ok and res.get("ghost_n") == 20 and res.get("ghost_mov") == 20, res)
chek("secuencia bound: numBlocks=0 lanza 'Minimum size is 1 block' (piso de 1 bloque)",
     ok and "Minimum size is 1 block" in str(res.get("piso", "")), res)
chek("bound: en 4 configs (bsphere 0.3, bbox 20, tx=10, invert) NINGUNA excluye (20/20)",
     ok and all(c == 20 for c in configs) and res.get("err_gp") == "", res)

# ── 4. estado canónico + material + cámara + PNG + guardia ──

def call_retry(tool, args, note, tries=4, wait=1.5):
    """tool call con reintento: TD lento devuelve 'recovering from a slow
    operation' (td_slow_operation, C14) — espera y reintenta la MISMA llamada."""
    r = {}
    for i in range(tries):
        r = g.call(tool, args, note)
        if not g.is_err(r):
            return r
        time.sleep(wait)
    g.fail("fallo la tool %s (%s) tras %d intentos" % (tool, note, tries))
    return r

time.sleep(2.0)  # dejar respirar a TD tras el barrido de bound (C14)
g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "pointspriteMAT", "name": "mat"},
          note="material")
bad, got = set_and_verify(g, ROOT + "/geo/mat", {"pointsize": 5.0, "colorr": 1.0, "colorg": 0.6, "colorb": 0.2},
                          "material naranja", call=call_retry)
chek("pars del material aplicados (C4)", not bad, got)
ok, d = g.exec_code(CHAIN + """
import json
import time
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
tf = op(ROOT + '/geo/tf')
gp = op(ROOT + '/geo/gp')
gp.par.debugcolor = True
gp.par.thinenabled = True
gp.par.thinoutrange = True
gp.par.thinrangestart = 0
gp.par.thinrangelength = 5
tf.par.ty = 1.2
tf.cook(force=True)
geo.par.material = geo.op('mat')
chk = op(ROOT + '/check')
chk.par.pop = tf
settle(3)
chk.cook(force=True)
medios = {}
for c in chk.chans():
    if c.name in ('P_0', 'P_1', 'P_2'):
        medios[c.name] = (min(c.vals) + max(c.vals)) / 2
cam.par.tx = round(medios.get('P_0', 0.0), 2)
cam.par.ty = round(medios.get('P_1', 0.0), 2)
cam.par.tz = round(medios.get('P_2', 0.0) + 3.0, 2)
ren.par.geometry = geo
ren.par.camera = cam
settle(3)
print('<<JSON>>' + json.dumps(dict(mat=str(geo.par.material.eval()),
                                   centro={k: round(v, 2) for k, v in medios.items()},
                                   n=tf.numPoints())))
""")
chek("estado canónico (filtro por ng1 + debugcolor) + material + cámara",
     ok and "mat" in str((d or {}).get("mat", "")) and (d or {}).get("n") == 20
     and len(((d or {}).get("centro") or {})) == 3, d)
g.call_retry = call_retry  # por si las tools MCP siguientes golpean C14
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_group.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

ok, d = g.exec_code(CHAIN + """
import json
import time
tf = op(ROOT + '/geo/tf')
settle(3)
time.sleep(1.5)
antes = px()
print('<<JSON>>' + json.dumps(dict(px_antes=antes, guardia=list(render_is_ours(tf)))))
""")
d = d or {}
guardia = d.get("guardia") or []
chek("el render subió la geometría (px > 0 antes de la guardia)", (d.get("px_antes") or 0) > 0,
     {"px": d.get("px_antes")})
chek("los px son del group chain (guardia: apagar el terminal → 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-group-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_group ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| fallos:", g.failures)
print("membresia:", json.dumps(report.get("membresia", {}), ensure_ascii=False))
print("ghost_bound:", json.dumps(report.get("ghost_bound", {}), ensure_ascii=False))
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

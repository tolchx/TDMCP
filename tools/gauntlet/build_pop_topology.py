#!/usr/bin/env python3
"""build_pop_topology.py — cobertura POP 5/6 (5c): topologyPOP.

Red /pop_topology: A (gridPOP 3x3 en 'points', trasladado tx=5: solo puntos,
9 pts / 0 prims) + B (gridPOP 3x3 quads en el origen: 9 pts / 4 quads) +
tp (topologyPOP: input A, primsourcemode='specpop' con primspop=B).
Mide (evidencia: build-pop-topology-report.json):
  * specpop EXACTO: la topologia de B (4 quads) se aplica sobre los puntos de A
    -> 9 pts / 4 prims.
  * P viene del INPUT: el rango de P_X del resultado es [4,6] (A trasladado a
    tx=5), no [-1,1] (B). Los atributos N y Tex del primsource estan accesibles
    en el resultado (el vertice referenciado ES el de B).
  * topology='ref' es VIVO: cambiar B none->triangles->quads cambia el resultado a
    0 prims, 8 tris y 4 quads respectivamente (con cook explicito de B).
  * topology='copy' NO congela: tras copiar, cambiar B a rows lleva el resultado
    a 0 prims (la copia se rehace por cook; es copia de buffers, no snapshot).
  * maxpointsmode='custom' con maxpoints=5 recorta el input a 5 pts manteniendo
    las 4 quads del primsource, y es deterministico (2 lecturas iguales).
  * render: camara con lookat al geometryCOMP + posicion iso (2,2,2) (mecanismo
    canonico del gauntlet; apuntar a mano con rx/ry da render negro).
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
g = Gauntlet(phase="build-pop-topology", run_id=RUN)
g.init()

ROOT = "/pop_topology"
CHAIN = chain_source(ROOT)

report = {"run_id": RUN,
          "objetivo": "topologyPOP: topologia de B (specpop) sobre puntos de A con P del input y "
                      "N/Tex del primsource, ref vivo ante cambios de B, copy no congela (por cook), "
                      "maxpoints custom recorta el input de forma deterministica",
          "ok": False, "cheks": []}


def chek(name, ok, detail=""):
    report["cheks"].append((name, bool(ok)))
    g.check(name, ok, str(detail)[:240])


# ── 0. entorno limpio + estructura ──
g.call("project_info", {}, note="TD vivo")
ok, d = g.exec_code("import json\ntry:\n op('%s').destroy()\n op('/pop_probe5c').destroy()\nexcept Exception:\n pass\n"
                    "print('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
chek("limpieza previa", ok)

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_topology",
                              "nodeX": 4400, "nodeY": 2600, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"}, {"type": "cameraCOMP", "name": "cam"},
    {"type": "renderTOP", "name": "ren"}, {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True}, note="estructura")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 1. specpop + P del input + ref vivo + copy + maxpoints ──
ok, d = g.exec_code(CHAIN + """
import json
import time
geo = op(ROOT + '/geo')
for c in list(geo.children):
    if c.name.lower().startswith('torus'):
        c.destroy()
pa = geo.create(gridPOP, 'A')
pa.par.rows = 3
pa.par.cols = 3
pa.par.sizex = 2.0
pa.par.sizey = 2.0
pa.par.surftype = 'none'
pa.par.tx = 5.0
pb = geo.create(gridPOP, 'B')
pb.par.rows = 3
pb.par.cols = 3
pb.par.sizex = 2.0
pb.par.sizey = 2.0
tp = geo.create(topologyPOP, 'tp')
tp.inputConnectors[0].connect(pa.outputConnectors[0])
tp.par.topology = 'ref'
tp.par.primsourcemode = 'specpop'
tp.par.primspop = pb
tp.display = True
tp.render = True
chk = op(ROOT + '/check')

def topo(pop):
    pop.cook(force=True)
    time.sleep(0.12)
    pop.cook(force=True)
    time.sleep(0.08)
    return dict(pts=pop.numPoints(), prims=pop.numPrims())

def leer_tp():
    chk.par.pop = tp
    tp.cook(force=True)
    time.sleep(0.1)
    chk.cook(force=True)
    time.sleep(0.08)
    chk.cook(force=True)
    return {c.name: list(c.vals) for c in chk.chans()}

def cambiar_b(st):
    pb.par.surftype = st
    pb.cook(force=True)
    time.sleep(0.12)
    pb.cook(force=True)
    time.sleep(0.08)

sal = {}
sal['A'] = topo(pa)
sal['B'] = topo(pb)
sal['tp_ref'] = topo(tp)
ch = leer_tp()
rango = {}
for n in ('P_0', 'P_1', 'P_2'):
    if n in ch:
        rango[n] = (round(min(ch[n]), 2), round(max(ch[n]), 2))
sal['tp_rango'] = rango
sal['tp_attrs'] = sorted(set(k.split('_')[0] for k in ch))
# ref vivo: B none -> tris -> quads (siempre con cook explicito de B)
cambiar_b('none')
sal['ref_none'] = topo(tp)
cambiar_b('triangles')
sal['ref_tris'] = topo(tp)
cambiar_b('quads')
sal['ref_quads'] = topo(tp)
# copy: se re-copia por cook, NO congela
tp.par.topology = 'copy'
sal['copy_quads'] = topo(tp)
cambiar_b('none')
sal['copy_tras_cambio'] = topo(tp)
cambiar_b('quads')
tp.par.topology = 'ref'
# maxpoints custom
tp.par.maxpointsmode = 'custom'
tp.par.maxpoints = 5
m1 = topo(tp)
m2 = topo(tp)
sal['maxpoints5'] = dict(a=m1, b=m2, deterministico=(m1 == m2))
tp.par.maxpointsmode = 'input'
print('<<JSON>>' + json.dumps(sal))
""")
res = d or {}
report["topo"] = res
chek("fuentes: A 9 pts / 0 prims (none, tx=5) y B 9 pts / 4 quads",
     ok and (res.get("A") or {}) == {"pts": 9, "prims": 0}
     and (res.get("B") or {}) == {"pts": 9, "prims": 4}, res)
chek("specpop EXACTO: topologia de B (4 quads) sobre los puntos de A -> 9 pts / 4 prims",
     ok and (res.get("tp_ref") or {}) == {"pts": 9, "prims": 4}, res)
tr = (res.get("tp_rango") or {})
chek("P viene del INPUT: P_X en [4,6] (A trasladado a tx=5), no el rango de B",
     ok and tr.get("P_0") == [4.0, 6.0] and tr.get("P_1") == [-1.0, 1.0], res)
chek("atributos del primsource accesibles en el resultado (N y Tex presentes)",
     ok and (res.get("tp_attrs") or []) == ["N", "P", "Tex"], res)
chek("topology=ref es VIVO: B none/triangles/quads -> tp 0 / 8 / 4",
     ok and (res.get("ref_none") or {}) == {"pts": 9, "prims": 0}
     and (res.get("ref_tris") or {}) == {"pts": 9, "prims": 8}
     and (res.get("ref_quads") or {}) == {"pts": 9, "prims": 4}, res)
chek("topology=copy NO congela: tras copiar, B en none lleva el resultado a 0 prims",
     ok and (res.get("copy_quads") or {}) == {"pts": 9, "prims": 4}
     and (res.get("copy_tras_cambio") or {}) == {"pts": 9, "prims": 0}, res)
mp = (res.get("maxpoints5") or {})
chek("maxpoints=5 recorta el input a 5 pts manteniendo 4 quads, deterministico (2 lecturas)",
     ok and (mp.get("a") or {}) == {"pts": 5, "prims": 4} and mp.get("deterministico") is True, res)

# ── 2. estado canónico + material + cámara + PNG + guardia ──
g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "pointspriteMAT", "name": "mat"},
          note="material")
bad, got = set_and_verify(g, ROOT + "/geo/mat", {"pointsize": 6.0, "colorr": 0.4, "colorg": 1.0, "colorb": 0.55},
                          "material verde")
chek("pars del material aplicados (C4)", not bad, got)
ok, d = g.exec_code(CHAIN + """
import json
import time
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
pa, pb, tp = op(ROOT + '/geo/A'), op(ROOT + '/geo/B'), op(ROOT + '/geo/tp')
pa.par.tx = 0.0
pb.par.surftype = 'quads'
tp.par.topology = 'ref'
tp.par.maxpointsmode = 'input'
tp.cook(force=True)
geo.par.material = geo.op('mat')
# camara canonica del gauntlet: lookat al geometryCOMP + posicion iso (2,2,2)
cam.par.lookat = geo
cam.par.tx, cam.par.ty, cam.par.tz = 2.0, 2.0, 2.0
ren.par.geometry = geo
ren.par.camera = cam
settle(4)
print('<<JSON>>' + json.dumps(dict(mat=str(geo.par.material.eval()),
                                   lookat=str(cam.par.lookat.eval()),
                                   pos=[round(cam.par.tx.eval(), 2), round(cam.par.ty.eval(), 2),
                                        round(cam.par.tz.eval(), 2)],
                                   n=tp.numPoints(), p=tp.numPrims())))
""")
chek("estado canónico (A en el origen + ref quads) + material + cámara lookat iso",
     ok and "mat" in str((d or {}).get("mat", "")) and (d or {}).get("n") == 9
     and (d or {}).get("p") == 4 and str((d or {}).get("lookat", "")).endswith("/geo")
     and (d or {}).get("pos") == [2.0, 2.0, 2.0], d)
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_topology.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

ok, d = g.exec_code(CHAIN + """
import json
import time
tpp = op(ROOT + '/geo/tp')
settle(3)
time.sleep(1.5)
antes = px()
print('<<JSON>>' + json.dumps(dict(px_antes=antes, guardia=list(render_is_ours(tpp)))))
""")
d = d or {}
guardia = d.get("guardia") or []
chek("el render subió la geometría (px > 0 antes de la guardia)", (d.get("px_antes") or 0) > 0,
     {"px": d.get("px_antes")})
chek("los px son del topology (guardia: apagar el terminal → 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-topology-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_topology ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| fallos:", g.failures)
print("topo:", json.dumps(report.get("topo", {}), ensure_ascii=False))
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

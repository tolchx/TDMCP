#!/usr/bin/env python3
"""build_pop_ray.py — cobertura POP 5d: rayPOP.

Red /pop_ray: gridPOP (origenes + N) -> rayPOP(0), boxPOP -> rayPOP(1), poptoCHOP.

Medido en TD 2025.32460 (MCP oficial 1.1.55):
  * con TODOS los toggles de salida apagados: 9 pts / 4 prims y sin atributos
    Ray*; pero P ya se reescribe a la posicion del impacto y N a la normal del
    impacto. Los toggles solo agregan los Ray*; no desactivan la reescritura.
  * con `dist`/`numhits`/`inside`/`hitprimindex`/`hitnormal`: P se REESCRIBE a la
    posicion del primer impacto (grid z=-1 + N +Z sobre box 1x1 -> z=-0.5), N se
    reescribe con la normal del impacto (-Z) y aparecen RayDistance=0.5,
    RayNumHits (3/2/4 por punto: caras trianguladas y diagonales), RayPrimIndex=0,
    RayInside.
  * RayInside es ruidoso en impactos de borde: con origenes fuera, las 4 esquinas
    de la grilla dan 1 (bug/quirks medido); no usarlo como test de volumen.
  * sin impacto (grid 3x3 de tamano 3): P queda en el origen, RayDistance=1e8,
    RayPrimIndex=4294967296 (centinelas), RayNumHits=0.
  * `limitraylength` + `scale=0.6`: P queda a 0.6*0.5 del origen (-1 -> -0.7) pero
    RayDistance/RayNumHits siguen reportando el impacto real (0.5 / 4).
  * `negateray`: sin impactos.
  * `lift=0.1`: P = -0.4 (se mueve CONTRA la normal outward, hacia el origen).
  * `bypass`: passthrough exacto y sin atributos Ray*.
  * `hwraytracing=fastbuild/fasttrace`: mismo conteo, pero solo reporta el primer
    impacto (RayNumHits=1) y los miss llevan los mismos centinelas.
  * `numbounces>1` EXIGE N en la geometria de colision: sin N -> error y salida
    intacta; una spherePOP con `normal='pointNormals'` + 2 bounces -> 27 pts / 9
    prims (3 puntos por rayo, 1 prim por rayo), sin error.
  * `barycoords=True` no agrega ningun atributo de punto visible en este build
    (se reporta, no se exige).
  * el menu de `rayattrib` es DINAMICO: lista los atributos del input (P, N, Tex,
    Tex.i01), no un set fijo.
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
g = Gauntlet(phase="build-pop-ray", run_id=RUN)
g.init()

ROOT = "/pop_ray"
CHAIN = chain_source(ROOT)

report = {"run_id": RUN,
          "objetivo": "rayPOP: reescritura de P/N al impacto, RayDistance/RayNumHits/"
                      "RayPrimIndex/RayInside, centinelas de miss, limitraylength, "
                      "negateray, lift, bypass, HW tracing, bounces que exigen N",
          "ok": False, "cheks": []}


def chek(name, ok, detail=""):
    report["cheks"].append((name, bool(ok)))
    g.check(name, ok, str(detail)[:240])


def call_retry(tool, args, note, tries=4, wait=1.5):
    r = {}
    for _ in range(tries):
        r = g.call(tool, args, note)
        if not g.is_err(r):
            return r
        time.sleep(wait)
    g.fail("fallo la tool %s (%s) tras %d intentos" % (tool, note, tries))
    return r


# ── 0. entorno limpio + estructura ──
g.call("project_info", {}, note="TD vivo")
ok, d = g.exec_code("import json\ntry:\n op(%r).destroy()\nexcept Exception:\n pass\n"
                    "print('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
chek("limpieza previa", ok)

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_ray",
                              "nodeX": 4400, "nodeY": 2600, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"}, {"type": "cameraCOMP", "name": "cam"},
    {"type": "renderTOP", "name": "ren"}, {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True}, note="estructura")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 1. medicion de rayPOP ──
ok, d = g.exec_code(CHAIN + """
import json
import time
geo = op(ROOT + '/geo')
for c in list(geo.children):
    c.destroy()
g = geo.create(gridPOP, 'g')
box = geo.create(boxPOP, 'box')
r = geo.create(rayPOP, 'r')
chk = op(ROOT + '/check')
chk.par.pop = r
g.par.cols = 3
g.par.rows = 3
g.par.tz = -1.0
g.outputConnectors[0].connect(r.inputConnectors[0])
box.outputConnectors[0].connect(r.inputConnectors[1])

TOGGLES = ('dist', 'hitnormal', 'numhits', 'inside', 'hitprimindex', 'barycoords',
           'bypass', 'negateray', 'limitraylength', 'trimray', 'connectpoints')


def clean():
    for p in TOGGLES:
        setattr(r.par, p, False)
    r.par.rayattrib = 'N'
    r.par.scale = 1.0
    r.par.lift = 0.0
    r.par.numbounces = 1
    r.par.hwraytracing = 'off'
    g.par.cols = 3
    g.par.rows = 3
    g.par.sizex = 1.0
    g.par.sizey = 1.0
    g.par.tz = -1.0
    box.outputConnectors[0].connect(r.inputConnectors[1])
    cook()


def cook():
    settle(2)
    for o in (g, box, r, chk):
        o.cook(force=True)
    time.sleep(0.12)
    for o in (r, chk):
        o.cook(force=True)
    time.sleep(0.05)


def snap():
    ch = {}
    for c in chk.chans():
        ch[c.name] = [round(v, 4) for v in c.vals]
    return dict(npts=r.numPoints(), nprims=r.numPrims(), err=r.errors(),
                attrs=[a.name for a in r.pointAttributes], ch=ch)


def set_toggles(*names):
    for p in TOGGLES:
        setattr(r.par, p, False)
    for p in names:
        setattr(r.par, p, True)


sal = {}
# A: passthrough puro
clean()
sal['off'] = snap()
sal['rayattrib_menu'] = list(r.par.rayattrib.menuNames)
# B: impacto (grid 1x1 -> todas las esquinas dan en la cara frontal)
clean()
set_toggles('dist', 'hitnormal', 'numhits', 'inside', 'hitprimindex')
cook()
sal['hit'] = snap()
# C: miss (grid 3x3 de tamano 3: solo el centro da en la caja 1x1)
clean()
set_toggles('dist', 'numhits', 'inside', 'hitprimindex')
g.par.sizex = 3.0
g.par.sizey = 3.0
cook()
sal['miss'] = snap()
# D: limitraylength + scale 0.6 -> P a 0.3 del origen, atributos del impacto real
clean()
set_toggles('dist', 'numhits')
g.par.sizex = 1.0
g.par.sizey = 1.0
r.par.limitraylength = True
r.par.scale = 0.6
cook()
sal['limit'] = snap()
# E: negateray
clean()
set_toggles('dist', 'numhits', 'hitprimindex')
r.par.negateray = True
cook()
sal['negate'] = snap()
# F: lift 0.1 (medido: -0.5 -> -0.4, contra la normal outward)
clean()
set_toggles('dist')
r.par.lift = 0.1
cook()
sal['lift'] = snap()
# G: bypass exacto
clean()
r.par.bypass = True
cook()
sal['bypass'] = snap()
# H: HW tracing sobre el escenario de miss
clean()
set_toggles('dist', 'numhits')
g.par.sizex = 3.0
g.par.sizey = 3.0
r.par.hwraytracing = 'fastbuild'
cook()
sal['hw_fastbuild'] = snap()
r.par.hwraytracing = 'fasttrace'
cook()
sal['hw_fasttrace'] = snap()
# I: bounces sin N en la colision -> error
clean()
sph = geo.op('sph') or geo.create(spherePOP, 'sph')
sph.par.normal = 'none'
sph.outputConnectors[0].connect(r.inputConnectors[1])
g.par.sizex = 1.0
g.par.sizey = 1.0
g.par.tz = -2.0
r.par.numbounces = 2
cook()
sal['bounce_nonormals'] = snap()
# J: bounces con N(pointNormals)
sph.par.normal = 'pointNormals'
cook()
sal['bounce_normals'] = snap()
# K: barycoords sin atributo visible
clean()
r.par.barycoords = True
cook()
sal['bary'] = snap()
clean()
print('<<JSON>>' + json.dumps(sal))
""")
res = d or {}
report["ray"] = res

off = res.get("off") or {}
hit = res.get("hit") or {}
mis = res.get("miss") or {}
lim = res.get("limit") or {}
neg = res.get("negate") or {}
lif = res.get("lift") or {}
byp = res.get("bypass") or {}
hw = res.get("hw_fastbuild") or {}
hw2 = res.get("hw_fasttrace") or {}
bno = res.get("bounce_nonormals") or {}
bok = res.get("bounce_normals") or {}
bary = res.get("bary") or {}
menu = res.get("rayattrib_menu") or []


def near(a, b, tol=1e-3):
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def cans(dct, name):
    return (dct.get("ch") or {}).get(name) or []


chek("sin toggles: P y N ya reescritos al impacto, sin atributos Ray*",
     ok and off.get("npts") == 9 and off.get("nprims") == 4
     and all(near(v, -0.5) for v in cans(off, "P_2"))
     and all(near(v, -1.0) for v in cans(off, "N_2"))
     and not any(a.startswith("Ray") for a in off.get("attrs") or []),
     {"p2": cans(off, "P_2"), "n2": cans(off, "N_2"), "attrs": off.get("attrs")})

chek("impacto: P reescrito a z=-0.5 y N a la normal del impacto (-Z)",
     ok and all(near(v, -0.5) for v in cans(hit, "P_2"))
     and all(near(v, -1.0) for v in cans(hit, "N_2")), {"p2": cans(hit, "P_2"), "n2": cans(hit, "N_2")})

chek("RayDistance=0.5 exacto en los 9 rayos",
     ok and len(cans(hit, "RayDistance")) == 9
     and all(near(v, 0.5) for v in cans(hit, "RayDistance")), cans(hit, "RayDistance"))

chek("RayNumHits: 3/2/4 por punto (caras trianguladas, diagonal del centro)",
     ok and cans(hit, "RayNumHits") == [3, 2, 3, 2, 4, 2, 3, 2, 3], cans(hit, "RayNumHits"))

chek("RayPrimIndex=0 (cara frontal) en todos los impactos",
     ok and all(near(v, 0.0) for v in cans(hit, "RayPrimIndex")), cans(hit, "RayPrimIndex"))

chek("quirk RayInside: 1 en las 4 esquinas aun con origenes FUERA de la caja",
     ok and cans(hit, "RayInside") == [1, 0, 1, 0, 0, 0, 1, 0, 1], cans(hit, "RayInside"))

chek("miss: solo el centro impacta; el resto queda en el origen",
     ok and mis.get("npts") == 9
     and cans(mis, "P_2") == [-1, -1, -1, -1, -0.5, -1, -1, -1, -1], cans(mis, "P_2"))

chek("centinelas de miss: RayDistance=1e8 y RayPrimIndex=2^32",
     ok and cans(mis, "RayDistance") == [1e8] * 4 + [0.5] + [1e8] * 4
     and cans(mis, "RayPrimIndex") == [4294967296.0] * 4 + [0.0] + [4294967296.0] * 4,
     {"d": cans(mis, "RayDistance"), "p": cans(mis, "RayPrimIndex")})

chek("limitraylength + scale=0.6: P a -0.7 (0.6*0.5) y atributos del impacto real",
     ok and near(cans(lim, "P_2")[4], -0.7) and near(cans(lim, "RayDistance")[4], 0.5)
     and near(cans(lim, "RayNumHits")[4], 4.0), {"p2": cans(lim, "P_2"), "d": cans(lim, "RayDistance")})

chek("negateray: sin impactos (P en -1, RayNumHits=0, distancia centinela)",
     ok and all(near(v, -1.0) for v in cans(neg, "P_2"))
     and all(near(v, 0.0) for v in cans(neg, "RayNumHits"))
     and all(near(v, 1e8) for v in cans(neg, "RayDistance")), cans(neg, "RayNumHits"))

chek("lift=0.1 mueve P a -0.4 (contra la normal outward, hacia el origen)",
     ok and near(cans(lif, "P_2")[0], -0.4), cans(lif, "P_2"))

chek("bypass: passthrough exacto y sin atributos Ray*",
     ok and byp.get("npts") == 9 and all(near(v, -1.0) for v in cans(byp, "P_2"))
     and not any(a.startswith("Ray") for a in byp.get("attrs") or []), byp.get("attrs"))

chek("hwraytracing fastbuild: miss con centinelas y hit con RayNumHits=1",
     ok and near(cans(hw, "P_2")[4], -0.5) and near(cans(hw, "P_2")[0], -1.0)
     and near(cans(hw, "RayDistance")[4], 0.5) and near(cans(hw, "RayDistance")[0], 1e8)
     and near(cans(hw, "RayNumHits")[4], 1.0) and near(cans(hw, "RayNumHits")[0], 0.0),
     {"p2": cans(hw, "P_2"), "n": cans(hw, "RayNumHits")})

chek("fasttrace da el mismo resultado que fastbuild",
     ok and cans(hw2, "P_2") == cans(hw, "P_2")
     and cans(hw2, "RayDistance") == cans(hw, "RayDistance"), {"fast": cans(hw2, "P_2")})

chek("numbounces=2 sin N en la colision: error explicito y salida intacta",
     ok and "normals" in (bno.get("err") or "") and bno.get("npts") == 9, bno.get("err"))

chek("numbounces=2 con sphere normal='pointNormals': 27 pts / 9 prims, sin error",
     ok and bok.get("npts") == 27 and bok.get("nprims") == 9 and not bok.get("err"), bok)

chek("menu rayattrib dinamico: incluye N y NO inventa PartVel",
     ok and "N" in menu and "PartVel" not in menu, menu)

report["bary_attrs"] = bary.get("attrs")
chek("barycoords=True no agrega atributo de punto visible (se reporta como quirk)",
     ok and not any("bary" in a.lower() for a in (bary.get("attrs") or [])), bary.get("attrs"))

# ── 2. estado canonico + material + camara + PNG + guardia ──
time.sleep(1.5)
g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "pointspriteMAT", "name": "mat"},
          note="material")
bad, got = set_and_verify(g, ROOT + "/geo/mat",
                          {"pointsize": 6.0, "colorr": 0.2, "colorg": 0.9, "colorb": 1.0},
                          "material celeste", call=call_retry)
chek("pars del material aplicados (C4)", not bad, got)

ok, d = g.exec_code(CHAIN + """
import json
import time
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
g, box, r = geo.op('g'), geo.op('box'), geo.op('r')
g.par.cols = 10
g.par.rows = 10
g.par.sizex = 1.0
g.par.sizey = 1.0
g.par.tz = -1.0
box.outputConnectors[0].connect(r.inputConnectors[1])
r.par.bypass = False
r.par.negateray = False
r.par.limitraylength = False
r.par.numbounces = 1
r.par.hwraytracing = 'off'
r.display = True
r.render = True
box.display = False
box.render = False
geo.par.material = geo.op('mat')
cam.par.lookat = geo
cam.par.tx, cam.par.ty, cam.par.tz = 2.0, 2.0, 2.0
ren.par.geometry = geo
ren.par.camera = cam
settle(3)
print('<<JSON>>' + json.dumps(dict(mat=str(geo.par.material.eval()),
                                   lookat=str(cam.par.lookat.eval()), n=r.numPoints())))
""")
d = d or {}
chek("estado canonico: material + camara lookat=geo iso(2,2,2) + 10x10 impactos",
     ok and "mat" in str(d.get("mat", "")) and "geo" in str(d.get("lookat", "")) and d.get("n") == 100, d)
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_ray.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

ok, d = g.exec_code(CHAIN + """
import json
import time
r = op(ROOT + '/geo/r')
settle(3)
time.sleep(1.0)
antes = px()
print('<<JSON>>' + json.dumps(dict(px_antes=antes, guardia=list(render_is_ours(r)))))
""")
d = d or {}
guardia = d.get("guardia") or []
chek("el render subio los impactos (px > 0 antes de la guardia)", (d.get("px_antes") or 0) > 0,
     {"px": d.get("px_antes")})
chek("los px son del ray chain (guardia: apagar el terminal -> 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-ray-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_ray ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| fallos:", g.failures)
print("ray:", json.dumps({k: {kk: vv for kk, vv in (v or {}).items() if kk != "ch"}
                          for k, v in report.get("ray", {}).items() if isinstance(v, dict)},
                         ensure_ascii=False)[:2000])
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

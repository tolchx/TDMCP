#!/usr/bin/env python3
"""build_pop_mathcombine.py — cobertura POP 5d: mathcombinePOP (gating de rayPOP).

Red /pop_mathcombine: gridPOP 3x3 (origenes) -> rayPOP(0), boxPOP -> rayPOP(1);
la salida de rayPOP alimenta mathcombinePOP y mathmixPOP.

Medido en TD 2025.32460 (MCP oficial 1.1.55):
  * `gt` con un vector constante como segundo operando produce un atributo 0/1:
    RayNumHits [0,0,0,0,4,0,0,0,0] -> Hit [0,0,0,0,1,0,0,0,0].
  * `gt` es ESTRICTO: con umbral 4 el centro (4 hits) da 0; con umbral 3 da 1.
  * `mix` con C=Hit es el gating: lo=0.2, hi=0.9 -> Gate
    [0.2 x4, 0.9, 0.2 x4]. Con C=0.5 (constante) da 0.55 en los 9 puntos:
    es un lerp A*(1-C)+B*C, no un clamp 0/1.
  * `mathcombinePOP` encadena bloques: el bloque 1 puede leer `Hit` creado por el
    bloque 0. Cuatro bloques en el mismo op funcionan.
  * La pagina `attr` trae 1 bloque default vacio (`attr0customname=''`); no hace
    falta declarar nada: `comb*result` auto-crea `Hit`/`Gate`/`HitAt4`/`HitAt3`.
    `attr` solo predeclara nombres/tipos cuando se quiere controlar el default.
  * `mathmixPOP` es el control: mismos 3 bloques (gt -> mix -> add), `GateM`
    identico a `Gate` y `GateMPlusLo = GateM + lo` (0.4 / 1.1). No tiene pagina
    `attr`; para crear atributos se usa mathcombinePOP.
  * Gotcha: la segunda entrada de mathcombine no expone `in1_<attr>` en esta
    configuracion; `input1attrs='*'` deja visible `Tex` sin prefijo. No se usa aca.
  * render: 10x10 puntos con pointspriteMAT; camara iso (4,4,4) con lookat al geo.
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
g = Gauntlet(phase="build-pop-mathcombine", run_id=RUN)
g.init()

ROOT = "/pop_mathcombine"
CHAIN = chain_source(ROOT)

report = {"run_id": RUN,
          "objetivo": "mathcombinePOP: gating 0/1 de rayPOP (gt estricto, mix lerp, "
                      "encadenado de bloques, auto-atributos) y control mathmixPOP",
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

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_mathcombine",
                              "nodeX": 5200, "nodeY": 2600, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"}, {"type": "cameraCOMP", "name": "cam"},
    {"type": "renderTOP", "name": "ren"}, {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True}, note="estructura")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 1. medicion de mathcombinePOP / mathmixPOP ──
ok, d = g.exec_code(CHAIN + """
import json
import time
geo = op(ROOT + '/geo')
for c in list(geo.children):
    c.destroy()
g = geo.create(gridPOP, 'g')
g.par.cols = 3
g.par.rows = 3
g.par.sizex = 3.0
g.par.sizey = 3.0
g.par.tz = -1.0
box = geo.create(boxPOP, 'box')
r = geo.create(rayPOP, 'r')
r.par.numhits = True
mc = geo.create(mathcombinePOP, 'mc')
mm = geo.create(mathmixPOP, 'mm')
mh = geo.create(mathcombinePOP, 'mh')
chks = {}
for name, o in (('mc', mc), ('mm', mm), ('mh', mh)):
    chk = geo.create(poptoCHOP, 'chk_' + name)
    chk.par.pop = o
    chks[name] = chk
g.outputConnectors[0].connect(r.inputConnectors[0])
box.outputConnectors[0].connect(r.inputConnectors[1])
r.outputConnectors[0].connect(mc.inputConnectors[0])
mc.outputConnectors[0].connect(mm.inputConnectors[0])
r.outputConnectors[0].connect(mh.inputConnectors[0])

# vectores constantes
mc.par.vec.sequence.numBlocks = 5
mc.par.vec0name = 'thresh0'; mc.par.vec0value0 = 0.0
mc.par.vec1name = 'lo'; mc.par.vec1value0 = 0.2
mc.par.vec2name = 'hi'; mc.par.vec2value0 = 0.9
mc.par.vec3name = 'thresh4'; mc.par.vec3value0 = 4.0
mc.par.vec4name = 'thresh3'; mc.par.vec4value0 = 3.0
mm.par.vec.sequence.numBlocks = 3
mm.par.vec0name = 'thresh0'; mm.par.vec0value0 = 0.0
mm.par.vec1name = 'lo'; mm.par.vec1value0 = 0.2
mm.par.vec2name = 'hi'; mm.par.vec2value0 = 0.9
mh.par.vec.sequence.numBlocks = 3
mh.par.vec0name = 'lo'; mh.par.vec0value0 = 0.2
mh.par.vec1name = 'hi'; mh.par.vec1value0 = 0.9
mh.par.vec2name = 'half'; mh.par.vec2value0 = 0.5

# mathcombine: 4 bloques encadenados, sin pagina attr
mc.par.comb.sequence.numBlocks = 4
mc.par.comb0oper = 'gt'; mc.par.comb0scopea = 'RayNumHits'; mc.par.comb0scopeb = 'thresh0'; mc.par.comb0result = 'Hit'
mc.par.comb1oper = 'mix'; mc.par.comb1scopea = 'lo'; mc.par.comb1scopeb = 'hi'; mc.par.comb1scopec = 'Hit'; mc.par.comb1result = 'Gate'
mc.par.comb2oper = 'gt'; mc.par.comb2scopea = 'RayNumHits'; mc.par.comb2scopeb = 'thresh4'; mc.par.comb2result = 'HitAt4'
mc.par.comb3oper = 'gt'; mc.par.comb3scopea = 'RayNumHits'; mc.par.comb3scopeb = 'thresh3'; mc.par.comb3result = 'HitAt3'

# mathmix: control independiente con 3 bloques
mm.par.comb.sequence.numBlocks = 3
mm.par.comb0oper = 'gt'; mm.par.comb0scopea = 'RayNumHits'; mm.par.comb0scopeb = 'thresh0'; mm.par.comb0result = 'HitM'
mm.par.comb1oper = 'mix'; mm.par.comb1scopea = 'lo'; mm.par.comb1scopeb = 'hi'; mm.par.comb1scopec = 'HitM'; mm.par.comb1result = 'GateM'
mm.par.comb2oper = 'add'; mm.par.comb2scopea = 'GateM'; mm.par.comb2scopeb = 'lo'; mm.par.comb2result = 'GateMPlusLo'

# mathcombine: lerp con C fraccional constante
mh.par.comb.sequence.numBlocks = 1
mh.par.comb0oper = 'mix'; mh.par.comb0scopea = 'lo'; mh.par.comb0scopeb = 'hi'; mh.par.comb0scopec = 'half'; mh.par.comb0result = 'MixHalf'


def cook():
    settle(2)
    for o in (g, box, r, mc, mm, mh):
        o.cook(force=True)
    time.sleep(0.12)
    for o in (mc, mm, mh):
        o.cook(force=True)
    time.sleep(0.08)
    for o in chks.values():
        o.cook(force=True)
    time.sleep(0.05)


def snap():
    out = {}
    for name, o in (('mc', mc), ('mm', mm), ('mh', mh)):
        chk = chks[name]
        chk.cook(force=True)
        out[name] = dict(npts=o.numPoints(), nprims=o.numPrims(), err=o.errors(),
                         attrs=[a.name for a in o.pointAttributes],
                         ch={c.name: [round(v, 4) for v in c.vals] for c in chk.chans()})
    return out


cook()
res = snap()
res['mc_numblocks'] = int(mc.par.comb.sequence.numBlocks)
res['mm_numblocks'] = int(mm.par.comb.sequence.numBlocks)
res['mh_numblocks'] = int(mh.par.comb.sequence.numBlocks)
res['mc_has_attr_page'] = any(p.name == 'attr' for p in mc.pars())
res['mm_has_attr_page'] = any(p.name == 'attr' for p in mm.pars())
res['mc_attr_blocks'] = int(mc.par.attr.sequence.numBlocks)
res['mc_attr_customname'] = str(mc.par.attr0customname.eval())
print('<<JSON>>' + json.dumps(res))
""")
res = d or {}
report["math"] = res

mc = res.get("mc") or {}
mm = res.get("mm") or {}
mh = res.get("mh") or {}


def cans(dct, name):
    return (dct.get("ch") or {}).get(name) or []


def near_list(a, b, tol=1e-4):
    return len(a) == len(b) and all(abs(float(x) - float(y)) <= tol for x, y in zip(a, b))


chek("rayPOP: RayNumHits = [0,0,0,0,4,0,0,0,0] (solo el centro impacta)",
     ok and cans(mc, "RayNumHits") == [0, 0, 0, 0, 4, 0, 0, 0, 0], cans(mc, "RayNumHits"))

chek("mathcombinePOP gt: Hit 0/1 a partir de RayNumHits",
     ok and cans(mc, "Hit") == [0, 0, 0, 0, 1, 0, 0, 0, 0], cans(mc, "Hit"))

chek("mathcombinePOP mix con C=Hit: Gate = 0.2 salvo el centro 0.9",
     ok and near_list(cans(mc, "Gate"), [0.2, 0.2, 0.2, 0.2, 0.9, 0.2, 0.2, 0.2, 0.2]),
     cans(mc, "Gate"))

chek("gt ESTRICTO: umbral 4 sobre 4 hits -> HitAt4 todo 0",
     ok and cans(mc, "HitAt4") == [0, 0, 0, 0, 0, 0, 0, 0, 0], cans(mc, "HitAt4"))

chek("gt ESTRICTO: umbral 3 sobre 4 hits -> HitAt3 solo el centro",
     ok and cans(mc, "HitAt3") == [0, 0, 0, 0, 1, 0, 0, 0, 0], cans(mc, "HitAt3"))

chek("attr con bloque default VACIO: comb*result auto-crea Hit/Gate/HitAt4/HitAt3",
     ok and all(a in (mc.get("attrs") or []) for a in ("Hit", "Gate", "HitAt4", "HitAt3"))
     and res.get("mc_attr_blocks") == 1 and res.get("mc_attr_customname") == ""
     and res.get("mc_has_attr_page") is True,
     {"attrs": mc.get("attrs"), "blocks": res.get("mc_attr_blocks"),
      "customname": res.get("mc_attr_customname")})

chek("4 bloques encadenados en mathcombinePOP (los bloques ven resultados previos)",
     ok and res.get("mc_numblocks") == 4 and not mc.get("err"), mc.get("err"))

chek("mathmixPOP gt: HitM identico a Hit",
     ok and near_list(cans(mm, "HitM"), cans(mc, "Hit")), cans(mm, "HitM"))

chek("mathmixPOP mix: GateM identico a Gate",
     ok and near_list(cans(mm, "GateM"), cans(mc, "Gate")), cans(mm, "GateM"))

chek("mathmixPOP add: GateMPlusLo = GateM + 0.2 (0.4 / 1.1)",
     ok and near_list(cans(mm, "GateMPlusLo"), [0.4, 0.4, 0.4, 0.4, 1.1, 0.4, 0.4, 0.4, 0.4]),
     cans(mm, "GateMPlusLo"))

chek("mathmixPOP encadena 3 bloques y NO tiene pagina attr",
     ok and res.get("mm_numblocks") == 3 and res.get("mm_has_attr_page") is False
     and not mm.get("err"), {"blocks": res.get("mm_numblocks"), "err": mm.get("err")})

chek("mathcombinePOP mix con C=0.5 es lerp: 0.2*(1-0.5)+0.9*0.5 = 0.55",
     ok and near_list(cans(mh, "MixHalf"), [0.55] * 9), cans(mh, "MixHalf"))

chek("sin errores en los tres operadores", ok and not mc.get("err") and not mm.get("err")
     and not mh.get("err"), {"mc": mc.get("err"), "mm": mm.get("err"), "mh": mh.get("err")})

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
mc, mm, mh = geo.op('mc'), geo.op('mm'), geo.op('mh')
# grilla mas densa para que el PNG muestre el patron de impactos
g.par.cols = 10
g.par.rows = 10
g.par.sizex = 3.0
g.par.sizey = 3.0
g.par.tz = -1.0
for o in (mc, mm, mh, r, g, box):
    o.display = False
    o.render = False
mc.display = True
mc.render = True
geo.par.material = geo.op('mat')
cam.par.lookat = geo
cam.par.tx, cam.par.ty, cam.par.tz = 4.0, 4.0, 4.0
ren.par.geometry = geo
ren.par.camera = cam
settle(3)
print('<<JSON>>' + json.dumps(dict(mat=str(geo.par.material.eval()),
                                   lookat=str(cam.par.lookat.eval()), n=mc.numPoints())))
""")
d = d or {}
chek("estado canonico: material + camara lookat=geo iso(4,4,4) + 100 puntos",
     ok and "mat" in str(d.get("mat", "")) and "geo" in str(d.get("lookat", "")) and d.get("n") == 100, d)
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_mathcombine.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 100, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

ok, d = g.exec_code(CHAIN + """
import json
import time
mc = op(ROOT + '/geo/mc')
settle(3)
time.sleep(1.0)
antes = px()
print('<<JSON>>' + json.dumps(dict(px_antes=antes, guardia=list(render_is_ours(mc)))))
""")
d = d or {}
guardia = d.get("guardia") or []
chek("el render subio los puntos (px > 0 antes de la guardia)", (d.get("px_antes") or 0) > 0,
     {"px": d.get("px_antes")})
chek("los px son del mathcombine chain (guardia: apagar el terminal -> 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-mathcombine-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_mathcombine ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| fallos:", g.failures)
print("math:", json.dumps({k: {"npts": (v or {}).get("npts"), "err": (v or {}).get("err")}
                           for k, v in report.get("math", {}).items() if isinstance(v, dict)},
                          ensure_ascii=False))
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

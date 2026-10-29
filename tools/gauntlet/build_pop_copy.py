#!/usr/bin/env python3
"""build_pop_copy.py — cobertura POP 5d: copyPOP.

Red /pop_copy: boxPOP (fuente, 8 pts / 6 quads) -> copyPOP(0),
gridPOP 3x3 (template, 9 pts) -> copyPOP(1), poptoCHOP.

Medido en TD 2025.32460 (MCP oficial 1.1.55):
  * input 0 = geometria fuente, input 1 = puntos template. Sin template,
    `ncy` copia la fuente ncy veces: 1 -> 8/6, 2 -> 16/12, 3 -> 24/18
    (las copias quedan superpuestas: P identico).
  * con template 3x3 (9 pts) y ncy=1 -> 72 pts / 54 prims; ncy=2 -> 144/108.
    Formula: puntos = fuente_puntos * template_puntos * ncy.
  * `dotemplatetranslate` esta OFF por default: las copias quedan apiladas en la
    fuente (P en [-0.5,0.5]). Encendido, P = fuente + punto template:
    primera copia [-1,0,0,-1,-1,0,0,-1], rango x/y [-1,1], z [-0.5,0.5].
  * `copyid` respeta el scope: point -> pointAttributes, primitive ->
    primAttributes, vertex -> vertAttributes (con CopyId). Con ncy=1 NO aparece
    CopyId en ningun scope aunque haya 9 copias por template: el atributo se
    emite solo cuando ncy>1.
  * `bypass` devuelve la fuente intacta (8/6).
  * QUIRK medido: los pars de transform de la fuente (`tx`, `sx`, `scale`) NO
    cambian P en esta configuracion (template translate ON, ncy=1). Para ubicar
    copias hay que usar los puntos del template, no estos pars. Se testea para
    detectar si el build cambia.
  * render: 9 clusters de puntos (template size 3) con pointspriteMAT, camara iso (4,4,4).
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
g = Gauntlet(phase="build-pop-copy", run_id=RUN)
g.init()

ROOT = "/pop_copy"
CHAIN = chain_source(ROOT)

report = {"run_id": RUN,
          "objetivo": "copyPOP: formula de copias con/sin template, ncy, "
                      "dotemplatetranslate, scopes de CopyId, bypass y pars de "
                      "transform inertes",
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

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_copy",
                              "nodeX": 4800, "nodeY": 2600, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"}, {"type": "cameraCOMP", "name": "cam"},
    {"type": "renderTOP", "name": "ren"}, {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True}, note="estructura")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 1. medicion de copyPOP ──
ok, d = g.exec_code(CHAIN + """
import json
import time
geo = op(ROOT + '/geo')
for c in list(geo.children):
    c.destroy()
box = geo.create(boxPOP, 'box')
tmpl = geo.create(gridPOP, 'tmpl')
tmpl.par.cols = 3
tmpl.par.rows = 3
cp = geo.create(copyPOP, 'cp')
chk = op(ROOT + '/check')
chk.par.pop = cp
box.outputConnectors[0].connect(cp.inputConnectors[0])
tmpl.outputConnectors[0].connect(cp.inputConnectors[1])


def cook():
    settle(2)
    for o in (box, tmpl, cp):
        o.cook(force=True)
    time.sleep(0.12)
    cp.cook(force=True)
    chk.par.pop = None
    chk.par.pop = cp
    chk.cook(force=True)
    time.sleep(0.1)
    chk.cook(force=True)


def snap():
    ch = {}
    for c in chk.chans():
        v = [round(x, 4) for x in c.vals]
        ch[c.name] = [round(min(v), 4), round(max(v), 4), v[:16], len(v)]
    return dict(npts=cp.numPoints(), nprims=cp.numPrims(), err=cp.errors(),
                pattrs=[a.name for a in cp.pointAttributes],
                prattrs=[a.name for a in cp.primAttributes],
                vattrs=[a.name for a in cp.vertAttributes], ch=ch)


def clean():
    cp.par.ncy = 1
    cp.par.dotemplatetranslate = False
    cp.par.copyid = 'off'
    cp.par.bypass = False
    cp.par.tx = 0.0
    cp.par.sx = 1.0
    cp.par.sy = 1.0
    cp.par.sz = 1.0
    cp.par.scale = 1.0
    tmpl.par.sizex = 1.0
    tmpl.par.sizey = 1.0
    box.outputConnectors[0].connect(cp.inputConnectors[0])
    tmpl.outputConnectors[0].connect(cp.inputConnectors[1])
    cook()


def no_template():
    try:
        tmpl.outputConnectors[0].disconnect()
    except Exception:
        pass
    cook()


sal = {}
clean()
# A: sin template, ncy 1/2/3
no_template()
sal['notmpl_ncy1'] = snap()
cp.par.ncy = 2
cook()
sal['notmpl_ncy2'] = snap()
cp.par.ncy = 3
cook()
sal['notmpl_ncy3'] = snap()
# B: template 3x3
clean()
sal['tmpl_ncy1'] = snap()
cp.par.ncy = 2
cook()
sal['tmpl_ncy2'] = snap()
# C: template translate off/on
clean()
sal['translate_off'] = snap()
cp.par.dotemplatetranslate = True
cook()
sal['translate_on'] = snap()
# D: CopyId scopes (ncy=1 no aparece; ncy=2 si)
sal['copyid_off_ncy1'] = snap()
cp.par.ncy = 2
cp.par.copyid = 'point'
cook()
sal['copyid_point'] = snap()
cp.par.copyid = 'primitive'
cook()
sal['copyid_prim'] = snap()
cp.par.copyid = 'vertex'
cook()
sal['copyid_vert'] = snap()
# E: bypass
clean()
cp.par.bypass = True
cook()
sal['bypass'] = snap()
# F: quirk de transforms de fuente
clean()
cp.par.dotemplatetranslate = True
cook()
sal['transform_base'] = snap()
cp.par.tx = 1.0
cp.par.sx = 2.0
cp.par.scale = 2.0
cook()
sal['transform_moved'] = snap()
clean()
print('<<JSON>>' + json.dumps(sal))
""")
res = d or {}
report["copy"] = res

n1 = res.get("notmpl_ncy1") or {}
n2 = res.get("notmpl_ncy2") or {}
n3 = res.get("notmpl_ncy3") or {}
t1 = res.get("tmpl_ncy1") or {}
t2 = res.get("tmpl_ncy2") or {}
toff = res.get("translate_off") or {}
ton = res.get("translate_on") or {}
cid1 = res.get("copyid_off_ncy1") or {}
cidp = res.get("copyid_point") or {}
cidpr = res.get("copyid_prim") or {}
cidv = res.get("copyid_vert") or {}
byp = res.get("bypass") or {}
tbase = res.get("transform_base") or {}
tmove = res.get("transform_moved") or {}


def cans(dct, name):
    return (dct.get("ch") or {}).get(name) or [None, None, [], 0]


chek("sin template ncy=1: 8 pts / 6 prims (la fuente tal cual)",
     ok and n1.get("npts") == 8 and n1.get("nprims") == 6, {"n": n1.get("npts"), "p": n1.get("nprims")})
chek("sin template ncy=2: 16 pts / 12 prims (2 copias superpuestas)",
     ok and n2.get("npts") == 16 and n2.get("nprims") == 12
     and cans(n2, "P_0")[0] == -0.5 and cans(n2, "P_0")[1] == 0.5, {"n": n2.get("npts")})
chek("sin template ncy=3: 24 pts / 18 prims",
     ok and n3.get("npts") == 24 and n3.get("nprims") == 18, {"n": n3.get("npts")})

chek("template 3x3 (9 pts) + ncy=1: 72 pts / 54 prims",
     ok and t1.get("npts") == 72 and t1.get("nprims") == 54, {"n": t1.get("npts")})
chek("template 3x3 + ncy=2: 144 pts / 108 prims",
     ok and t2.get("npts") == 144 and t2.get("nprims") == 108, {"n": t2.get("npts")})

chek("dotemplatetranslate OFF (default): copias apiladas, P en [-0.5,0.5]",
     ok and cans(toff, "P_0")[0] == -0.5 and cans(toff, "P_0")[1] == 0.5
     and cans(toff, "P_2")[0] == -0.5 and cans(toff, "P_2")[1] == 0.5,
     {"P_0": cans(toff, "P_0")[:2], "P_2": cans(toff, "P_2")[:2]})
chek("dotemplatetranslate ON: P = fuente + template, x/y en [-1,1]",
     ok and cans(ton, "P_0")[0] == -1.0 and cans(ton, "P_0")[1] == 1.0
     and cans(ton, "P_1")[0] == -1.0 and cans(ton, "P_1")[1] == 1.0
     and cans(ton, "P_2")[0] == -0.5 and cans(ton, "P_2")[1] == 0.5,
     {"P_0": cans(ton, "P_0")[:2], "P_1": cans(ton, "P_1")[:2]})
chek("primera copia en el primer punto template (-0.5,-0.5): P_0 = [-1,0,0,-1,...]",
     ok and cans(ton, "P_0")[2][:8] == [-1.0, 0.0, 0.0, -1.0, -1.0, 0.0, 0.0, -1.0],
     cans(ton, "P_0")[2][:8])

chek("ncy=1 NO emite CopyId en ningun scope (aunque haya 9 copias)",
     ok and "CopyId" not in (cid1.get("pattrs") or [])
     and "CopyId" not in (cid1.get("prattrs") or [])
     and "CopyId" not in (cid1.get("vattrs") or []),
     {"p": cid1.get("pattrs"), "pr": cid1.get("prattrs"), "v": cid1.get("vattrs")})
chek("copyid='point' con ncy=2: CopyId en pointAttributes",
     ok and "CopyId" in (cidp.get("pattrs") or []), cidp.get("pattrs"))
chek("copyid='primitive': CopyId en primAttributes",
     ok and "CopyId" in (cidpr.get("prattrs") or []), cidpr.get("prattrs"))
chek("copyid='vertex': CopyId en vertAttributes",
     ok and "CopyId" in (cidv.get("vattrs") or []), cidv.get("vattrs"))

chek("bypass: la fuente intacta (8 pts / 6 prims)",
     ok and byp.get("npts") == 8 and byp.get("nprims") == 6, {"n": byp.get("npts")})

chek("QUIRK: tx=1/sx=2/scale=2 NO mueven P (usar puntos template para ubicar copias)",
     ok and cans(tmove, "P_0")[2][:8] == cans(tbase, "P_0")[2][:8]
     and cans(tmove, "P_0")[:2] == cans(tbase, "P_0")[:2],
     {"base": cans(tbase, "P_0")[:2], "movido": cans(tmove, "P_0")[:2]})

# ── 2. estado canonico + material + camara + PNG + guardia ──
time.sleep(1.5)
g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "pointspriteMAT", "name": "mat"},
          note="material")
bad, got = set_and_verify(g, ROOT + "/geo/mat",
                          {"pointsize": 6.0, "colorr": 0.9, "colorg": 0.6, "colorb": 0.2},
                          "material naranja", call=call_retry)
chek("pars del material aplicados (C4)", not bad, got)

ok, d = g.exec_code(CHAIN + """
import json
import time
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
box, tmpl, cp = geo.op('box'), geo.op('tmpl'), geo.op('cp')
tmpl.par.sizex = 3.0
tmpl.par.sizey = 3.0
cp.par.ncy = 1
cp.par.dotemplatetranslate = True
cp.par.copyid = 'off'
cp.par.bypass = False
cp.par.tx = 0.0
cp.par.sx = 1.0
cp.par.scale = 1.0
cp.display = True
cp.render = True
box.display = False
box.render = False
geo.par.material = geo.op('mat')
cam.par.lookat = geo
cam.par.tx, cam.par.ty, cam.par.tz = 4.0, 4.0, 4.0
ren.par.geometry = geo
ren.par.camera = cam
settle(3)
print('<<JSON>>' + json.dumps(dict(mat=str(geo.par.material.eval()),
                                   lookat=str(cam.par.lookat.eval()), n=cp.numPoints())))
""")
d = d or {}
chek("estado canonico: material + camara lookat=geo iso(4,4,4) + 72 puntos",
     ok and "mat" in str(d.get("mat", "")) and "geo" in str(d.get("lookat", "")) and d.get("n") == 72, d)
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_copy.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 100, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

ok, d = g.exec_code(CHAIN + """
import json
import time
cp = op(ROOT + '/geo/cp')
settle(3)
time.sleep(1.0)
antes = px()
print('<<JSON>>' + json.dumps(dict(px_antes=antes, guardia=list(render_is_ours(cp)))))
""")
d = d or {}
guardia = d.get("guardia") or []
chek("el render subio las copias (px > 0 antes de la guardia)", (d.get("px_antes") or 0) > 0,
     {"px": d.get("px_antes")})
chek("los px son del copy chain (guardia: apagar el terminal -> 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-copy-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_copy ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| fallos:", g.failures)
print("copy:", json.dumps({k: {"npts": (v or {}).get("npts"), "nprims": (v or {}).get("nprims")}
                           for k, v in report.get("copy", {}).items() if isinstance(v, dict)},
                          ensure_ascii=False))
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

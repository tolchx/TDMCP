#!/usr/bin/env python3
"""build_pop_color_trails_attr.py — sexto proyecto POP (variante SIN GLSL): attributePOP + estelas.

Veredicto medido (la sonda lo refutó y el build lo documenta): attributePOP NO puede mapear
atributo→atributo por punto. Sus herramientas: `attr` (constantes — FUNCIONA), `dup`
(duplicar atributo) y `ren` (renombrar) — **inefectivos en el build vivo**: read-back ok
(`dup0name='PartVel'` queda escrito) y CERO efecto sobre los atributos (ni siquiera sobre un
Color ya creado). El mapeo por punto con rampa necesita glslPOP (proyecto F,
`/pop_color_trails`) u otro POP de mapping no explorado aún.

Lo que ESTE build verifica (todo real):
  * attributePOP CREA el atributo `Color` float4 con valores constantes (`attr0name='color'`):
    `inspect_values` lo confirma (`pointAttributesChanged: ['Color']`).
  * El color constante SOBREVIVE toda la cadena (tint → trail → topoints → null_render) y llega
    al render con los valores configurados — el material blanco lo muestra sin distorsión.
  * El defecto queda ASSERTADO como check negativo: con `dup PartVel→Color` activo, Color sigue
    constante (no sigue a PartVel_1 que sí varía).

Pipeline: emit → sim → grav ─┬→ fb (targetpop, C10)
                └→ curl → tint(attributePOP, Color constante) → tr(trail) → topoints → null_render
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
g = Gauntlet(phase="build-pop-color-trails-attr", run_id=RUN)
g.init()

ROOT = "/pop_color_trails_attr"
GEO = ROOT + "/geo"
CHAIN = chain_source(ROOT)

CHANS = ("PartVel_0", "PartVel_1", "PartVel_2", "Color_0", "Color_1", "Color_2")

report = {"run_id": RUN,
          "objetivo": "estelas con color por velocidad SIN glsl (attributePOP dup/ren PartVel→Color)",
          "ok": False, "cheks": []}


def chek(name, ok, detail=""):
    report["cheks"].append((name, bool(ok)))
    g.check(name, ok, str(detail)[:240])


def snapshot(nodes, label):
    """PartVel/Color (min,max,uniq) por nodo, en UNA llamada (mismo frame)."""
    ok, d = g.exec_code(CHAIN + """
import json
settle(4)
chk = op('%s/check')
out = dict()
for n in %r:
    chk.par.pop = ('%s/geo/null_render' if n == 'term' else '%s/geo/' + n)
    chk.cook(force=True)
    m = dict()
    for c in chk.chans():
        if c.name in %r:
            vals = c.vals
            m[c.name] = dict(mn=round(min(vals), 3), mx=round(max(vals), 3),
                             uniq=len(set(round(v, 2) for v in vals)))
    m['n'] = chk.numSamples
    out[n] = m
chk.par.pop = '%s/geo/null_render'
print('<<JSON>>' + json.dumps(dict(out=out, t=round(absTime.seconds, 2))))
""" % (ROOT, list(nodes), ROOT, GEO, CHANS, ROOT))
    if not ok:
        print("    (medición falló: %s)" % json.dumps(d)[:200])
        return {}
    m = d.get("out") or {}
    print("    [%s] tint n=%s Color_1=%s | term n=%s Color_1=%s"
          % (label, (m.get("tint") or {}).get("n"), ((m.get("tint") or {}).get("Color_1") or {}).get("mx"),
             (m.get("term") or {}).get("n"), ((m.get("term") or {}).get("Color_1") or {}).get("mx")))
    return m


# ── 0. entorno limpio ──
g.call("project_info", {}, note="TD vivo")
ok, d = g.exec_code("import json\ntry:\n op('%s').destroy()\nexcept Exception:\n pass\n"
                    "print('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
chek("limpieza previa", ok)

# ── 1. estructura de render ──
g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_color_trails_attr",
                              "nodeX": -2000, "nodeY": 900, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"},
    {"type": "cameraCOMP", "name": "cam"},
    {"type": "lightCOMP", "name": "light"},
    {"type": "renderTOP", "name": "ren"},
    {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True},
    note="estructura geo+render+check")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 2. auto-torus fuera ──
ok, d = g.exec_code("""
import json
geo = op('%s')
torus = [c.name for c in geo.children if c.name.lower().startswith('torus')]
for n in torus:
    geo.op(n).destroy()
print('<<JSON>>' + json.dumps({'had_torus': torus}))
""" % GEO)
chek("auto-torus borrado", ok and bool(d.get("had_torus")), d)

# ── 3. cadena POP: sim → fuerzas → curl → TINT (attributePOP) → trail → prims; fb desde grav ──
g.call_ok("build_network", {"parent_path": GEO, "operators": [
    {"type": "spherePOP", "name": "emit"},
    {"type": "particlePOP", "name": "sim"},
    {"type": "forceradialPOP", "name": "grav"},
    {"type": "noisePOP", "name": "curl"},
    {"type": "attributePOP", "name": "tint"},
    {"type": "trailPOP", "name": "tr"},
    {"type": "convertPOP", "name": "topoints"},
    {"type": "nullPOP", "name": "null_render"},
    {"type": "nullPOP", "name": "fb"}],
    "connections": [{"from": "emit", "to": "sim"}, {"from": "sim", "to": "grav"},
                    {"from": "grav", "to": "curl"}, {"from": "curl", "to": "tint"},
                    {"from": "tint", "to": "tr"}, {"from": "tr", "to": "topoints"},
                    {"from": "topoints", "to": "null_render"}, {"from": "grav", "to": "fb"}],
    "auto_layout": True}, note="cadena sim+color(attr)+estelas con feedback")

# ── 4. parámetros de la cadena ──
ok, d = g.exec_code("""
import json
emit, sim, gv = op('%s/emit'), op('%s/sim'), op('%s/grav')
curl, tint, tr = op('%s/curl'), op('%s/tint'), op('%s/tr')
sim.par.targetpop = op('%s/fb')
emit.par.radx = 0.3
emit.par.rady = 0.3
emit.par.radz = 0.3
sim.par.timeintegration = True
sim.par.birthrate = 60
sim.par.life = 1.2
sim.par.maxparticles = 2000
sim.par.initvelocityy = 0
sim.par.preroll = 0
gv.par.globforcemult = 1
gv.par.globforcey = -2
gv.par.radial = 0
gv.par.axial = 0
gv.par.spiral = 0
gv.par.planar = 0
curl.par.mode = 'quality'
curl.par.type = 'simplex3d'
curl.par.amp = 0.35
curl.par.offset = 0.0
curl.par.curl3d = True
tr.par.lengthunit = 'frames'
tr.par.length = 16
tr.par.reset.pulse()
print('<<JSON>>' + json.dumps(dict(target=str(sim.par.targetpop), fy=gv.par.globforcey.eval(),
                                   amp=curl.par.amp.eval(), lu=str(tr.par.lengthunit.eval()),
                                   ln=tr.par.length.eval())))
""" % (GEO, GEO, GEO, GEO, GEO, GEO, GEO))
chek("cadena aplicada (fb, g=-2, curl 3D, trail 16 FRAMES)",
     ok and str(d.get("target", "")).endswith("/fb") and d.get("fy") == -2
     and d.get("amp") == 0.35 and d.get("lu") == "frames" and d.get("ln") == 16, d)

# ── 5. attributePOP 'tint': Color CONSTANTE vía `attr` (lo que el nodo sí hace) ──
ok, d = g.exec_code(CHAIN + """
import json
tint = op('%s/tint')
tint.par.dup0name = ''
tint.par.ren0from = ''
tint.par.attr.sequence.numBlocks = 1
tint.par.attr0name = 'color'
tint.par.attr0numcomps = '4'
tint.par.attr0value0 = 0.2
tint.par.attr0value1 = 1.0
tint.par.attr0value2 = 0.4
tint.par.attr0value3 = 1.0
settle(4)
print('<<JSON>>' + json.dumps(dict(attr0=str(tint.par.attr0name.eval()),
                                   comps=str(tint.par.attr0numcomps.eval()))))
""" % GEO)
chek("attributePOP configurado (Color constante 0.2/1.0/0.4)",
     ok and d.get("attr0") == "color" and d.get("comps") == "4", d)

# creación del atributo: inspect_values es la fuente autoritativa (td-pop-family)
r = g.call("inspect_values", {"path": GEO + "/tint", "max_points": 1},
           note="pointAttributes tras tint")
txt = g.text_of(r)
creo = '"pointAttributesChanged"' in txt and 'Color' in txt.split('pointAttributesChanged')[1][:60]
chek("attributePOP CREA el atributo Color (inspect: pointAttributesChanged)", creo, txt[-200:])

bad, got = set_and_verify(g, GEO + "/topoints", {"convert": "topointprims"}, "prims de punto")
chek("topointprims aplicado", not bad, got)

# ── 6. material BLANCO (multiplica el Color del punto) + flags + cámara al dato ──
g.call_ok("create_operator", {"parent_path": GEO, "type": "pointspriteMAT", "name": "mat"},
          note="material de puntos")
ok, d = g.exec_code(
    CHAIN
    + """
import json
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
m = op(ROOT + '/geo/mat')
m.par.pointsize = 4.0
m.par.colorr = 1.0
m.par.colorg = 1.0
m.par.colorb = 1.0
geo.par.material = m
term = geo.op('null_render')
term.display = True
term.render = True
chk = op(ROOT + '/check')
chk.par.pop = ROOT + '/geo/null_render'
settle()
chk.cook(force=True)
medios = []
for c in chk.chans():
    if c.name in ('P_0', 'P_1', 'P_2'):
        medios.append((min(c.vals) + max(c.vals)) / 2)
cam.par.tx = round(medios[0], 2)
cam.par.ty = round(medios[1], 2)
cam.par.tz = round(medios[2] + 10.0, 2)
ren.par.geometry = geo
ren.par.camera = cam
ren.par.lights = op(ROOT + '/light')
settle()
print('<<JSON>>' + json.dumps({'mat': str(geo.par.material.eval()),
                               'centro_P': [round(v, 2) for v in medios]}))
""")
chek("material blanco + flags + camara-al-dato + bindings",
     ok and "mat" in str(d.get("mat", "")) and d.get("centro_P"), d)

# ── 7. verificación: números antes que píxeles (C5) ──
ok, d = g.exec_code("""
import json
%s
term = op('%s/null_render')
chk = op('%s/check')
settle()
chk.cook(force=True)
out = {'pts': term.numPoints(), 'prims': term.numPrims(), 'samples': chk.numSamples, 'px': px()}
print('<<JSON>>' + json.dumps(out))
""" % (CHAIN, GEO, ROOT))
chek("1 prim/punto + poptoCHOP ve el terminal", ok and d.get("prims") == d.get("pts")
     and (d.get("samples") or 0) > 0 and (d.get("px") or 0) > 500, d)

ok, d = g.exec_code("""
import json
%s
own = render_is_ours(op('%s/geo/null_render'))
print('<<JSON>>' + json.dumps({'ok': own[0], 'on': own[1], 'off': own[2]}))
""" % (CHAIN, ROOT))
chek("los px son nuestros (guardia: apagar el terminal -> 0)", ok and d.get("ok") is True, d)

# ── 8. LO NUEVO: el color constante sobrevive la cadena; el mapeo queda REFUTADO ──
time.sleep(1.5)
s = snapshot(("term",), "color constante")
c = s.get("term") or {}

def rango(ch):
    e = c.get(ch) or {}
    return (e.get("mx", 0) - e.get("mn", 0))

constantes = (abs((c.get("Color_0") or {}).get("mn", -1) - 0.2) < 0.02
              and abs((c.get("Color_1") or {}).get("mn", -1) - 1.0) < 0.02
              and abs((c.get("Color_2") or {}).get("mn", -1) - 0.4) < 0.02)
chek("el Color constante llega INTACTO al terminal (0.2/1.0/0.4)",
     bool(c) and rango("Color_0") < 0.02 and rango("Color_1") < 0.02
     and rango("Color_2") < 0.02 and constantes, {"term_Color": [c.get("Color_0"), c.get("Color_1"), c.get("Color_2")]})

# el defecto, ASSERTADO: con dup PartVel→Color activo, Color NO sigue a PartVel_1 (que sí varía)
ok, d = g.exec_code(CHAIN + """
import json
tint = op('%s/tint')
tint.par.dup0name = 'PartVel'
settle(5)
chk = op('%s/check')
chk.par.pop = '%s/geo/null_render'
chk.cook(force=True)
m = dict()
for c in chk.chans():
    if c.name in ('PartVel_1', 'Color_1'):
        vals = c.vals
        m[c.name] = dict(mn=round(min(vals), 3), mx=round(max(vals), 3),
                         uniq=len(set(round(v, 2) for v in vals)))
chk.par.pop = '%s/geo/null_render'
print('<<JSON>>' + json.dumps(m))
""" % (GEO, ROOT, ROOT, ROOT))
m = d if ok else {}
pv = (m.get("PartVel_1") or {})
cl = (m.get("Color_1") or {})
report["mapeo_refutado"] = m
chek("DEFECTO documentado: dup/ren NO mapean por punto (Color constante pese a PartVel variable)",
     bool(pv) and pv.get("uniq", 0) > 5 and cl.get("uniq", 1) <= 2,
     {"PartVel_1": pv, "Color_1": cl})

# dejar tint en el estado que SÍ funciona (attr constante)
ok, d = g.exec_code("""
import json
tint, gv, tr = op('%s/tint'), op('%s/grav'), op('%s/tr')
tint.par.dup0name = ''
tint.par.ren0from = ''
gv.par.globforcey = -2
tr.par.reset.pulse()
print('<<JSON>>' + json.dumps(dict(fy=gv.par.globforcey.eval())))
""" % (GEO, GEO, GEO))
chek("estado canónico restaurado (attr constante, g=-2)", ok and d.get("fy") == -2, d)

# ── 9. errores + evidencia visual ──
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_color_trails_attr.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

# ── 10. cierre ──
report["final_px"] = d
report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-color-trails-attr-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_color_trails_attr ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| fallos:", g.failures)
print("mecanismo de color:", report.get("mecanismo_color"))
print("color:", json.dumps(report.get("color_evidencia", {}), ensure_ascii=False)[:700])
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

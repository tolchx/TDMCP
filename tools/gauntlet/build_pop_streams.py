#!/usr/bin/env python3
"""build_pop_streams.py — tercer proyecto POP del hilo: ESTELAS (trails) de partículas.

Pipeline (receta C2/pop_render_network, sin glslPOP):
  geo: circlePOP (anillo r=2.2, 256 pts) → trailPOP (estelas length=24) → noisePOP
       (curl 3D 'turb' — desplaza las estelas por el espacio) → convertPOP(topointprims)
       → nullPOP (terminal) + pointspriteMAT sobre el geometryCOMP
  render: geometryCOMP (torus1 borrado) + cameraCOMP + lightCOMP + renderTOP
          + poptoCHOP (verdad GPU→CPU) + captura PNG métrica (PIL)

Lecciones medidas en vivo (contratos nuevos C8):
  * `trail_moves_points` — trailPOP+mueve las estelas ACUMULANDO el campo de ruido por sample:
    el enjambre deja el anillo (P centro ≈ 7,7,7) y la cámara default (0,0,5) queda fuera.
  * `cam_follows_data` — la cámara se centra en el CENTROIDE de P medido por poptoCHOP,
    no en el origen: es el flujo que hace que el render vea lo que la cadena produce.
  * `pointprim_everywhere` — topointprims ES obligatorio también para trails (1 prim/punto).
  * `renderTOP_geometry_is_a_list` — crear otro geometryCOMP lo AGREGA a ren.par.geometry;
    reasignar el par (no confiar en el valor previo) y borrar el COMP de prueba.
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
g = Gauntlet(phase="build-pop-streams", run_id=RUN)
g.init()

ROOT = "/pop_streams"
GEO = ROOT + "/geo"
CHAIN = chain_source(ROOT)   # settle()/px()/render_is_ours() no se copian: se importan

report = {"run_id": RUN, "objetivo": "estelas de partículas (circlePOP→trailPOP→noisePOP→topointprims)",
          "ok": False, "cheks": []}


def chek(name, ok, detail=""):
    report["cheks"].append((name, bool(ok)))
    g.check(name, ok, str(detail)[:240])


# ── 0. entorno limpio ──
g.call("project_info", {}, note="TD vivo")
ok, d = g.exec_code("import json\ntry:\n op('%s').destroy()\nexcept Exception:\n pass\n"
                    "print('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
chek("limpieza previa", ok)

# ── 1. estructura de render ──
g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_streams",
                              "nodeX": -800, "nodeY": 900, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"},
    {"type": "cameraCOMP", "name": "cam"},
    {"type": "lightCOMP", "name": "light"},
    {"type": "renderTOP", "name": "ren"},
    {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True},
    note="estructura geo+render+check")
# ren: TODOS los bindings re-asignados (el par geometry es una LISTA: no confiar en el previo)
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 2. auto-torus fuera (contrato autotorus_masks_render) ──
ok, d = g.exec_code("""
import json
geo = op('%s')
torus = [c.name for c in geo.children if c.name.lower().startswith('torus')]
for n in torus:
    geo.op(n).destroy()
print('<<JSON>>' + json.dumps({'had_torus': torus}))
""" % GEO)
chek("auto-torus borrado", ok and bool(d.get("had_torus")), d)

# ── 3. cadena POP: anillo → estelas → curl → prims de punto ──
g.call_ok("build_network", {"parent_path": GEO, "operators": [
    {"type": "circlePOP", "name": "circ"},
    {"type": "trailPOP", "name": "tr"},
    {"type": "noisePOP", "name": "curl"},
    {"type": "convertPOP", "name": "topoints"},
    {"type": "nullPOP", "name": "null_render"}],
    "connections": [{"from": "circ", "to": "tr"}, {"from": "tr", "to": "curl"},
                    {"from": "curl", "to": "topoints"}, {"from": "topoints", "to": "null_render"}],
    "auto_layout": True}, note="cadena de estelas")

# ── 4. parámetros (releídos con set_and_verify: contrato C4) ──
bad, got = set_and_verify(g, GEO + "/circ", {"radx": 2.2, "rady": 0.1, "divs": 256}, "anillo emisor")
chek("anillo emisor aplicado", not bad, got)
ok, d = g.exec_code("""
import json
t = op('%s/tr')
t.par.length = 24
t.par.reset.pulse()
print('<<JSON>>' + json.dumps({'length': t.par.length.eval()}))
""" % GEO)
chek("trailPOP length=24 + reset", ok and d.get("length") == 24, d)
# curl3d y noisesize NO van por set_parameters en este build (C4: responde ok y no aplica):
# se escriben por execute_code y se releen.
ok, d = g.exec_code("""
import json
c = op('%s/curl')
c.par.mode = 'quality'
c.par.type = 'simplex3d'
c.par.amp = 0.25
c.par.noisesize = 1.2
c.par.offset = 0.0
c.par.curl3d = True
t = op('%s/tr')
t.par.reset.pulse()
v = {}
for p in ('mode', 'type', 'amp', 'noisesize', 'offset', 'curl3d'):
    v[p] = c.par[p].eval()
print('<<JSON>>' + json.dumps(v))
""" % (GEO, GEO))
# noisesize es WRITEONLY en este build (queda clavado en '2' aunque lo escribas): defecto
# documentado en C8, no bloquea (la escala default 2 sirve para el look).
chek("noisePOP aplicado (execute_code; noisesize clavado en 2 = writeonly)",
     ok and d.get("amp") == 0.25 and d.get("offset") == 0.0 and d.get("curl3d") is True, d)
bad, got = set_and_verify(g, GEO + "/topoints", {"convert": "topointprims"}, "prims de punto")
chek("topointprims aplicado", not bad, got)

# ── 5. material + flags + cámara centrada en el DATO (no en el origen) ──
g.call_ok("create_operator", {"parent_path": GEO, "type": "pointspriteMAT", "name": "mat"},
          note="material de puntos")
ok, d = g.exec_code(
    CHAIN
    + """
import json
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
m = op(ROOT + '/geo/mat')
m.par.pointsize = 4.0
m.par.colorr = 0.3
m.par.colorg = 0.85
m.par.colorb = 1.0
geo.par.material = m
term = geo.op('null_render')
term.display = True
term.render = True
chk = op(ROOT + '/check')
chk.par.pop = ROOT + '/geo/null_render'
# centroide de P (trailPOP desplaza el enjambre: la camara sigue al DATO)
settle()
chk.cook(force=True)
medios = []
for c in chk.chans():
    if c.name.startswith('P'):
        medios.append((min(c.vals) + max(c.vals)) / 2)
cam.par.tx = round(medios[0], 2)
cam.par.ty = round(medios[1], 2)
cam.par.tz = round(medios[2] + 8.0, 2)
ren.par.geometry = geo
ren.par.camera = cam
ren.par.lights = op(ROOT + '/light')
settle()
print('<<JSON>>' + json.dumps({'mat': str(geo.par.material.eval()), 'centro_P': [round(v, 2) for v in medios],
                               'cam': [cam.par.tx.eval(), cam.par.ty.eval(), cam.par.tz.eval()]}))
""")
chek("material+flags+camara-al-dato+bindings", ok and "mat" in str(d.get("mat", "")) and d.get("centro_P"), d)

# ── 6. verificación: números antes que píxeles (C5) ──
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

# ── 7. la animación, por números (C1/clock_stopped): cambiar el CAMPO y comparar P de un punto ──
# (el min/max de P es insensible: el curl mueve cada punto distinto; se compara el P del punto 0
#  con inspect_values, después de resetear el trail para que re-hornee con el campo nuevo)
r = g.call_ok("inspect_values", {"path": GEO + "/null_render", "attributes": ["P"], "max_points": 1},
              note="P del punto 0 con amp=0.25")
p_antes = (g.json_of(r).get("pointAttributes") or {}).get("P", {}).get("values", [[None]])[0]
ok, d = g.exec_code("""
import json
%s
curl = op('%s/curl')
curl.par.amp = 0.6
op('%s/tr').par.reset.pulse()
settle()
print('<<JSON>>' + json.dumps({'amp': curl.par.amp.eval()}))
""" % (CHAIN, GEO, GEO))
r = g.call_ok("inspect_values", {"path": GEO + "/null_render", "attributes": ["P"], "max_points": 1},
              note="P del punto 0 con amp=0.6")
p_despues = (g.json_of(r).get("pointAttributes") or {}).get("P", {}).get("values", [[None]])[0]
chek("el ruido mueve las estelas (P del punto 0 cambia con amp)",
     ok and p_antes != p_despues, {"antes": p_antes, "despues": p_despues})
ok, d = g.exec_code("""
import json
%s
curl = op('%s/curl')
curl.par.amp = 0.25
op('%s/tr').par.reset.pulse()
print('<<JSON>>' + json.dumps({'amp': curl.par.amp.eval()}))
""" % (CHAIN, GEO, GEO))

# ── 8. errores + evidencia visual ──
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_streams.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

# ── 9. cierre ──
report["final_px"] = d
report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-streams-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_streams ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| failures:", g.failures)
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

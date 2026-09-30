#!/usr/bin/env python3
"""build_pop_field.py — cuarto proyecto POP del hilo: CAMPO DE RUIDO animado por t4d.

A diferencia de `/curl_field` (campo estático sobre grilla 3D) y `/pop_streams` (estelas),
acá el atractor del campo es el TIEMPO: noisePOP con `t4d` (time 4D) congelado/escalonado
(medido: el reloj no corre en execute_code, C1/clock_stopped) sobre sprinklePOP sobre
superficie de toro — puntos que RESPONDEN al campo sin simulación de partículas.

Pipeline:
  geo: torusPOP (superficie) → sprinklePOP (muestrea la superficie) → noisePOP (turb, curl3d,
       t4d escalonado) → convertPOP(topointprims) → nullPOP (terminal) + pointspriteMAT
  render: geometryCOMP (torus1 borrado) + cameraCOMP + lightCOMP + renderTOP
          + poptoCHOP + captura PNG métrica (PIL)
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
g = Gauntlet(phase="build-pop-field", run_id=RUN)
g.init()

ROOT = "/pop_field"
GEO = ROOT + "/geo"
CHAIN = chain_source(ROOT)   # settle()/px()/render_is_ours() no se copian: se importan

report = {"run_id": RUN, "objetivo": "campo de ruido 4D sobre muestreo de toro (sprinkle+noise)",
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
g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_field",
                              "nodeX": -400, "nodeY": 900, "display": True}, note="contenedor")
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

# ── 3. cadena POP: superficie de toro → muestreo → ruido → prims de punto ──
g.call_ok("build_network", {"parent_path": GEO, "operators": [
    {"type": "torusPOP", "name": "toro"},
    {"type": "sprinklePOP", "name": "spr"},
    {"type": "noisePOP", "name": "warp"},
    {"type": "convertPOP", "name": "topoints"},
    {"type": "nullPOP", "name": "null_render"}],
    "connections": [{"from": "toro", "to": "spr"}, {"from": "spr", "to": "warp"},
                    {"from": "warp", "to": "topoints"}, {"from": "topoints", "to": "null_render"}],
    "auto_layout": True}, note="cadena de campo")

# ── 4. parámetros (los que set_parameters ignora van por execute_code: C4) ──
ok, d = g.exec_code("""
import json
toro = op('%s/toro')
toro.par.radx = 2.2
toro.par.rady = 2.2
toro.par.scale = 0.55
spr = op('%s/spr')
spr.par.numpoints = 3000
spr.par.seed = 11.0
warp = op('%s/warp')
warp.par.mode = 'quality'
warp.par.type = 'simplex4d'
warp.par.amp = 0.4
warp.par.offset = 0.0
warp.par.curl3d = True
v = {'toro_radx': toro.par.radx.eval(), 'spr_numpoints': spr.par.numpoints.eval(),
     'amp': warp.par.amp.eval(), 'curl3d': bool(warp.par.curl3d.eval())}
print('<<JSON>>' + json.dumps(v))
""" % (GEO, GEO, GEO))
chek("toro r=2.2 + sprinkle 3000 + ruido amp=0.4", ok and d.get("spr_numpoints") == 3000
     and d.get("amp") == 0.4 and d.get("curl3d") is True, d)

bad, got = set_and_verify(g, GEO + "/topoints", {"convert": "topointprims"}, "prims de punto")
chek("topointprims aplicado", not bad, got)

# ── 5. material + flags + cámara centrada en el DATO ──
g.call_ok("create_operator", {"parent_path": GEO, "type": "pointspriteMAT", "name": "mat"},
          note="material de puntos")
ok, d = g.exec_code(
    CHAIN
    + """
import json
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
m = op(ROOT + '/geo/mat')
m.par.pointsize = 3.0
m.par.colorr = 1.0
m.par.colorg = 0.6
m.par.colorb = 0.2
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
    if c.name.startswith('P'):
        medios.append((min(c.vals) + max(c.vals)) / 2)
cam.par.tx = round(medios[0], 2)
cam.par.ty = round(medios[1], 2)
cam.par.tz = round(medios[2] + 9.0, 2)
ren.par.geometry = geo
ren.par.camera = cam
ren.par.lights = op(ROOT + '/light')
settle()
print('<<JSON>>' + json.dumps({'mat': str(geo.par.material.eval()),
                               'centro_P': [round(v, 2) for v in medios]}))
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

# ── 7. el campo ES temporal: t4d escalonado debe mover los puntos (medido por punto, no min/max) ──
r = g.call_ok("inspect_values", {"path": GEO + "/null_render", "attributes": ["P"], "max_points": 1},
              note="P del punto 0 con t4d=0")
p_antes = (g.json_of(r).get("pointAttributes") or {}).get("P", {}).get("values", [[None]])[0]
ok, d = g.exec_code("""
import json
%s
warp = op('%s/warp')
warp.par.t4d = 3.5
print('<<JSON>>' + json.dumps({'t4d': warp.par.t4d.eval()}))
""" % (CHAIN, GEO))
r = g.call_ok("inspect_values", {"path": GEO + "/null_render", "attributes": ["P"], "max_points": 1},
              note="P del punto 0 con t4d=3.5")
p_despues = (g.json_of(r).get("pointAttributes") or {}).get("P", {}).get("values", [[None]])[0]
chek("el campo 4D mueve los puntos (P cambia con t4d)", ok and p_antes != p_despues,
     {"antes": p_antes, "despues": p_despues})
ok, d = g.exec_code("""
import json
op('%s/warp').par.t4d = 0.0
print('<<JSON>>' + json.dumps({'t4d': op('%s/warp').par.t4d.eval()}))
""" % (GEO, GEO))

# ── 8. errores + evidencia visual ──
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_field.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

# ── 9. cierre ──
report["final_px"] = d
report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-field-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_field ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| failures:", g.failures)
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

"""Fase 3 — Nivel 5: mini-render 3D dentro de un baseCOMP.

renderTOP + cameraCOMP/lightCOMP/geometryCOMP (hermanos) + pbrMAT con
environmentlightCOMP + constantTOP como env map + graders (bindings, errores,
contenido del geo) + PNG y grid temporal de evidencia.
Contratos sondeados: renderTOP no auto-crea hijos; pars camera/light/geometry
son OP; envlightmap es TOP (se cablea, no se bindea).
"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gauntlet_client import Gauntlet

g = Gauntlet("f3-n5-render")
SB = "/gauntlet_n5"
g.call("delete_operator", {"path": SB}, note="limpieza (tolerada)")

# 1) contenedor + ops 3D (hermanos dentro del COMP)
g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "gauntlet_n5",
                              "nodeX": -1300, "nodeY": 700}, note="COMP del render")
g.call_ok("build_network", {"parent_path": SB, "operators": [
    {"type": "renderTOP", "name": "ren"},
    {"type": "cameraCOMP", "name": "cam"},
    {"type": "lightCOMP", "name": "light"},
    {"type": "geometryCOMP", "name": "geo"},
    {"type": "geometryCOMP", "name": "envgeo"},
    {"type": "environmentlightCOMP", "name": "envlight"},
    {"type": "constantTOP", "name": "envmap"},
    {"type": "nullTOP", "name": "out1"}],
    "connections": [{"from": "ren", "to": "out1"}],
    "auto_layout": True}, note="8 ops del render")

# 2) MAT + material del geo + asegurar contenido del geo (torus -> null1)
g.call_ok("create_operator", {"parent_path": SB + "/geo", "type": "pbrMAT", "name": "materialMAT"})
ok, d = g.exec_code(f"""
import json
g = op('{SB}/geo')
g.par.material = op('{SB}/geo/materialMAT')  # path completo: ./ en exec_code resuelve contra me, no contra geo
names = [x.name for x in g.children if x.valid]
created = []
if 'torus1' not in names:
    g.create('torus', 'torus1'); created.append('torus1')
if 'null1' not in names:
    g.create('nullTOP', 'null1'); created.append('null1')
try:
    op('{SB}/geo/torus1').outputConnectors[0].connect(op('{SB}/geo/null1'))
except Exception:
    pass
op('{SB}/geo').par.rx.expr = 'absTime.seconds * 40'
print('<<JSON>>' + json.dumps({{'material': str(g.par.material.eval()),
      'kids': sorted(x.name + ':' + x.type for x in g.children if x.valid),
      'created': created}}))""")
g.check("material asignado al geo", ok and "materialMAT" in str(d.get("material")), str(d)[:250])
g.check("geo con contenido (torus->null1)", ok and "torus1" in str(d.get("kids")) and "null1" in str(d.get("kids")), str(d)[:250])
print("  (info) geo:", json.dumps(d, ensure_ascii=False)[:300])

# 3) env light: el env map es el PAR envlightmap (OP), el COMP no tiene inputs.
# Hallazgo: environmentlightCOMP no acepta wiring; binding por ejecutar codigo.
ok, d = g.exec_code(f"""
import json
op('{SB}/envlight').par.envlightmap = op('{SB}/envmap')
print('<<JSON>>' + json.dumps({{'envmap_par': str(op('{SB}/envlight').par.envlightmap.eval())}}))""")
g.check("envmap asignado al par envlightmap", ok and "envmap" in str(d.get("envmap_par", "")), str(d)[:200])
g.call_ok("set_parameters", {"path": SB + "/envlight", "values": {"dimmer": 1.0}})
g.call_ok("set_parameters", {"path": SB + "/geo/materialMAT", "values": {
    "constantr": 0.9, "constantg": 0.9, "constantb": 0.9, "roughness": 0.25}},
    note="pbr constant (components constantr/g/b)")
# bindings OP del renderTOP: por exec_code (set_parameters solo acepta constantes)
ok, d = g.exec_code(f"""
import json
ren = op('{SB}/ren')
ren.par.camera = op('{SB}/cam')
ren.par.geometry = op('{SB}/geo')
light_par = None
for p in ren.pars():
    if p.name == 'light':
        light_par = 'light'; break
    if p.name.lower().startswith('light') and p.isDefault is False:
        light_par = light_par or p.name
if light_par:
    setattr(ren.par, light_par, op('{SB}/light'))
print('<<JSON>>' + json.dumps({{'cam': str(ren.par.camera.eval()),
      'geo': str(ren.par.geometry.eval()), 'light_par': light_par}}))""")
g.check("bindings OP del renderTOP", ok, str(d)[:200])
g.call_ok("set_parameters", {"path": SB + "/ren", "values": {"resolutionw": 480, "resolutionh": 360}})

# ── graders estaticos ─────────────────────────────────────────────────────
ok, d = g.exec_code(f"""
import json
r = {{'cam_bound': str(op('{SB}/ren').par.camera.eval() or ''),
      'geo_bound': str(op('{SB}/ren').par.geometry.eval() or ''),
      'envmap_par': str(op('{SB}/envlight').par.envlightmap.eval() or '')}}
print('<<JSON>>' + json.dumps(r))""")
g.check("camera bound en renderTOP", "cam" in str(d.get("cam_bound")), str(d)[:250])
g.check("geo bound en renderTOP", "geo" in str(d.get("geo_bound")), str(d)[:200])
g.check("envmap en envlightmap", "envmap" in str(d.get("envmap_par")), str(d)[:200])

errs = g.call_ok("get_errors", {"path": SB})
et = g.text_of(errs)
g.check("get_errors sin errores", '"count": 0' in et or '"items": []' in et, et[:250])

# ── PNG del render (inline) ──────────────────────────────────────────────
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}})
r = g.call_ok("view_operator", {"path": SB + "/out1", "resolution": "small"}, note="png del render")
png = g.save_image(r, os.path.join(HERE, "results", g.run_id, "n5_render.png"))
g.check("PNG del render capturado", bool(png))

# ── grid temporal (el torus rota via rx expr -> 3 frames distintos) ─────
r = g.call_ok("view_operator", {"path": SB + "/out1", "frames": 3, "step": 8, "resolution": "small"},
              note="job grid del render")
job = g.json_of(r).get("job_id", "")
time.sleep(4.0)
r = g.call("view_operator", {"path": SB + "/out1", "job_id": job}, note=f"retrieve grid {job}")
png2 = g.save_image(r, os.path.join(HERE, "results", g.run_id, "n5_render_grid.png"))
g.check("grid temporal del render capturado", bool(png2))
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}})

g.call_ok("delete_operator", {"path": SB}, note="cleanup N5")
s = g.summary()
print("\nN5:", json.dumps(s, ensure_ascii=False))
sys.exit(0 if s["ok"] else 1)

#!/usr/bin/env python3
"""build_pop_fountain.py — test de las tools del MCP oficial construyendo una
fuente de partículas POP (sphere→particle→force→topointprims) y dejando evidencia
para que el juez externo (Jev) revise su UTILIDAD.

Corre la cadena completa: project_info → get_help → create_operator → build_network
→ set_parameters → wiring → execute_code → get_errors → inspect_values → view_operator.
"""
from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gauntlet_client import Gauntlet  # noqa: E402

RUN = os.environ.get("GAUNTLET_RUN_ID") or time.strftime("%Y%m%d-%H%M%S")
g = Gauntlet(phase="build-fountain", run_id=RUN)
g.init()

ROOT = "/fountain_demo"
GEO = ROOT + "/geo"
report = {"run_id": RUN, "objetivo": "fuente de partículas POP (sphere→particle→gravedad→topointprims)",
          "ok": False, "cheks": []}


# ── 0. scout ──
g.call("project_info", {}, note="TD vivo + root")
g.call("list_operators", {"path": "/"}, note="estado previo en /")


# ── 1. get_help: nombres de par REALES antes de tocar nada ──
g.call("get_help", {"types": ["particlePOP", "forceradialPOP"], "verbose": True},
       note="pars reales de particlePOP + forceradialPOP")


# ── 2. limpiar si existía ──
ok, d = g.exec_code(f"import json\ntry:\n op('{ROOT}').destroy()\n print('<<JSON>>' + json.dumps({{'clean':'ok'}}))\nexcept Exception as e:\n print('<<JSON>>' + json.dumps({{'clean':str(e)}}))")
report["cheks"].append(("limpio previo", ok))


# ── 3. baseCOMP principal ──
g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "fountain_demo",
                              "nodeX": -400, "nodeY": 900, "display": True}, note="baseCOMP principal")
report["cheks"].append(("baseCOMP creado", True))

# ── 4. estructura (geometryCOMP + render) ──
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"},
    {"type": "cameraCOMP", "name": "cam"},
    {"type": "lightCOMP", "name": "light"},
    {"type": "renderTOP", "name": "ren"},
    {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True},
    note="estructura geo+render+check")
report["cheks"].append(("estructura construida", True))

# ── 5. borrar auto-torus del geometryCOMP ──
ok, d = g.exec_code(f"""
import json
geo = op('{GEO}')
torus = [c.name for c in geo.children if c.name.lower().startswith('torus')]
for n in torus:
    geo.op(n).destroy()
print('<<JSON>>' + json.dumps({{'had_torus': bool(torus), 'kids': [c.name for c in geo.children]}}))""")
report["cheks"].append(("auto-torus borrado", ok and d.get("had_torus") is True))

# ── 6. cadena POP dentro del geo ──
g.call_ok("build_network", {"parent_path": GEO, "operators": [
    {"type": "spherePOP", "name": "emit"},
    {"type": "particlePOP", "name": "particles"},
    {"type": "forceradialPOP", "name": "gravity"},
    {"type": "convertPOP", "name": "topoints"},
    {"type": "nullPOP", "name": "null_render"}],
    "connections": [], "auto_layout": True}, note="cadena POP dentro de geo")

# ── 7. wire de la cadena ──
for a, b in [("emit", "particles"), ("particles", "gravity"), ("gravity", "topoints"), ("topoints", "null_render")]:
    g.call_ok("wiring", {"from_path": GEO + "/" + a, "to_path": GEO + "/" + b, "to_index": 0},
              note=f"{a}->{b}")

# ── 8. parámetros (values, no params) ──
g.call_ok("set_parameters", {"path": GEO + "/emit",
                             "values": {"radx": 0.3, "rady": 0.3, "radz": 0.3, "cols": 8, "rows": 8}},
          note="esfera emisora chica (rad=XYZW, cols/rows NO columns)")
g.call_ok("set_parameters", {"path": GEO + "/particles",
                             "values": {"birthrate": 80, "life": 2.5, "initvelocityy": 3, "initvelocityz": 0.5, "maxparticles": 800, "timeintegration": True}},
          note="partículas: nacen y suben (timeintegration ON para que se muevan)")
g.call_ok("set_parameters", {"path": GEO + "/topoints", "values": {"convert": "topointprims"}},
          note="topointprims -> nube de puntos")

# forceradialPOP: sin globforcemult la gravedad NO hace nada; la fuerza es globforce (XYZW)
ok, d = g.exec_code(f"""
import json
gv = op('{GEO}/gravity')
gv.par.globforcemult = 1
gv.par.globforcey = -6
gv.par.radial = 0
gv.par.axial = 0
gv.par.planar = 0
out = op('{GEO}/null_render')
out.display = True
out.render = True
ren = op('{ROOT}/ren')
ren.par.camera = './cam'
print('<<JSON>>' + json.dumps({{'globforcemult': gv.par.globforcemult.eval(), 'globforcey': gv.par.globforcey.eval()}}))""")
report["cheks"].append(("gravedad globforcemult aplicada", ok and d.get("globforcemult") == 1))

# ── 9. material pointsprite ──
g.call_ok("create_operator", {"parent_path": GEO, "type": "pointspriteMAT", "name": "sprite_mat"},
          note="material pointsprite")
ok, d = g.exec_code(f"""
import json
geo = op('{GEO}')
geo.par.material = './sprite_mat'
m = op('{GEO}/sprite_mat')
m.par.pointsize = 4
print('<<JSON>>' + json.dumps({{'mat': str(geo.par.material.eval())}}))""")
report["cheks"].append(("material asignado", ok and "sprite_mat" in d.get("mat", "")))

# ── 10. settle + verificación GPU->CPU ──
ok, d = g.exec_code(f"""
import json, time
def settle(n=8):
    for _ in range(n):
        for p in ['{GEO}/emit','{GEO}/particles','{GEO}/gravity','{GEO}/topoints','{GEO}/null_render']:
            try: op(p).cook(force=True)
            except: pass
        time.sleep(0.05)
settle()
pc = op('{ROOT}/check')
pc.par.pop = '{GEO}/null_render'
pc.cook(force=True)
chans = [c.name for c in pc.chans()]
n = pc.numSamples
print('<<JSON>>' + json.dumps({{'channels': chans[:6], 'samples': n, 'npoints': n}}))""")
report["cheks"].append(("poptoCHOP cuenta puntos", ok and d.get("npoints", 0) > 0))

# ── 11. errores ──
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call("inspect_values", {"path": GEO + "/null_render", "attributes": ["P", "Cd"], "max_points": 8},
       note="atributos del POP")

# ── 12. evidencia visual (Inline Images ON + job async) ──
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call("view_operator", {"path": GEO, "resolution": "small"}, note="captura (async)")
job = g.json_of(r).get("job_id", "")
time.sleep(0.4)
r2 = g.call("view_operator", {"path": GEO, "job_id": job}, note=f"retrieve {job}") if job else r
img = g.save_image(r2, os.path.join(g.out_dir, "fountain.png"))
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")
report["cheks"].append(("captura PNG", bool(img)))

# ── 13. cierre ──
final = g.call("list_operators", {"path": ROOT}, note="estado final")
errs = g.call("get_errors", {"path": ROOT}, note="errores finales")
report["final_ops"] = g.text_of(final)[:900]
report["errors_text"] = g.text_of(errs)[:700]
report["tools_called"] = [l["tool"] for l in g.log]
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures

out_path = os.path.join(g.out_dir, "build-fountain-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN ===")
print(json.dumps(report, ensure_ascii=False, indent=2)[:3000])
print(f"\nReporte: {out_path}")

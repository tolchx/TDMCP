#!/usr/bin/env python3
"""build_pop_fountain.py — test de las tools del MCP oficial construyendo un
sistema de partículas POP (feedback + fuerzas) y dejando evidencia para el juez.

Objetivo: ejercitar las tools del oficial (build_network, get_help, set_parameters,
execute_code, get_errors, inspect_values, view_operator) sobre operadores POP y
producir un resumen JSON que Jev pueda revisar por UTILIDAD.

Efecto: fuente de partículas que suben, caen por gravedad (forceradialPOP) y
rebotan en un piso, renderizadas como point sprites (pointspriteMAT).
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

ROOT = "/project1/fountain_demo"

report = {"run_id": RUN, "objetivo": "fuente de partículas POP (feedback + fuerzas)",
          "tools": [], "build": [], "verificacion": [], "errores": []}


def used(tool, note):
    report["tools"].append(f"{tool}: {note}")


# ── 0. scout ──
used("project_info", "verificar TD vivo")
g.call("project_info", {})
used("list_operators", "estado previo en /project1")
g.call("list_operators", {"path": "/project1"})


# ── 1. limpiar si existía ──
g.call("execute_code", {"code": f"import json\nimport td\no = op('{ROOT}')\nprint('existía' if o else 'no existía')"})


# ── 2. get_help sobre los POP que voy a usar (test de get_help) ──
used("get_help", "parámetros de feedbackPOP + forceradialPOP")
g.call("get_help", {"types": ["feedbackPOP", "forceradialPOP", "particlePOP"], "verbose": True})


# ── 3. construir la red con build_network ──
# Cadena: sourcePOP → feedbackPOP → forceradialPOP → nullPOP, dentro de un geometryCOMP
used("build_network", "geometryCOMP + cadena POP (source→feedback→force→null)")
build = {
    "parent_path": "/project1",
    "operators": [
        {"type": "geometryCOMP", "name": "fountain_demo"},
        {"type": "spherePOP", "name": "emit", "parent": f"{ROOT}"},
        {"type": "feedbackPOP", "name": "sim", "parent": f"{ROOT}"},
        {"type": "forceradialPOP", "name": "gravity", "parent": f"{ROOT}"},
        {"type": "nullPOP", "name": "out", "parent": f"{ROOT}"},
    ],
    "connections": [
        {"from": "emit", "to": "sim"},
        {"from": "sim", "to": "gravity"},
        {"from": "gravity", "to": "out"},
    ],
}
r = g.call("build_network", build, note="red de partículas")
report["build"].append("build_network: geometryCOMP + spherePOP→feedbackPOP→forceradialPOP→nullPOP")

# ── 4. configurar parámetros con set_parameters + execute_code ──
# spherePOP: pocos puntos, emisor
used("set_parameters", "spherePOP size + feedbackPOP/force pars")
g.call("set_parameters", {"path": f"{ROOT}/emit", "params": {"radx": 0.3, "rady": 0.3, "radz": 0.3}})

# feedbackPOP: lifecycle + forceradial: gravedad (globforcemult pitfall)
code = f"""
import td
sim = op('{ROOT}/sim')
gv = op('{ROOT}/gravity')
# forceradialPOP: sin globforcemult la gravedad no hace nada
gv.par.globforcemult = 1
gv.par.globforcey = -6
# flags de render en el terminal
out = op('{ROOT}/out')
out.par.display = True
out.par.render = True
# borrar el auto-torus del geometryCOMP (pitfall clásico)
geo = op('{ROOT}')
for c in list(geo.children):
    if 'torus' in c.name.lower():
        c.destroy()
print('configurado')
"""
used("execute_code", "forceradial globforcemult + flags render + borrar auto-torus")
g.call("execute_code", {"code": code})

# convertPOP topointprims para que dibuje (puntos no renderizan sin primitivas)
used("build_network", "convertPOP topointprims entre gravity y out")
g.call("create_operator", {"parent_path": f"{ROOT}", "type": "convertPOP", "name": "topoints"})
g.call("set_parameters", {"path": f"{ROOT}/topoints", "params": {"convert": "topointprims"}})
# rewire: gravity → topoints → out
g.call("execute_code", {"code": f"""
import td
gv = op('{ROOT}/gravity')
tp = op('{ROOT}/topoints')
out = op('{ROOT}/out')
gv.outputConnectors[0].connect(tp)
tp.outputConnectors[0].connect(out)
print('rewired')
"""})

# ── 5. material pointsprite ──
used("create_operator", "pointspriteMAT aditivo")
g.call("create_operator", {"parent_path": f"{ROOT}", "type": "pointspriteMAT", "name": "sprite_mat"})
g.call("set_parameters", {"path": f"{ROOT}/sprite_mat", "params": {"pointsize": 3}})
g.call("execute_code", {"code": f"""
import td
geo = op('{ROOT}')
geo.par.material = './sprite_mat'
# blending aditivo
m = op('{ROOT}/sprite_mat')
for p in m.pars():
    if p.name in ('srcblend','destblend'):
        pass
print('material asignado')
"""})

# ── 6. settle + verificar ──
used("execute_code", "settle() para asentar el cook lag")
g.call("execute_code", {"code": f"""
import td, time
def settle(n=6):
    for _ in range(n):
        for p in ['{ROOT}/emit','{ROOT}/sim','{ROOT}/topoints','{ROOT}/out']:
            try: op(p).cook(force=True)
            except: pass
        time.sleep(0.05)
settle()
# poptoCHOP ground truth
import json
pc = op('{ROOT}/popto1') if op('{ROOT}/popto1') else op('{ROOT}').create(td.poptoCHOP, 'popto1')
pc.par.pop = './out'
pc.cook(force=True)
chans = [c.name for c in pc.channels]
n = len(pc.channel(chans[0])) if chans else 0
print(json.dumps({{'channels': chans[:6], 'samples': n}}))
"""})

used("get_errors", "verificar que no haya errores")
g.call("get_errors", {"path": f"{ROOT}"})

used("inspect_values", "muestrear atributos del POP")
g.call("inspect_values", {"path": f"{ROOT}/out", "attributes": ["P", "Cd"], "max_points": 10})

# ── 7. evidencia visual ──
used("view_operator", "captura del geometryCOMP")
g.call("view_operator", {"path": f"{ROOT}", "resolution": "small"})

# ── 8. resumen para Jev ──
# estado final
final = g.call("list_operators", {"path": f"{ROOT}"})
report["final_ops"] = g.text_of(final)[:800]
errs = g.call("get_errors", {"path": f"{ROOT}"})
report["errors_text"] = g.text_of(errs)[:800]
report["tools_count"] = len(g.log)
report["tools_called"] = [l["tool"] for l in g.log]

out_path = os.path.join(g.out_dir, "build-fountain-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN PARA JEV ===")
print(json.dumps(report, ensure_ascii=False, indent=2)[:2500])
print(f"\nReporte: {out_path}")
print(f"Log de tools: {g.log_path}")

#!/usr/bin/env python3
"""probe_5d_scout.py — sonda desechable (5d): esquema REAL de los 6 tipos elegidos.

Fase por tipo: crear el op en una red desechable, wiring minimo (input del grid),
cook, numPoints/numPrims, y dump de pars con menus (get_parameters include_menus).
Salida: JSON por fase para disenar los builds.
"""
from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gauntlet_client import Gauntlet  # noqa: E402
from td_probe import chain_source  # noqa: E402

TIPO = sys.argv[1] if len(sys.argv) > 1 else "mergePOP"
RUN = "probe_5d"
g = Gauntlet(phase=f"scout-{TIPO}", run_id=RUN)
g.init()

ROOT = "/pop_5d_scout"
CHAIN = chain_source(ROOT)

ok, _ = g.exec_code("import json\ntry:\n op(%r).destroy()\nexcept Exception:\n pass\n"
                    "print('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
assert ok, "limpieza fallo"
g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_5d_scout",
                              "nodeX": 3600, "nodeY": 2600}, note="contenedor")
g.call_ok("create_operator", {"parent_path": ROOT, "type": "geometryCOMP", "name": "geo"}, note="geo")

setup = {
    "mergePOP": """
gx = geo.create(gridPOP, 'gx')
gx.par.rows = 5
gx.par.cols = 4
pat = geo.create(patternPOP, 'pat')
pat.par.numpoints = 7
t = geo.create(mergePOP, 't')
t.inputConnectors[0].connect(gx.outputConnectors[0])
t.inputConnectors[1].connect(pat.outputConnectors[0])
""",
    "deletePOP": """
gx = geo.create(gridPOP, 'gx')
gx.par.rows = 5
gx.par.cols = 4
t = geo.create(deletePOP, 't')
t.inputConnectors[0].connect(gx.outputConnectors[0])
""",
    "linePOP": """
t = geo.create(linePOP, 't')
""",
    "blendPOP": """
gx = geo.create(gridPOP, 'gxa')
gx.par.rows = 5
gx.par.cols = 4
gx2 = geo.create(gridPOP, 'gxb')
gx2.par.rows = 5
gx2.par.cols = 4
gx2.par.tx = 3.0
t = geo.create(blendPOP, 't')
t.inputConnectors[0].connect(gx.outputConnectors[0])
t.inputConnectors[1].connect(gx2.outputConnectors[0])
""",
    "cachePOP": """
gx = geo.create(gridPOP, 'gx')
gx.par.rows = 5
gx.par.cols = 4
t = geo.create(cachePOP, 't')
t.inputConnectors[0].connect(gx.outputConnectors[0])
""",
    "feedbackPOP": """
gx = geo.create(gridPOP, 'gx')
gx.par.rows = 5
gx.par.cols = 4
tr = geo.create(transformPOP, 'tr')
t = geo.create(feedbackPOP, 't')
t.inputConnectors[0].connect(gx.outputConnectors[0])
""",
}
NET = setup.get(TIPO, "")
ok, d = g.exec_code(CHAIN + f"""
import json
import time
geo = op(ROOT + '/geo')
{NET}
t = op(ROOT + '/geo/t')
settle(2)
t.cook(force=True)
time.sleep(0.1)
t.cook(force=True)
sal = dict(pts=t.numPoints(), prims=t.numPrims(), inputs=len(t.inputs),
           err=t.errors()[:80])
print('<<JSON>>' + json.dumps(sal))
""")
print("== wiring minimo:", json.dumps(d, ensure_ascii=False))

resp = g.call("get_parameters", {"path": ROOT + "/geo/t", "include_defaults": True,
                                 "include_menus": True}, note=f"esquema {TIPO}")
txt = g.text_of(resp).replace("*** isError=true ***", "").strip()
try:
    j = json.loads(txt)
except Exception:
    j = {}
pars = j.get("parameters") or j.get("params") or j
if isinstance(pars, dict):
    sel = {k: v for k, v in pars.items() if isinstance(v, dict)}
else:
    sel = {p.get("name"): p for p in (pars or []) if isinstance(p, dict)}
print(f"== {TIPO}: {len(sel)} pars ==")
for name, v in sorted(sel.items()):
    base = {k: v[k] for k in ("value", "default", "page") if k in v}
    if v.get("menuNames"):
        base["menus"] = v["menuNames"][:14]
    if "enable" in v:
        base["ui_enable"] = v["enable"]
    print(f"  {name}: {json.dumps(base, ensure_ascii=False)}")

# limpiar la red scout
g.exec_code("import json\nop(%r).destroy()\nprint('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
sys.exit(0)

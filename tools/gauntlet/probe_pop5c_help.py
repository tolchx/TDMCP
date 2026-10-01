#!/usr/bin/env python3
"""probe_pop5c_help.py — SONDA DESECHABLE (no se commitea).

Baja help (get_help del build vivo) y parámetros vivos (menús/defaults reales)
de los 6 tipos del ítem 5c: groupPOP, proximityPOP, revolvePOP, tubePOP,
topologyPOP, lookupTexturePOP. Salida: results/<run>/help/help-*.txt + live-*.json.
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
g = Gauntlet(phase="probe-pop5c-help", run_id=RUN)
g.init()

TIPOS = ["groupPOP", "proximityPOP", "revolvePOP", "tubePOP", "topologyPOP", "lookuptexturePOP"]
HELP_DIR = os.path.join(g.out_dir, "help")
os.makedirs(HELP_DIR, exist_ok=True)

g.call("project_info", {}, note="TD vivo")

# 1) help del build vivo, uno por tipo
for t in TIPOS:
    r = g.call("get_help", {"types": [t], "verbose": True}, note="help %s" % t)
    txt = g.text_of(r)
    with open(os.path.join(HELP_DIR, "help-%s.txt" % t.lower()), "w", encoding="utf-8") as f:
        f.write(txt)
    print("help %s: %d chars" % (t, len(txt)))

# 2) live-params: crear cada tipo y volcar pars reales (menús/defaults)
g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_probe5c",
                              "nodeX": 6000, "nodeY": 2600}, note="sandbox")
g.call_ok("create_operator", {"parent_path": "/pop_probe5c", "type": "geometryCOMP", "name": "geo"},
          note="geo del sandbox")

ok, d = g.exec_code("""
import json
geo = op('/pop_probe5c/geo')
tipos = ["groupPOP", "proximityPOP", "revolvePOP", "tubePOP", "topologyPOP", "lookuptexturePOP"]
sal = {}
for t in tipos:
    try:
        o = geo.create(t, 'tmp')
    except Exception as e:
        sal[t] = {'ok': False, 'error': str(e)}
        continue
    pars = []
    for p in o.pars():
        rec = {'name': p.name, 'style': p.style}
        try:
            rec['val'] = str(p.eval())[:48]
        except Exception:
            pass
        try:
            mn = p.menuNames
            if mn:
                rec['menu'] = list(mn)
        except Exception:
            pass
        pars.append(rec)
    sal[t] = {'ok': True, 'npars': len(pars), 'pars': pars}
    o.destroy()
print('<<JSON>>' + json.dumps(sal))
""")

sal = d or {}
if not ok or "groupPOP" not in sal:
    print("DIAG exec live-params:", json.dumps(sal, ensure_ascii=False)[:900])
resumen = {}
for t in TIPOS:
    rec = sal.get(t) or {"ok": False, "error": "sin respuesta"}
    with open(os.path.join(HELP_DIR, "live-%s.json" % t.lower()), "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=1)
    resumen[t] = "%s pars" % rec.get("npars") if rec.get("ok") else "ERROR: %s" % rec.get("error")

# 3) candidatos para el 'lookupTexturePOP' que no existe con ese nombre
ok2, d2 = g.exec_code("""
import json
geo = op('/pop_probe5c/geo')
candidatos = ['lookuptexturePOP', 'texturelookupPOP', 'lookupPOP', 'texturePOP',
              'sampletexturePOP', 'pointtexturePOP', 'uvlookupPOP']
sal = {}
for t in candidatos:
    try:
        o = geo.create(t, 'tmpx')
        sal[t] = 'OK %s pars' % len(o.pars())
        o.destroy()
    except Exception as e:
        sal[t] = 'NO: %s' % str(e)[:80]
print('<<JSON>>' + json.dumps(sal))
""")
print("CANDIDATOS lookup:", json.dumps(d2 or {"_diag": (sal if isinstance(sal, str) else d2)}, ensure_ascii=False))

# 4) limpiar el sandbox
g.exec_code("import json\nop('/pop_probe5c').destroy()\nprint('<<JSON>>' + json.dumps({'clean': 1}))")

print("\n=== RESUMEN sonda 5c ===")
for k, v in resumen.items():
    print("  %-18s %s" % (k, v))
print("Help dir:", HELP_DIR)

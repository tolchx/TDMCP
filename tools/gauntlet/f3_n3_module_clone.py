"""Fase 3 — Nivel 3: módulo TOP reutilizable, clon y override (contratos verificados).

Master baseCOMP (inTOP -> blurTOP -> nullTOP) + custom pars (Blur, Amount) +
parentshortcut + referencia interna parent().par.Blur -> blurTOP.par.size.
Clon con edit_operator{copy_to} + par clone + override.
"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gauntlet_client import Gauntlet

g = Gauntlet("f3-n3-module-clone")
for p in ("/gauntlet_n3", "/msmod", "/msmod2", "/feed"):
    g.call("delete_operator", {"path": p}, note=f"limpieza previa {p} (tolerada)")

# 1) master + red interna
g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "gauntlet_n3",
                              "nodeX": -1300, "nodeY": -600}, note="master")
g.call_ok("build_network", {"parent_path": "/gauntlet_n3", "operators": [
    {"type": "inTOP", "name": "in1"},
    {"type": "blurTOP", "name": "blur"},
    {"type": "nullTOP", "name": "out1"}],
    "connections": [{"from": "in1", "to": "blur"}, {"from": "blur", "to": "out1"}],
    "auto_layout": True}, note="interna in1->blur->out1")

# 2) custom pars (schema oficial: page + add[{name,type,default}])
r = g.call_ok("edit_custom_parameters", {"path": "/gauntlet_n3", "page": "Module", "add": [
    {"name": "Blur", "type": "Float", "default": 0.05, "min": 0.0, "max": 1.0},
    {"name": "Amount", "type": "Float", "default": 1.0, "min": 0.0, "max": 1.0}]},
    note="custom pars Module")
d = g.json_of(r)
g.check("custom pars agregados", len(d.get("added", [])) == 2, g.text_of(r)[:250])

# 3) parentshortcut + referencia interna (blurTOP usa par 'size' segun get_help)
g.call_ok("set_parameters", {"path": "/gauntlet_n3", "values": {"parentshortcut": "MsMod"}})
ok, d = g.exec_code("""
import json
op('/gauntlet_n3/blur').par.size.expr = "parent().par.Blur"
print('<<JSON>>' + json.dumps({'ok': True}))""")
g.check("blur.par.size -> parent().par.Blur", ok, str(d)[:250])

# 4) rename (arg correcto: 'name') y clon (copy_to)
g.call_ok("edit_operator", {"path": "/gauntlet_n3", "name": "msmod"}, note="rename a msmod")
ok, d = g.exec_code("""
import json
print('<<JSON>>' + json.dumps({'renamed': bool(op('/msmod')) and not op('/gauntlet_n3')}))""")
g.check("rename efectivo", d.get("renamed") is True, str(d)[:200])
g.call_ok("edit_operator", {"path": "/msmod", "copy_to": "/", "name": "msmod2",
                            "nodeX": -1100, "nodeY": -600}, note="clonar via copy_to")
ok, d = g.exec_code("""
import json
c = op('/msmod2')
print('<<JSON>>' + json.dumps({'exists': bool(c),
      'children': sorted(x.name for x in c.children if c.valid and x.valid)}))""")
g.check("clon existe con red heredada", d.get("exists") and d.get("children") == ["blur", "in1", "out1"],
        str(d)[:250])

# 5) clone + override
g.call_ok("set_parameters", {"path": "/msmod2", "values": {"clone": "/msmod"}})
g.call_ok("set_parameters", {"path": "/msmod2", "values": {"Blur": 0.6}}, note="override del clon")
g.call_ok("set_parameters", {"path": "/msmod", "values": {"Amount": 0.3}}, note="el master SI cambia")

# ── graders ──────────────────────────────────────────────────────────────
ok, d = g.exec_code("""
import json
m, c = op('/msmod'), op('/msmod2')
r = {'master_par': m.par.Blur.eval(), 'clon_par': c.par.Blur.eval(),
     'master_amount': m.par.Amount.eval(), 'clon_amount_hereda': c.par.Amount.eval(),
     'clon_network': sorted(x.name for x in c.children if c.valid and x.valid),
     'shortcut': m.par.parentshortcut.eval(),
     'blursize_clon': op('/msmod2/blur').par.size.eval()}
print('<<JSON>>' + json.dumps(r))""")
g.check("override del clon (0.6)", abs((d.get("clon_par") or 0) - 0.6) < 1e-6, str(d)[:300])
g.check("master conserva default (0.05)", abs((d.get("master_par") or 0) - 0.05) < 1e-6, str(d)[:300])
g.check("master Amount cambia (0.3)", abs((d.get("master_amount") or 0) - 0.3) < 1e-6, str(d)[:300])
g.check("clon hereda Amount (1.0)", abs((d.get("clon_amount_hereda") or 0) - 1.0) < 1e-6, str(d)[:300])
g.check("parentshortcut en master", d.get("shortcut") == "MsMod", str(d)[:300])

ok, d = g.exec_code("""
import json
print('<<JSON>>' + json.dumps({'src': [x.owner.name for x in op('/msmod2/blur').inputConnectors[0].connections]}))""")
g.check("interna del clon cableada in1->blur", d.get("src") == ["in1"], str(d)[:200])

# feed + png
g.call_ok("create_operator", {"parent_path": "/", "type": "constantTOP", "name": "feed",
                              "parameters": {"colorr": 0.9, "colorg": 0.2, "colorb": 0.4},
                              "nodeX": -1500, "nodeY": -600}, note="fuente de prueba")
g.call_ok("wiring", {"from_path": "/feed", "to_path": "/msmod", "to_index": 0}, note="feed->master")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}})
r = g.call_ok("view_operator", {"path": "/msmod/out1", "resolution": "small"}, note="png del modulo")
png = g.save_image(r, os.path.join(HERE, "results", g.run_id, "n3_module.png"))
g.check("PNG del modulo alimentado", bool(png))
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}})

for p in ("/msmod", "/msmod2", "/feed"):
    g.call_ok("delete_operator", {"path": p}, note=f"cleanup {p}")
s = g.summary()
print("\nN3:", json.dumps(s, ensure_ascii=False))
sys.exit(0 if s["ok"] else 1)

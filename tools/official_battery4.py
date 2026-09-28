import sys, os, json, base64, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tdmcp_client import init, notify, call, text_of

HERE = os.path.dirname(os.path.abspath(__file__))
init(); notify("notifications/initialized")
SB = "/hermes_hp2"

def show(label, r, maxlen=900):
    print("\n" + "=" * 78); print("###", label); print(text_of(r)[:maxlen])
    return r

show("1. crear sandbox", call("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "hermes_hp2"}))
show("2. build (from/to)", call("build_network", {"parent_path": SB,
    "operators": [{"type": "noiseTOP", "name": "src"}, {"type": "levelTOP", "name": "lvl"}],
    "connections": [{"from": "src", "to": "lvl"}], "auto_layout": True}))

# --- search de parametros: probar variantes ---
print("\n" + "#" * 78)
print("# SEARCH DE PARAMETROS: variantes")
for label, args in [
    ("a) name res*", {"search": {"name": "res*", "depth": 1}}),
    ("b) name *res*", {"search": {"name": "*res*", "depth": 1}}),
    ("c) name brightness*", {"search": {"name": "brightness*"}}),
    ("d) value 512", {"search": {"value": "512", "depth": 1}}),
    ("e) expr absTime", {"search": {"expr": "*absTime*"}}),
    ("f) op_type noiseTOP name *", {"search": {"op_type": "noiseTOP", "name": "*"}}),
]:
    a = dict(args); a["path"] = SB
    show(f"SEARCH {label}", call("get_parameters", a), 500)

# --- undo real ---
print("\n" + "#" * 78)
show("DOCS clase Undo", call("get_docs", {"query": "Undo", "kind": "python"}), 700)
show("UNDO via tool: set brightness1=3.0", call("set_parameters", {"path": SB + "/lvl", "values": {"brightness1": 3.0}}))
show("leer valor", call("execute_code", {"code": "print(op('/hermes_hp2/lvl').par.brightness1.eval())\nresult=op('/hermes_hp2/lvl').par.brightness1.eval()"}))
show("execute_code: ui.undo (member) + redo", call("execute_code", {"code": "print('tipo ui.undo:', type(ui.undo), '| ui.redo:', type(ui.redo))\nimport td\nprint('dir ui.undo:', [m for m in dir(ui.undo) if not m.startswith('_')][:20])\nresult='ok'"}))

# --- Inline images toggle ---
print("\n" + "#" * 78)
show("INLINE ON: setear Inlineimages=true", call("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}))
r = call("view_operator", {"path": SB + "/lvl", "resolution": "tiny"})
t = text_of(r)
imgs = [c for c in r.get("result", {}).get("content", []) if c.get("type") == "image"]
print("\n### VIEW con inline ON -> content types:", [c.get("type") for c in r.get("result", {}).get("content", [])])
print(t[:500])
if imgs:
    p = os.path.join(HERE, "inline_on.png")
    open(p, "wb").write(base64.b64decode(imgs[0]["data"]))
    print("--> PNG inline guardado:", p, os.path.getsize(p), "bytes")
show("INLINE OFF (restaurar)", call("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}))
r2 = call("view_operator", {"path": SB + "/lvl", "resolution": "tiny"})
print("### VIEW con inline OFF -> content types:", [c.get("type") for c in r2.get("result", {}).get("content", [])])
print(text_of(r2)[:300])

show("cleanup", call("delete_operator", {"path": SB}))

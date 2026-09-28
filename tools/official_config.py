import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tdmcp_client import init, notify, call, text_of
init(); notify("notifications/initialized")

print("### Config MCP page del componente oficial (/TDMCP) ###")
for pat in ["*port*", "*address*", "*https*", "*auth*", "*delete*", "*install*", "*name*"]:
    r = call("get_parameters", {"path": "/TDMCP", "pattern": pat, "include_defaults": True})
    print(f"--- {pat}")
    print(text_of(r)[:700])

print("\n### Tune page ###")
for pat in ["*inline*", "*cache*", "*rate*", "*slow*", "*cooldown*", "*request*", "*follow*", "*highlight*"]:
    r = call("get_parameters", {"path": "/TDMCP", "pattern": pat, "include_defaults": True})
    print(f"--- {pat}: {text_of(r)[:400]}")

print("\n### Docs page ###")
r = call("get_parameters", {"path": "/TDMCP", "pattern": "doc*", "include_defaults": True})
print(text_of(r)[:900])

"""Fase 1 — Smoke: handshake, 26 tools, version, latencias, sanity CRUD.

La version del server NO se pinea (el gauntlet es la regresion que corre
antes/después de actualizar el .tox): se registra en meta para el diff.
Se puede pinear con GAUNTLET_PIN_VERSION=1.1.55 si se quiere.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gauntlet_client import Gauntlet, TOOLS_EXPECTED

g = Gauntlet("f1-smoke")
full = g.init()
info = full.get("result", {})
si = info.get("serverInfo", {})
server_version = si.get("version", "?")
g.meta.update({"server_version": server_version, "td_save_build": None})
print("serverInfo:", json.dumps(si))
print("instructions (primeros 200):", (info.get("instructions") or "")[:200])

g.check("server activo", bool(si))
pinned = os.environ.get("GAUNTLET_PIN_VERSION")
g.check("version del server", (server_version == pinned) if pinned else bool(server_version and server_version != "?"),
        f"version={server_version}" + (f" (se esperaba {pinned})" if pinned else ""))

tl = g.call("get_errors", {"path": "/"}, note="probe tools/list via llamada real")
# tools/list propiamente dicha: se registra el catalogo completo en meta
tl_raw = g._post({"jsonrpc": "2.0", "id": 5, "method": "tools/list"})
names = sorted(t["name"] for t in tl_raw.get("result", {}).get("tools", []))
print(f"tools ({len(names)}):", ", ".join(names))
g.meta["tools"] = names
g.check(f"26 tools (hay {len(names)})", len(names) == TOOLS_EXPECTED)

# project_info (registra build de TD y rootPath en meta para el diff del runner)
pi = g.call_ok("project_info", {}, note="identidad del proyecto")
d = g.json_of(pi)
print("project_info:", json.dumps(d, ensure_ascii=False)[:400])
g.check("project_info responde", "name" in d or "project" in d or bool(d))
g.meta.update({"td_save_build": d.get("saveBuild"), "project": d.get("name"),
               "root_path": d.get("rootPath")})

# sanity CRUD
SB = "/gauntlet_smoke"
g.call("delete_operator", {"path": SB}, note="limpieza previa (tolera operator_not_found)")
r = g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "gauntlet_smoke",
                                  "nodeX": -900, "nodeY": -900}, note="sandbox")
bn = g.call_ok("build_network", {"parent_path": SB, "operators": [
    {"type": "noiseTOP", "name": "src"},
    {"type": "blurTOP", "name": "blur"},
    {"type": "nullTOP", "name": "out1"}],
    "connections": [{"from": "src", "to": "blur"}, {"from": "blur", "to": "out1"}],
    "auto_layout": True}, note="noise->blur->null")
g.call_ok("set_parameters", {"path": SB + "/src", "values": {"resolutionw": 256, "resolutionh": 256}})
errs = g.call_ok("get_errors", {"path": SB})
et = g.text_of(errs)
g.check("sin errores tras el build", "error" not in et.lower() or "no errors" in et.lower() or '"errors": []' in et, et[:200])
view = g.call_ok("view_operator", {"path": SB + "/out1", "resolution": "tiny"}, note="captura")
g.check("view_operator devuelve ruta o imagen", ("image" in g.text_of(view)) or (".png" in g.text_of(view).lower()))
g.call_ok("delete_operator", {"path": SB}, note="cleanup")

s = g.summary()
print("\nSMOKE:", json.dumps(s, ensure_ascii=False))

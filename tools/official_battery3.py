"""Bateria 3: args correctos, sandbox limpio, verificacion de bugs y latencias."""
import json, os, sys, time, base64
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tdmcp_client import init, notify, call, text_of
import tdmcp_client as C

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = []
SB = "/hermes_hp"

def T(label, tool, args=None, save_img=None, maxlen=1300):
    t0 = time.time()
    r = call(tool, args)
    ms = round((time.time() - t0) * 1000, 1)
    t = text_of(r)
    OUT.append({"test": label, "tool": tool, "args": args, "ms": ms, "response": t[:6000]})
    print("\n" + "=" * 78)
    print(f"### {label}   [{tool}]  {ms}ms")
    print(t[:maxlen])
    imgs = [c for c in r.get("result", {}).get("content", []) if c.get("type") == "image"]
    if imgs:
        print(f"--> INLINE IMAGE presente: {len(imgs)} ({len(imgs[0].get('data',''))} b64 chars)")
        if save_img:
            open(save_img, "wb").write(base64.b64decode(imgs[0]["data"]))
            print(f"--> guardada: {save_img}")
    return r

full = init()
print("INIT KEYS:", list(full.get("result", {}).keys()))
instr = full.get("result", {}).get("instructions")
print("INSTRUCTIONS (primeros 500):", (instr or "(ninguna)")[:500])
notify("notifications/initialized")

# limpieza de lo anterior
for p in ["/hermes_probe", "/hermes_hp"]:
    call("delete_operator", {"path": p})

T("B1. crear sandbox limpio", "create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "hermes_hp", "nodeX": 500, "nodeY": -150})
T("B2. BUG-FIX? build_network with from/to names + auto_layout", "build_network", {
    "parent_path": SB,
    "operators": [
        {"type": "noiseTOP", "name": "src"},
        {"type": "levelTOP", "name": "lvl"},
        {"type": "nullTOP", "name": "out1"},
    ],
    "connections": [{"from": "src", "to": "lvl"}, {"from": "lvl", "to": "out1"}],
    "auto_layout": True}, maxlen=900)
T("B3. verificar error posterior (deberia estar limpio)", "get_errors", {"path": SB})
T("B4. get_connections graph=true en el COMP", "get_connections", {"path": SB, "graph": True}, maxlen=1200)
T("B5. BUG? get_parameters search (objeto)", "get_parameters", {"path": SB, "search": {"name": "res*", "depth": 1}}, maxlen=900)
T("B6. BUG? reposition_operators positions dict", "reposition_operators", {"parent_path": SB, "positions": {"src": [-300, 200], "lvl": [0, 200], "out1": [300, 200]}})
T("B7. get_docs kind=python (clase)", "get_docs", {"query": "matrix", "kind": "python"}, maxlen=700)
T("B8. get_docs drill section", "get_docs", {"query": "noiseTOP", "kind": "concept", "section": "Parameters - Noise Page"}, maxlen=700)
T("B9. ERROR menu invalido (par real: type)", "set_parameters", {"path": SB + "/src", "values": {"type": "perlin_99"}})
T("B10. set_parameters valido en menu", "set_parameters", {"path": SB + "/src", "values": {"type": "simplex3d", "resolutionw": 512}})
T("B11. UNDO: setear y verificar", "execute_code", {"code": "n=op('/hermes_hp/lvl')\nn.par.brightness1 = 2.5\nprint('brightness ahora:', op('/hermes_hp/lvl').par.brightness1.eval())\nresult = op('/hermes_hp/lvl').par.brightness1.eval()"})
T("B12. execute_code undo() -> revierte?", "execute_code", {"code": "ui.undo()\nprint('brightness tras undo:', op('/hermes_hp/lvl').par.brightness1.eval())\nresult = op('/hermes_hp/lvl').par.brightness1.eval()"})
T("B13. inspect_values CHOP", "execute_code", {"code": "op('/hermes_hp').create('lfoCHOP','lfo')\nprint('creado lfo')\nresult='ok'"})
T("B14. inspect_values CHOP real", "inspect_values", {"path": SB + "/lfo", "include_samples": True}, maxlen=800)
T("B15. tableDAT: set rows + read", "create_operator", {"parent_path": SB, "type": "tableDAT", "name": "tbl", "parameters": {}})
T("B16. set_dat_content rows", "set_dat_content", {"path": SB + "/tbl", "rows": [["k", "v"], ["a", 1], ["b", 2]]})
T("B17. get_dat_content", "get_dat_content", {"path": SB + "/tbl"})
T("B18. set_dat_content file sync (textarea + file)", "set_dat_content", {"path": SB + "/tbl", "text": "hola\n", "file_path": os.path.join(HERE, "synced_dat.txt"), "file_content": "hola desde hermes\n"})
T("B19. view_operator (inline off por default)", "view_operator", {"path": SB + "/out1"})
T("B20. pulso real + verify", "pulse_parameter", {"path": SB + "/out1", "parameter": "cookpulse"})
T("B21. list_operators depth 2 sobre el COMP oficial", "list_operators", {"path": "/TDMCP", "depth": 1}, maxlen=600)
T("B22. get_cook_performance global", "get_cook_performance", {"top_n": 3}, maxlen=700)
T("B23. search_operators global por nombre", "search_operators", {"name_pattern": "*hermes*"}, maxlen=600)
T("B24. delete_operator (auto-accept?)", "delete_operator", {"path": SB})
T("B25. verificar borrado", "list_operators", {"path": "/", "depth": 1}, maxlen=600)

json.dump(OUT, open(os.path.join(HERE, "official_battery3.json"), "w", encoding="utf-8"), indent=2)
lat = [(o["tool"], o["ms"]) for o in OUT]
print("\n\nLATENCIAS (ms):", sorted(lat, key=lambda x: -x[1])[:8])
print("=== guardado official_battery3.json ===")

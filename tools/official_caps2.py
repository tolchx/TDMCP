import sys, os, json, base64
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tdmcp_client import init, notify, call, text_of
HERE = os.path.dirname(os.path.abspath(__file__))
init(); notify("notifications/initialized")
SB = "/hermes_cap2"
OUT = []
def show(l, r, n=1100, img=None):
    print("\n" + "=" * 78); print("###", l); print(text_of(r)[:n])
    imgs = [c for c in r.get("result", {}).get("content", []) if c.get("type") == "image"]
    if imgs and img:
        open(img, "wb").write(base64.b64decode(imgs[0]["data"])); print(f"--> PNG {img} ({os.path.getsize(img)} b)")
    OUT.append({"label": l, "resp": text_of(r)[:3000]}); return r

call("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}})
show("1. get_help types=noiseTOP verbose", call("get_help", {"types": ["noiseTOP"], "pattern": "type,resolution*", "verbose": True}), 1800)
show("2. get_help family=POP (lista completa)", call("get_help", {"family": "POP"}), 1600)
show("3. get_help lfoCHOP (menus)", call("get_help", {"types": ["lfoCHOP"]}), 1200)

show("4. sandbox", call("build_network", {"parent_path": "/", "operators": [
    {"type": "baseCOMP", "name": "hermes_cap2"},
    {"type": "noiseTOP", "name": "src"},
    {"type": "nullTOP", "name": "out1"}],
    "connections": [{"from": "src", "to": "out1"}], "auto_layout": True}))

show("5. view_operator frames=4 (async job)", call("view_operator", {"path": SB + "/out1", "frames": 4, "step": 8, "resolution": "tiny"}))
import time; time.sleep(4)
show("6. view_operator job_id (grid temporal)", call("view_operator", {"job_id": "grid_out1_1"}), 900, img=os.path.join(HERE, "grid_frames.png"))
show("7. inspect_values record_seconds=1s", call("inspect_values", {"path": SB + "/src", "record_seconds": 1.0}), 900)
time.sleep(2)
show("8. retrieve record job", call("inspect_values", {"path": SB + "/src"}), 500)

print("\n" + "#" * 78)
show("9. DAT file-sync: crear textDAT y escribir shader a disco", call("create_operator", {"parent_path": SB, "type": "textDAT", "name": "shader"}))
show("10. set_dat_content file_content (glsl)", call("set_dat_content", {"path": SB + "/shader", "file_content": "out vec4 fragColor;\nvoid main(){ fragColor = TDOutputSwizzle(vec4(1.0,0.5,0.0,1.0)); }\n", "file_type": "glsl"}))
show("11. verificar file-sync del DAT", call("get_parameters", {"path": SB + "/shader", "names": ["file", "syncfile", "loadonstart", "language", "extension"]}), 800)
show("12. get_dat_content del DAT sincronizado", call("get_dat_content", {"path": SB + "/shader"}), 500)

call("delete_operator", {"path": SB})
call("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}})
json.dump(OUT, open(os.path.join(HERE, "official_caps2.json"), "w", encoding="utf-8"), indent=2)
print("\n=== guardado official_caps2.json ===")

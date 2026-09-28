import sys, os, json, base64, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tdmcp_client import init, notify, call, text_of
HERE = os.path.dirname(os.path.abspath(__file__))
init(); notify("notifications/initialized")
SB = "/hermes_grid"
call("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}})
print(call("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "hermes_grid"}).get("result", {}).get("content", [{}])[0].get("text"))
print(call("build_network", {"parent_path": SB, "operators": [
    {"type": "noiseTOP", "name": "src"}, {"type": "levelTOP", "name": "lvl"}, {"type": "nullTOP", "name": "out1"},
    {"type": "lfoCHOP", "name": "lfo"}],
    "connections": [{"from": "src", "to": "lvl"}, {"from": "lvl", "to": "out1"}], "auto_layout": True}).get("result", {}).get("content", [{}])[0].get("text")[:400])

# animar con expression para que los frames difieran
print(call("set_parameters", {"path": SB + "/lvl", "values": {"brightness1": {"expr": "absTime.seconds % 2"}}}).get("result", {}).get("content", [{}])[0].get("text")[:300])

print("\n### grid capture (3 frames sobre tiempo) ###")
r = call("view_operator", {"path": SB + "/out1", "frames": 3, "step": 20, "resolution": "low"})
t = text_of(r); print(t[:600])
job = None
try:
    job = json.loads(t)["job_id"]
except Exception:
    pass
print("job:", job)
time.sleep(3)
if job:
    r2 = call("view_operator", {"job_id": job})
    print("\n### retrieve ###")
    print(text_of(r2)[:500])
    imgs = [c for c in r2.get("result", {}).get("content", []) if c.get("type") == "image"]
    print("content:", [c.get("type") for c in r2.get("result", {}).get("content", [])])
    if imgs:
        p = os.path.join(HERE, "grid_temporal.png")
        open(p, "wb").write(base64.b64decode(imgs[0]["data"]))
        print("PNG:", p, os.path.getsize(p), "bytes")

print("\n### record_seconds CHOP ###")
r3 = call("inspect_values", {"path": SB + "/lfo", "record_seconds": 1.0})
print(text_of(r3)[:600])
try:
    j2 = json.loads(text_of(r3)).get("job_id")
except Exception:
    j2 = None
time.sleep(2.5)
if j2:
    r4 = call("inspect_values", {"path": SB + "/lfo", "job_id": j2})
    print("\n### record retrieve ###"); print(text_of(r4)[:900])

call("delete_operator", {"path": SB})
call("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}})
print("\n=== fin ===")

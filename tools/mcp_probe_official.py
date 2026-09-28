import json, urllib.request, sys

URL = "http://127.0.0.1:13316/mcp"
HDRS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
SESSION = {"id": None}

def rpc(method, params=None, notify=False):
    body = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        body["params"] = params
    if not notify:
        body["id"] = 1
    h = dict(HDRS)
    if SESSION["id"]:
        h["Mcp-Session-Id"] = SESSION["id"]
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            sid = r.headers.get("Mcp-Session-Id")
            if sid:
                SESSION["id"] = sid
            raw = r.read().decode("utf-8", "replace")
            ct = r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return {"_http_error": e.code, "_body": e.read().decode("utf-8", "replace")[:2000]}
    if "text/event-stream" in ct:
        out = None
        for line in raw.splitlines():
            if line.startswith("data:"):
                out = line[5:].strip()
        return json.loads(out) if out else {"_raw": raw[:1000]}
    return json.loads(raw) if raw.strip() else {}

init = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                          "clientInfo": {"name": "hermes-probe", "version": "1.0"}})
print("SESSION:", SESSION["id"])
print("SERVER:", json.dumps(init.get("result", {}).get("serverInfo", {}), indent=None))
rpc("notifications/initialized", {}, notify=True)

tools = rpc("tools/list", {})
tl = tools.get("result", {}).get("tools", [])
print("TOOL COUNT:", len(tl))
with open("official_tools.json", "w", encoding="utf-8") as f:
    json.dump(tl, f, indent=2)
for t in tl:
    print("-", t["name"], "|", (t.get("description") or "").split("\n")[0][:120])
res = rpc("resources/list", {})
print("RESOURCES:", json.dumps(res)[:1500])

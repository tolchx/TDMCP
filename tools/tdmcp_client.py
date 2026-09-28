import json, urllib.request, urllib.error, os, base64, sys

URL = "http://127.0.0.1:13316/mcp"
_S = {"id": None, "seq": 10}

def _post(payload):
    data = json.dumps(payload).encode()
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if _S["id"]:
        h["Mcp-Session-Id"] = _S["id"]
    req = urllib.request.Request(URL, data=data, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            sid = r.headers.get("Mcp-Session-Id")
            if sid:
                _S["id"] = sid
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return {"_http_error": e.code, "_body": e.read().decode("utf-8", "replace")[:2000]}
    if body.startswith("event:") or "\ndata:" in body or body.startswith("data:"):
        for line in body.splitlines():
            if line.startswith("data:"):
                body = line[5:].strip()
    try:
        return json.loads(body)
    except Exception:
        return {"_raw": body[:2000]}

def init():
    return _post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                  "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                             "clientInfo": {"name": "hermes-probe", "version": "1.0"}}})
    _post({"jsonrpc": "2.0", "method": "notifications/initialized"})

def notify(method, params=None):
    return _post({"jsonrpc": "2.0", "method": method, "params": params or {}})

def call(name, args=None, timeout=None):
    _S["seq"] += 1
    return _post({"jsonrpc": "2.0", "id": _S["seq"], "method": "tools/call",
                  "params": {"name": name, "arguments": args or {}}})

def text_of(resp):
    """Flatten a tools/call response into readable text."""
    if "_http_error" in resp or "_raw" in resp:
        return json.dumps(resp)[:1500]
    if "error" in resp:
        return "RPC ERROR: " + json.dumps(resp["error"])[:1500]
    res = resp.get("result", {})
    parts = []
    for c in res.get("content", []):
        if c.get("type") == "text":
            parts.append(c.get("text", ""))
        elif c.get("type") == "image":
            parts.append(f"[IMAGE {c.get('mimeType')} {len(c.get('data',''))} b64 chars]")
        else:
            parts.append(json.dumps(c)[:400])
    if res.get("structuredContent"):
        parts.append("STRUCTURED: " + json.dumps(res["structuredContent"])[:1500])
    if res.get("isError"):
        parts.insert(0, "*** isError=true ***")
    return "\n".join(parts) if parts else json.dumps(res)[:1500]

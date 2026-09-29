"""Prueba real del MCP offline td-knowledge: handshake + tools/list + llamadas."""
import json, os, subprocess, sys

SERVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")
PY = sys.executable


def run(calls):
    # El hijo escribe su stdout con el encoding de locale (cp1252 en Windows);
    # forzar utf-8 para que el pipe coincida con la decodificacion del padre.
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.Popen([PY, SERVER], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1,
                         env=env)
    out = []
    for c in calls:
        p.stdin.write(json.dumps(c) + "\n")
    p.stdin.flush()
    n = 0
    while n < len([c for c in calls if "id" in c]):
        line = p.stdout.readline()
        if not line:
            break
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "id" in msg:
            out.append(msg)
            n += 1
    p.stdin.close()
    try:
        p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        p.kill()
    err = p.stderr.read()
    return out, err


def text_of(r):
    try:
        return r["result"]["content"][0]["text"]
    except Exception:
        return json.dumps(r)


calls = [
    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18",
                                                                   "capabilities": {}, "clientInfo": {"name": "hermes-probe", "version": "1"}}},
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "kb_info", "arguments": {}}},
    {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "kb_search", "arguments": {"query": "how to build a particle system gravity", "limit": 3}}},
    {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "pop_matrix", "arguments": {"type": "particlePOP"}}},
    {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "resolve_operator", "arguments": {"text": "quiero una camara web en vivo"}}},
    {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "glsl_analyze", "arguments": {"code": "void main(){\n  P[id] = P[id] * 1.001;\n  Cd[id] = vec4(1.0);\n}\n", "family": "pop"}}},
    {"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": {"name": "glsl_analyze", "arguments": {"code": "out vec4 fragColor;\nvoid main(){ vec2 c = vUV.uv; fragColor = vec4(c,0.,1.); }", "family": "top"}}},
    {"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "recipes", "arguments": {"action": "list"}}},
    {"jsonrpc": "2.0", "id": 10, "method": "tools/call", "params": {"name": "kb_get", "arguments": {"name_or_slug": "particlePOP", "max_chars": 900}}},
    {"jsonrpc": "2.0", "id": 11, "method": "tools/call", "params": {"name": "contracts", "arguments": {"list": True}}},
    {"jsonrpc": "2.0", "id": 12, "method": "tools/call", "params": {"name": "contracts", "arguments": {"section": "cook_lag"}}},
]
res, err = run(calls)
print("stderr:", err.strip()[:200])
# handshake
init = res[0]["result"]
print("SERVER:", init["serverInfo"], "| protocolo:", init["protocolVersion"])
tools = res[1]["result"]["tools"]
print("TOOLS:", len(tools))
names = [t["name"] for t in tools]
assert len(names) == len(set(names)), "nombres duplicados!"
print("  " + ", ".join(names))
print()
labels = {3: "kb_info", 4: "kb_search", 5: "pop_matrix(particlePOP)", 6: "resolve_operator", 7: "glsl_analyze POP (P se lee y escribe)",
          8: "glsl_analyze TOP (.uv)", 9: "recipes list", 10: "kb_get particlePOP",
          11: "contracts (indice de contratos verificados)", 12: "contracts (section=cook_lag)"}
for r in res[2:]:
    mid = r["id"]
    print("=" * 78); print(f"### [{mid}] {labels.get(mid)}  isError={r['result'].get('isError')}")
    print(text_of(r)[:1500])
json.dump(res, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "selftest_protocol.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print("\n=== evidencia -> selftest_protocol.json ===")

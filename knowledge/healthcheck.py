#!/usr/bin/env python3
"""healthcheck.py - watchdog del stack TD-MCP (sin bridge).

Patron watchdog: si todo esta bien NO imprime nada (stdout vacio => el cron
no_agent no entrega). Si algo falla, imprime una linea compacta con el problema.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# el kb/ puede estar al lado del server (knowledge/kb) o un nivel arriba (repo/kb)
KB = os.environ.get("TD_KNOWLEDGE_KB") or (os.path.join(HERE, "kb") if os.path.isdir(os.path.join(HERE, "kb"))
                                           else os.path.join(os.path.dirname(HERE), "kb"))
problems = []


def check_kb():
    """La KB offline tiene que estar y ser legible."""
    import sqlite3
    db = os.path.join(KB, "knowledge_brain.db")
    if not os.path.isfile(db):
        problems.append("falta la KB (" + db + ") -> correr build_assets.py")
        return
    try:
        con = sqlite3.connect(db)
        n = con.execute("select count(*) from docs").fetchone()[0]
        con.close()
        if n < 1000:
            problems.append("KB con solo " + str(n) + " docs (esperado ~1048)")
    except Exception as e:
        problems.append("KB ilegible: " + str(e)[:120])


EXPECTED_TOOLS = 27  # 21 offline + 6 live


def check_tools():
    """El server tiene que exponer las 27 tools (21 offline + 6 live)."""
    sys.path.insert(0, HERE)
    import server  # noqa: F401  (importarlo no arranca el loop stdio)
    n = len(server.TOOLS)
    if n < EXPECTED_TOOLS:
        problems.append("server.py expone " + str(n) + " tools (esperado " + str(EXPECTED_TOOLS) + ")")


def check_contracts():
    """El fichero de contratos verificados tiene que estar (lo sirve la tool offline)."""
    f = os.path.join(HERE, "contracts", "VERIFIED_CONTRACTS.md")
    if not os.path.isfile(f):
        problems.append("falta contracts/VERIFIED_CONTRACTS.md (tool `contracts` sin datos)")


def check_td():
    """El MCP oficial tiene que responder (esto es lo unico que depende de TD)."""
    import live
    st = live.t_status({})
    if not st.get("td_up"):
        problems.append("TD/TDMCP no responde: " + str(st.get("error"))[:140])


for fn in (check_kb, check_tools, check_contracts, check_td):
    try:
        fn()
    except Exception as e:
        problems.append(fn.__name__ + " exploto: " + type(e).__name__ + ": " + str(e)[:120])

if problems:
    print("TD-MCP healthcheck: " + " | ".join(problems))
sys.exit(0)

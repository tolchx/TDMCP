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


EXPECTED_OFFLINE = 22  # tools sin TD (server.OFFLINE_NAMES)
EXPECTED_LIVE = 42  # tools que hablan con el MCP oficial (live.LIVE_TOOLS)
EXPECTED_TOOLS = EXPECTED_OFFLINE + EXPECTED_LIVE  # 63: pineadas por separado a propósito


def check_tools():
    """Las DOS mitades de la superficie, por separado: si live.py no carga, se ve.

    Antes era `EXPECTED_TOOLS = 27` con guardia `n < EXPECTED_TOOLS`: el server
    expone 63, así que 63 < 27 nunca se cumplía y la guardia no podía fallar.
    Peor aún: las mitades se chequeaban juntas, así que perder las 41 live y
    ganar 41 offline pasaba inadvertido.
    """
    sys.path.insert(0, HERE)
    import server  # noqa: F401  (importarlo no arranca el loop stdio)
    off = len(server.OFFLINE_NAMES)
    n = len(server.TOOLS)
    live_n = n - off
    if off != EXPECTED_OFFLINE or live_n != EXPECTED_LIVE:
        problems.append("server.py expone " + str(off) + " offline + " + str(live_n)
                        + " live (esperado " + str(EXPECTED_OFFLINE) + " + " + str(EXPECTED_LIVE)
                        + " = " + str(EXPECTED_TOOLS) + "; si live=0, revisá el import de live.py)")


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
        return
    # Vivo NO alcanza: hay que decir EN QUE puerto. Si no es el default del repo, el resto
    # de la cadena (clientes, scripts, config de Hermes) apunta a un puerto muerto y el
    # sintoma es "TD cerrado" con TD abierto (medido 2026-11-11: MCP vivo en 13317).
    #
    # PERO esto NO es un fallo de salud: el watchdog es mudo cuando el MCP contesta (si no,
    # el canario de 30 min manda 48 avisos/dia por un detalle de configuracion que ademas
    # se resuelve solo). Se informa cuando alguien corre el healthcheck a mano (tty) o pide
    # el aviso con TDMCP_WARN_DRIFT=1; el drift igual queda visible en `knowledge/endpoint.py`,
    # en el encabezado del gauntlet y en el BACKLOG.
    ep = live.endpoint_info()
    if ep.get("drift") and (os.environ.get("TDMCP_WARN_DRIFT") == "1" or sys.stdout.isatty()):
        problems.append(ep["drift"] + " -> fijalo en <repo>/local/tdmcp-endpoint.txt "
                                      "o en TDMCP_URL")


for fn in (check_kb, check_tools, check_contracts, check_td):
    try:
        fn()
    except Exception as e:
        problems.append(fn.__name__ + " exploto: " + type(e).__name__ + ": " + str(e)[:120])

if problems:
    print("TD-MCP healthcheck: " + " | ".join(problems))
sys.exit(0)

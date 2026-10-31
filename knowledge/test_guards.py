"""test_guards.py — las tres guardias que no podían fallar. Offline: no necesita TD.

1. healthcheck: los conteos pineados tienen que coincidir con la superficie real
   (decía 27 contra 63 reales, así que `n < 27` nunca se cumplía).
2. wire: el parseo del marcador tolera la cola tras el payload (antes devolvía
   «payload ilegible: Extra data» aunque el JSON hubiera llegado).
3. transporte: se reintenta solo lo que no llegó; un timeout de lectura no.

Uso: `python test_guards.py` (exit 1 si algo falla) o `pytest test_guards.py`.
"""
import json
import os
import re
import sys
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "tools", "gauntlet"))

import wire          # noqa: E402
import server        # noqa: E402
import live          # noqa: E402

FAILS = []


def ok(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ((" — " + detail) if not cond else ""))
    if not cond:
        FAILS.append(name)


# ── 1. healthcheck: los pines coinciden con la superficie real ────────────────
def test_healthcheck_pines():
    # se lee la FUENTE a propósito: importar healthcheck dispara check_td (red)
    with open(os.path.join(HERE, "healthcheck.py"), encoding="utf-8") as f:
        src = f.read()
    off = int(re.search(r"EXPECTED_OFFLINE = (\d+)", src).group(1))
    live_n = int(re.search(r"EXPECTED_LIVE = (\d+)", src).group(1))
    ok("healthcheck pinea las 22 offline reales", off == len(server.OFFLINE_NAMES),
       "%d vs %d" % (off, len(server.OFFLINE_NAMES)))
    ok("healthcheck pinea las 41 live reales", live_n == len(live.LIVE_TOOLS),
       "%d vs %d" % (live_n, len(live.LIVE_TOOLS)))
    ok("la guardia puede fallar (no es `if n < esperado`)",
       "if n < EXPECTED_TOOLS:" not in src
       and "if off != EXPECTED_OFFLINE or live_n != EXPECTED_LIVE:" in src)


# ── 2. wire: el marcador y la cola ───────────────────────────────────────────
def test_marcador():
    good, d = wire.json_after_mark('hola\n<<JSON>>{"a": 1, "b": [2, 3]}\nsegundo print')
    ok("tolera un segundo print DESPUÉS del payload (el bug «Extra data»)",
       good and d == {"a": 1, "b": [2, 3]}, str(d))
    good, d = wire.json_after_mark('<<JSON>>{"a": 1}<<JSON>>{"b": 2}')
    ok("con dos payloads gana el primero", good and d == {"a": 1}, str(d))
    good, d = wire.json_after_mark("sin marcador")
    ok("sin marcador devuelve error explícito",
       (not good) and d.get("error") == "sin marcador", str(d))
    good, d = wire.json_after_mark("<<JSON>>{roto")
    ok("JSON roto se reporta como payload ilegible",
       (not good) and d.get("error", "").startswith("payload ilegible"), str(d))
    good, d = wire.json_after_mark("<<JSON>>[1, 2]")
    ok("un payload que no es objeto se rechaza", not good, str(d))
    ok("live.MARK es el mismo literal que wire.MARK", live.MARK == wire.MARK)


# ── 3. transporte: qué se reintenta y qué no ─────────────────────────────────
def test_politica_reintento():
    refused = urllib.error.URLError(ConnectionRefusedError(10061, "refused"))
    ok("ECONNREFUSED es reintentable", wire.is_refused(refused) is True)
    ok("ConnectionRefusedError directo es reintentable", wire.is_refused(ConnectionRefusedError()) is True)
    ok("un timeout de lectura NO es reintentable", wire.is_refused(TimeoutError("timed out")) is False)
    ok("URLError que envuelve un timeout NO es reintentable",
       wire.is_refused(urllib.error.URLError(TimeoutError())) is False)
    ok("sesión vencida en 404 se reconoce",
       wire.is_session_error(404, '{"error": "session not found"}') is True)
    ok("un 404 normal no se confunde con sesión", wire.is_session_error(404, "no such tool") is False)
    ok("un 500 con la palabra session no se reintenta", wire.is_session_error(500, "session") is False)
    ok("rate limiter: lee la espera del mensaje",
       wire.rate_wait("TouchDesigner is recovering from a slow operation. Wait 1.0s, then retry this exact call") == 1.0)
    ok("rate limiter: None en una respuesta normal", wire.rate_wait('{"ok": true}') is None)


# ── 4. el cliente del gauntlet ya no se cae con el puerto cerrado ────────────
def test_gauntlet_transporte():
    import gauntlet_client as gc
    g = gc.Gauntlet("test-guards", run_id="_test-guards")
    old = gc.URL
    gc.URL = "http://127.0.0.1:1/mcp"  # puerto cerrado: rechazo inmediato
    try:
        r = g._post({"jsonrpc": "2.0", "id": 1, "method": "ping"})
    finally:
        gc.URL = old
    ok("un puerto cerrado devuelve error de transporte, no traceback",
       "_transport_error" in r, json.dumps(r)[:200])
    ok("y se marca como reintentable", r.get("_retryable") is True, json.dumps(r)[:200])
    ok("is_err lo trata como error", gc.Gauntlet.is_err(r) is True)


# ── 5. la regla de hogar único sigue limpia ─────────────────────────────────
def test_single_home():
    import check_single_home as csh
    bad = csh.violations()
    ok("check_single_home sin violaciones (settle/px/marcador)", not bad, str(bad[:3]))


for fn in (test_healthcheck_pines, test_marcador, test_politica_reintento,
           test_gauntlet_transporte, test_single_home):
    print("\n### " + fn.__name__)
    fn()

print("\n%d fallo(s)" % len(FAILS))
sys.exit(1 if FAILS else 0)

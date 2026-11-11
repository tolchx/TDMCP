#!/usr/bin/env python3
"""test_endpoint_resolver.py — autoprueba SIN TD de la resolución del endpoint del MCP.

Qué se verifica, EJECUTANDO el resolver real contra servidores HTTP falsos en puertos
efímeros (no string-matching del código):

  1. `TDMCP_URL` manda sobre archivo y sonda (y no paga sonda si está puesta).
  2. El archivo local acepta las tres formas que alguien escribe a mano: URL completa,
     `host:puerto` y `puerto` suelto (con comentarios y líneas vacías alrededor).
  3. Sonda: si el default no contesta y el MCP está en otro puerto, lo ENCUENTRA y lo
     reporta como `drift` (el caso que hizo que 7 corridas dijeran «TD cerrado» con TD vivo).
  4. **Puerto abierto ≠ MCP vivo**: un HTTP server que contesta 404 al POST `initialize`
     NO se acepta como MCP (contrato medido, VERIFIED_CONTRACTS).
  5. Nada contesta: devuelve el default, `reachable=False` y dice qué puertos probó.
  6. `drift` es None cuando el puerto usado es el default del repo (puerto parametrizado
     en el módulo, no en el test).
  7. `live._reresolve()` cambia la URL una sola vez por proceso (guarda contra ECONNREFUSED).
  8. `gauntlet_client.URL` y `run_regression.URL` salen del resolver (TDMCP_URL manda).

Uso: python scripts/test_endpoint_resolver.py   (exit 0 = PASS, 1 = FAIL)
"""
from __future__ import annotations

import importlib.util
import json
import os
import socket
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

AQUI = Path(__file__).resolve().parent
REPO = AQUI.parent
CONOCIMIENTO = REPO / "knowledge"

FALLOS: list[str] = []
CORRIDOS = 0


def check(nombre: str, ok: bool, detalle: str = "") -> None:
    global CORRIDOS
    CORRIDOS += 1
    if not ok:
        FALLOS.append(nombre)
    print(f"  [{'ok ' if ok else 'FAIL'}] {nombre}" + (f"  -> {detalle}" if (detalle and not ok) else ""))


def cargar(nombre: str, path: Path, **extra):
    """Importa un módulo por ruta (como hacen live.py y el gauntlet)."""
    spec = importlib.util.spec_from_file_location(nombre, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = mod
    spec.loader.exec_module(mod)
    for k, v in extra.items():
        setattr(mod, k, v)
    return mod


def puerto_libre() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class _MCPFalso(BaseHTTPRequestHandler):
    """Contesta `initialize` como el MCP oficial (y nada más)."""

    protocol_version = "HTTP/1.1"

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        cuerpo = json.loads(self.rfile.read(n) or b"{}")
        if cuerpo.get("method") != "initialize":
            self.send_response(400)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        out = json.dumps({"jsonrpc": "2.0", "id": cuerpo.get("id"),
                          "result": {"protocolVersion": "2025-06-18",
                                     "capabilities": {},
                                     "serverInfo": {"name": "touchdesigner-mcp",
                                                    "version": "1.1.55"}}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):  # silencio
        pass


class _NoMCP(BaseHTTPRequestHandler):
    """Puerto ABIERTO que no es MCP: 404 a todo (el caso `LISTENING` != MCP vivo)."""

    protocol_version = "HTTP/1.1"

    def do_POST(self):  # noqa: N802
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *a):
        pass


def arrancar(handler) -> tuple:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    h = threading.Thread(target=srv.serve_forever, daemon=True)
    h.start()
    return srv, srv.server_address[1]


def main() -> int:
    ep = cargar("td_knowledge_endpoint", CONOCIMIENTO / "endpoint.py")
    srv_mcp, p_mcp = arrancar(_MCPFalso)
    srv_nomcp, p_nomcp = arrancar(_NoMCP)
    viejo_env = os.environ.pop("TDMCP_URL", None)
    try:
        print("1. TDMCP_URL manda sobre archivo y sonda")
        url_mcp = f"http://127.0.0.1:{p_mcp}/mcp"
        os.environ["TDMCP_URL"] = url_mcp
        r = ep.resolve()
        check("source=env", r["source"] == "env", str(r))
        check("reachable=True", r["reachable"] is True, str(r))
        check("server identificado", "touchdesigner-mcp" in r["server"], str(r))
        check("drift por puerto no-default", bool(r["drift"]) and str(p_mcp) in r["drift"], str(r))
        os.environ.pop("TDMCP_URL", None)

        print("2. El archivo de endpoint acepta URL, host:puerto y puerto suelto")
        tmp = Path(tempfile.mkdtemp(prefix="ep_"))
        for texto, esperado in (
            (f"http://127.0.0.1:{p_mcp}/mcp\n", url_mcp),
            (f"# el .tox de hoy\n\n127.0.0.1:{p_mcp}\n", url_mcp),
            (f"  {p_mcp}  \n", url_mcp),
        ):
            f = tmp / "ep.txt"
            f.write_text(texto, encoding="utf-8")
            leido = ep._read_file_port(str(f))
            check(f"{texto.strip()!r} -> {esperado}", leido == esperado, leido)
        check("archivo inexistente -> ''", ep._read_file_port(str(tmp / "no_existe")) == "")

        print("3. Sonda: encuentra el MCP en otro puerto y lo reporta como drift")
        f = tmp / "ep.txt"
        f.write_text(f"{p_mcp}\n", encoding="utf-8")
        r = ep.resolve(file=str(f))
        check("source=file", r["source"] == "file", str(r))
        check("reachable=True", r["reachable"] is True, str(r))
        check("drift nombra el puerto real", str(p_mcp) in str(r["drift"]), str(r))

        r = ep.resolve(ports=[puerto_libre(), p_mcp], file=str(tmp / "vacio.txt"))
        check("source=probe al no haber archivo", r["source"] == "probe", str(r))
        check("url = el puerto que contesta", r["url"] == url_mcp, str(r))
        check("probó primero el puerto muerto", len(r["tried"]) >= 1, str(r["tried"]))

        print("4. Puerto abierto NO es MCP vivo (404 al initialize no alcanza)")
        vivo, info = ep.probe(f"http://127.0.0.1:{p_nomcp}/mcp")
        check("probe=False en un 404", vivo is False, str(info))
        r = ep.resolve(ports=[p_nomcp], file=str(tmp / "vacio.txt"))
        check("no lo acepta como endpoint", r["reachable"] is False and r["source"] == "default", str(r))

        print("5. Nada contesta: default + reachable=False + puertos probados")
        muerto = puerto_libre()
        r = ep.resolve(ports=[muerto], file=str(tmp / "vacio.txt"))
        check("url=default", r["url"] == ep.default_url(), str(r))
        check("reachable=False", r["reachable"] is False, str(r))
        check("el error dice qué probó", str(muerto) in str(r["error"]), str(r["error"]))

        print("6. Sin drift cuando el puerto usado es el default del repo")
        viejo_default = ep.DEFAULT_PORT
        ep.DEFAULT_PORT = p_mcp  # el "default" pasa a ser el puerto del falso MCP
        try:
            r = ep.resolve(env=False, file=str(tmp / "vacio.txt"), ports=[p_mcp])
            check("drift=None", r["drift"] is None, str(r))
        finally:
            ep.DEFAULT_PORT = viejo_default

        print("7. live._reresolve(): una sola vez por proceso")
        sys.path.insert(0, str(CONOCIMIENTO))
        live = cargar("td_knowledge_live", CONOCIMIENTO / "live.py")
        antes = live.URL
        orig_resolve = live._endpoint.resolve
        live.URL = "http://127.0.0.1:1/mcp"          # puerto muerto
        live._PROBED = False
        live._endpoint.resolve = lambda **kw: {"url": url_mcp, "source": "test", "drift": None}
        try:
            cambio = live._reresolve()
            check("devuelve True y cambia la URL", cambio is True and live.URL == url_mcp, str(live.URL))
            vivo2 = live._reresolve()
            check("segunda vez: no re-sondea", vivo2 is False, str(vivo2))
        finally:
            live._endpoint.resolve = orig_resolve   # NO dejar el stub al resto del test
            live.URL = antes

        print("8. gauntlet_client / run_regression toman la URL del resolver")
        os.environ["TDMCP_URL"] = url_mcp
        gc = cargar("gauntlet_client_test", REPO / "tools" / "gauntlet" / "gauntlet_client.py")
        check("gauntlet_client.URL == TDMCP_URL", gc.URL == url_mcp, gc.URL)
        rr = cargar("run_regression_test", REPO / "tools" / "gauntlet" / "run_regression.py")
        check("run_regression.URL == TDMCP_URL", rr.URL == url_mcp, rr.URL)
    finally:
        if viejo_env is not None:
            os.environ["TDMCP_URL"] = viejo_env
        else:
            os.environ.pop("TDMCP_URL", None)
        srv_mcp.shutdown()
        srv_nomcp.shutdown()

    print()
    if FALLOS:
        print(f"FAIL: {len(FALLOS)} chequeo(s) — {', '.join(FALLOS)}")
        return 1
    print(f"PASS: {CORRIDOS}/{CORRIDOS} chequeos")
    return 0


if __name__ == "__main__":
    sys.exit(main())

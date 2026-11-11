#!/usr/bin/env python3
"""endpoint.py — resolución del endpoint del MCP oficial: el puerto REAL, no el asumido.

Por qué existe: el `.tox` oficial expone su server en el puerto que tenga puesto en su
página *MCP*, y ese valor vive **dentro del TOE de Tolch**, no en el repo. Todo el repo
asumía `13316` (correcto para el default de fábrica). Cuando el TOE abierto usaba otro
puerto, el canario y el ciclo diario reportaban «TD cerrado / WinError 10061» con
TouchDesigner vivo y el MCP respondiendo: siete corridas del loop dijeron «pendiente por
entorno» sobre un entorno que estaba arriba (medido 2026-11-11: TD vivo, MCP 1.1.55 en
`13317`).

Orden de resolución (el primero que contesta manda):
  1. argumento explícito (`url=`)
  2. env `TDMCP_URL`
  3. archivo de endpoint: `local/tdmcp-endpoint.txt` (gitignored, específico de la máquina)
     o el que diga `TDMCP_ENDPOINT_FILE`
  4. sonda de puertos: `13316` y siguientes (`TDMCP_PROBE_SPAN`, default 4 → 13316..13320)
  5. default `13316` (sin respuesta)

La sonda **no** se conforma con TCP abierto: hace un `initialize` MCP real, porque
`LISTENING` no implica MCP vivo (contrato medido, ver
`knowledge/contracts/VERIFIED_CONTRACTS.md`).

Uso:
    import endpoint
    ep = endpoint.resolve()          # dict: url, source, reachable, drift, server, tried
    print(ep["url"])

Sólo stdlib. No importa `server.py` ni `live.py` (lo usan ellos).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

DEFAULT_PORT = 13316
DEFAULT_HOST = "127.0.0.1"


def default_url() -> str:
    return "http://%s:%d/mcp" % (DEFAULT_HOST, DEFAULT_PORT)


def endpoint_file() -> str:
    return os.environ.get("TDMCP_ENDPOINT_FILE") or os.path.join(REPO, "local", "tdmcp-endpoint.txt")


def candidates(ports=None, span=None) -> list:
    """Puertos a sondear, en orden: 13316 primero (el default de fábrica), después el resto."""
    if ports:
        return [int(p) for p in ports]
    p0 = DEFAULT_PORT
    try:
        p0 = int(os.environ.get("TDMCP_PORT") or DEFAULT_PORT)
    except ValueError:
        p0 = DEFAULT_PORT
    if span is None:
        span = int(os.environ.get("TDMCP_PROBE_SPAN", "4"))
    out = [p0]
    for i in range(1, max(0, span) + 1):
        out.append(p0 + i)
    return out


def _post_initialize(url: str, timeout: float = 0.6) -> dict:
    """POST `initialize` al endpoint. Devuelve el `result` o levanta la excepción real."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "td-knowledge-endpoint", "version": "1.0"},
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", "replace")
    s = raw.lstrip()
    if s.startswith("event:") or s.startswith("data:"):
        for line in raw.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip()).get("result") or {}
        return {}
    return json.loads(raw).get("result") or {}


def probe(url: str, timeout: float = 0.6) -> tuple:
    """(vivo, info). `vivo` = el server contestó `initialize` (no sólo el puerto abierto)."""
    try:
        res = _post_initialize(url, timeout=timeout)
    except urllib.error.HTTPError as e:  # 4xx/5xx: hay algo escuchando, pero no es el MCP
        return False, "HTTP %s" % e.code
    except Exception as e:  # URLError/refused/timeout/json
        return False, "%s: %s" % (type(e).__name__, str(e)[:120])
    si = res.get("serverInfo") or {}
    info = " ".join(x for x in (si.get("name"), si.get("version")) if x) or "initialize ok"
    return True, info


def _read_file_port(path: str) -> str:
    """Primera línea no vacía ni comentada del archivo de endpoint.

    Acepta `http://host:port/mcp`, `127.0.0.1:13317` o sólo `13317` (el caso natural:
    alguien anota el puerto que ve en la página MCP del `.tox`).
    """
    if not path or not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            t = line.strip()
            if not t or t.startswith("#"):
                continue
            if t.startswith("http://") or t.startswith("https://"):
                return t
            if t.isdigit():
                return "http://%s:%s/mcp" % (DEFAULT_HOST, t)
            if ":" in t:
                host, _, port = t.rpartition(":")
                port = port.split("/")[0]
                if port.isdigit():
                    return "http://%s:%s/mcp" % (host.strip() or DEFAULT_HOST, port)
            return ""
    return ""


def resolve(url: str = "", env: bool = True, file: str = "", ports=None,
            span=None, do_probe: bool = True, timeout: float = 0.6) -> dict:
    """Resuelve el endpoint. Ver el docstring del módulo para el orden.

    Devuelve `{url, source, reachable, drift, server, error, tried}`.
    `source` ∈ {arg, env, file, probe, default}. `drift` es una frase lista para imprimir
    cuando el puerto usado NO es el default de fábrica.
    """
    default = default_url()
    tried: list = []

    def build(u, source):
        alive, info = (False, "no sonda")
        if do_probe and u:
            alive, info = probe(u, timeout=timeout)
        drift = None
        try:
            port = urllib.parse.urlsplit(u).port
        except ValueError:
            port = None
        if alive and port is not None and port != DEFAULT_PORT:
            drift = ("drift de puerto: el MCP responde en %s pero el default del repo es %d"
                     % (u, DEFAULT_PORT))
        return {"url": u, "source": source, "reachable": alive,
                "drift": drift, "server": info if alive else "",
                "error": "" if alive else info, "tried": tried}

    if url:
        return build(url, "arg")
    if env and os.environ.get("TDMCP_URL"):
        return build(os.environ["TDMCP_URL"], "env")

    f = file or endpoint_file()
    fu = _read_file_port(f) if f else ""
    if fu:
        return build(fu, "file")

    if do_probe:
        for p in candidates(ports, span):
            u = "http://%s:%d/mcp" % (DEFAULT_HOST, p)
            tried.append(p)
            alive, info = probe(u, timeout=timeout)
            if alive:
                drift = None
                if p != DEFAULT_PORT:
                    drift = ("drift de puerto: el MCP responde en %s pero el default del "
                             "repo es %d" % (u, DEFAULT_PORT))
                return {"url": u, "source": "probe", "reachable": True,
                        "drift": drift, "server": info, "error": "", "tried": tried}

    return {"url": default, "source": "default", "reachable": False,
            "drift": None, "server": "",
            "error": "sin respuesta en %s (probado: %s)"
                     % (default, ", ".join(str(p) for p in tried) or "sin sonda"),
            "tried": tried}


def describe(ep: dict) -> str:
    """Una línea legible del endpoint resuelto (para logs y reportes)."""
    base = "endpoint %s (fuente: %s)" % (ep.get("url"), ep.get("source"))
    if ep.get("drift"):
        return base + " — " + ep["drift"]
    if not ep.get("reachable"):
        return base + " — sin respuesta: " + str(ep.get("error"))[:140]
    return base + " — vivo: " + str(ep.get("server"))


if __name__ == "__main__":
    print(describe(resolve()))

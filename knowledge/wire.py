#!/usr/bin/env python3
r"""wire.py — lo que comparten los DOS transportes MCP del repo.

Hasta ahora `live.py` (server, knowledge/) y `tools/gauntlet/gauntlet_client.py`
(harness) tenían su propia copia de tres decisiones, y las copias divergieron:

1. `MARK` — el marcador que separa el payload JSON del `output` de `execute_code`.
2. `json_after_mark()` — el parseo. Era `out.split(MARK, 1)[1]` + `json.loads`:
   si el código imprime algo DESPUÉS del payload (un segundo print, un aviso de
   TD, un traceback), `json.loads` ve datos extra y devuelve
   «payload ilegible: Extra data» aunque el JSON SÍ llegó. Medido 2026-10-31
   contra el proyecto vivo: el dato estaba ahí, se perdió en el parser.
   La regla de `td_probe.py` ("UN solo print") existía justamente para esquivar
   este bug; con `raw_decode` deja de ser necesaria.
3. La política de reintento: qué error se puede reintentar y cuál no.
   Reintentar un timeout de LECTURA es reintentar una llamada que pudo
   ejecutarse (un build a medio hacer, un render encolado); un ECONNREFUSED es
   seguro porque la petición nunca llegó al server.

Una sola casa para las tres. `check_single_home.py` vigila que el parseo no se
re-implemente en tools/gauntlet/.
"""
from __future__ import annotations

import json
import re
import urllib.error

MARK = "<<JSON>>"

_RE_WAIT = re.compile(r"Wait\s+([\d.]+)\s*s")


# ── el marcador ──────────────────────────────────────────────────────────────
def json_after_mark(text: str) -> tuple[bool, dict]:
    """-> (ok, dict). Parsea el PRIMER objeto JSON tras MARK e ignora la cola.

    La cola (un segundo print, warnings de TD) se descarta a propósito: es ruido
    de diagnóstico, no parte del contrato. Si en cambio no hay marcador o el JSON
    está roto, se devuelve el motivo con el output crudo para diagnosticar.
    """
    text = text or ""
    if MARK not in text:
        return False, {"error": "sin marcador", "output": text[:500]}
    tail = text.split(MARK, 1)[1].strip()
    if not tail:
        return False, {"error": "marcador sin payload", "output": text[:500]}
    try:
        obj, _end = json.JSONDecoder().raw_decode(tail)
    except Exception as e:
        return False, {"error": f"payload ilegible: {e}", "output": tail[:500]}
    if not isinstance(obj, dict):
        return False, {"error": "el payload no es un objeto JSON", "output": tail[:500]}
    return True, obj


# ── política de reintento ────────────────────────────────────────────────────
def is_refused(err: BaseException) -> bool:
    """¿La petición no llegó al server? Solo entonces reintentar es seguro.

    `URLError` envuelve el motivo real, así que se desenvuelve. Un timeout
    (socket.timeout / TimeoutError) NO es seguro: el server pudo ejecutar la
    llamada y solo se perdió la respuesta.
    """
    seen = 0
    while err is not None and seen < 5:
        if isinstance(err, ConnectionRefusedError):
            return True
        if isinstance(err, urllib.error.URLError):
            err = err.reason
            seen += 1
            continue
        break
    return False


def is_session_error(code: int, body: str) -> bool:
    """¿El 400/404 es una sesión MCP vencida (server reiniciado) y no un bug?"""
    return code in (400, 404) and "session" in (body or "").lower()


def rate_wait(text: str) -> float | None:
    """Segundos que pide el rate limiter del componente, o None si no es eso.

    Forma del mensaje (C14): «TouchDesigner is recovering from a slow operation.
    Wait 1.0s, then retry this exact call». Se reintenta la MISMA llamada.
    """
    text = text or ""
    if "recovering from a slow operation" not in text:
        return None
    m = _RE_WAIT.search(text)
    return float(m.group(1)) if m else 1.0

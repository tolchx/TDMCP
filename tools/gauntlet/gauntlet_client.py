"""gauntlet_client.py — cliente MCP para el gauntlet del TDMCP oficial.

Hábito: cada tool call queda logueada (args, ms, respuesta truncada) en
results/<run_id>/<fase>.jsonl y acumulada en memoria para el resumen.
Basado en tools/tdmcp_client.py (HTTP + JSON-RPC) y en el patrón MARK de
knowledge/live.py para execute_code.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

URL = os.environ.get("TDMCP_URL", "http://127.0.0.1:13316/mcp")
TIMEOUT = float(os.environ.get("TDMCP_TIMEOUT", "120"))
HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
MARK = "<<JSON>>"

VERSION_ASSERT = "1.1.55"
TOOLS_EXPECTED = 26


class Gauntlet:
    def __init__(self, phase: str, run_id: str | None = None):
        # GAUNTLET_RUN_ID permite que un runner agrupe varias fases en un mismo
        # directorio de corrida (regresión: un run = un veredicto).
        self.run_id = run_id or os.environ.get("GAUNTLET_RUN_ID") or time.strftime("%Y%m%d-%H%M%S")
        self.phase = phase
        self.out_dir = os.path.join(RESULTS, self.run_id)
        os.makedirs(self.out_dir, exist_ok=True)
        self.log_path = os.path.join(self.out_dir, f"{phase}.jsonl")
        self.log = []
        self.meta: dict = {}
        self.sid: str | None = None
        self._seq = 100
        self.failures: list[str] = []

    # ── transporte ───────────────────────────────────────────────────────
    def _post(self, payload: dict, timeout: float | None = None) -> dict:
        data = json.dumps(payload).encode()
        h = {"Content-Type": "application/json",
             "Accept": "application/json, text/event-stream"}
        if self.sid:
            h["Mcp-Session-Id"] = self.sid
        req = urllib.request.Request(URL, data=data, headers=h, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout or TIMEOUT) as r:
                got = r.headers.get("Mcp-Session-Id")
                if got:
                    self.sid = got
                body = r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return {"_http_error": e.code,
                    "_body": e.read().decode("utf-8", "replace")[:2000]}
        s = body.lstrip()
        if s.startswith("event:") or s.startswith("data:"):
            for line in body.splitlines():
                if line.startswith("data:"):
                    return json.loads(line[5:].strip())
        if not body.strip():
            return {}
        try:
            return json.loads(body)
        except Exception:
            return {"_raw": body[:2000]}

    def init(self) -> dict:
        full = self._post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                      "clientInfo": {"name": "codebuff-gauntlet", "version": "1.0"}}})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return full

    # ── llamada con log ──────────────────────────────────────────────────
    def call(self, tool: str, args: dict | None = None, note: str = "",
             timeout: float | None = None, quiet: bool = False) -> dict:
        self._seq += 1
        t0 = time.time()
        r = self._post({"jsonrpc": "2.0", "id": self._seq, "method": "tools/call",
                        "params": {"name": tool, "arguments": args or {}}}, timeout)
        ms = round((time.time() - t0) * 1000, 1)
        entry = {"tool": tool, "args": args or {}, "ms": ms, "note": note,
                 "response": self.text_of(r)[:4000]}
        self.log.append(entry)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if not quiet:
            flag = "ERR" if self.is_err(r) else "ok "
            print(f"  [{flag}] {tool:<24} {ms:>7} ms  {note}")
        return r

    def call_ok(self, tool: str, args: dict | None = None, note: str = "",
                timeout: float | None = None) -> dict:
        r = self.call(tool, args, note, timeout)
        if self.is_err(r):
            self.fail("fallo la tool %s (%s)" % (tool, note or ""))
        return r

    @staticmethod
    def is_err(resp: dict) -> bool:
        if "_http_error" in resp or "error" in resp:
            return True
        res = resp.get("result", {})
        txt = "".join(c.get("text", "") for c in res.get("content", [])
                      if c.get("type") == "text")
        return bool(res.get("isError")) or txt.lstrip().startswith("*** isError=true ***")

    @staticmethod
    def text_of(resp: dict) -> str:
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
                parts.append(f"[IMAGE {c.get('mimeType')} {len(c.get('data', ''))} b64]")
            else:
                parts.append(json.dumps(c)[:400])
        sc = res.get("structuredContent")
        if sc:
            parts.append("STRUCTURED: " + json.dumps(sc)[:1500])
        if res.get("isError"):
            parts.insert(0, "*** isError=true ***")
        return "\n".join(parts) if parts else json.dumps(res)[:1500]

    def json_of(self, resp: dict) -> dict:
        """JSON parseado del primer content de texto; {} si no es JSON."""
        txt = self.text_of(resp).replace("*** isError=true ***", "").strip()
        try:
            return json.loads(txt)
        except Exception:
            # a veces vienen keys STRUCTURED mezcladas: intentar la primera línea JSON
            for line in txt.splitlines():
                line = line.strip()
                if line.startswith("{"):
                    try:
                        return json.loads(line)
                    except Exception:
                        continue
            return {"_unparsed": txt[:500]}

    def save_image(self, resp: dict, path: str) -> str | None:
        for c in resp.get("result", {}).get("content", []):
            if c.get("type") == "image":
                with open(path, "wb") as f:
                    f.write(base64.b64decode(c["data"]))
                return path
        return None

    # ── execute_code con marcador JSON ───────────────────────────────────
    def exec_code(self, code: str, timeout: float | None = None) -> tuple[bool, dict]:
        r = self.call("execute_code", {"code": code}, quiet=True, timeout=timeout)
        if self.is_err(r):
            return False, self.json_of(r) or {"raw": self.text_of(r)[:500]}
        d = self.json_of(r)
        out = str(d.get("output", "") or "")
        if MARK in out:
            try:
                return True, json.loads(out.split(MARK, 1)[1].strip())
            except Exception as e:
                return False, {"error": f"payload ilegible: {e}", "output": out[:500]}
        return False, {"error": "sin marcador", "output": out[:500],
                       "variables": list((d.get("variables") or {}).keys())}

    # ── graders / asserts ────────────────────────────────────────────────
    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        tag = "PASS" if ok else "FAIL"
        print(f"    {tag}  {name}" + (f" — {detail}" if detail and not ok else ""))
        if not ok:
            self.failures.append(f"{self.phase}: {name} {detail}")
        return ok

    def fail(self, msg: str):
        self.failures.append(f"{self.phase}: {msg}")
        print(f"    !! {msg}")

    # ── resumen ──────────────────────────────────────────────────────────
    def summary(self) -> dict:
        lat = sorted(e["ms"] for e in self.log)
        p50 = lat[len(lat) // 2] if lat else 0
        p95 = lat[int(len(lat) * 0.95) - 1] if len(lat) > 1 else (lat[0] if lat else 0)
        s = {"phase": self.phase, "run_id": self.run_id, "calls": len(self.log),
             "p50_ms": p50, "p95_ms": p95, "failures": self.failures,
             "meta": self.meta, "ok": not self.failures}
        with open(os.path.join(self.out_dir, f"{self.phase}-summary.json"), "w",
                  encoding="utf-8") as f:
            json.dump(s, f, indent=2, ensure_ascii=False)
        return s


def new_run() -> str:
    rid = time.strftime("%Y%m%d-%H%M%S")
    os.makedirs(os.path.join(RESULTS, rid), exist_ok=True)
    return rid

#!/usr/bin/env python3
"""loop_triage.py — descubrimiento del loop del TD-MCP (mitad que faltaba).

Convierte SEÑALES REALES del repo en CANDIDATOS A ITEM con su evidencia. Es
determinista y sin LLM: el juicio (convertir un candidato en item, priorizarlo,
resolverlo) queda para el agente o para Tolch. Sin descubrimiento, un loop solo
ejecuta la cola que alguien escribió a mano; con descubrimiento, el MCP se
auto-mejora a partir de lo que realmente se rompe.

Uso:
  python scripts/loop_triage.py             # solo reporta candidatos NUEVOS (para cron)
  python scripts/loop_triage.py --all       # reporta todos, aunque ya los haya visto
  python scripts/loop_triage.py --full      # además corre las suites (lento)
  python scripts/loop_triage.py --audit     # puntaje de preparación del loop + gaps
  python scripts/loop_triage.py --json      # salida JSON cruda

Códigos de salida (para que un cron decida si molesta al humano):
  0 = sin novedades
  3 = hay candidatos nuevos
  4 = loop pausado (kill switch)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "loop-candidates.json"
CLIENT_LOG = Path(os.environ.get("TEMP", "/tmp")) / "tdmcp-client.log"
# Fork tolchx: la evidencia de aceptación en vivo vive en los resultados del gauntlet.
EVIDENCE_DIRS = [ROOT / "tools" / "gauntlet" / "results"]


def paused() -> bool:
    if (ROOT / "loop-pause-all").exists():
        return True
    state = ROOT / "STATE.md"
    if state.exists() and re.search(r"^loop:\s*paused", state.read_text(encoding="utf-8", errors="replace"), re.M):
        return True
    return False


def sh(args: list[str], timeout: int = 900) -> tuple[int, str]:
    try:
        r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, shell=os.name == "nt")
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:  # noqa: BLE001
        return 1, f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# Señales
# ---------------------------------------------------------------------------

def sig_dirty_tree() -> list[dict]:
    """Archivos sucios que NO son de Tolch ni evidencia local."""
    code, out = sh(["git", "status", "--porcelain"])
    if code != 0:
        return []
    # Los `.toe`/`.tox` de Tolch son intocables (loop-constraints): su rotacion de backups
    # no es "trabajo sucio" y no debe consumir el candidato del dia.
    ignorar = ("toe/develop", "docs/glsl_pops_reference.json", "mcp/_tool_list.json",
               ".freebuff_tasks/", ".toe", ".tox")
    dirty = []
    for line in out.splitlines():
        path = line[3:].strip().strip('"')
        if not path or any(ig in path for ig in ignorar):
            continue
        dirty.append(path)
    if not dirty:
        return []
    return [{
        "id": "arbol-sucio",
        "titulo": f"{len(dirty)} archivo(s) modificados sin commitear",
        "evidencia": dirty[:15],
        "sugerencia": "Decidir por archivo: es trabajo en curso (commitear) o residuo (revertir). Un árbol sucio contamina al juez externo.",
        "peso": 2,
    }]


def sig_queue_drift() -> list[dict]:
    if not (ROOT / "scripts" / "reconcile_backlog_queue.py").exists():
        return []
    code, out = sh(["python", "scripts/reconcile_backlog_queue.py", "--check"])
    if code == 0:
        return []
    return [{
        "id": "cola-drift",
        "titulo": "La cola de briefs quedó desincronizada del BACKLOG",
        "evidencia": out.strip().splitlines()[:12],
        "sugerencia": "Correr sin --check para reconciliar y revisar briefs que apunten a items cerrados.",
        "peso": 3,
    }]


def sig_live_evidence_fail() -> list[dict]:
    """Evidencia de aceptación en vivo que quedó en rojo."""
    out = []
    for d in EVIDENCE_DIRS:
        for f in sorted(d.glob("*.json")) if d.exists() else []:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if data.get("all_ok") is False:
                fallas = [c.get("name") for c in data.get("checks", []) if not c.get("ok")]
                out.append({
                    "id": f"vivo-rojo-{f.stem}",
                    "titulo": f"Aceptación en vivo en ROJO: {f.name}",
                    "evidencia": fallas[:8],
                    "sugerencia": f"Reproducir con `{_comando_de(f.stem)}` y abrir item con el fallo concreto.",
                    "peso": 5,
                })
    return out


def _comando_de(stem: str) -> str:
    if "chain" in stem:
        return "node scripts/live/twozero_chain_live.mjs --scope /"
    if "http" in stem:
        return "python scripts/live/twozero_http_live.py"
    if "measure" in stem:
        return "node scripts/live/twozero_measure_live.mjs"
    return "revisar scripts/live/"


def sig_client_log() -> list[dict]:
    """Tipos de error que el cliente ve de verdad en el campo."""
    if not CLIENT_LOG.exists():
        return []
    kinds: dict[str, int] = {}
    ultima_ok = None
    for line in CLIENT_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-2000:]:
        try:
            rec = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if rec.get("ok"):
            ultima_ok = rec.get("ts")
        elif rec.get("kind"):
            kinds[rec["kind"]] = kinds.get(rec["kind"], 0) + 1
    out = []
    for kind in ("connect_reset", "timeout"):
        if kinds.get(kind, 0) >= 3 and ultima_ok:
            out.append({
                "id": f"log-{kind}",
                "titulo": f"{kinds[kind]} fallas de tipo `{kind}` en el log del cliente",
                "evidencia": {"kind": kind, "conteo": kinds[kind], "ultima_llamada_ok": ultima_ok},
                "sugerencia": "Conectividad inestable: revisar si el reintento/cooldown alcanza o si hace falta backoff mayor.",
                "peso": 4,
            })
    return out


def sig_closed_without_live() -> list[dict]:
    """Items cerrados que se declararon con verificación en vivo PENDIENTE."""
    bl = ROOT / "docs" / "BACKLOG.md"
    if not bl.exists():
        return []
    texto = bl.read_text(encoding="utf-8", errors="replace")
    pendientes = re.findall(r"^- \[x\] (\d+)\.([^\n]*)", texto, re.M)
    out = []
    for num, cuerpo in pendientes:
        if re.search(r"en vivo (pendiente|PENDIENTE)|pendiente:? aceptaci", cuerpo, re.I):
            out.append({
                "id": f"vivo-pendiente-{num}",
                "titulo": f"Item {num} cerrado con verificación en vivo pendiente",
                "evidencia": cuerpo.strip()[:200],
                "sugerencia": "Cuando TD esté arriba, correr la aceptación de ese item y actualizar la línea.",
                "peso": 3,
            })
    return out


def sig_stale_briefs() -> list[dict]:
    q = ROOT / ".freebuff_tasks" / "queue"
    if not q.exists():
        return []
    briefs = sorted(q.glob("*.txt"))
    if len(briefs) <= 4:
        return []
    return [{
        "id": "cola-larga",
        "titulo": f"{len(briefs)} briefs encolados para Freebuff",
        "evidencia": [b.name for b in briefs],
        "sugerencia": "La cola se paga en contexto y en horas de agente: priorizar 1 grande por día y fusionar los chicos.",
        "peso": 2,
    }]


def sig_tests(full: bool) -> list[dict]:
    if not full:
        return []
    out = []
    # Fork tolchx: la "suite" es el gauntlet corto (F1+F2). exit 2 = entorno caído (no rojo).
    code, salida = sh(["python", "tools/gauntlet/run_regression.py", "--quick"], timeout=1800)
    if code in (0, 2):
        return []
    m = re.search(r"FAIL\s*[:)]?\s*(\d+)", salida)
    en_rojo = re.findall(r"(?:FAIL|✖)\s*[:\-]?\s*(.+)$", salida, re.M)[:8]
    out.append({
        "id": "gauntlet-rojo",
        "titulo": f"Gauntlet en rojo ({m.group(1) if m else '?'} fases)",
        "evidencia": en_rojo or salida[-500:],
        "sugerencia": "Una fase del gauntlet en rojo es un hallazgo: abrir item con la fase y su salida, no 'arreglar' deshabilitándola.",
        "peso": 5,
    })
    return out


SIGNALS = [sig_dirty_tree, sig_queue_drift, sig_live_evidence_fail,
           sig_closed_without_live, sig_stale_briefs]
# NOTA fork tolchx: sig_client_log quedó FUERA. El log `tdmcp-client.log` era del bridge
# propio retirado (127.0.0.1:44444); el MCP oficial (13316) no escribe ese log, así que la
# señal generaba candidatos falsos de "timeout" sobre un log congelado del sistema viejo.


# ---------------------------------------------------------------------------
# Auditoría del loop (imita loop-audit: puntaje de preparación)
# ---------------------------------------------------------------------------

def audit() -> dict:
    items = [
        ("LOOP.md documenta los loops (propósito, cadencia, niveles)", (ROOT / "LOOP.md").exists(), 10),
        ("loop-constraints.md con reglas vinculantes", (ROOT / "loop-constraints.md").exists(), 12),
        ("loop-budget.md con cupos y kill switch", (ROOT / "loop-budget.md").exists(), 12),
        ("gate.yaml mecánico (denylist + allowlist + maxFiles)", (ROOT / "gate.yaml").exists(), 12),
        ("loop-run-log.md append-only (sin amnesia)", (ROOT / "loop-run-log.md").exists(), 10),
        ("Estado legible por máquina (docs/BACKLOG.md + STATE.md)", (ROOT / "docs" / "BACKLOG.md").exists() and (ROOT / "STATE.md").exists(), 8),
        ("Maker ≠ checker (juez externo configurado)", (ROOT / "scripts").exists(), 8),
        ("Verificación de comportamiento ejecutable (gauntlet)", (ROOT / "tools" / "gauntlet" / "run_regression.py").exists(), 12),
        ("Verificación EN VIVO automatizada (healthcheck + gauntlet)", (ROOT / "knowledge" / "healthcheck.py").exists(), 10),
        ("Cap de intentos / ledger por item", (ROOT / "loop-ledger.json").exists(), 6),
        ("Kill switch respetado por los scripts", (ROOT / "scripts" / "loop_triage.py").exists(), 6),
        ("Descubrimiento automático (este script)", True, 4),
    ]
    total = sum(p for _, _, p in items)
    obtenido = sum(p for _, ok, p in items if ok)
    score = round(100 * obtenido / total)
    faltan = [n for n, ok, _ in items if not ok]
    nivel = "L0" if score < 25 else "L1" if score < 50 else "L2" if score < 80 else "L3"
    return {"score": score, "nivel": nivel, "faltan": faltan,
            "detalle": [{"check": n, "ok": ok, "peso": p} for n, ok, p in items]}


# ---------------------------------------------------------------------------
# Estado de candidatos (dedupe entre corridas)
# ---------------------------------------------------------------------------

def huella(cand: dict) -> str:
    raw = json.dumps({k: cand.get(k) for k in ("id", "titulo", "evidencia")}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def cargar_estado() -> dict:
    if CANDIDATES.exists():
        try:
            return json.loads(CANDIDATES.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {"vistos": {}, "corridas": 0}


def main() -> int:
    ap = argparse.ArgumentParser(description="Descubrimiento del loop del TD-MCP")
    ap.add_argument("--all", action="store_true", help="reportar todos, incluso los ya vistos")
    ap.add_argument("--full", action="store_true", help="además correr las suites")
    ap.add_argument("--audit", action="store_true", help="puntaje de preparación del loop")
    ap.add_argument("--json", action="store_true", help="salida JSON cruda")
    args = ap.parse_args()

    if paused():
        print("loop pausado (loop-pause-all o STATE.md) — no hago nada", file=sys.stderr)
        return 4

    if args.audit:
        a = audit()
        if args.json:
            print(json.dumps(a, indent=2, ensure_ascii=False))
        else:
            print(f"Loop Readiness: {a['score']}/100 — nivel {a['nivel']}\n")
            for d in a["detalle"]:
                print(f"  [{'x' if d['ok'] else ' '}] ({d['peso']:>2}) {d['check']}")
            if a["faltan"]:
                print("\nFalta:")
                for f in a["faltan"]:
                    print(f"  - {f}")
        return 0

    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    candidatos: list[dict] = []
    for sig in SIGNALS:
        try:
            candidatos.extend(sig())
        except Exception as e:  # noqa: BLE001
            candidatos.append({"id": f"error-{sig.__name__}", "titulo": f"la señal {sig.__name__} falló",
                               "evidencia": str(e), "sugerencia": "arreglar el triage", "peso": 1})
    candidatos.extend(sig_tests(args.full))
    candidatos.sort(key=lambda c: -int(c.get("peso", 0)))

    estado = cargar_estado()
    vistos = estado.get("vistos", {})
    nuevos = []
    for c in candidatos:
        h = huella(c)
        c["huella"] = h
        if args.all or h not in vistos:
            nuevos.append(c)
        vistos[h] = {"id": c["id"], "visto_en": ahora, "titulo": c["titulo"]}

    estado["vistos"] = dict(sorted(vistos.items(), key=lambda kv: kv[1]["visto_en"])[-300:])
    estado["corridas"] = int(estado.get("corridas", 0)) + 1
    estado["ultima_corrida"] = ahora
    estado["candidatos"] = candidatos
    CANDIDATES.write_text(json.dumps(estado, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.json:
        print(json.dumps({"nuevos": nuevos, "total": len(candidatos), "audit": audit()}, indent=2, ensure_ascii=False))
    else:
        print(f"triage {ahora} · {len(candidatos)} candidato(s), {len(nuevos)} nuevo(s) · estado: {CANDIDATES.name}")
        for c in nuevos:
            print(f"\n  [{c['peso']}] {c['titulo']}  (id: {c['id']}, huella {c['huella']})")
            ev = c.get("evidencia")
            if isinstance(ev, list):
                for e in ev[:6]:
                    print(f"        - {e}")
            elif ev:
                print(f"        - {ev}")
            print(f"        → {c['sugerencia']}")
        if not nuevos:
            print("  (sin novedades: nada que escalar)")
    return 3 if nuevos else 0


if __name__ == "__main__":
    raise SystemExit(main())

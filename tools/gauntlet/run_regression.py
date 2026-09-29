"""run_regression.py — el gauntlet completo como test de regresión de un solo comando.

Uso (correr con TouchDesigner abierto y el .tox activo en 13316):
    python tools/gauntlet/run_regression.py                    # suite completa
    python tools/gauntlet/run_regression.py --skip-ab          # sin F4 (informative)
    python tools/gauntlet/run_regression.py --quick            # solo F1+F2
    python tools/gauntlet/run_regression.py --tag despues      # sufijo del run
    python tools/gauntlet/run_regression.py --baseline tools/gauntlet/results/<run>/regression-report.json

Qué hace:
  1. Pre-chequea que el server MCP esté vivo (si no: exit 2, sin correr nada).
  2. Corre las fases F1..F4 como subprocess con GAUNTLET_RUN_ID compartido
     (todo cae en results/<run_id>/). F5 (Hermes/KB) queda fuera: verifica el
     entorno del agente, que no depende de la versión del .tox.
  3. Lee el *-summary.json de cada fase y emite veredicto PASS/FAIL
     (F4 es "informativa": sus graders naive fallan BY DESIGN).
  4. Escribe regression-report.json + regression-report.md con el estado del
     entorno (versión del server, build de TD, catálogo de tools) y un veredicto
     global. Con --baseline, agrega un diff contra esa corrida (tools nuevas/
     quitadas, cambios de versión/build, fases que cambiaron de veredicto).

Exit codes: 0 = PASS global · 1 = FAIL global · 2 = entorno caído.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
URL = os.environ.get("TDMCP_URL", "http://127.0.0.1:13316/mcp")

# (etiqueta, script, summaries, requerida)  — summaries = nombres de fase que
# el script le pasa a Gauntlet() (así se llama su *-summary.json)
PHASES = [
    ("F1  Smoke",           "f1_smoke.py",            ["f1-smoke"],          True),
    ("F2  API core",        "f2_core.py",             ["f2-core"],           True),
    ("F3.1 Cadena TOP",     "f3_n1_top.py",           ["f3-n1-top-chain"],   True),
    ("F3.2 Reloj audio",    "f3_n2_audio_clock.py",   ["f3-n2-audio-clock"], True),
    ("F3.3 Modulo + clon",  "f3_n3_module_clone.py",  ["f3-n3-module-clone"], True),
    ("F3.4 Extension py",   "f3_n4_extension.py",     ["f3-n4-extension"],   True),
    ("F3.5 Mini-render",    "f3_n5_render.py",        ["f3-n5-render"],      True),
    ("F3.6 GLSL POP",       "f3_n6_glsl_pop.py",      ["f3-n6-glsl-pop"],    True),
    ("F4  A/B naive",       "f4_ab.py",               ["f4-naive-n2", "f4-naive-n3"], False),
]


def server_alive(timeout: float = 5.0) -> tuple[bool, str]:
    try:
        data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                      "clientInfo": {"name": "gauntlet-regression", "version": "1.0"}}}).encode()
        req = urllib.request.Request(URL, data=data, headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
        for line in body.splitlines():
            if line.startswith("data:"):
                body = line[5:].strip()
                break
        si = json.loads(body).get("result", {}).get("serverInfo", {})
        return True, f"{si.get('name')} v{si.get('version')}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def run_phase(label: str, script: str, run_id: str, pin_version: str | None) -> tuple[int, float]:
    # PYTHONIOENCODING: el hijo emite utf-8 y el padre decodifica utf-8 (sin mojibake
    # de cp1252); el reconfigure aguanta cualquier caracter no imprimible restante.
    env = dict(os.environ, GAUNTLET_RUN_ID=run_id, PYTHONIOENCODING="utf-8")
    if pin_version:
        env["GAUNTLET_PIN_VERSION"] = pin_version
    t0 = time.time()
    proc = subprocess.Popen([sys.executable, script], cwd=HERE, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", bufsize=1)
    for line in proc.stdout:
        sys.stdout.write("     " + line)
    proc.wait()
    return proc.returncode, time.time() - t0


def load_summaries(run_id: str, summary_names: list[str]) -> list[dict]:
    out = []
    for name in summary_names:
        p = os.path.join(RESULTS, run_id, f"{name}-summary.json")
        if os.path.exists(p):
            out.append(json.load(open(p, encoding="utf-8")))
    return out


def diff_baseline(report: dict, baseline_path: str) -> list[str]:
    diffs = []
    try:
        base = json.load(open(baseline_path, encoding="utf-8"))
    except Exception as e:
        return [f"baseline ilegible: {e}"]
    bm = base.get("env", {}); cm = report.get("env", {})
    if bm.get("server_version") != cm.get("server_version"):
        diffs.append(f"server version: {bm.get('server_version')} -> {cm.get('server_version')}")
    if bm.get("td_save_build") != cm.get("td_save_build"):
        diffs.append(f"TD save build: {bm.get('td_save_build')} -> {cm.get('td_save_build')}")
    bt, ct = set(bm.get("tools") or []), set(cm.get("tools") or [])
    if bt - ct:
        diffs.append("tools QUITADAS: " + ", ".join(sorted(bt - ct)))
    if ct - bt:
        diffs.append("tools NUEVAS: " + ", ".join(sorted(ct - bt)))
    for label, entry in report.get("phases", {}).items():
        old = base.get("phases", {}).get(label, {})
        if old and old.get("verdict") != entry.get("verdict"):
            diffs.append(f"{label}: {old.get('verdict')} -> {entry.get('verdict')}")
    if not diffs:
        diffs.append("sin cambios de entorno ni de veredictos")
    return diffs


def main() -> int:
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Gauntlet TDMCP como regresion de un comando")
    ap.add_argument("--skip-ab", action="store_true", help="salta F4 (A/B naive)")
    ap.add_argument("--quick", action="store_true", help="solo F1+F2 (smoke + API core)")
    ap.add_argument("--tag", default="", help="sufijo para el run_id")
    ap.add_argument("--pin-version", default=None,
                    help="falla si la version del server no es esta (ej. 1.1.55)")
    ap.add_argument("--baseline", default=None,
                    help="regression-report.json previo: agrega diff de entorno y veredictos")
    args = ap.parse_args()

    alive, info = server_alive()
    if not alive:
        print(f"ENTORNO CAIDO — no hay server MCP en {URL} ({info})")
        print("Abri TouchDesigner con el .tox TDMCP y pulsa Active en su pagina MCP.")
        return 2
    print(f"Server: {info} @ {URL}")

    run_id = time.strftime("%Y%m%d-%H%M%S") + (f"-{args.tag}" if args.tag else "")
    out_dir = os.path.join(RESULTS, run_id)
    os.makedirs(out_dir, exist_ok=True)
    print(f"Run: {run_id}  ->  results/{run_id}/\n")

    phases_report, all_ok = {}, True
    for label, script, summaries, required in PHASES:
        if args.quick and not script.startswith(("f1_", "f2_")):
            continue
        if args.skip_ab and script == "f4_ab.py":
            continue
        print(f"== {label}  ({script}) " + "=" * max(1, 60 - len(label)))
        rc, secs = run_phase(label, script, run_id, args.pin_version)
        sums = load_summaries(run_id, summaries)
        calls = sum(s.get("calls", 0) for s in sums)
        p50 = max((s.get("p50_ms", 0) for s in sums), default=0)
        fails = [f for s in sums for f in s.get("failures", [])]
        meta = next((s.get("meta") or {} for s in sums if s.get("meta")), {})
        if not required:
            verdict = "INFO"          # F4: los graders naive fallan by design
        elif rc == 0 and not fails:
            verdict = "PASS"
        else:
            verdict = "FAIL"
            all_ok = False
        phases_report[label] = {"script": script, "exit": rc, "secs": round(secs, 1),
                                "calls": calls, "p50_ms": p50, "verdict": verdict,
                                "failures": fails, "meta": meta}
        print(f"   -> {verdict}  ({calls} calls, p50 {p50} ms, {len(fails)} fallos, {secs:.1f}s)\n")

    env = {}
    for entry in phases_report.values():
        m = entry.get("meta") or {}
        if m.get("server_version"):
            env["server_version"] = m["server_version"]
        if m.get("td_save_build"):
            env["td_save_build"] = m["td_save_build"]
        if m.get("tools"):
            env["tools"] = m["tools"]
        if m.get("project"):
            env["project"] = m["project"]
        if m.get("root_path"):
            env["root_path"] = m["root_path"]

    baseline_diff = diff_baseline({"env": env, "phases": phases_report},
                                  args.baseline) if args.baseline else None

    report = {"run_id": run_id, "finished": time.strftime("%Y-%m-%d %H:%M:%S"),
              "url": URL, "overall": "PASS" if all_ok else "FAIL",
              "env": env, "phases": phases_report, "baseline": args.baseline,
              "baseline_diff": baseline_diff}
    rp = os.path.join(out_dir, "regression-report.json")
    json.dump(report, open(rp, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    # reporte legible
    lines = [f"# Regresión gauntlet — {run_id}",
             f"Veredicto global: **{report['overall']}** · server `{env.get('server_version')}` · TD `{env.get('td_save_build')}`",
             "", "| Fase | Veredicto | calls | p50 ms | fallos |", "|---|---|---|---|---|"]
    for label, e in phases_report.items():
        lines.append(f"| {label} | {e['verdict']} | {e['calls']} | {e['p50_ms']} | {len(e['failures'])} |")
    if baseline_diff:
        lines += ["", "## Diff vs baseline (" + os.path.basename(args.baseline) + ")",
                  *[f"- {d}" for d in baseline_diff]]
    mp = os.path.join(out_dir, "regression-report.md")
    open(mp, "w", encoding="utf-8").write("\n".join(lines) + "\n")

    print("=" * 78)
    for label, e in phases_report.items():
        mark = {"PASS": "+", "FAIL": "x", "INFO": "i"}[e["verdict"]]
        print(f"  [{mark}] {label:<22} {e['verdict']:<5} {e['calls']:>3} calls  p50 {e['p50_ms']:>6} ms"
              + (f"  | {e['failures'][0][:70]}" if e["failures"] and e["verdict"] == "FAIL" else ""))
    if baseline_diff:
        print(f"\n  DIFF vs {os.path.basename(args.baseline)}:")
        for d in baseline_diff:
            print(f"    - {d}")
    print(f"\nVEREDICTO GLOBAL: {report['overall']}   (reporte: {os.path.relpath(rp, HERE)})")
    return 0 if all_ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ninterrumpido")
        sys.exit(130)

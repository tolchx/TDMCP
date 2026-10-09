#!/usr/bin/env python3
"""loop_gate.py — enforcement mecánico de gate.yaml (no depende del criterio del agente).

Un loop que se auto-publica necesita un freno que no sea "el agente dice que está bien".
Este script mira el diff y el gate.yaml y decide ALLOW/BLOCK sin juicio humano de por medio.
También lleva el LEDGER de intentos por item, que es lo que hace cumplir el "máx 3 intentos".

Uso:
  python scripts/loop_gate.py --action commit --paths docs/BACKLOG.md mcp/src/tools/medical.ts
  python scripts/loop_gate.py --action commit          # deriva los paths de git
  python scripts/loop_gate.py --action auto-merge --paths docs/BACKLOG.md
  python scripts/loop_gate.py --action commit --no-tests
  python scripts/loop_gate.py --action commit --paths a.py b.py --do-commit "mensaje"
                                       # tras ALLOW: git add <paths> + git commit -m MSG -- <paths>
                                       # commit por PATHSPEC: entra exactamente lo pedido, nunca -A
  python scripts/loop_gate.py --attempt 52             # registra un intento del item 52
  python scripts/loop_gate.py --status                 # intentos por item

Códigos de salida:
  0 = permitido
  2 = bloqueado (mirar el motivo)
  4 = loop pausado (kill switch)
  5 = cap de intentos alcanzado para ese item → escalar a humano
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "gate.yaml"
LEDGER = ROOT / "loop-ledger.json"
RUNLOG = ROOT / "loop-run-log.md"

MINI_YAML_KEYS = ("version", "maxFiles", "maxLines", "requireGreenTests")


# ---------------------------------------------------------------------------
# gate.yaml (parser mínimo: listas de strings + escalares, sin dependencias)
# ---------------------------------------------------------------------------

def load_gate(path: Path) -> dict:
    try:
        import yaml  # type: ignore
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        pass
    data: dict = {}
    clave = None
    for linea in path.read_text(encoding="utf-8").splitlines():
        s = linea.split("#", 1)[0].rstrip()
        if not s.strip():
            continue
        if re.match(r"^\S.*:\s*$", s):
            clave = s.split(":", 1)[0].strip()
            data[clave] = []
            continue
        m = re.match(r"^\s*-\s*[\"']?(.+?)[\"']?\s*$", s)
        if m and clave:
            data[clave].append(m.group(1))
            continue
        m = re.match(r"^(\w+):\s*(.+)$", s)
        if m:
            k, v = m.group(1), m.group(2).strip().strip('"')
            data[k] = {"true": True, "false": False}.get(v.lower(), v)
            clave = None
    return data


# ---------------------------------------------------------------------------
# Diff y comparaciones
# ---------------------------------------------------------------------------

def sh(args: list[str], timeout: int = 1800) -> tuple[int, str]:
    try:
        r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, shell=os.name == "nt")
        # Sólo stdout: `git` manda los avisos de LF→CRLF por stderr y, mezclados, `changed_paths()`
        # los cuenta como archivos (16 reales → 29) y el gate bloquea por maxFiles sin motivo.
        return r.returncode, (r.stdout or "")
    except Exception as e:  # noqa: BLE001
        return 1, f"{type(e).__name__}: {e}"


def changed_paths() -> list[str]:
    paths: set[str] = set()
    for args in (["git", "diff", "--name-only", "HEAD"], ["git", "ls-files", "--others", "--exclude-standard"]):
        code, out = sh(args)
        if code == 0:
            paths.update(p.strip() for p in out.splitlines() if p.strip())
    return sorted(paths)


def added_lines(paths: list[str]) -> int:
    # Con pathspec: contar SOLO las líneas de los paths juzgados — los archivos
    # dirty de un escritor concurrente no inflan el conteo del commit (ítem 3).
    code, out = sh(["git", "diff", "--numstat", "HEAD", "--"] + paths)
    if code != 0:
        return 0
    total = 0
    for linea in out.splitlines():
        partes = linea.split("\t")
        if len(partes) >= 2 and partes[0].isdigit():
            total += int(partes[0])
    return total


def staged_paths() -> list[str]:
    """Lo que hay en el INDEX (`git diff --cached --name-only`, contra HEAD).

    Es la superficie exacta de un `git add -A`: un commit sin pathspec publicaría
    TODO esto, incluidos los archivos que la corrida no tocó (ítem 3).
    """
    code, out = sh(["git", "diff", "--cached", "--name-only"])
    if code != 0:
        return []
    return sorted(p.strip().replace("\\", "/") for p in out.splitlines() if p.strip())


def concurrent_outside(paths: list[str]) -> list[str]:
    """Archivos dirty (staged/unstaged/untracked) que NO están en los paths juzgados.

    No bloquean (un commit por pathspec no los toca y revertirlos sería destructivo
    sobre trabajo vivo — decisión del ítem 4), pero el cierre debe DEJARLOS VISIBLES:
    son la firma de un escritor concurrente en el mismo árbol.
    """
    en_paths = {p.replace("\\", "/") for p in paths}
    return sorted(p for p in changed_paths() if p not in en_paths)


def match_any(path: str, patterns: list[str]) -> str | None:
    p = path.replace("\\", "/")
    for pat in patterns or []:
        if fnmatch.fnmatch(p, pat) or fnmatch.fnmatch(p, pat.rstrip("/") + "/**") or p == pat:
            return pat
    return None


def sh_raw(args: list[str], timeout: int = 600) -> tuple[int, str]:
    """Como sh() pero SIN shell y CON stderr: para git add/commit, cuyos errores
    ("nothing to commit", pathspec inválido) van a stderr. shell=False conserva
    intacto el MENSAJE del commit (espacios/newlines) — sh() con shell=True en
    Windows lo re-ensamblaría y lo rompería.
    """
    try:
        r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, shell=False)
        salida = (r.stdout or "") + (("\n[stderr] " + r.stderr) if r.stderr else "")
        return r.returncode, salida
    except Exception as e:  # noqa: BLE001
        return 1, f"{type(e).__name__}: {e}"


def do_commit(paths: list[str], mensaje: str) -> int:
    """ALLOW → commit por PATHSPEC: entra exactamente lo pedido, nunca -A (ítem 3).

    `git commit -m MSG -- <paths>` toma el contenido del working tree de esos paths
    e IGNORA lo stageado de otros paths: el `git add -A` de un escritor ajeno NO
    entra. El add previo es sólo para que los paths NUEVOS (untracked) sean
    conocidos por el pathspec del commit.
    """
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # Declara los paths del item para el hook mecánico (.git/hooks/pre-commit):
    # sin esto el hook bloquea el commit (regla: nada fuera de lo declarado).
    try:
        allow = os.path.join(".git", "gate-allowlist")
        with open(allow, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("".join(p.rstrip() + "\n" for p in paths))
    except OSError as e:  # noqa: BLE001
        print(f"  ✖ no pude escribir .git/gate-allowlist: {e}", file=sys.stderr)
        return 2
    code, out = sh_raw(["git", "add", "--"] + paths)
    if code != 0:
        print(f"  ✖ git add falló: {out.strip()[:300]}", file=sys.stderr)
        append_runlog(f"- {ts} | gate | — | git add falló antes del commit | BLOCK | gate.yaml")
        return 2
    code, out = sh_raw(["git", "commit", "-m", mensaje, "--"] + paths)
    if code != 0:
        print(f"  ✖ git commit falló (¿paths sin cambios?): {out.strip()[:400]}", file=sys.stderr)
        append_runlog(f"- {ts} | gate | — | git commit falló (paths sin cambios u otro error) | BLOCK | gate.yaml")
        return 2
    m = re.search(r"\[[^\]]+ ([0-9a-f]{7,})\]", out)
    h = m.group(1) if m else "?"
    print(f"  ✔ commit {h} — {len(paths)} archivo(s) exactos por pathspec (nunca -A)")
    append_runlog(f"- {ts} | gate | — | commit {h} de {len(paths)} archivo(s) (pathspec, --do-commit) | gate.yaml")
    return 0


def paused() -> bool:
    if (ROOT / "loop-pause-all").exists():
        return True
    st = ROOT / "STATE.md"
    return bool(st.exists() and re.search(r"^loop:\s*paused", st.read_text(encoding="utf-8", errors="replace"), re.M))


# ---------------------------------------------------------------------------
# Ledger de intentos
# ---------------------------------------------------------------------------

def load_ledger() -> dict:
    if LEDGER.exists():
        try:
            return json.loads(LEDGER.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {"items": {}}


def save_ledger(l: dict) -> None:
    LEDGER.write_text(json.dumps(l, indent=2, ensure_ascii=False), encoding="utf-8")


def register_attempt(item: str, max_attempts: int = 3) -> int:
    l = load_ledger()
    reg = l["items"].setdefault(item, {"attempts": 0, "history": []})
    reg["attempts"] += 1
    reg["history"].append(datetime.now(timezone.utc).isoformat(timespec="seconds"))
    reg["history"] = reg["history"][-20:]
    save_ledger(l)
    print(f"item {item}: intento {reg['attempts']} de {max_attempts}")
    if reg["attempts"] > max_attempts:
        print(f"CAP ALCANZADO: {reg['attempts']} intentos en '{item}'. Escalar a humano con el historial: {reg['history']}")
        return 5
    return 0


def append_runlog(texto: str) -> None:
    if not RUNLOG.exists():
        RUNLOG.write_text("# loop-run-log.md\n", encoding="utf-8")
    with RUNLOG.open("a", encoding="utf-8") as fh:
        fh.write(texto if texto.endswith("\n") else texto + "\n")


# ---------------------------------------------------------------------------
# Consola segura: nunca morir por el encoding del terminal
# ---------------------------------------------------------------------------

def _force_safe_output() -> None:
    """Windows con consola legacy (cp1252) no puede codificar los glifos del
    veredicto (✔/✖): el gate moría con UnicodeEncodeError a mitad de impresión,
    DESPUÉS de decidir ALLOW/BLOCK, dejando sin veredicto ni exit code.

    - Stream redirigido (CI, pipe, archivo): forzar UTF-8 — es lo que el resto
      del repo asume y lo que esperan los consumidores del log.
    - Consola real (isatty): respetar su encoding pero degradar lo no
      codificable (errors='replace', ✔→'?') en vez de lanzar excepción.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            reconfigure = getattr(stream, "reconfigure", None)
            if reconfigure is None:  # wrappers sin reconfigure (caps, mocks)
                continue
            tty = stream.isatty()
            if tty:
                reconfigure(errors="replace")
            else:
                reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass  # stream raro que no se puede reconfigurar: mejor intento


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Juez externo (jev) — presente en el proceso, sin volverse dependencia
# ---------------------------------------------------------------------------

JUDGE = os.path.join(os.environ.get("LOCALAPPDATA", ""), "hermes", "scripts", "jev_audit_diff.py")


def run_judge(brief: str | None) -> tuple[bool, dict, str]:
    """Corre el juez externo sobre el árbol. Devuelve (permite, veredicto, motivo).

    Regla de Tolch (advisory, no dependencia): si el juez NO está disponible
    (sin saldo, sin red, script ausente) el loop SIGUE, avisando. Lo que sí
    frena es un veredicto NEGATIVO: naturaleza que no sea trabajo real, o
    debilita alta. El detalle queda en loop-ledger.json.
    """
    if not os.path.isfile(JUDGE):
        return True, {"estado": "no_disponible"}, "juez no encontrado: se sigue (advisory)"
    cmd = ["python", JUDGE, "--repo", str(ROOT), "--json"]
    if brief:
        cmd += ["--brief", brief]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=900)
        v = json.loads((r.stdout or "").strip() or "{}")
    except Exception as e:  # timeout, JSON roto, lo que sea
        return True, {"estado": "error", "detalle": str(e)[:200]}, f"juez no concluyó ({e}): se sigue (advisory)"

    naturaleza = str(v.get("naturaleza") or "").lower()
    debilita = float(v.get("debilita") or 0.0)
    corresponde = v.get("corresponde_al_brief")

    motivos = []
    if "no_" in naturaleza or naturaleza in ("", "ruido") or "evidencia" in naturaleza:
        motivos.append(f"la naturaleza juzgada no es trabajo real ('{naturaleza}')")
    if debilita >= 0.6:
        motivos.append(f"debilita {debilita} (>= 0.6): el diff empeora el repo")
    if corresponde is not None and float(corresponde) < 0.2:
        motivos.append(f"corresponde_al_brief {corresponde} (< 0.2): no parece ser la tarea pedida")
    permite = not motivos
    return permite, v, ("; ".join(motivos) if motivos else f"veredicto {v.get('veredicto')} · {naturaleza} · debilita {debilita}")


def run_tests() -> tuple[bool, dict]:
    """Suites verdes antes de dejar pasar un commit. Devuelve (ok, detalle).

    Adaptado al fork tolchx: las suites son (1) el self-test offline de la KB,
    (2) el test de protocolo MCP, (3) el gauntlet corto (F1+F2) que exige TD, y
    (4) las dos suites de host del gauntlet: la invariante del único dueño de la
    medición (`check_single_home.py`) y su autoprueba sin TD (`td_probe.py`).
    El gauntlet devuelve exit 2 cuando TD está caído — eso NO es un rojo, es
    "no runnable": se anota y no bloquea (el canario de 30 min cubre ese caso).
    Las suites de host no dependen de TD: si alguna se pone roja, bloquea siempre.
    """
    res: dict = {}
    ok = True
    pasos = [
        ("kb_selftest", ["python", "knowledge/server.py", "--selftest"], ROOT),
        ("kb_protocol", ["python", "knowledge/test_protocol.py"], ROOT),
        ("gauntlet_quick", ["python", "tools/gauntlet/run_regression.py", "--quick"], ROOT),
        ("single_home", ["python", "tools/gauntlet/check_single_home.py"], ROOT),
        ("td_probe_selftest", ["python", "tools/gauntlet/td_probe.py"], ROOT),
    ]
    for nombre, cmd, cwd in pasos:
        try:
            r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=1800,
                               shell=os.name == "nt")
            salida = (r.stdout or "") + (r.stderr or "")
            code = r.returncode
        except Exception as e:  # noqa: BLE001
            code, salida = 1, f"{type(e).__name__}: {e}"
        # exit 2 del gauntlet = entorno caído (TD no abierto / .tox inactivo): no es rojo
        if nombre == "gauntlet_quick" and code == 2:
            res[nombre] = {"exit": code, "resumen": "entorno caído (TD no abierto): salteado"}
            continue
        res[nombre] = {"exit": code,
                       "resumen": ("ok" if code == 0 else salida.strip().splitlines()[-8:])}
        if code != 0:
            ok = False
    return ok, res



def main() -> int:
    _force_safe_output()
    ap = argparse.ArgumentParser(description="Gate mecánico del loop del TD-MCP")
    ap.add_argument("--action", choices=["commit", "auto-merge"], default="commit")
    ap.add_argument("--paths", nargs="*", default=None)
    ap.add_argument("--no-tests", action="store_true")
    ap.add_argument("--do-commit", metavar="MENSAJE", default=None,
                    help="tras ALLOW: git add <paths> + git commit -m MENSAJE -- <paths> "
                         "(commit por pathspec: exactamente los paths, nunca -A; ítem 3)")
    ap.add_argument("--judge", dest="judge", action="store_true", default=True,
                    help="corre el juez externo (jev) sobre el arbol; por defecto ON")
    ap.add_argument("--no-judge", dest="judge", action="store_false",
                    help="saltea el juez externo (queda registrado en el ledger)")
    ap.add_argument("--brief-file", metavar="ARCHIVO", default=None,
                    help="brief enviado, para que el juez evalue el alcance")
    ap.add_argument("--attempt", metavar="ITEM", help="registrar un intento del item")
    ap.add_argument("--max-attempts", type=int, default=3)
    ap.add_argument("--status", action="store_true", help="intentos por item")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if paused():
        print("loop pausado (loop-pause-all o STATE.md) — el gate no deja pasar nada", file=sys.stderr)
        return 4

    if args.status:
        l = load_ledger()
        print(json.dumps(l, indent=2, ensure_ascii=False) if args.json
              else "\n".join(f"  item {k}: {v['attempts']} intento(s)" for k, v in l["items"].items()) or "  (sin intentos registrados)")
        return 0

    if args.attempt:
        return register_attempt(args.attempt, args.max_attempts)

    if not GATE.exists():
        print("no existe gate.yaml: sin gate no hay auto-publicación", file=sys.stderr)
        return 2
    gate = load_gate(GATE)

    paths = args.paths if args.paths else changed_paths()
    paths = [p for p in paths if p.strip()]
    if not paths:
        print("ALLOW (no hay cambios que revisar)")
        return 0

    motivos: list[str] = []
    denylist = list(gate.get("denylist") or [])
    allowlist = list(gate.get("autoMergeAllowlist") or [])
    max_files = int(gate.get("maxFiles") or 999)
    max_lines = int(gate.get("maxLines") or 10**9)

    for p in paths:
        hit = match_any(p, denylist)
        if hit:
            motivos.append(f"'{p}' está en la denylist (patrón '{hit}'): requiere revisión humana explícita")
        if args.action == "auto-merge" and not match_any(p, allowlist):
            motivos.append(f"'{p}' no está en el allowlist de auto-merge")

    if len(paths) > max_files:
        motivos.append(f"{len(paths)} archivos > maxFiles={max_files}: cambio demasiado grande para auto-publicar")
    lineas = added_lines(paths)
    if lineas > max_lines:
        motivos.append(f"{lineas} líneas agregadas > maxLines={max_lines}")

    # Ítem 3 — barrido ajeno: con paths explícitos, lo STAGEADO fuera de ellos es
    # la huella de un `git add -A` (propio o de otro escritor en el mismo árbol).
    # Un commit por pathspec no lo tocaría, pero el cierre se ABORTA igual: el
    # stage ajeno se perdería o se publicaría en el PRÓXIMO commit sin gate.
    norm = {p.replace("\\", "/") for p in paths}
    stageados = staged_paths()
    ajenos = [p for p in stageados if p not in norm]
    if ajenos:
        lista = ", ".join(ajenos[:5]) + ("…" if len(ajenos) > 5 else "")
        motivos.append(f"{len(ajenos)} archivo(s) STAGEADOS fuera de --paths ({lista}): probable "
                       "`git add -A` de otro escritor — abortar el cierre (git restore --staged "
                       "o incluirlos explícitamente en --paths)")
    concurrentes = concurrent_outside(norm)

    if not motivos and args.judge:
        permite, v, motivo = run_judge(args.brief_file)
        judge_info = {"veredicto": v.get("veredicto"), "naturaleza": v.get("naturaleza"),
                      "debilita": v.get("debilita"), "corresponde_al_brief": v.get("corresponde_al_brief"),
                      "costo_usd": v.get("costo_usd"), "motivo": motivo}
        print(("  \u2714 juez externo (jev): " if permite else "  \u2716 juez externo (jev): BLOQUEA — ") + motivo)
        if not permite:
            motivos.append(f"juez externo (jev): {motivo}")
    else:
        judge_info = {"estado": "salteado" if args.judge else "apagado"}

    tests_info = None
    if not motivos and gate.get("requireGreenTests", True) and not args.no_tests:
        ok, tests_info = run_tests()
        if not ok:
            motivos.append("las suites no están verdes (ver detalle)")

    veredicto = "BLOCK" if motivos else "ALLOW"
    resumen = {"veredicto": veredicto, "accion": args.action, "judge": judge_info, "archivos": len(paths),
               "lineas_agregadas": lineas, "motivos": motivos, "tests": tests_info, "paths": paths[:20],
               "stageados_ajenos": ajenos, "concurrentes": concurrentes[:20]}
    if args.json:
        print(json.dumps(resumen, indent=2, ensure_ascii=False))
    else:
        print(f"{veredicto} · acción={args.action} · {len(paths)} archivo(s), {lineas} línea(s) agregadas")
        for m in motivos:
            print(f"  ✖ {m}")
        if concurrentes:
            lista = ", ".join(concurrentes[:5]) + ("…" if len(concurrentes) > 5 else "")
            print(f"  ! {len(concurrentes)} archivo(s) dirty fuera de --paths (no entran al commit con "
                  f"pathspec; escritor concurrente?): {lista}")
        if not motivos:
            print("  ✔ dentro de gate.yaml (denylist, maxFiles/maxLines, allowlist, suites verdes)")

    if veredicto == "ALLOW":
        append_runlog(f"- {datetime.now(timezone.utc).isoformat(timespec='seconds')} | gate | — | {args.action} sobre {len(paths)} archivo(s) | ALLOW | conc={len(concurrentes)} | gate.yaml")
        if args.do_commit:
            return do_commit(paths, args.do_commit)
        return 0
    append_runlog(f"- {datetime.now(timezone.utc).isoformat(timespec='seconds')} | gate | — | {args.action} sobre {len(paths)} archivo(s) | BLOCK: {'; '.join(motivos)[:200]} | gate.yaml")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

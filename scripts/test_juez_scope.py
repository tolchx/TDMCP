#!/usr/bin/env python3
"""test_juez_scope.py — autoprueba SIN red y SIN TD del alcance del juez externo.

Ítem 11 del BACKLOG: `jev_audit_diff.py` arma su diff con `git status --porcelain`,
así que con cualquier WIP ajeno en el working tree juzga archivos que NO entran al
commit (y trunca el diff real). `loop_gate.juez_scope(paths)` le da al juez un clon
aislado con SOLO los paths del commit.

Qué se verifica acá (ejecutando de verdad, no string-matching):
  1. El clon aislado deja como único diff los paths pedidos: el WIP ajeno (modificado,
     untracked) NO aparece y un archivo borrado en el working tree SÍ se refleja.
  2. `run_judge(..., paths)` corre el juez sobre ese clon: un juez de prueba que
     reporta lo que ve con `git status` devuelve exactamente los paths del commit.
  3. A/B del defecto: el mismo juez sobre el árbol completo ve el WIP ajeno (4
     entradas) y scopeado ve 1. Eso es la prueba de que el ítem 11 estaba abierto.

Uso: python scripts/test_juez_scope.py   (exit 0 = PASS, 1 = FAIL)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import loop_gate  # noqa: E402

FALLOS: list[str] = []


def check(nombre: str, ok: bool, detalle: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + nombre + (f" — {detalle}" if detalle and not ok else ""))
    if not ok:
        FALLOS.append(nombre)


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.stdout or ""


def estado(repo: Path) -> list[str]:
    """Paths sucios según git status --porcelain (lo mismo que mira el juez)."""
    out = git(repo, "status", "--porcelain")
    res = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        p = line[3:].strip().strip('"')
        if " -> " in p:
            p = p.split(" -> ")[-1].strip().strip('"')
        res.append(f"{line[:2]} {p}")
    return sorted(res)


def crear_repo(base: Path) -> Path:
    repo = base / "repo_prueba"
    repo.mkdir()
    (repo / "a.txt").write_text("a v1\n", encoding="utf-8")
    (repo / "b.txt").write_text("b v1\n", encoding="utf-8")
    (repo / "del.txt").write_text("borrame\n", encoding="utf-8")
    git(repo, "init", "-q")
    git(repo, "-c", "user.email=loop@test", "-c", "user.name=loop", "add", "-A")
    git(repo, "-c", "user.email=loop@test", "-c", "user.name=loop", "commit", "-q", "-m", "init")
    # WIP: dos modificados, uno borrado, uno untracked (el "escritor concurrente")
    (repo / "a.txt").write_text("a v2 (commit)\n", encoding="utf-8")
    (repo / "b.txt").write_text("b v2 (ajeno)\n", encoding="utf-8")
    (repo / "c.txt").write_text("untracked ajeno\n", encoding="utf-8")
    (repo / "del.txt").unlink()
    return repo


def escribir_juez_falso(base: Path) -> Path:
    """Juez de prueba: reporta como 'archivos_juzgados' lo que ve con git status.

    Además guarda en `argv.json` los argumentos con los que lo llamaron, para poder
    verificar el `--max-chars` del alcance sin depender del juez real.
    """
    f = base / "juez_falso.py"
    f.write_text(
        "import argparse, json, subprocess, sys\n"
        "ap = argparse.ArgumentParser()\n"
        "ap.add_argument('--repo'); ap.add_argument('--brief'); ap.add_argument('--json', action='store_true')\n"
        "ap.add_argument('--max-chars', type=int, default=16000)\n"
        "a = ap.parse_args()\n"
        "out = subprocess.run(['git', '-C', a.repo, 'status', '--porcelain'],\n"
        "                     capture_output=True, text=True).stdout\n"
        "files = [ln[3:].strip().strip('\"') for ln in out.splitlines() if len(ln) >= 4]\n"
        "open(sys.argv[0] + '.argv.json', 'w', encoding='utf-8').write(json.dumps(sys.argv))\n"
        "print(json.dumps({'veredicto': 'VERDE', 'naturaleza': 'trabajo_real', 'debilita': 0.0,\n"
        "                  'corresponde_al_brief': None, 'archivos_juzgados': files,\n"
        "                  'max_chars': a.max_chars}))\n",
        encoding="utf-8")
    return f


def main() -> int:
    base = Path(tempfile.mkdtemp(prefix="test-juez-scope-"))
    try:
        repo = crear_repo(base)
        juez = escribir_juez_falso(base)

        print("[1] juez_scope: el clon aislado contiene SOLO los paths del commit")
        aislado, motivo = loop_gate.juez_scope(["a.txt"], root=repo)
        check("juez_scope devuelve un clon", bool(aislado), motivo)
        if aislado:
            try:
                clon = Path(aislado)
                sucio = estado(clon)
                check("un solo path sucio en el clon", sucio == ["M  a.txt"] or sucio == [" M a.txt"],
                      f"visto: {sucio}")
                check("el WIP ajeno (b.txt) no viaja", not any("b.txt" in s for s in sucio), f"visto: {sucio}")
                check("el untracked ajeno (c.txt) no viaja", not any("c.txt" in s for s in sucio), f"visto: {sucio}")
                check("el contenido es el del working tree",
                      (clon / "a.txt").read_text(encoding="utf-8") == "a v2 (commit)\n")
            finally:
                shutil.rmtree(Path(aislado).parent, ignore_errors=True)

        aislado2, motivo2 = loop_gate.juez_scope(["a.txt", "b.txt", "del.txt"], root=repo)
        check("juez_scope con 3 paths devuelve clon", bool(aislado2), motivo2)
        if aislado2:
            try:
                sucio = estado(Path(aislado2))
                check("refleja el borrado del working tree",
                      any(s.startswith(" D") and s.endswith("del.txt") for s in sucio), f"visto: {sucio}")
                check("3 paths sucios, nada más", len(sucio) == 3, f"visto: {sucio}")
            finally:
                shutil.rmtree(Path(aislado2).parent, ignore_errors=True)

        print("[2] run_judge scopeado: el juez ve exactamente el commit")
        orig_root, orig_judge = loop_gate.ROOT, loop_gate.JUDGE
        try:
            loop_gate.ROOT, loop_gate.JUDGE = repo, str(juez)
            permite, v, motivo = loop_gate.run_judge(None, ["a.txt"])
            vistos = v.get("archivos_juzgados")
            check("run_judge permite (advisory, juez VERDE)", permite, motivo)
            check("el juez miró sólo a.txt", vistos == ["a.txt"], f"visto: {vistos}")
            check("el veredicto declara el scope aislado", "clon aislado" in str(v.get("scope")), str(v.get("scope")))
            check("scopeado: el juez recibe --max-chars 40000 (el diff ES el commit)",
                  v.get("max_chars") == 40000, str(v.get("max_chars")))

            print("[3] A/B del ítem 11: sin scope el juez ve el WIP ajeno")
            _, v2, _ = loop_gate.run_judge(None, None)
            vistos2 = v2.get("archivos_juzgados") or []
            check("sin scope ve 4 archivos (contaminado)", len(vistos2) == 4, f"visto: {vistos2}")
            check("el scope redujo el diff de 4 a 1", len(vistos2) > len(vistos or ["a.txt"]),
                  f"completo={vistos2} scopeado={vistos}")
            check("sin scope conserva el presupuesto del juez (16000)",
                  v2.get("max_chars") == 16000, str(v2.get("max_chars")))
        finally:
            loop_gate.ROOT, loop_gate.JUDGE = orig_root, orig_judge
    finally:
        shutil.rmtree(base, ignore_errors=True)

    total_ok = not FALLOS
    print(f"test_juez_scope: {'PASS' if total_ok else 'FAIL'} "
          f"({len(FALLOS)} fallo(s){': ' + ', '.join(FALLOS) if FALLOS else ''})")
    return 0 if total_ok else 1


if __name__ == "__main__":
    sys.exit(main())

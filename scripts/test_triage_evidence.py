#!/usr/bin/env python3
"""test_triage_evidence.py — autoprueba SIN red y SIN TD de la señal de evidencia en rojo.

Ítem 6 del BACKLOG (sub-hallazgo offline): `sig_live_evidence_fail()` globeaba
`tools/gauntlet/results/*.json` **sin recursión** y buscaba la clave `all_ok`. En el
repo real eso da 1 archivo visible de 934 (los `*-summary.json` y el
`regression-report.json` viven en `results/<run_id>/`) y el esquema que escribe el
gauntlet es `ok`/`failures` (summary) y `overall`/`phases` (reporte). Conclusión: la
señal de "aceptación en vivo en rojo" era **incapaz de dispararse**, y el loop solo
podía descubrir árboles sucios.

Qué se verifica acá, ejecutando la función real sobre fixtures reales de disco:
  1. A/B del defecto: el mismo fixture rojo anidado → lógica vieja 0 candidatos,
     lógica nueva 1. Es la prueba de que el hallazgo era real.
  2. Esquema real del summary (`ok:false` + `failures`) → candidato con el fallo.
  3. Esquema real del reporte (`overall:FAIL` + `phases`) → UN candidato, no uno
     por fase, y la evidencia nombra la fase caída.
  4. Solo cuenta la última corrida: rojo viejo + verde nuevo → 0; verde viejo +
     rojo nuevo → 1 con el `run_id` nuevo (no los 184 rojos históricos del repo).
  5. Verde → 0 candidatos.
  6. Compatibilidad con el esquema viejo de las sondas (`all_ok`/`checks`).
  7. La sugerencia de reproducción apunta al gauntlet, no a `scripts/live/`.

Uso: python scripts/test_triage_evidence.py   (exit 0 = PASS, 1 = FAIL)
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import loop_triage  # noqa: E402

FALLOS: list[str] = []


def check(nombre: str, ok: bool, detalle: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + nombre + (f" — {detalle}" if detalle and not ok else ""))
    if not ok:
        FALLOS.append(nombre)


def escribir(p: Path, data: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")


def correr(raiz: Path) -> list[dict]:
    """Corre la señal REAL apuntándola al fixture."""
    previo = loop_triage.EVIDENCE_DIRS
    loop_triage.EVIDENCE_DIRS = [raiz]
    try:
        return loop_triage.sig_live_evidence_fail()
    finally:
        loop_triage.EVIDENCE_DIRS = previo


def logica_vieja(raiz: Path) -> list[dict]:
    """La implementación anterior, copiada tal cual: glob no recursivo + `all_ok`."""
    out = []
    for f in sorted(raiz.glob("*.json")) if raiz.exists() else []:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if data.get("all_ok") is False:
            out.append({"id": f"vivo-rojo-{f.stem}"})
    return out


SUM_ROJO = {"phase": "f2-core", "run_id": "20261021-000100", "calls": 26,
            "failures": ["f2-core: reposition_operators mueve de verdad"], "ok": False}
SUM_VERDE = {"phase": "f2-core", "run_id": "20261021-000100", "calls": 26,
             "failures": [], "ok": True}
REPORTE_ROJO = {"run_id": "20261021-000200", "overall": "FAIL",
                "phases": {"F1  Smoke": {"verdict": "PASS", "failures": []},
                           "F2  Core": {"verdict": "FAIL",
                                        "failures": ["reposition_operators mueve de verdad"]}}}
REPORTE_VERDE = {"run_id": "20261021-000200", "overall": "PASS",
                 "phases": {"F1  Smoke": {"verdict": "PASS", "failures": []}}}


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="triage_ev_"))
    try:
        print("1. A/B del defecto (summary anidado en rojo)")
        a = tmp / "ab"
        escribir(a / "20261021-000100" / "f2-core-summary.json", SUM_ROJO)
        check("la lógica vieja NO ve el rojo anidado (0 candidatos)", len(logica_vieja(a)) == 0,
              f"vio {len(logica_vieja(a))}")
        n = correr(a)
        check("la lógica nueva SÍ lo ve (1 candidato)", len(n) == 1, f"vio {len(n)}")

        print("2. Esquema real del summary (ok/failures)")
        check("un candidato con el texto del fallo",
              len(n) == 1 and n[0]["evidencia"] == SUM_ROJO["failures"],
              f"{n[0]['evidencia'] if n else 'sin candidatos'}")
        check("peso 5 (evidencia en vivo manda)", bool(n) and n[0]["peso"] == 5)
        check("el id lleva el run_id (huella por corrida)",
              bool(n) and n[0]["id"] == "vivo-rojo-20261021-000100-f2-core-summary",
              n[0]["id"] if n else "")

        print("3. Esquema real del reporte (overall/phases)")
        b = tmp / "rep"
        escribir(b / "20261021-000200" / "regression-report.json", REPORTE_ROJO)
        escribir(b / "20261021-000200" / "f1-smoke-summary.json", SUM_VERDE)
        escribir(b / "20261021-000200" / "f2-core-summary.json", SUM_ROJO)
        n = correr(b)
        check("UN solo candidato por corrida (el reporte agrega las fases)", len(n) == 1, f"vio {len(n)}")
        check("la evidencia nombra la fase caída",
              bool(n) and any("F2" in str(x) for x in n[0]["evidencia"]),
              str(n[0]["evidencia"]) if n else "")

        print("4. Solo la última corrida")
        c = tmp / "viejo_rojo_nuevo_verde"
        escribir(c / "20261020-235900" / "regression-report.json", REPORTE_ROJO)
        escribir(c / "20261021-000300" / "regression-report.json", REPORTE_VERDE)
        check("rojo viejo + verde nuevo → 0 (no 184 rojos históricos)", len(correr(c)) == 0)

        d = tmp / "viejo_verde_nuevo_rojo"
        escribir(d / "20261020-235900" / "regression-report.json", REPORTE_VERDE)
        escribir(d / "20261021-000400" / "regression-report.json", REPORTE_ROJO)
        n = correr(d)
        check("verde viejo + rojo nuevo → 1, con el run_id NUEVO",
              len(n) == 1 and "20261021-000400" in n[0]["id"],
              str([x["id"] for x in n]))

        print("5. Verde no genera nada")
        e = tmp / "verde"
        escribir(e / "20261021-000500" / "f2-core-summary.json", SUM_VERDE)
        escribir(e / "20261021-000500" / "regression-report.json", REPORTE_VERDE)
        check("PASS → 0 candidatos", len(correr(e)) == 0)

        print("6. Compatibilidad con el esquema viejo (sondas: all_ok/checks)")
        f = tmp / "sonda"
        escribir(f / "20261021-000600" / "probe-x.json",
                 {"all_ok": False, "checks": [{"name": "check_a", "ok": False},
                                              {"name": "check_b", "ok": True}]})
        n = correr(f)
        check("all_ok=false → 1 candidato con el nombre del check",
              len(n) == 1 and n[0]["evidencia"] == ["check_a"], str(n))

        print("7. Sugerencia de reproducción")
        check("una fase f2-core se reproduce con el gauntlet",
              loop_triage._comando_de("f2-core") == "python tools/gauntlet/run_regression.py",
              loop_triage._comando_de("f2-core"))
        check("el reporte también",
              loop_triage._comando_de("regression-report") == "python tools/gauntlet/run_regression.py")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FALLOS:
        print(f"FAIL: {len(FALLOS)} chequeo(s) — {', '.join(FALLOS)}")
        return 1
    print("PASS: 13/13 chequeos")
    return 0


if __name__ == "__main__":
    sys.exit(main())

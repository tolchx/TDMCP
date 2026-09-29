# Loop engineering del TDMCP — migración al fork tolchx (2026-09-29)

Registro de la migración del sistema de loop engineering desde el repo viejo
(`Touchdesigner_MCP/Main`, bridge propio en `127.0.0.1:44444`, retirado) al fork
`tolchx-TDMCP` (MCP oficial de Derivative en `127.0.0.1:13316/mcp` + capa offline `knowledge/`).

## Qué se migró

| Artefacto | Estado |
|---|---|
| `LOOP.md`, `loop-constraints.md`, `loop-budget.md`, `gate.yaml`, `STATE.md` | ✅ creados, adaptados al fork |
| `scripts/loop_triage.py` | ✅ migrado: señales → candidatos. `sig_tests` ahora corre `run_regression.py --quick`; `EVIDENCE_DIRS` → `tools/gauntlet/results/`; `sig_queue_drift` con guard; **`sig_client_log` retirado** (el log `tdmcp-client.log` era del bridge viejo y generaba falsos positivos de "timeout") |
| `scripts/loop_gate.py` | ✅ migrado: `run_tests` = `server.py --selftest` + `test_protocol.py` + `run_regression.py --quick` (exit 2 del gauntlet = entorno caído → salteado, no rojo) |
| `scripts/loop_promote.py` | ✅ migrado: briefs con los comandos del gauntlet; `pausado()` usa `STATE.md` de raíz; `ACCIONABLE` con `gauntlet-rojo` |
| `scripts/loop_worktree.py` | ✅ copiado (sin uso, ver LOOP.md) |
| `.freebuff_tasks/`, `docs/BACKLOG.md`, `loop-run-log.md`, `loop-ledger.json` | ✅ creados (semillas) |
| `.gitignore` | ✅ `knowledge/kb/`, `.freebuff_tasks/`, `tools/gauntlet/results/`, `loop-candidates.json`, `loop-ledger.json` |

## Readiness del loop

`python scripts/loop_triage.py --audit` → **100/100 — nivel L3** (antes: 58/100 L2, porque el
audit apuntaba a los artefactos del repo viejo).

## Crons de Hermes

| Loop | Cron | Cadencia | Tipo |
|---|---|---|---|
| Canario en vivo | `2070d33e1350` (ya existía) | 30 min | script `td_mcp_verify.py` → `knowledge/healthcheck.py` |
| Descubrimiento (triage) | `01760963eec3` | 4 h | script `td_mcp_loop_triage.py`, no_agent, silencioso si no hay candidatos |
| Ejecución (ciclo diario) | `b92f7702ebb1` | 20 min (gate de ventana limpia) | agente, `monitor=mcp_daily_gate.py`, workdir en el fork |

**Flujo del ciclo diario** (`b92f7702ebb1`): triage → promote → ejecutar ítem → verificar
(gauntlet) → documentar (contrato + skill + `docs/loop-run-YYYY-MM-DD.md`) → gate → commit/push
→ escribir `mcp_daily_done.txt`.

## Cómo correrlo a mano

```bash
cd C:/Users/Tolch/Documents/AI_Code/TDMCP/tolchx-TDMCP
python scripts/loop_triage.py              # descubrimiento (solo reporta lo nuevo)
python scripts/loop_triage.py --audit      # readiness (100/100)
python scripts/loop_promote.py --list      # candidatos + accionable vs decisión humana
python scripts/loop_gate.py --action commit --paths <archivos>   # gate mecánico
python tools/gauntlet/run_regression.py --quick     # regresión corta (F1+F2)
python knowledge/server.py --selftest      # self-test de la KB (offline)
```

## Ritual cuando se descubre algo nuevo

Ver `docs/td-lecciones-aprendidas-2026-09-29.md` §6 — el loop no improvisa: cada hallazgo se
verifica dos veces, se anota como contrato (`knowledge/contracts/VERIFIED_CONTRACTS.md`), se
lleva a la skill `td-*` y se deja la herramienta en `td_probe.py`.

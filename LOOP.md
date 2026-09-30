# LOOP.md — los loops que mantienen el TDMCP (fork tolchx)

Este archivo documenta **cómo se opera este repositorio** con loop engineering: qué loops
corren, con qué cadencia, en qué nivel de autonomía, qué estado escriben y cuándo le pasan
la pelota a Tolch. Es la semilla de los loops que mantienen el MCP.

Inspirado en [cobusgreyling/loop-engineering](https://github.com/cobusgreyling/loop-engineering)
(5 bloques + memoria; reportar → asistir → desatender). No se instaló su CLI: el loop es
nativo de Hermes. Lo que se copió es la disciplina de artefactos
(`loop-constraints.md`, `loop-budget.md`, `loop-run-log.md`, `gate.yaml`).

## Contexto: de dónde venimos

Antes (bridge propio en `127.0.0.1:44444` + Node 107 tools) el loop vivía en
`Touchdesigner_MCP/Main` con crons `4fc977b6a811` (ciclo diario), `2070d33e1350` (canario),
`9b14aa6fd344` (campaña soak). El transporte propio quedó **retirado**: ahora el lado vivo es
el **MCP oficial de Derivative** (`component/TDMCP.tox`, 26 tools, en `127.0.0.1:13316/mcp`) y
la capa offline es `knowledge/` (21 tools, stdio). Este fork es el que se auto-mejora.

## Los cinco bloques, mapeados a lo que tenemos

| Bloque | En este repo |
|---|---|
| Automatización / scheduling | crons de Hermes: **canario en vivo** (`2070d33e1350`, c/30 min), **triage** (c/4 h), **ciclo diario** (c/20 min con gate de ventana limpia) |
| Worktrees | ❌ no se usan (se trabaja sobre el árbol principal; el gate + juez externo mitigan) |
| Skills | ✅ `skills-hermes/td-*` (19) + `knowledge/contracts/VERIFIED_CONTRACTS.md` |
| Conectores (MCP) | ✅ MCP oficial en `127.0.0.1:13316/mcp`, `td-knowledge` offline, juez externo `jev`, `mnemosyne` |
| Sub-agentes maker/checker | ✅ **agente del ciclo** = implementer; **juez externo (`jev_audit_diff.py`) + `tools/gauntlet`** = verifier; el verifier NO marca su propio trabajo |
| Memoria / estado | ✅ **dueño único: `docs/BACKLOG.md`** (items + sección *Estado verificado*), `STATE.md`, `mcp_daily_done.txt`, `loop-run-log.md`, `loop-candidates.json`, `loop-ledger.json`, vault + Mnemosyne. `.freebuff_tasks/BACKLOG.md` es sólo un puntero al dueño |

## Loops activos

### 1. Verificación en vivo (canario) — L1, script, sin LLM
- Cadencia: cada 30 min (`2070d33e1350`, `td_mcp_verify.py`)
- Qué hace: `knowledge/healthcheck.py` — KB offline + 21 tools + MCP oficial respondiendo.
  Watchdog silencioso: si todo está bien no imprime nada; si falla, una línea.
- Complemento: `tools/gauntlet/run_regression.py` (suite completa, ~1.5 min) para
  aceptación end-to-end cuando TD está arriba.

### 2. Descubrimiento (triage) — L1, script, sin LLM
- Cadencia: cada 4 h (cron `TD-MCP · loop triage`)
- Comando: `python scripts/loop_triage.py`
- Qué hace: lee señales **reales** del repo (árbol sucio, drift de cola, suites en rojo,
  evidencia del gauntlet en rojo, items cerrados sin verificación en vivo, briefs rancios)
  y escribe **candidatos a item** con su evidencia en `loop-candidates.json`.
  Solo reporta los NUEVOS (dedupe por huella).
- Promoción: `scripts/loop_promote.py` convierte el candidato de mayor peso **no promovido**
  en item real (ambos BACKLOG) + brief en la cola si es accionable.
- **Esto es lo que hace que el MCP se auto-mejore.**

### 3. Ejecución — L2/L3, agente
- Cadencia: 1 corrida real por día (cron ciclo diario, con `mcp_daily_gate.py` esperando
  ventana limpia — Tolch no tiene la PC encendida a hora fija)
- Flujo: triage → promote → auditar lo que dejó el agente → correr gauntlet → juez externo →
  publicar (commit + push con gate) → anotar en `loop-run-log.md`
- Estado: `STATE.md`, `mcp_daily_done.txt`, `docs/BACKLOG.md`
- Handoff: diffs fuera del brief, decisiones de diseño, cualquier cosa que toque `component/*.tox`

### 4. Regresión del núcleo — on-demand
- Comando: `python tools/gauntlet/run_regression.py [--baseline ...] [--quick]`
- Cuándo: antes y después de actualizar el `.tox` oficial; o el ciclo diario si hubo cambios.

## Prioridad cuando dos loops chocan

Verificación en vivo → Ejecución (ciclo diario) → Descubrimiento.

## Gates y seguridad

- **Antes de publicar**: `python scripts/loop_gate.py --action commit --paths <archivos>`.
  Aplica `gate.yaml`: denylist (`component/*.tox` del oficial, `knowledge/kb/` derivada,
  secretos), `maxFiles`, `maxLines`, allowlist de auto-merge y la exigencia de suites verdes.
- **Juez externo**: el diff se audita con `jev` (trabajo real / corresponde al brief / debilita).
- **Humano**: push a `main` solo después de gate + juez. Commits locales libres.
- **Kill switch**: archivo `loop-pause-all` en la raíz o `loop: paused` en `STATE.md`.

## Nivel actual y qué falta para L3 pleno

- Hoy: **L2 sólido** (reporta, ejecuta, verifica con gauntlet + juez, publica con gate).
- Para L3 pleno falta: (a) verificación de comportamiento en vivo dentro del propio loop de
  cierre (hoy la corre el gauntlet, que el ciclo puede correr, o Tolch a mano); (b) cap de
  intentos con ledger; (c) aislamiento por worktree si el árbol se ensucia.

## Cómo correrlo a mano

```bash
python scripts/loop_triage.py            # descubrimiento (solo reporta lo nuevo)
python scripts/loop_triage.py --audit    # puntaje de preparación del loop (0-100) + gaps
python scripts/loop_promote.py --list    # candidatos y si son accionables o decisión humana
python scripts/loop_gate.py --action commit --paths docs/BACKLOG.md
python tools/gauntlet/run_regression.py --quick   # regresión corta (F1+F2)
python knowledge/server.py --selftest    # self-test de la KB (offline)
```

---
*Este archivo es documentación y a la vez la semilla de los loops que mantienen el MCP.*

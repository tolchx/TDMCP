# loop-budget.md — presupuesto y límites del loop del TDMCP (fork tolchx)

> El agente lee este archivo al empezar cada corrida y escribe su consumo al terminar
> (en `loop-run-log.md`). Sin esto, un loop es una cuenta abierta.

## Límites diarios

| Loop | Cada | Max corridas/día | Intento max/item |
|------|------|------------------|------------------|
| Ciclo diario (agente + gauntlet + gate + push) | 20 min (gate de ventana limpia) | 1 corrida real/día | 3 |
| Triage de descubrimiento (script, sin LLM) | 4 h | 6 | — |
| Canario en vivo (healthcheck, script) | 30 min | 48 | — |

## Costo
- El costo dominante son los tokens del agente del ciclo diario (audita + decide) y el juez
  externo. Regla práctica: **1 item grande por día**, no cinco chicos; el contexto de la cola
  se paga una vez.
- Los loops de script (triage, canario) son casi gratis: no usan LLM. Por eso el descubrimiento
  va en script y el juicio va en agente.
- El gauntlet completo (~1.5 min) y el `--quick` (~15 s) corren dentro del ciclo diario, no
  en cada tick: el canario de 30 min solo corre el healthcheck (barato, sin TD-heavy).

## Al exceder el presupuesto
1. Pausar el ciclo diario (`cronjob pause <job_id>`).
2. Anotar el evento en `loop-run-log.md`.
3. Reportarle a Tolch con el gasto y la causa.

## Kill switch
- Crear el archivo `loop-pause-all` en la raíz del repo, o poner `loop: paused` en `STATE.md`.
- Los scripts (`loop_triage.py`, `loop_gate.py`, `loop_promote.py`) lo respetan y salen con
  código 4.
- Para reanudar: borrar el archivo (o la línea) y anotarlo en `loop-run-log.md`.

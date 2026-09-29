# BACKLOG — items del TDMCP (fork tolchx)

(El triage del loop los agrega automáticamente.)

- [x] 1. Hallado por el loop (triage automático, id `arbol-sucio`, huella `63cc9331b8a0d0a5`):
  9 archivos modificados sin commitear. **CERRADO 2026-09-29** (ciclo diario, intento 1): eran **un
  solo trabajo coherente**, no residuo — el refactor "un solo dueño de la medición" (`td_chain.py`
  inyectado por `td_probe.chain_source`, `Gauntlet.offline()` como único wrapper de td-knowledge,
  `check_single_home.py` como regla ejecutable). Verificado con gauntlet completo **PASS**
  (`results/20260929-032041`), `td_probe` 5/5 y `check_single_home` 0 violaciones; gate **ALLOW**;
  commit `bdee341` (árbol limpio al cerrar). Evidencia: `docs/loop-run-2026-09-29.md`.
  Razón del cierre: un árbol sucio contamina al juez externo y re-dispara el candidato cada día.

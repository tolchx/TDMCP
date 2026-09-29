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

- [ ] 2. **El gate no corre `check_single_home.py`: un archivo que re-implementa la medición pasa
  igual.** Evidencia real (2026-09-29, ciclo diario): `python tools/gauntlet/check_single_home.py` →
  `VIOLACION build_pop_fountain.py:136: def settle(n=6):` · `1 violaciones` · exit 1, con ese archivo
  ya publicado en `6cab054` y el gate habiendo dado ALLOW (sus suites son `server.py --selftest`,
  `test_protocol.py` y `run_regression.py --quick`; el guard no está cableado). Qué hacer: cablear
  `check_single_home.py` como parte de las suites que exige `requireGreenTests` (`gate.yaml` /
  `loop_gate.run_tests`) y cerrar la violación de `build_pop_fountain.py` (usar `td_probe.chain_source`
  en vez de su `settle()` inyectado a mano). Detectado por: el ciclo diario, verificando el árbol
  publicado.

- [ ] 3. **El cierre del ciclo commitea con `git add -A` y publica WIP de un escritor concurrente.**
  Evidencia real (2026-09-29): el commit de cierre `6cab054` barrió `tools/gauntlet/build_pop_fountain.py`
  (nuevo, 179 líneas, mtime 03:24:01) y `tools/gauntlet/td_probe.py` (+30) que **no** escribió la
  corrida: los escribió otro agente/sesión en el **mismo working tree** (sus corridas quedaron en
  `results/20260929-032233/032405/032429`). El gate no lo vio porque sólo juzga los paths que se le
  pasan. Qué hacer: cerrar con `git add <paths explícitos>` (nunca `-A`) y abortar el cierre si
  aparecen archivos nuevos/modificados que la corrida no tocó. Detectado por: el ciclo diario
  (comparando `git status` antes/después del add).

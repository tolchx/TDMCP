# loop-constraints.md — reglas VINCULANTES del loop del TDMCP (fork tolchx)

> Todo agente que corra un loop sobre este repo lee este archivo ANTES de tocar nada.
> Lo de acá NO se negocia: si una regla impide terminar una tarea, se escala, no se ignora.
> El gemelo mecánico es `gate.yaml` (lo aplica `scripts/loop_gate.py`).

## Alcance
- El loop SOLO toca este repo (`C:/Users/Tolch/Documents/AI_Code/TDMCP/tolchx-TDMCP`).
- Un item por corrida. Nada de "de paso arreglo esto otro": eso es otro item.
- Prohibido tocar `component/TDMCP.tox` (el núcleo oficial viaja con su SHA-256), los `.toe`
  de Tolch, `Config/System` de TouchDesigner y la UI global de TD. Si una tarea lo requiere,
  se escala con el diff exacto propuesto.

## Verdad
- Prohibido simular una verificación en vivo. Si TD está DOWN, se dice "pendiente por entorno"
  y el item NO se cierra. Nunca se escribe "verificado" sobre algo que no se corrió.
- Ninguna tool nueva se cierra sin un test que EJECUTE lo que genera (no string-matching).
- Toda cifra que se publique sale de correr el comando, no de la memoria del agente.
- **La salida del build no es la verdad**: releer siempre después de `settle()`, y verificar
  imágenes con PIL, no con decoders caseros (ver `knowledge/contracts/VERIFIED_CONTRACTS.md`).

## Código
- Antes de proponer un fix: `python knowledge/server.py --selftest`,
  `python knowledge/test_protocol.py`, y si TD está arriba `python tools/gauntlet/run_regression.py --quick`.
  Se pegan los conteos reales.
- Prohibido deshabilitar, saltear o "arreglar" un test para que CI dé verde. Un test en rojo
  es un hallazgo, no un obstáculo.
- Un fix por corrida. Refactor no relacionado = rechazo.
- Máximo 3 intentos por item. Al cuarto, se escala con el historial (loop-ledger.json).
- Nada de `raise SystemExit` ni efectos de import en código que corre DENTRO de TD
  (mata el script del server y el llamador recibe "sin respuesta" en vez del error).

## Secretos y datos de Tolch
- Nunca commitear tokens, claves, rutas absolutas de la máquina de Tolch en código que se
  entrega a terceros, ni datos personales.
- La KB derivada (`knowledge/kb/`) y los `.tox` NO se versionan; lo que se versiona es el
  resumen en `docs/` y los contratos en `knowledge/contracts/`.

## Comunicación
- Se le dice a Tolch que se va a hacer antes de hacerlo, y que se hizo después (con la evidencia).
- `push` solo después del gate y con el visto bueno del juez externo. Los commits locales
  son libres; el push a `main` no.
- Nunca cerrar un item sin evidencia pegada (comando + salida).

## Presupuesto
- Límites en `loop-budget.md`. Al 80% del cupo diario, el loop pasa a modo SOLO REPORTE.
- Si existe el archivo `loop-pause-all` en la raíz (o `STATE.md` dice `loop: paused`), el loop
  sale inmediatamente sin hacer nada.

# gauntlet/ — regresión del TDMCP oficial en un solo comando

Suite de verificación del núcleo oficial (`.tox`) + skills: smoke, API core, 5 niveles
de construcción dentro de componentes y un A/B informativo con/sin skills.
Desarrollada el 2026-09-28 (ver `docs/tdmcp-gauntlet-2026-09-28.md`); ahora es el
**test de regresión** que corre antes y después de cada actualización del `.tox`.

## Requisito

TouchDesigner abierto con el componente TDMCP **Active** en `127.0.0.1:13316`
(exporta `TDMCP_URL` para otro puerto/host).

## Uso

```bash
# suite completa (~1.5 min), crea results/<run_id>/
python tools/gauntlet/run_regression.py

# primera vez o tras una actualización del .tox: fijar el baseline
python tools/gauntlet/run_regression.py --tag baseline

# después de actualizar el .tox: correr con diff contra el baseline
python tools/gauntlet/run_regression.py --baseline tools/gauntlet/results/<run-baseline>/regression-report.json

# variantes
python tools/gauntlet/run_regression.py --quick        # solo F1+F2 (~15 s)
python tools/gauntlet/run_regression.py --skip-ab      # sin F4
python tools/gauntlet/run_regression.py --pin-version 1.1.55   # exigir versión concreta
```

## Veredicto

Por fase (`PASS` / `FAIL` / `INFO`) y global; exit code `0` PASS, `1` FAIL,
`2` entorno caído (TD no abierto / `.tox` inactivo). `F4 A/B` es **informativa**:
los graders "naive" fallan by design (miden la diferencia de construir sin skills).

El reporte (`regression-report.json` + `.md`) registra el entorno de la corrida:
versión del server, build de TD, catálogo de tools. El diff contra baseline marca
tools nuevas/quitadas, cambios de versión/build y fases que cambiaron de veredicto.

## Contenido

| Archivo | Fase |
|---|---|
| `run_regression.py` | runner de un comando |
| `gauntlet_client.py` | cliente MCP con logging, latencias, graders, `GAUNTLET_RUN_ID` |
| `f1_smoke.py` | F1 handshake + 26 tools + sanity CRUD |
| `f2_core.py` | F2 API core + wrappers live de `knowledge/live.py` |
| `f3_n1_top.py` … `f3_n5_render.py` | F3 niveles de construcción |
| `f3_n6_glsl_pop.py` | F3.6 GLSL POP: `glsl_analyze` (offline) dicta los params, build en vivo y verificación GPU→CPU por `poptoCHOP` |
| `f4_ab.py` | F4 A/B con vs sin skills |
| `build_particle_fx.py` | build + verificación de `/particle_swirl` (efecto de partículas POP GLSL): shader validado offline, nube de puntos, animación por `poptoCHOP`, capturas PNG |
| `verify_visual.py` / `make_preview.py` | métricas de los PNG del build (PIL) y HTML de preview con las imágenes embebidas |
| `td_chain.py` | **el programa que se inyecta en TD** por `execute_code`: `settle()`, `px()` y `render_is_ours()`, con `ROOT` fijado por `chain_source()`. Es código importable, así que se prueba sin TD con un `op`/`px` de mentira |
| `td_probe.py` | los helpers del **host**: `chain_source(root)` (serializa `td_chain.py` con `ROOT` fijo), `set_and_verify()` (escribir-y-releer, contrato C4), `stats_of()` / `png_stats()` / `grid_cells()` (PIL) y `selftest_render_ownership()` (contra TD: prueba que la guardia puede **FALLAR**). `python td_probe.py` corre los chequeos locales |
| `check_single_home.py` | hace ejecutable la regla del único dueño: exit 1 si un consumidor redefine `settle` / `px` / `render_is_ours` en vez de importarlos de `td_probe`. Los builds y `verify_visual` importan de acá: no copies versiones paralelas. Lo corre el gate, junto con `td_probe.py`, como paso de `scripts/loop_gate.py::run_tests` |
| `results/<run_id>/` | logs por fase (`.jsonl`), summaries, PNGs, reportes |

## Antes de improvisar: leé los contratos

Los comportamientos que no están en ninguna doc oficial (cook lag de 1+, caché de geometría del
renderTOP, flags del terminal del chain, `pointspriteMAT` en píxeles, contratos de las tools) están
en **`knowledge/contracts/VERIFIED_CONTRACTS.md`**, servibles offline con la tool `contracts` de
`td-knowledge` (`section='cook_lag'`, `list=true`, …). Al descubrir algo nuevo, agregalo ahí (y a la
skill correspondiente): el ritual está en `docs/td-lecciones-aprendidas-2026-09-29.md` §6.

## Estado de sandboxes

Cada fase crea y borra sus sandboxes en root (`/gauntlet_*`, `/msmod*`, `/pwm_lfo`).
Si una fase muere a mitad, el sandbox queda — la limpieza previa de cada fase lo
borra en la próxima corrida. Dejar `results/` sin trackear si molesta en git.

## Límites conocidos

- **F3.2 (`f3-n2-audio-clock`) no es determinista (medido 2026-10-02).** El check
  `"par animado por expresion cambia en el tiempo"` (`f3_n2_audio_clock.py:102`) compara dos lecturas
  de `fondo.par.colorr.eval()` separadas 1.2 s y exige `delta > 1e-4`; su señal de movimiento incluye
  `0.15*abs(absTime.seconds % 2 - 1)`, sensible a la fase absoluta del reloj. Puede dar **rojo falso**:
  suite `results/20261002-000742` → FAIL `delta=2.6e-07`; la misma fase sola (`20261002-000913`) y la
  suite siguiente (`20261002-000922`) → PASS. **Ante un FAIL global cuyo único fallo sea F3.2,
  reintentar la fase antes de declarar regresión.** Pendiente: robustecer el check (`docs/BACKLOG.md` ítem 6).

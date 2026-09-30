# Lecciones aprendidas construyendo en TouchDesigner con TDMCP

> ⚠️ **AVISO (pase 2, 2026-09-29).** La "lección" de esta sesión sobre POP→render
> (`deleteprims` = nube que dibuja) resultó **falsa**: `deleteprims` deja 0 primitivas y el render
> sale **negro**. La verificación se apoyaba en el `torus1` que el `geometryCOMP` auto-crea. Leé
> primero `docs/td-curl-field-2026-09-29.md` y la receta corregida en
> `skills-hermes/td-pop-render-pipeline/SKILL.md`. El estado verificado del toolkit (qué suites
existen y con qué corrida) vive en **`docs/BACKLOG.md` → *Estado verificado***, no acá.

**Sesiones:** 2026-09-28 (gauntlet de migración al TDMCP oficial) y 2026-09-29 (efecto
`/particle_swirl` de POPs GLSL).
**Entorno:** TouchDesigner 2025.32460 · TDMCP oficial 1.1.55 · Windows 11 · Python 3.12/3.13.
**Método:** todo lo de abajo se probó contra TD vivo; cada contrato tiene su evidencia, no su
opinión. Los contratos están destilados en `knowledge/contracts/VERIFIED_CONTRACTS.md`
(servible offline con la tool `contracts`) y repartidos en las skills `td-*`.

Este documento es el **registro de lo aprendido**; los contratos son la **fuente operativa**; las
skills son lo que carga un agente antes de construir. Cuando algo nuevo se verifica, se anota en los
tres lugares (ver §6, el ritual).

---

## 1. Lo que se construyó y qué se verificó

| Sesión | Entregable | Verificación |
|---|---|---|
| 2026-09-28 | Migración al TDMCP oficial + gauntlet F1–F6 (offscreen, core, TOP/CHOP/DAT/COMP, GLSL POP) | 8 fases PASS; informe `docs/tdmcp-gauntlet-2026-09-28.md`; 7 issues upstream en `docs/issues-filed/` |
| 2026-09-29 | `/particle_swirl` — enjambre de POPs GLSL animado (`spherePOP → topointprims → glslPOP → nullPOP`, `pointspriteMAT` aditivo, `renderTOP`) | run verde 35/35 (`tools/gauntlet/build_particle_fx.py`), animación probada por `poptoCHOP`, captura PNG decodificada con PIL. ⚠️ El "35/35" de entonces medía el auto-torus; la receta se corrigió en el pase 2 |

## 2. Las cinco lecciones que más costaron (y cómo evitarlas)

### 2.1 El cook lag: medir antes de asentar es medir el pasado
Los cambios de **shader DAT** y **uniforms `vec*`** se aplican **un cook después**.
Evidencia: `P[id] = pos*2.0` en el DAT no cambió P (seguía 1.0257); al **restaurar** el DAT, el
siguiente cook mostró **2.0513**. Ese retraso hizo que durante horas se creyera que los uniforms no
estaban conectados. **Regla:** `settle()` (cocinar `geo → glsl → null → ren` 4 veces) y recién leer.

### 2.2 El render no es un termómetro de datos
El `renderTOP` reacciona a **material** (color) y a **estructura** (rewire, flags, rebind), pero no
re-sube geometría POP ante cambios de datos (uTime, uSwirl, `radx`). **Regla:** datos y animación se
verifican por `poptoCHOP` (GPU→CPU); los píxeles responden "¿hay algo dibujado?" y "¿de qué color?".

### 2.3 Superficie ≠ nube de partículas
`spherePOP` con defaults = **252 pts / 500 prims** y el render dibuja un blob sólido: eran las
primitivas de la superficie, no un fallo del material. Lo que lo arregla es
`convertPOP(convert='topointprims')` → **252 pts / 252 prims** (una primitiva de punto por punto).
Ojo: `deleteprims` deja **0 prims** y el render sale **negro** — ver el aviso de arriba y C2.

### 2.4 El reloj puede estar parado (y eso no es un bug del efecto)
En remoto, `absTime.seconds` **no avanza** dentro de un `execute_code`; `absTime` no tiene `.play` y
`op('/')` no tiene pars `play`/`frame`/`rate` en 2025.32460 (el reloj es el timeCOMP `/local/`).
**Regla:** verificá animación **escalonando el uniform** y midiendo por poptoCHOP; en la GUI con play
la expresión `absTime.seconds` anima sola.

### 2.5 Verificar también se equivoca
Un decoder de PNG casero (filtros Sub/Paeth a medias) reportó **728 px "ámbar"** donde PIL ve
**4398 px azul/cian** en la misma imagen; y un check de "movimiento" comparaba bboxes con offsets de
celda, declarando distintos cuatro fotogramas idénticos. **Regla:** PIL para imágenes, comparaciones
con coordenadas locales, y desconfiar de un PASS que no se puede explicar.

## 3. Contratos verificados (resumen; detalle en `contracts`)

- **Render/pipeline:** el geometryCOMP dibuja el stream del **terminal** con `display=true` **y**
  `render=true`; `renderTOP` (TOP, no `renderCOMP`) con bindings OP por `execute_code`; la luz es el
  par **`lights`** (plural).
- **POPs:** `numPoints`/`numPrims` son **método** en POPs y **propiedad** en SOPs; `convertPOP`
  **`topointprims`** para partículas (`deleteprims` deja 0 prims = render **negro**); `ParMode` es
  enum (`str`, no `int`); clases `spherePOP`/`sphereSOP`.
- **glslPOP:** `outputattrs` para atributos re-escritos (si no, `undeclared identifier`); Create
  Attributes con `attr0name='custom'` lowercase + `attr0customname`/`numcomps`; bindear `computedat`
  **antes** de setear la secuencia `vec` (enlazar la resetea).
- **pointspriteMAT:** `constatten` + **`pointsize`** (default **1.0** ≈ 2 px; `attensizenear` queda
  **inerte** con `attenpscale=0`); blending aditivo `sa/one`; `colorr/g/b` multiplica el `Cd` del punto.
- **Tools TDMCP:** `set_parameters` = solo constantes y **puede no aplicar un par respondiendo ok**
  (releer siempre); `annotation` usa `comment`; `edit_custom_parameters` con `{path, page, add:[...]}`;
  `edit_operator` renombra con `name` y clona con `copy_to`.
- **Scripts de build:** con `if __name__ == "__main__":` o importarlos ejecuta el build entero (y su
  `sys.exit()` mata al importador) — pasó tres veces.

## 4. Herramientas que quedaron (reutilizables)

| Artefacto | Para qué |
|---|---|
| `tools/gauntlet/td_chain.py` | el programa que se **inyecta** en TD: `settle()`/`px()`/`render_is_ours()`. **Dueño único** de la medición — `check_single_home.py` lo hace cumplir y el gate lo corre |
| `tools/gauntlet/td_probe.py` | los helpers del **host**: `chain_source(root)` (serializa `td_chain.py` con `ROOT` fijo), `set_and_verify()` (escribe-y-relee), `stats_of`/`png_stats`/`grid_cells` (PIL), `selftest_render_ownership()` |
| `tools/gauntlet/build_particle_fx.py` | build + verificación del efecto; re-ejecutable; deja `/particle_swirl` de pie |
| `tools/gauntlet/build_pop_curlfield.py` | segunda red POP (curl-noise) y playtest de la receta, con el experimento `deleteprims` vs `topointprims` |
| `tools/gauntlet/verify_visual.py` | decodifica los PNG del build (frame + grid) con PIL y reporta métricas |
| `tools/gauntlet/make_preview.py` | HTML de preview con los PNG embebidos |
| `tools/gauntlet/gauntlet_client.py` | cliente MCP del gauntlet (log por fase, `exec_code` con marcador) |
| `knowledge/contracts/VERIFIED_CONTRACTS.md` + tool `contracts` | contratos servibles sin TD abierto |
| skills `td-pop-render-pipeline`, `td-live-verification` | la receta y la metodología, cargables por un agente |

## 5. Cómo se conecta con lo que ya existía

- El **gauntlet** (`tools/gauntlet/run_regression.py`, fases F1–F6) es la red de seguridad de las
  tools; el build de efectos es ahora un caso de uso con verificación propia.
- Las **skills Hermes** (`skills-hermes/td-*`) son la capa que un agente carga al construir; las
  nuevas (`td-pop-render-pipeline`, `td-live-verification`) cubren el hueco que quedó: cómo hacer que
  un efecto se **dibuje** y cómo **medir sin engañarse**.
- La **KB offline** (`knowledge/`) sigue siendo la capa sin TD; ahora también sirve los contratos
  verificados, que es información que ninguna doc oficial tiene (porque es empírica).

## 6. Ritual para que cada prueba mejore el sistema

Cuando una sesión descubre algo (un contrato nuevo, un par que no se aplica, un límite del entorno):

1. **Verificalo dos veces** con evidencia numérica (medición antes/después, PNG decodificado, valor
   releído). Sin evidencia, es una hipótesis: anotala como tal.
2. **Anotalo como contrato** en `knowledge/contracts/VERIFIED_CONTRACTS.md` con: síntoma → contrato →
   cómo se verificó. Es el único lugar que debe estar completo y citable.
3. **Llevá el contrato a la skill correspondiente** (una línea con el síntoma, no la teoría) y, si es
   un tema nuevo, creá una skill `td-*` (patrón: `Use when …` + secciones cortas + pitfalls).
4. **Dejá la herramienta**: si lo que aprendiste se puede automatizar, agregalo a `td_chain.py` (si se
   inyecta en TD) o a `td_probe.py` (si mide desde el host) — no a una copia local: el script de la
   fase importa, y `check_single_home.py` falla si lo re-implementa.
5. **Registrá la sesión** en un `docs/*-YYYY-MM-DD.md` con el run id de la evidencia, y ampliá
   `FORK-NOTES.md` si cambió el inventario del fork.
6. **Corré la verificación de la capa**: `python knowledge/server.py --selftest` y
   `python knowledge/test_protocol.py` (KB) y, si tocaste tools, la fase del gauntlet que cubre ese
   dominio.

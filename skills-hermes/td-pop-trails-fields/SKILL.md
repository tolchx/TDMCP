---
name: td-pop-trails-fields
description: "Use when building motion trails (trailPOP) or animated 4D noise fields (noisePOP t4d) over POPs. Recetas verificadas de /pop_streams y /pop_field: cadena, parámetros reales del build y pitfalls de medición."
---

> **Adaptación Hermes.** Estas skills son del repo oficial `TouchDesigner/TDMCPSkills`
> y asumen el MCP oficial corriendo en TD. En Hermes las 26 tools del oficial se
> llaman **`mcp_tdmcp_<tool>`** (ej. `get_help` → `mcp_tdmcp_get_help`,
> `list_operators` → `mcp_tdmcp_list_operators`); los nombres "pelados" que
> aparecen en el texto son de Claude Code/Codex: traducilos con ese prefijo.
> Cargá **`td-general` primero** en cualquier tarea de TouchDesigner.

> **Verificado en vivo (2026-09-29, TD 2025.32460 + TDMCP 1.1.55).** Recetas extraídas de dos
> redes construidas y verificadas en frío: **`/pop_streams`** (estelas) y **`/pop_field`**
> (campo 4D). Qué corrida verificó cada una: `docs/BACKLOG.md → Estado verificado` (dueño único).
> Contratos completos con evidencia: **C8** y **C9** de `knowledge/contracts/VERIFIED_CONTRACTS.md`
> (tool offline `contracts`). La estructura de render (geometryCOMP, auto-torus, flags del
> terminal, material, gradables) la da **`td-pop-render-pipeline`** — acá sólo lo específico de
> trails y campos.

# Estelas (trailPOP) y campos 4D animados (noisePOP t4d)

Dos formas de mover puntos sin escribir shaders: el **trail** re-hornea historial de posición
(estelas), el **campo 4D** desplaza puntos con ruido cuyo tiempo se escala a mano. Ambos terminan
en `convertPOP(convert='topointprims')` + pointsprite (sin primitivas de punto NO dibujan).

## Receta A — estelas

Cadena dentro del `geometryCOMP` (estructura geo/cam/light/ren/check: `td-pop-render-pipeline`):

```
circlePOP (radx=2.2, rady=0.1, divs=256)  →  trailPOP (length=24)  →
noisePOP (mode='quality', type='simplex3d', amp=0.25, curl3d=True)  →
convertPOP (convert='topointprims')  →  nullPOP 'null_render' (display+render)  +  pointspriteMAT
```

Pars reales del build (releídos, NO los que sugiere `get_help`):

| nodo | par | valor | nota |
|---|---|---|---|
| circlePOP | `radx`/`rady` | 2.2 / 0.1 | `rad` a secas no existe en este nodo; `divs` = puntos del anillo |
| trailPOP | `length` | 24 | ⚠️ es TIEMPO de estela, no "cantidad de segmentos": `lengthunit` ∈ {seconds, frames} (default seconds) |
| trailPOP | `reset` | pulse | `trail.par.reset.pulse()` re-hornea la estela desde cero |
| noisePOP | `mode` | `quality` | menú real {performance, quality} — NO "turb" (es el label del get_help) |
| noisePOP | `type` | `simplex3d` | menú real {perlin,simplex}×{2d,3d,4d} |
| noisePOP | `amp`, `curl3d` | 0.25, True | el curl desplaza los puntos por el campo |
| convertPOP | `convert` | `topointprims` | OBLIGATORIO también para trails: 1 prim/punto |

> **Auditoría de la receta oficial** (`particle-system-pop` de la KB, 2026-09-29): de sus
> sugerencias para el trailPOP, **sólo `length` existe**. **Mienten** (no existen en el build):
> `velocityscale`, `color1r/g/b`, `color2r/g/b`. El trailPOP del build tiene 37 pars y NINGUNO de
> color/fade/opacity/tint — el color de las estelas lo pone el **material** (pointsprite
> `colorr/g/b`), no el nodo. Otros pars reales útiles: `inc`/`incunit`, `maxls`, `ageattr`,
> `attrname`/`attrmatch` (trail por atributo), `oldestpointfirst`, `closed`, `fillmissedframes`,
> `surftype` (semántica no auditada aún). La misma receta también inventa pars para noisePOP
> (`amplitude`/`period`/`harmonics`: el real es `amp`) y spherePOP (`radius`: es `rad` XYZW).

### El trail ACUMULA el campo (`trail_moves_points`) [V]

El trailP re-hornea los samples acumulando el desplazamiento a lo largo de la estela: los puntos
nuevos arrancan del anillo, pero el historial quedó donde lo dejó el campo. Con `amp=0.25` el
enjambre migra del anillo a P-centro ≈ (7, 7, 7). No es un bug: es la definición de estela.
Consecuencias medidas:

1. **La cámara NO va al origen** (`cam_follows_data`): centrarla en el **centroide de P** medido
   por `poptoCHOP` (+distancia). Con cámara default (0,0,5) y P-centro (7,7,7): **0 px**; con la
   cámara al dato: 4315 px (misma red, mismo frame).
2. **El min/max de P es insensible** para verificar animación (cada punto se mueve distinto):
   compará **el P de UN punto** (`inspect_values`, `max_points=1`) antes/después de escalar la
   palanca — y **`trail.par.reset.pulse()`** antes de re-medir, para que la estela re-hornee con
   el campo nuevo.

## Receta B — campo 4D animado SIN simulación

Cadena:

```
torusPOP (radx=rady=2.2, scale=0.55)  →  sprinklePOP (numpoints=3000, seed=11)  →
noisePOP (type='simplex4d', amp=0.4, curl3d=True, t4d=0→3.5)  →
convertPOP (topointprims)  →  nullPOP 'null_render'  +  pointspriteMAT
```

- **`t4d` (tiempo del ruido) sólo mueve puntos si `type` es 4D** (`simplex4d`/`perlin4d`):
  medido con `simplex3d` + t4d 0→3.5, el P del punto era **idéntico**; con `simplex4d` cambió
  (`t4d_needs_4d_type`). Es la forma de animar un campo sin simulación ni reloj: escaloná `t4d`
  y medí por punto.
- **`torusPOP`**: `rad` es XYZW (`radx`/`rady`); el grosor del tubo NO es `radz`: es **`scale`**
  (`torusPOP_rad`).
- `sprinklePOP.numpoints` muestrea la superficie que le entra (3000 pts); `seed` hace el
  muestreo reproducible.

## Animación por números (el reloj no corre en `execute_code`)

Dentro de una llamada `execute_code` NADA avanza (C1/clock_stopped): el ruido no "anima solo" ni
el trail acumula mientras esperás. Patrón de verificación:

1. `inspect_values` del punto 0 → snapshot A.
2. Escaloná la palanca temporal: `t4d` (campo 4D), `amp`/`offset` (curl), o la fuerza si hay sim.
3. Si hay trail: `trail.par.reset.pulse()` antes de re-medir.
4. `inspect_values` del punto 0 → snapshot B; assert `A != B`.

El min/max de P por `poptoCHOP` sirve para desplazamientos **colectivos** (p. ej. la caída de
una simulación al escalar gravedad), no para campos que mueven cada punto distinto.

## Pitfalls

- **`noisePOP.noisesize` es writeonly** [V*]: lo escribas como lo escribas (`set_parameters` o
  `execute_code`), `eval()` no cambia. El valor de atasco **varía por contexto** (`'2'` en
  `/pop_streams`, `'3'` en otra red): el contrato es "NO aplica lo escrito", no "queda en 2".
  La escala default sirve para el look; assertá que no cambió, no un valor fijo.
- **`ren.par.geometry` es multi-valor (LISTA)** [V]: crear OTRO geometryCOMP (p. ej. una prueba)
  lo **agrega** al render y ambos dibujan. Reasigná `ren.par.geometry = geo` en cada build y
  borrá los COMP de prueba (`renderTOP_geometry_is_a_list`).
- **`wiring` falla si el destino declara 0 inputs** [V] (`"vel has 0 input(s), to_index=0 out of
  range"`): cadena POP lineal, un input por nodo, `to_index=0`, sin nodos transformadores sin
  input (`POP_wiring_inputs_declarados`).
- **El filtro `c.name.startswith('P')` sobre `poptoCHOP.chans()` toma de más**: los canales
  incluyen `P_0/1/2` pero también `PartVel_*`, `PartId`, `PartAge`, `PartForce_*`. Usá la lista
  **exacta** de canales — un prefijo suelto mezcló posición con velocidad/ids y sesgó una
  medición de cámara (detalle en C10).
- **Trails sobre simulación**: el `particlePOP` necesita su **loop de feedback cerrado**
  (rama a un `nullPOP` + par `targetpop`) o la integración se descarta y las estelas no siguen
  nada. Receta y evidencia: C10 (`particle_feedback_loop`) en
  `knowledge/contracts/VERIFIED_CONTRACTS.md` y `docs/BACKLOG.md → Proyectos POP`.
- **Memoria del trail**: `length` está en **unidades de tiempo** (`lengthunit`: seconds/frames),
  no en puntos — el buffer escala con el tiempo de estela × puntos. La receta oficial que habla
  de "trail segment count" miente en la semántica; sus pars de color/velocidad no existen (ver
  auditoría arriba).

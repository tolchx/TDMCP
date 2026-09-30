---
name: td-pop-family
description: "Use when building GPU point operations. Redes POP: partículas, geometryCOMP, feedback, fuerzas, instancing."
---

> **Adaptación Hermes.** Estas skills son del repo oficial `TouchDesigner/TDMCPSkills`
> y asumen el MCP oficial corriendo en TD. En Hermes las 26 tools del oficial se
> llaman **`mcp_tdmcp_<tool>`** (ej. `get_help` → `mcp_tdmcp_get_help`,
> `list_operators` → `mcp_tdmcp_list_operators`); los nombres "pelados" que
> aparecen en el texto son de Claude Code/Codex: traducilos con ese prefijo.
> Cargá **`td-general` primero** en cualquier tarea de TouchDesigner.

---

# POP Networks

GPU-accelerated point operations. POPs replace SOPs for 3D geometry with massively parallel GPU compute. See `reference.md` for operator decision tree and attribute reference.

## Core Concepts

- **Points with attributes**: P (position), N (normal), Color, Tex, custom
- **GPU-resident**: all data stays on GPU, downloading to CPU causes stalls
- **Memory model**: unmodified input attributes pass by reference (zero-copy)
- **Points alone don't render** — need Point Primitives (set Connectivity on generators)
- **Rendering**: POPs in geometryCOMPs, rendered by renderTOP. MATs read POP attributes
- **Data sourcing**: POPs can exist in any COMP (baseCOMP, etc.) for data extraction without rendering
- **GPU→CPU cost**: `poptoCHOP` and `poptoDAT` copy data from GPU to CPU — can be heavy for large point counts

## geometryCOMP Setup

1. Create geometryCOMP
2. **Delete auto-created torus** immediately
3. Build POP chain inside, end with nullPOP
4. Set `display=true render=true` on output nullPOP
5. Material: place MAT inside geometryCOMP, reference as `./mat_name`. See `td-mat-family` skill
6. For instancing: see `td-geometry-instancing` skill

### Verificado en vivo (2026-09-29): qué hace que un POP se DIBUJE

Contratos probados contra TD 2025.32460 con evidencia numérica. Receta completa y gradables en la
skill **`td-pop-render-pipeline`**; detalle en `knowledge/contracts/VERIFIED_CONTRACTS.md` (C2).

- **Lo que dibuja son las PRIMITIVAS** — `spherePOP` con defaults = 252 pts / **500 prims**
  (superficie, se ve como blob). Para partículas de verdad, dá a cada punto su primitiva de punto:
  `convertPOP (convert='topointprims')` → 252 pts / **252 prims** y se dibuja como nube.
  ⚠️ **`convert='deleteprims'` NO sirve para renderizar**: deja **0 prims** y el render sale
  **negro** (medido: 0 px). `deleteprims` es para *quitar* primitivas, no para dibujar puntos.
- **El `geometryCOMP` auto-crea un `torus1` que DIBUJA** (800 pts/800 prims). Si no lo borrás, el
  `px>500` del render mide el torus, no tu cadena. Evidencia: en `/particle_swirl` apagar el flag
  `render` del torus lleva el render de 81572 px a **0**. Ver `td-pop-render-pipeline`.
- **La flag que dibuja es `render=true` en el TERMINAL del chain** (p. ej. el `nullPOP` de salida),
  junto con `display=true`. Solo `display` no alcanza; `render=false` → render **negro**.
- **El render no refleja cambios de datos** en remoto (uTime/uSwirl/radx): el `renderTOP` re-sube
  geometría solo ante cambios de material o estructura. Verificá animación por `poptoCHOP`, no por
  píxeles. Detalle en `td-live-verification`.
- **Si el dibujo se wedgea** tras muchas iteraciones de rewire/flags sobre el mismo geometryCOMP
  (datos correctos, 0 px) → reconstruí el chain/la red; el estado se cura con un build limpio.
- **Python**: `numPoints`/`numPrims` son **método** en POPs (`null_out.numPoints()`) pero **propiedad
  int** en SOPs (`tor1.numPoints`). Clases para `COMP.create()`: `spherePOP`, `convertPOP`,
  `nullPOP`, `sphereSOP`, `convertSOP`, `constantMAT` (sin sufijo no existen).

## Feedback Simulation

feedbackPOP has 1 input (reset/initial geometry). Loop back from output null is automatic.
- **Lifecycle**: `initializepulse` (reset) → `startpulse` (begin playback) → `play` (pause/resume)
- **particlePOP same lifecycle** — also requires `initializepulse` then `startpulse` to reset and run
- **Reinit after attribute changes**: `pulse_parameter` with `initializepulse` then `startpulse`
- **Conservative initial forces**: start low (gravity ~0.1-0.2, damping ~0.98)
- **forceradialPOP planar force** — creates soft repulsion, not hard bounces. Use mathmixPOP for floor collision (see reference.md)

## GLSL POP

- `glslPOP` — default choice, one attribute class, supports multi-pass
- `glsladvancedPOP` — only when needed: multi-class read/write, index buffer (`I[]`), extra outputs. See `td-glsl-shaders/glsladvancedPOP.md` for buffer allocation, output count control, and pitfalls
- Set `computedat` to textDAT name, list output attributes in `outputattrs`
- **Custom attributes** — use the `attr` sequence: `attr0name=color`, `attr0type=color`. GLSL buffer is auto-declared as `Color` (capital C, matching POP attribute name). Write as `Color[idx] = vec4(...)`. Do NOT manually declare an SSBO — it compiles but writes to an unmapped buffer
- **Attribute must exist before writing** — `outputattrs` only grants write access to attributes that already exist on the points. To write a new attribute: either create it with the `attr` sequence on the glslPOP itself, or place an `attributePOP` upstream to initialize it. Then list it in `outputattrs` explicitly
- **writeonly caveat** — with default `outputaccess=writeonly`, attributes listed in `outputattrs` that aren't written in the shader may get zeroed
- `TDPerlinNoise()` NOT available — write custom noise or use sampler input
- Multi-pass: `Passes=N, prevPassOutput=ON` for iterative solvers
- **`vec` not `const` for uniforms** — `const` sequence recompiles shader on every value change. Use `vec` for runtime parameters (see `td-glsl-shaders` skill)
- **Prefer built-in POPs over trivial glslPOP** — operations like texture lookup + math (abs, multiply, add) can use `lookuptexturePOP → mathmixPOP` chain instead of custom GLSL

## Common Patterns

- **Basic point cloud**: `gridPOP → noisePOP → nullPOP`
- **Particle sim**: `sourcePOP → feedbackPOP → [forces] → nullPOP`
- **Built-in particles**: `pointgeneratorPOP → particlePOP → [forces/bounce] → nullPOP`
- **Trails / animated 4D fields**: `trailPOP` (ACUMULA el campo: el enjambre migra y la cámara
  va al centroide de P, no al origen) y `noisePOP` con `type` 4D animado por `t4d` (sólo mueve
  puntos con tipo 4D). Recetas verificadas y pars reales del build: skill **`td-pop-trails-fields`**
- **Spatial interaction**: `neighborPOP` adds `Nebr`/`NumNebrs` for flocking/collision
- **SOP conversion**: `soptoPOP → attributePOP → nullPOP`
- **Copy/instance**: `copyPOP` (simple) or `glslcopyPOP` (custom per-copy transform, see below)

## GLSL Copy POP

`glslcopyPOP` copies source geometry N times with a custom GLSL transform per copy. See `reference.md` for full shader API.
- **Inputs**: input 0 = source geometry, input 1 = template points (optional, determines copy count)
- **Shader in docked DAT only** — write to `<name>_ptCompute`, never a separate textDAT (TDCopyIndex breaks). Delete unused `_vertCompute` and `_primCompute` docked DATs if not writing vert/prim shaders
- **Key functions**: `TDCopyIndex()`, `TDTemplate_P()`, `TDTemplate_AttribName()`, `TDIn_P()`

## Attributes

- See `reference.md` for full attribute list (reserved, common, particlePOP-specific)
- **Component access**: `P.x`, `P.y`, `P.z` (preferred) or `P(0)`, `P(1)`, `P(2)`. Use `.x/.y/.z` for readability
- **User-defined**: lowercase first letter to avoid conflicts with Derivative attrs
- **Debug values**: `inspect_values(path)` returns `pointAttributes[name].values` — sampled point values per attribute. `max_points=100` default (cap 10000), even-spaced stride when over cap. `attributes=["P","Cd"]` to filter. Type strings: `float3`, `int`, `float` (TD doesn't expose color/dir semantics — infer from name)

## Pitfalls

- **Locked nullPOP breaks POP cook loops** — cachePOPs keep cooking even when `active=false`, creating dependency loops in iterative POP pipelines. Place a `nullPOP` after the cachePOP and lock it (`op.lock = True`). The locked null holds stable geometry and breaks the cook chain. See `td-glsl-shaders/glsladvancedPOP.md` for the full cache feedback pattern
- **Default torus not deleted** — renders instead of your chain
- **No display/render flags on output null** — nothing renders
- **feedbackPOP not reinitialized after attribute changes** — stale attribute schema
- **Avoid SOPs inside geometryCOMPs** — use POP equivalents (spherePOP not sphereSOP)
- **copyPOP too heavy** — N vertices × M particles. Use instancing instead for many copies
- **GPU download stalls** — use `delayed=True` in Python for POP data access
- **lookuptexturePOP defaults wrong** — `lookupindexattr0/1` default to `P(0)`/`P(1)` (world position), NOT `Tex(0)`/`Tex(1)`. Explicitly set to Tex coords when sampling by UV
- **normalPOP tangents for PBR** — set `tang=alwayscompute` when using pbrMAT. Without tangents, PBR lighting fails
- **Point vs vertex attributes for materials** — glslPOP writes point attributes. pbrMAT/phongMAT read Tex as vertex attributes. Use `attributeconvertPOP` (`convertop=pointtovert`, `inputattrs=Tex`) to convert before the output null. Also disable spherePOP's built-in vertex Tex (`texture=none`) to avoid conflicts
- **mathmixPOP/mathcombinePOP sequences start empty** — `vec`/`comb` sequence pars don't exist until you add blocks: `n.par.comb.sequence.numBlocks = 2`. Must do this before setting `comb0oper` etc. Also `combNscopea/b/result` stay disabled until that block's `combNoper` is set — set opers first, scopes in a second pass
- **forceradialPOP Global Force multiplier defaults to 0** — `globforce*` values do nothing until `globforcemult` is set (e.g. gravity: `globforcey=-6`, `globforcemult=1`). Same trap with `windspeed*`/`windspeedmult`
- **rectanglePOP size is `sizeu`/`sizev`**, NOT `sizex/y/z/w` despite get_help showing those as components. Setting `sizex` silently does nothing. Same U/V naming on other 2D primitives with UV semantics — always verify live pars with `get_parameters(include_defaults=true)` before trusting get_help's `components` list
- **POP render color attr = `Color` (float4), NOT `Cd`** — SOP→POP trap. `attributePOP` value params are `attr0value0..3`. `constantMAT applypointcolor=1` renders point AND primitive `Color`
- **Filled POP geometry invisible from one side** — set MAT `cullface=neither`; default backface-culls primitives whose winding faces away
- **particlePOP no se mueve sin `timeintegration=ON`** — el Toggle "Enable Time Integration" integra posición/velocidad en el tiempo. Con OFF las partículas nacen pero quedan estáticas. Verificado en la fuente de partículas (2026-09-29)
- **spherePOP es `rad` (XYZW) y `cols`/`rows`** — NO `radius` ni `columns`. `rad` expone `radx/rady/radz`. `cols`/`rows` son los Int de subdivisión. (circlePOP en cambio sí usa `radx/rady`)
- **`display`/`render` son PROPIEDADES del OP, no params** — `op.display = True` / `op.render = True`. `op.par.display` da `AttributeError: 'td.ParCollection' object has no attribute 'display'`
- **poptoCHOP: `.chans()` y `.numSamples`** — NO `.channels` (método vs atributo). `poptoCHOP.par.pop` toma ruta **absoluta** (relativa `./geo/x` → warning "Invalid path")
- **`set_parameters` del MCP usa clave `values`** — `{"path":..., "values":{...}}`, no `params`
- **mathMixPOP y lookupAttributePOP NO existen en el build** — `get_help` responde `unknown_operator_type` verbatim (98 familias POP reales vs 101 docs de la KB); nunca asumir que un tipo de la lista de la KB existe
- **sprinklePOP sin input alimenta 0 canales al poptoCHOP** — necesita geometría debajo (toro/grilla): los generadores de superficie no generan nada solos
- **groupPOP `debugcolor=1` es el único camino para LEER membresía de grupo** — escribe Color=0.8 dentro / 0.2 fuera; sin él el grupo no deja canal alguno; condición por `attr0inattr/attr0func/attr0value`
- **transformPOP.group con grupo vacío o mal escrito NO filtra: mueve TODO** — el string no se valida; para excluir hace falta un groupPOP aguas arriba
- **quantizePOP y limitPOP aplican EN SITIO con `outputattrscope` vacío (default)** — no son no-op; y `limitPOP maxtype0='loop'` desplaza UNA ventana completa w=max0−min0 (0.5→−0.1), no envuelve dentro del rango
- **sortPOP `ptmethod='vector'` reordena el BUFFER** (0 descensos, multiset intacto); escribir `pointdirx/y/z` explícitos y releerlos; `seed` es determinístico por semilla; `pointshift` permuta reversiblemente
- **neighborPOP `nebroutput='avg'` no promedia nada sin `nebrptattrs='P'`** (default '' → P crudo); en modo avg también promedia NumNebrs; arrays por vecino llegan como `Nebr_0_`, `NebrP_0_`, `Dist_0_` (con doble underscore final)
- **connectivityPOP reconecta sin tocar puntos** — grilla 4x4: lines 12, linestrips 4, triangles 18, quads 9, points 16, none 0; `firstdimclosed` agrega +1 cerrojo por fila (12→16) y `seconddimclosed` no agrega nada
- **`get_help` usa firma `{'types':[...], 'verbose':true}`** — `operator_type` no existe; y sus menús vienen stale (`menuDataStale`): valores de menú reales con `get_parameters(path, include_defaults=true, include_menus=true)` sobre un op vivo

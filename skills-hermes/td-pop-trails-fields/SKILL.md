---
name: td-pop-trails-fields
description: "Use when building motion trails (trailPOP), particle sims with feedback (particlePOP), speed-colored trails (glslPOP Color or attributePOP+rerangePOP without shaders) or animated 4D noise fields (t4d). Recetas verificadas de /pop_streams, /pop_field, /pop_sim_trails, /pop_color_trails y /pop_field_trails: cadena, parámetros reales del build y pitfalls de medición."
---

> **Adaptación Hermes.** Estas skills son del repo oficial `TouchDesigner/TDMCPSkills`
> y asumen el MCP oficial corriendo en TD. En Hermes las 26 tools del oficial se
> llaman **`mcp_tdmcp_<tool>`** (ej. `get_help` → `mcp_tdmcp_get_help`,
> `list_operators` → `mcp_tdmcp_list_operators`); los nombres "pelados" que
> aparecen en el texto son de Claude Code/Codex: traducilos con ese prefijo.
> Cargá **`td-general` primero** en cualquier tarea de TouchDesigner.

> **Verificado en vivo (2026-09-29/30, TD 2025.32460 + TDMCP 1.1.55).** Recetas extraídas de cinco
> redes construidas y verificadas en frío: **`/pop_streams`** (estelas), **`/pop_field`** (campo 4D),
> **`/pop_sim_trails`** (simulación + estelas), **`/pop_color_trails`** (color por velocidad) y
> **`/pop_field_trails`** (campo de estelas directo sin glsl, proyecto 8).
> Qué corrida verificó cada una: `docs/BACKLOG.md → Estado verificado` (dueño único).
> Contratos completos con evidencia: **C8–C11** de `knowledge/contracts/VERIFIED_CONTRACTS.md`
> (tool offline `contracts`). La estructura de render (geometryCOMP, auto-torus, flags del
> terminal, material, gradables) la da **`td-pop-render-pipeline`** — acá sólo lo específico de
> trails, sims y campos.

# Estelas, sims y campos 4D

Cuatro formas de mover/pintar puntos: el **trail** re-hornea historial de posición (estelas), el
**campo 4D** desplaza puntos con ruido cuyo tiempo se escala a mano, la **simulación** integra
velocidades con un loop de feedback, y el **color por velocidad** pinta cada punto según su
`PartVel`. Todas terminan en `convertPOP(convert='topointprims')` + pointsprite (sin primitivas
de punto NO dibujan) — salvo el atajo del trail directo (más abajo).

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
> `colorr/g/b`), no el nodo. La semántica de los demás pars reales está en la tabla de arriba.

### Auditoría COMPLETA de la receta oficial (scratch en vivo + dump `op.pars()`, 2026-09-29 noche)

| nodo que usa la receta | veredicto | realidad del build |
|---|---|---|
| spherePOP | `radius` **NO existe** | `radx`/`rady`/`radz` (XYZW). `cols`/`rows`/`freq` SÍ existen (Int). 42 pars |
| particlePOP | `birth`, `lifevar`, `speedvar` **NO existen** | reales: `birthrate`, `lifevariance`. `life`/`speed`/`maxparticles` SÍ (53 pars; también `birthattr`, `jitterbirthpos/time`, `pointidreuse`) |
| noisePOP | `amplitude`, `harmonics` **NO existen** | real: `amp`. **`period` SÍ existe y aplica** (única sugerencia acertada junto a `type`). Menús: {perlin,simplex}×{2d,3d,4d} · {performance, quality}. 62 pars |
| renderPOP | **EL NODO NO EXISTE** en este build | no está entre los 89 POPs del build ni es creable (`create` → NameError). El render 3D real: `geometryCOMP` + `renderTOP` (`td-pop-render-pipeline`); para POP→textura existe `poptoTOP` (28 pars: `fillmode`, `rgbamode`, `toptype`… — sin camera/pointscale) |
| trailPOP | ver tabla de Receta A arriba | `velocityscale`/`color1*`/`color2*` inventados; `length` es TIEMPO |

> Nota de método: los pars Int clampean (escribir 3.25 → 3) y los MENÚ rechazan strings en
> silencio (C4) — un write/read mal diseñado da falsos negativos de existencia; el dump de
> `op.pars()` es el que decide.

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

### Semántica de los demás pars del trailPOP (medidos en vivo, 2026-09-29 noche)

| par | menú / default | qué hace (medido) |
|---|---|---|
| `inc` + `incunit` | float, default 1 · {seconds, frames} | **cadencia de muestreo**: cada cuánto se agrega un sample a la estela. inc=5 → ~2× menos samples que inc=1 (636 vs 1139, medido back-to-back) |
| `maxls` | Int, default 4096 | cap duro del trail (0.3 se recorta a 1: cast entero). El control fino del tamaño es `length`+`inc` |
| `ageattr` | {none, seconds, frames} | qué edad emite el PROPIO trail (no un nombre libre: `'myage'` se rechaza en silencio y queda 'none'). Con 'none' no agrega canal — el `PartAge` del sim aguas arriba pasa igual |
| `attrname` + `attrmatch` | StrMenu de atributos EXISTENTES (P(0..2), PartAge, PartId, PartVel…) + on/off | probable corte de estela por cambios de atributo; el efecto sobre el conteo quedó contaminado por drift del buffer → **(abierto)** |
| `oldestpointfirst` | on/off | el flip cambia el primer sample de la primitiva [V*]: consistente con inversión de orden, no distinguible del re-horneo en red viva |
| `closed` | on/off | sin efecto en píxeles a escala de pointsprites (9477 = 9477 px); importa con `surftype` de superficies |
| `surftype` | {none, points, rows, cols, rowcol, triangles, alttriangles, quads} | conectividad del trail (default `rows`). **VERIFICADO 2026-09-29 noche**: `'points'` entrega las primitivas de punto y el trail **renderiza sin `convertPOP`** (nube aislada: 0 px con `rows` vs 5495 px con `points`, mismo frame). `none` → 0 prims (nada); `triangles` → 0 prims sin fuentes de superficie |
| `fillmissedframes` | on/off | sin semántica probada |

> **Lección de medición:** en una red viva con simulación, `n(tr)` DERRAPA entre llamadas (el
> buffer del trail también arrastra slots muertos — 49664 samples en el baseline que bajaron a
> ~900 al tocar un par — y la sim alimenta puntos continuo). Para semántica, usar fingerprints
> diferenciales back-to-back (set → medir → restaurar dentro del mismo experimento), no conteos
> absolutos.

### Color por velocidad SIN glsl: attributePOP + rerangePOP (2026-09-30, cerrado con proyecto 8 [V])
El hueco del attributePOP (crea `Color` constante pero `dup`/`ren` no mapean) se cierra con
**rerangePOP** como mapeador atributo→atributo: `inputattrscope` + `outputattrscope` (el
atributo lo puede crear un attributePOP aguas arriba o el propio rerange). Verificado dos veces:
el Color de salida ESPEJA el atributo de entrada por punto, y con rangos `from=[-0.5,0.5] →
to=[0,1]` la salida es **entrada + 0.5 término a término** — corr(N_i, C_i) = 1.0 en las 3
componentes. El rango escalar aplica a TODAS las componentes (sólo queda abierto el caso de
rangos DISTINTOS por componente con `parsize>1`). `lookupchannelPOP` NO sirve para esto (su
input es un CHOP). Detalle y evidencia: C11 + C14 en `knowledge/contracts/VERIFIED_CONTRACTS.md`.

### Receta E — campo de estelas CERO glsl, CERO convertPOP (proyecto 8 [V])
```
toro(r=2.2, tubo scale 0.55) → sprinkle(3000) → noisePOP(simplex4d + gradient=True)
  → attributePOP(crea Color float4) → rerangePOP(NoiseGradient→Color) → trailPOP DIRECTO
```
- **`noisePOP.gradient=True` escribe `NoiseGradient_0..3`** (el vector del campo por punto =
  la "velocidad" sin sim); `curl2d` escribe `NoiseCurl2_0/1`; el modo noise plano no escribe
  nada. Los attrs de un POP no se enumeran con `pointAttrs` — se ven por canales del poptoCHOP.
- El trail directo: `tr.par.surftype='points'` + flags `display`/`render` en el propio trail
  (C8: `numPrims()==numPoints()` 1:1).
- La animación va por `t4d` escalonado a mano (C9): las estelas acumulan el historial del campo
  (el uniq de P_0 crece al escalonar).
- Guardia de render AL FINAL de la corrida y calentamientos suaves: los loops de settle+sleep
  dentro de una llamada agotan a TD (`td_slow_operation`, C14) y tras un rebind de cámara el
  primer `numpyArray()` puede leer 0 aunque `view_operator` vea contenido (`render_cache_vs_data`).

### Variante corta: el trail renderiza solo con surftype='points' (head-to-head [V])
Para estelas puras podés ahorrar el `convertPOP`: `tr.par.surftype = 'points'` + flags
`display`/`render` en el propio trailPOP. Comparación MISMO frame, misma red (2026-09-30):

| modo | px | prims |
|---|---|---|
| clásico (`rows`→curl→`convertPOP`→terminal) | 6938 | 507/507 |
| **directo** (`points` + flags del trail, sin `convertPOP`) | **7248** | 507/507 |
| control (`rows` + flags del trail) | **0** | 507/507 |

El directo no pierde píxeles: gana ~4,5% y ahorra el nodo de conversión. `numPrims()==numPoints()`
es SIEMPRE 1:1 en rows/points (el gradable es el TIPO de primitiva, no el conteo): con `rows` son
polilíneas que dibujan 0 sprites.

**El look se iguala con `pointsize`** (sweep mismo frame, 2026-09-30): a `pointsize` 1/2/4 el
directo EMPATA al clásico (ratio 1.02 / 1.00 / 0.99); a 8 pierde ~14% (16186 vs 18878 px — los
samples del trail se solapan sobre sí mismos y saturan). O sea: la vieja advertencia de "1 px"
sólo aplica al default 1.0 — con `pointsize>=2` el look directo es equivalente y la Receta A
deja de ser necesaria para estelas puras.

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

## Receta C — simulación + estelas (particlePOP con fuerzas)

Cadena dentro del `geometryCOMP` (run `/pop_sim_trails`, 13/13):

```
spherePOP (radx=rady=radz=0.3)  →  particlePOP (sim)  →  forceradialPOP (grav)  ─┬→ trailPOP
      → noisePOP (curl 3D)  →  convertPOP (topointprims)  →  null_render        └→ nullPOP 'fb'
                                  y  sim.par.targetpop = fb   (¡el LOOP de feedback!)
```

| nodo | par | valor | nota |
|---|---|---|---|
| spherePOP | `radx/rady/radz` | 0.3 | emisor chico; `radius` NO existe; `cols/rows` no aplican por set_parameters (C4) |
| particlePOP | `timeintegration` | True | sin ON no integra nada (C6) |
| particlePOP | `birthrate`/`life`/`maxparticles` | 60 / 1.2 / 2000 | el reciclado lo hace `life` contra el timeline |
| particlePOP | `targetpop` | la ruta del `fb` | **SIN el loop cerrado la integración se descarta**: `PartForce`/`PartVel` se escriben pero P queda clavado en el emisor (`particle_feedback_loop`, C10) |
| forceradialPOP | `globforcemult` + `globforcey` | 1 + -2/-6 | sin el mult la fuerza global no hace nada (C6); toggles radial/axial/spiral/planar en 0 |
| trailPOP | `lengthunit='frames'`, `length` | 16 | el trail re-hornea cada frame: la estela SIGUE a la sim |
| noisePOP | curl 3D | amp 0.35 | turbulencia opcional sobre las estelas |

**LO QUE NO HACER [V]:** `initializepulse` + `preroll` — hinchan el buffer del loop (30k-103k
"samples" con maxparticles=2000) y la red queda enferma (`particle_initialize_enferma`, C10).

**Verificación (C1-friendly):** la palanca es la **gravedad** y va en llamadas MCP separadas —
dentro de una llamada no corre nada; entre llamadas el timeline sí corre y `life` recicla la
población. Escalá `globforcey` -6 → -14, esperá 2.5 s (host) y medí **P_1.min** (lista EXACTA de
canales: un `startswith('P')` pesca PartVel/PartId): medido -1.89 → -5.03 en la sim y
-3.45 → -10.11 en el terminal. La población viva se mide por **`PartId`** (respeta
`maxparticles`), no por `numSamples` (el buffer arrastra slots muertos).

## Receta D — color por velocidad (glslPOP ANTES del trail)

Cadena (run `/pop_color_trails`, 14/14): igual a la Receta C pero con un `glslPOP` 'shade'
**entre curl y trail** — la estela arrastra el color que el punto tenía en cada frame:

```
sim → grav → curl → shade(glslPOP) → trailPOP → convertPOP → null_render    (+ fb desde grav)
```

Setup del shader (C3/C11, todo por execute_code, el DAT **antes** que attr/vec):
1. `textDAT` hermano con `language='glsl'` + `shade.par.computedat = dat`.
2. Main canónico (el `id` y la guardia los escribís VOS):

```glsl
void main()
{
    const uint id = TDIndex();
    if (id >= TDNumElements())
        return;
    float v = length(TDIn_PartVel());
    float t = clamp(v * uSpeedScale, 0.0, 1.0);
    Color[id] = vec4(mix(vec3(0.15, 0.30, 1.0), vec3(1.0, 0.85, 0.25), t), 1.0);
}
```

3. `outputattrs='Color'` + **crear** el atributo: `attr0name='color'`, `attr0numcomps='4'`
   (menú directo del build; `glsl_analyze` sugiere 'custom'+'customname' — otra era).
4. Uniform palanca: `vec0name='uSpeedScale'`, `vec0valuex=0.4` (después del bind).
5. Los inputs de ENTRADA se leen con **`TDIn_PartVel()`** (helper), NO como buffers —
   `PartVel[id]` compila con `"'PartVel' : undeclared identifier"` (`glsl_input_attrs_por_helper`).
6. El log del compilador vive en el DAT perezoso `<nombre>_info`.

Material pointsprite **BLANCO** (multiplica el Color del punto; un material coloreado
distorsiona el rampa). Sin shader, la variante sin glsl es attributePOP+rerangePOP (sección de
arriba); el attributePOP solo da color constante.

**Gradables del color** (canales `Color_0/1/2` del poptoCHOP, lista EXACTA): rango de `Color_2`
> 0.1 · la media de `Color_0` cambia > 0.02 al escalar `uSpeedScale` (medido 0.547 → 0.300) ·
el trail arrastra HISTORIAL: uniq del terminal > uniq de shade y max del terminal > max de shade
(medido 0.943 vs 0.626). **`n` (numSamples) NO es la señal** (buffer con slots muertos, C10).

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
  nada. Receta completa arriba (**Receta C**) y evidencia: C10 (`particle_feedback_loop`) en
  `knowledge/contracts/VERIFIED_CONTRACTS.md`.
- **Memoria del trail**: `length` está en **unidades de tiempo** (`lengthunit`: seconds/frames),
  no en puntos — el buffer escala con el tiempo de estela × puntos. La receta oficial que habla
  de "trail segment count" miente en la semántica; sus pars de color/velocidad no existen (ver
  auditoría arriba).

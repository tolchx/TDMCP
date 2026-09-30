# Contratos verificados — TouchDesigner 2025.32460 + TDMCP 1.1.55

Reglas aprendidas **probando contra TD vivo**, no leyendo docs. Cada bloque dice cómo se
verificó y qué síntoma produce ignorarlo. Es la fuente que sirve la tool offline `contracts`
de `td-knowledge` y de la que se nutren las skills `td-*`.

> Leyenda: **[V]** verificado en vivo con evidencia numérica · **[V*]** verificado pero el
> comportamiento cambió entre pruebas (anotado) · **[W]** warning: doc oficial o wiki dice otra cosa.
>
> **Historial de correcciones:** 2026-09-29 (pase 2, red `/curl_field`) — `points_need_deleteprims`
> era **falso** → reemplazado por `points_need_pointprims`; `pointsprite_pars` corregido
> (**`pointsize`**, no `attensizenear`); sumados `autotorus_masks_render`, `glslPOP`
> `numBlocks`/docks perezosos, y la ampliación de `set_parameters` a los `vecNvaluex`.
>
> **2026-09-29 (pase 3):** C4 suma que un arg mal nombrado se ignora en silencio
> (`list_operators` quiere `path`, no `parent_path` → default `/project1`).
>
> **2026-09-29 (ciclo diario):** fijada la regla del **único dueño de la medición**: el programa
> inyectado `tools/gauntlet/td_chain.py` (vía `td_probe.chain_source(root)`) y el wrapper
> `Gauntlet.offline()`; ejecutable con `tools/gauntlet/check_single_home.py`, que corre el gate.
>
> **Qué quedó probado y con qué corrida: `docs/BACKLOG.md` → *Estado verificado*** (dueño único).
> Acá no se repiten conteos ni corridas: ya derivaron una vez.
>
> **2026-09-29 (proyectos POP):** C8 abajo (trails/cámara/renderTOP-lista/noisesize-writeonly)
> y C9 (ruido 4D).
>
> **2026-09-29 (noche, proyecto sim+trails):** C10 abajo (el loop de feedback del particlePOP
> es obligatorio; initializepulse/preroll enferman el buffer; canales Part* del poptoCHOP;
> spherePOP radz/cols) y update de C8 (noisesize: el valor de atasco varía).
>
> **2026-09-29 (noche, proyecto color):** C11 abajo (glslPOP para colorear: main canónico,
> inputs por TDIn_*, Color float4 por attr, gradables de color e historial del trail).

---

## C1 — Medición: siempre asentar antes de leer

### `cook_lag` — los cambios de DAT/uniforms se aplican con un cook de retraso
**Síntoma:** editás el shader o un uniform y "no pasa nada"; medís de nuevo y aparece el valor
*anterior*. Conclusión falsa típica: "el uniform no está conectado".

**Evidencia [V]:** shader editado a `P[id] = pos * 2.0` → el poptoCHOP seguía mostrando `P_0.max
= 1.0257`; al *restaurar* el DAT, el cook siguiente mostró `2.0513` (exactamente 2×).

**Regla:** tras tocar DAT/parámetros/uniforms, cocinar en cadena varias veces y **releer**:

```python
def settle(n=4):
    for _ in range(n):
        op('/X/geo').cook(force=True)
        op('/X/geo/glsl').cook(force=True)
        op('/X/geo/null_out').cook(force=True)
        op('/X/ren').cook(force=True)
        time.sleep(0.04)
```

### `render_cache_vs_data` — el render no siempre re-sube geometría POP
**Síntoma [V*]:** `ren.numpyArray()` devuelve píxeles idénticos aunque cambien P (uTime, uSwirl) o
incluso `radx` de la esfera.

**Lo que sí refleja el renderTOP (verificado):**
- cambios de **material** (color/look) → se ve al instante en la siguiente lectura [V];
- cambios **estructurales** (rewire, flags display/render, rebind `geometry`) → se ven [V].

**Conclusión:** no uses píxeles para verificar *animación*; usá `poptoCHOP` (GPU→CPU), que sigue
los cambios de datos. Un renderTOP recién creado tampoco refresca datos POP en este entorno.

### `clock_stopped` — el reloj maestro puede estar parado
**Síntoma [V]:** `absTime.seconds` **no avanza** dentro de un `execute_code` (0.4–0.8 s de
`time.sleep` → mismo valor); `uTime = absTime.seconds` queda congelado y el efecto parece estático.

**Datos del build 2025.32460:** `absTime` expone solo `frame`, `seconds`, `step`, `stepSeconds`
(lectura, sin `.play`). `op('/')` **no tiene** `play`/`frame`/`rate` en `par`. El reloj del
proyecto es el timeCOMP `/local/` (`root.time`, con `play=True`, `frame`, `seconds`, `rate`) y
`frame` **no es asignable** desde Python.

**Regla:** para verificar animación no dependas del reloj: **escaloná el uniform** (`par.val = 0/3`)
y medí por poptoCHOP. En la GUI con el frame loop activo el efecto anima solo.

### `png_use_pil` — verificá imágenes con PIL, no con un decoder casero
**Síntoma [V]:** un decoder casero (filtros Sub/Paeth a medias) reportó 728 px "ámbar" donde PIL ve
4398 px azul/cian → conclusiones invertidas.

**Contrato:** los PNG de `view_operator` son **RGBA 8-bit (color type 6), orden RGB**, sin
premultiplicar. Calibrado con sondas de color puro: material rojo → byte0 domina; azul → byte2.
Usá PIL. Formatos de captura: `resolution="small"` → **148×111**; `frames=4` → **640×360** en grid
2×2 (no tira 1×4).

---

## C2 — POPs y render

### `points_need_pointprims` — lo que dibuja son las PRIMITIVAS, no los puntos
> **[CORREGIDO 2026-09-29]** El contrato anterior `points_need_deleteprims` era **falso**. Decía que
> `convertPOP(convert='deleteprims')` hacía la "nube de puntos pura" y que **eso dibujaba**, con
> gradable `numPrims()==0`. Se sostuvo durante una sesión entera porque había un auto-torus tapando
> el error (ver `autotorus_masks_render`).

**Síntoma [V]:** la red está perfecta por números (numPoints>0, atributos vivos, poptoCHOP anima) y
el render es **negro** (0 px).

**Contrato [V]:** un POP se dibuja por sus **primitivas**. `deleteprims` deja **0 primitivas** → el
render no dibuja **nada**. Hay que dar a cada punto su **primitiva de punto**:

```
gridPOP/spherePOP → convertPOP (convert='topointprims') → glslPOP → nullPOP
```
o, directo en el generador, `gridPOP.par.surftype = 'points'` ("Point Primitives").

**Evidencia [V] (2026-09-29, `/curl_field`, grilla 16³ = 4096 pts):**

| conversión | prims en el terminal | px del renderTOP |
|---|---|---|
| `deleteprims` (lo que decía la receta) | 0 | **0** |
| `topointprims` ("Points to Point Primitives") | 4096 | **6353** |

**Gradable correcto:** `term.numPrims() == term.numPoints()` (una primitiva por punto). **No**
`numPrims()==0`. El menú de `convertPOP.convert` incluye ambos: `deleteprims` y `topointprims`.

### `autotorus_masks_render` — el auto-torus hace pasar por bueno un render roto
**Síntoma [V]:** dás la red por verificada (px>500) y esos píxeles son el `torus1` que el
`geometryCOMP` **crea solo**.

**Contrato [V]:** `geometryCOMP` auto-crea `torus1` (POP, **800 pts / 800 prims**, con
`display=render=true`) y el renderTOP lo dibuja. Evidencia: en `/particle_swirl`, con la cadena de
partículas dada por verificada (35/35 PASS), **apagar el flag `render` del torus lleva el render de
81572 px a 0** → las partículas nunca se dibujaron; lo que se veía era el torus.

**Regla:** borrá el auto-torus al crear el `geometryCOMP` **y** comprobá que lo que ves es tu cadena:
`geo.children` sin `torus*`; si dudás, apagá el flag `render` del terminal y confirmá que el render
cae a 0 (si no cae, estabas midiendo otra cosa).

### `render_flag_on_terminal` — las flags van en el nodo terminal del chain
**Contrato [V]:** el geometryCOMP dibuja el **draw-stream del nodo con `render=true`**. Con
`render=false` (o `display=false` en ese nodo) el render sale **negro** aunque la red esté
perfecta. `display` solo no alcanza: hacen falta `display=true` **y** `render=true` en el terminal
(`null_render`), no en el `nullTOP` del viewer.

### `pop_render_network` — receta mínima que dibuja (verificada)
```
/comp
  geo (geometryCOMP)          ← borrar el torus1 que auto-crea (y confirmar que quedó sin torus)
    gridPOP | spherePOP → convertPOP(topointprims) → glslPOP → nullPOP   (display+render)
    pointspriteMAT            ← geo.par.material = ./pointsprite_mat
  cam (cameraCOMP, tz=5) · light (lightCOMP)
  ren (renderTOP)  →  null_view (nullTOP)
  check (poptoCHOP, par pop → geo/null_render)
```
> Verificado en frío construyendo `/curl_field` (run `20260929-014634`): con `deleteprims` el mismo
> chain da **0 px**; con `topointprims`, dibuja.
Bindings del renderTOP **solo por `execute_code`** (son OP-pars):
`ren.par.camera = op('.../cam')`, `ren.par.geometry = op('.../geo')`, y la luz por el par que
empieza con `light` (en este build el par real es **`lights`** plural; resolverlo iterando
`ren.pars()`).

### `pointsprite_pars` — el look de partículas
> **[CORREGIDO 2026-09-29]** `attensizenear` **no** controla el tamaño del sprite (era la creencia
> anterior). El tamaño es **`pointsize`** (default **1.0** ≈ 2 px). La doc oficial ya lo decía
> —"Constant Point Size … specifies the number of pixels wide the sprite will be"— y la receta la
> ignoró (la doc estaba descargada en `results/20260928-222507/`).

| Par | Qué hace | Verificado |
|---|---|---|
| `pointsize` | **tamaño del sprite**. En `constatten` = **píxeles**; en `perspective` = unidades de mundo | [V] |
| `sizingmodel` | menú de **2** opciones: `constatten` ("Constant/Attenuate") · `perspective` ("Perspective Correct") | [V] |
| `attenpscale` | mezcla constante↔atenuado. **Default 0** = 100% constante → los pars de atenuación quedan **inertes** | [V] |
| `attensizenear` / `attensizefar` | **no cambian el tamaño** con `attenpscale=0` | [V] |
| `blending` + `srcblend='sa'` + `destblend='one'` | aditivo: partículas luminosas que se suman | [V] |
| `colorr/g/b` | multiplica el color del punto (`Cd` del shader llega al sprite) | [V] |

**Evidencia [V] (2026-09-29, `/particle_swirl`, 252 puntos, 640×480, con `settle()`):**
`pointsize` **1 → 641 px · 2 → 1742 · 3 → 3324 · 4 → 5313** (≈ lineal). `attensizenear` **1 / 8 / 60 →
488 px idéntico** (mismo `mean`). `sizingmodel='perspective'` + pointsize 1 → **300758 px** (llena la
pantalla). Moraleja: si tus "puntos" se ven como una pelotita de 2 px, subí **`pointsize`**.

### `python_pop_api` — POPs vs SOPs en Python
- `numPoints`/`numPrims` son **método** en POPs (`nr.numPoints()`) y **propiedad int** en SOPs
  (`tor1.numPoints`) → llamar `tor1.numPoints()` da `TypeError: 'int' object is not callable`.
- Clases para `COMP.create()`: POP/SOP/MAT expuestos como `spherePOP`, `convertPOP`, `nullPOP`,
  `sphereSOP`, `convertSOP`, `constantMAT`. `sphere`/`convert` a secas **no existen**.
- `ParMode` es **enum**: `int(par.mode)` falla; usar `str(par.mode)`.
- Rewire en vivo: `dst.inputConnectors[i].connections[0].disconnect()` y
  `src.outputConnectors[0].connect(dst)` (o `connect(dst.inputConnectors[i])`).

---

## C3 — GLSL POP (uniforms, atributos, DAT)

- **`outputattrs`** lista los atributos **re-escritos**; si el shader escribe `P` hay que declararlo
  (`outputattrs='P'`) o falla con `'P' : undeclared identifier` [V].
- **La secuencia `vec` arranca en `numBlocks=1`** [V]: para **más de un** uniform hay que subirla
  **primero**, por `execute_code`: `glsl.par.vec.sequence.numBlocks = 3`. No es una constante (el
  `set_parameters` no la maneja) y la receta original solo usaba 2 uniforms sin mencionarlo.
- **Los DATs dockeados del `glslPOP` aparecen perezosamente** [V]: recién creado,
  `glslPOP.children == []` (0 DATs); después de cocinar/enlazar `computedat` aparecen `<name>_info`
  y `<name>_compute`. La skill `td-glsl-shaders` dice "escribí el shader en `<name>_compute`": eso
  **no es estable** en el momento de crear el nodo. El flujo que funciona siempre es
  **textDAT hermano + `computedat`** (lo que dice este contrato).
- **`TDPerlinNoise()` no existe en compute shaders** [V]: un campo de ruido (curl-noise, etc.) hay
  que **escribirlo a mano** (hash + interpolación) o pasar una textura por sampler.
- **Create Attributes** para atributos nuevos: `attr0name='custom'` (**lowercase**, el menú vivo lo
  rechaza con mayúscula), `attr0customname='Cd'`, `attr0numcomps=4` [V].
- **Uniforms**: la secuencia `vec` los auto-declara como `float` — **no redeclarar** en el shader
  (error de redeclaración). Enlazar `computedat` **resetea la secuencia vec**: bindear el DAT
  **primero** y setear `vec0name`/`vec1name`/valores **después** [V].
- **Animar**: `par.vec0valuex.expr = 'absTime.seconds'` (expresión) y un valor constante por
  `par.vec1valuex` para parámetros que el usuario mueve. Verificar por poptoCHOP escalonando el
  valor (ver C1/clock_stopped).
- **DAT del shader**: en este build el flujo que funcionó siempre es **textDAT hermano** +
  `language='glsl'` explícito + `glslPOP.par.computedat = op(...)`. (El auto-dock de DATs del
  glslPOP no es fiable entre builds; el oficial documenta el dock: aplicá **[W]** y verificá con
  `get_operator_info` qué hijos quedaron realmente creados.)
- **`glsl_analyze`** offline valida R1–R4 antes de tocar TD y emite los params exactos de Create
  Attributes: usarlo siempre primero.

---

## C4 — Herramientas TDMCP (contratos de API)

- **`set_parameters` = constantes solo.** Expresiones y pars con valor OP (camera/geometry/material)
  van por `execute_code`: `par.X.expr = "..."`, `op('ren').par.camera = op('cam')` [V].
- **`set_parameters` puede no aplicar un par y responder ok.** Verificado con
  `pointspriteMAT.attensizenear` (quedaba en el default mientras la tool decía ok) **y con los
  `vecNvaluex` del `glslPOP`** (quería `uAmount=0.9`/`uScale=1.6`; quedaron en **0.5/0.5**, la tool
  respondió ok). Ojo: el `vecNname` **sí** aplica por `set_parameters`; los **valores** no. **Regla:
  tras cualquier write, releer y, si no cambió, escribir por `execute_code`** [V].
- **Un arg con nombre equivocado se ignora en silencio.** `list_operators` toma **`path`** (no
  `parent_path`, que es el nombre en `create_operator`/`build_network`/`annotation`): el nombre
  equivocado NO da error, la tool cae a su default **`/project1`** y contesta `Path not found:
  /project1` [V]. Si una tool falla con una ruta que vos no pediste, sospechá del nombre del arg;
  `tools/list` da el `inputSchema` real de cada tool.
- **Los pars MENÚ rechazan valores inválidos en silencio [V].** Escribir `par.ageattr = 'myage'
  (menú real {none, seconds, frames}) no da error y `eval()` sigue en 'none'. Tras escribir un
  menú, releé y assertá el valor (mismo hábito que C4 para `set_parameters`).
- **`build_particle_fx`/scripts propios**: si un script de build no tiene `if __name__ ==
  '__main__'`, importarlo **ejecuta el build entero** (y su `sys.exit()` mata al importador).
- **`annotation`** crea con `comment` (no `text`); **`edit_custom_parameters`** usa
  `{path, page, add:[...]}` (un envelope con `action`/`parameters` responde `success: true` y no
  crea nada); **`edit_operator`** renombra con `name` y clona con `copy_to`; un `type` desconocido en
  `create_operator` devuelve error claro [V]. Ver `docs/issues-filed/`.
- **`view_operator`** devuelve imagen inline solo con `Inlineimages=true` en `/TDMCP` (y volver a
  `false` después) [V*]: dejarlo en true puede desincronizar capturas posteriores.

---

## C5 — Cómo verificar un efecto (checklist)

1. **Números antes que píxeles.** `poptoCHOP` (canales P/Cd/N) es la verdad GPU→CPU: cuenta de
   puntos, rangos de atributos, y si un uniform mueve P (`sig` antes/después con `settle`).
   **Ojo:** que la cadena tenga datos sanos NO implica que dibuje — mirá las **primitivas**
   (`points_need_pointprims`) y que no haya un auto-torus (`autotorus_masks_render`).
2. **Píxeles después.** `numpyArray()` del renderTOP con `settle`: `px = (arr[:,:,:3].max(2) >
   0.02).sum()` y `mean` de los píxeles encendidos. Un render vacío da 0.
3. **Captura como evidencia.** `view_operator` → PNG → decodificar con **PIL** (px, mean RGB, bbox,
   píxel más brillante). Un PNG "con contenido" puede ser un blob de superficie: mirá el color y el
   bbox, no el tamaño del archivo.
4. **Estado persistido.** Antes de cerrar, releer: flags del terminal, material (`sizingmodel`,
   **`pointsize`**, blending), uniforms (`vecNname`, expr), `poptoCHOP.par.pop`, `get_errors(path)`.
5. **Antes de creer que dibuja:** apagá el flag `render` del **terminal** y confirmá que el render
   cae a 0. Si no cae, los píxeles vienen de otro nodo (típicamente el auto-torus).
6. **Si el dibujo se wedgea** (0 px con datos correctos): reconstruir el chain (o la red) desde
   cero. Ha pasado tras muchas iteraciones de rewire/flags sobre el mismo geometryCOMP.
7. **Leer píxeles de OTRA red:** el `settle()` debe cocinar **la cadena de esa red**. Un `settle()`
   cableado a `/curl_field` no refresca `/particle_swirl` y `numpyArray()` devuelve el **frame
   cacheado** (medido: togglear `torus1.render` sin cocinar la cadena de swirl no cambió nada; al
   cocinarla, cayó a 0).

---

## C6 — Nombres REALES de parámetros POP (vía get_help, 2026-09-29)

Verificado construyendo una fuente de partículas con el MCP oficial (8/8 checks). Lo que la
doc "de memoria" dice mal y lo que el `get_help` del build vivo devuelve:

- **spherePOP**: `rad` (XYZW → `radx`/`rady`/`radz`), `cols`/`rows` (NO `columns`), `freq`.
- **particlePOP**: `timeintegration` (Toggle, **debe estar ON** para que los puntos se muevan;
  con OFF nacen pero no integran posición/velocidad), `birthrate`, `life`, `initvelocity`
  (XYZW → `initvelocityy`/`z`), `maxparticles`, `createpointprim` (crea point primitives él
  mismo, sin convertPOP), `emissionmode` (rate|attr).
- **forceradialPOP**: `globforce` (XYZW → `globforcey`), `globforcemult` (Float, **sin él la
  fuerza global no hace nada**), y los toggles `radial`/`axial`/`spiral`/`planar`. **NO existe**
  `globforceradial`.
- **API Python de POPs**: `display`/`render` son **propiedades del OP** (`op.display = True`),
  NO parámetros (`op.par.display` → `AttributeError`). Conteo: `.numPoints()` / `.numPrims()`.
- **poptoCHOP**: `.chans()` (método) y `.numSamples`, NO `.channels`. `poptoCHOP.par.pop` acepta
  **ruta absoluta** (una relativa `./geo/x` da warning "Invalid path").
- **`set_parameters`** del MCP usa la clave **`values`** (no `params`).
- **`view_operator` async**: primera llamada devuelve `{status: capturing, job_id, waitTime}`;
  la imagen se recupera con una segunda llamada `view_operator {path, job_id}` (sleep ~0.4s).

---

## C7 — GLSL pesado puede provocar TDR de GPU (Vulkan crash), 2026-09-29

**Síntoma:** diálogo *"Vulkan Device Error"* → *"Fatal Error"* → TD se cierra y auto-guarda
`CrashAutoSave...toe`. El MCP deja de responder (connection refused) porque **TD se crasheó**, no
por el `.tox`.

**Causa:** TDR (Timeout Detection and Recovery) de Windows — un shader GLSL tardó más de lo que
el driver tolera y Windows mató el contexto Vulkan. Disparado por el fluid solver "Low
Performances" de SARVJ: `glsl_addForces` (vorticidad ∇×u + gradiente |ω| + flotabilidad + no-slip
BC) se calcula en **cada punto de la grilla R³**, y la presión se resuelve con Jacobi iterativo.
Apilar un render más (God Rays + variación) sobre el mismo render pesado lo empujó al límite.

**Mitigación (en orden):**
1. Subir `TdrDelay` (registro): `reg add "HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers" /v TdrDelay /t REG_DWORD /d 60 /f` (+ reiniciar).
2. Bajar `SimRes` de la grilla (cada voxel extra = un punto más que cocina el shader de fuerzas).
3. No apilar pases de post (God Rays + variaciones) sobre el render del solver al mismo tiempo.

**Lección para el loop:** un "connection refused" del MCP ≠ `.tox` inactivo. Antes de pedirle al
usuario que toquee el toggle, revisar si TD se crasheó (diálogo Vulkan/Fatal Error) o si hay un
`CrashAutoSave.*.toe` recién escrito en la carpeta del proyecto.

---

## C8 — Trails, cámara y renderTOP (medido en `/pop_streams`, 2026-09-29)

### `trail_moves_points` — trailPOP acumula desplazamiento: el enjambre SALE del anillo
**Síntoma [V]:** con `circlePOP(r=2.2) → trailPOP → noisePOP`, el P-medio del terminal era
`(7.1, 7.0, 7.0)` — no el anillo. Con `amp=0` del ruido el anillo quedaba en el origen.

**Contrato [V]:** el trailP re-hornea los samples acumulando el campo de desplazamiento a lo largo
de la estela: cada cook, los puntos NUEVOS arrancan del anillo pero el historial quedó donde lo
dejo el campo. No es un bug: es la definición de estela. Consecuencia práctica: **la cámara no
debe apuntar al origen**, apunta al centroide de P (ver abajo).

### `cam_follows_data` — la cámara se centra en el centroide de P medido, no en el origen
**Contrato [V]:** en redes cuyo generador se desplaza (trails, partículas con fuerzas), leer el
centroide de P por `poptoCHOP` y posicionar `cam.par.t` ahí (+distancia). Con cámara en `(0,0,5)`
default y P-centro `(7,7,7)`: **0 px**; con cámara al dato: **4315 px** (misma red, mismo frame).

### `renderTOP_geometry_is_a_list` — crear OTRO geometryCOMP lo AGREGA a `ren.par.geometry`
**Síntoma [V]:** un `geometryCOMP` de prueba creado en la misma red apareció **concatenado** en
`ren.par.geometry` (`"[type:geometryCOMP path:/a/geo, type:geometryCOMP path:/a/geo_probe]"`),
heredando la cámara del render.

**Contrato [V]:** `ren.par.geometry` es **multi-valor**: no confíes en lo que ya tenía; reasigná
`ren.par.geometry = geo` en cada build y borrá cualquier COMP de prueba (o van a renderizar juntos).

### `noisesize_writeonly` — `noisePOP.noisesize` no cambia aunque lo escribas [V*]
Medido: `par.val = 1.2` por `execute_code` **y** por `set_parameters`: `eval()` sigue `'2'` (str).
Los menús reales del build: `mode` ∈ {performance, quality} (NO "turb" — el get_help miente, es el
label), `type` ∈ {perlin2d/3d/4d, simplex2d/3d/4d}. La escala default (2) sirve para el look.
> **[2026-09-29 noche]** el valor de atasco **depende del contexto**: en `/pop_sim_trails` quedó
> clavado en `'3'` (se pidió 1.2). El contrato es "NO aplica lo escrito", no "queda en 2".

### `POP_wiring_inputs_declarados` — wiring falla si el destino declara 0 inputs [V]
`wiring` con destino de 0 inputs responde `"vel has 0 input(s), to_index=0 out of range"`. En la
práctica: cadena POP lineal (un input por nodo), `to_index=0`, sin nodos transformadores sin input.

### `trailPOP_pars` — la receta oficial inventa pars del trailPOP; `length` es TIEMPO [V]
Auditoría contra el build vivo (dump de los 37 pars del trailPOP de `/pop_sim_trails`, 2026-09-29
noche): de lo que sugiere la receta `particle-system-pop` de la KB, **sólo `length` existe**.
**NO existen**: `velocityscale`, `color1r/g/b`, `color2r/g/b` — el nodo no tiene NINGÚN par de
color/fade/opacity (el color de las estelas lo pone el material). Y `length` NO es "cantidad de
segmentos": es tiempo de estela, con `lengthunit` ∈ {seconds, frames} (default seconds). La misma
receta también inventa pars para noisePOP (`amplitude`/`period`/`harmonics`: el real es `amp`) y
spherePOP (`radius`: es `rad` XYZW). Regla: pars de una receta KB → auditar con dump de
`op.pars()` antes de confiar. Receta corregida: skill `td-pop-trails-fields`.

**Semántica de los demás pars (medida en vivo en la misma sonda):** `inc`+`incunit` = cadencia
de muestreo de la estela (inc=5 → ~2× menos samples que inc=1); `maxls` = cap Int (default 4096,
0.3 se recorta a 1); `ageattr` ∈ {none, seconds, frames} — no es un nombre libre (un string
desconocido se rechaza en silencio, ver C4) y con 'none' no agrega canal; `attrname` (StrMenu de
atributos existentes) + `attrmatch` = corte por atributo **(abierto)**: el conteo quedó
contaminado por drift del buffer; `oldestpointfirst` cambia el primer sample [V*] (inversión o
re-horneo, indistinguible en red viva); `closed` sin efecto en px con pointsprites (9477=9477);
`surftype` = conectividad del trail {none, points, rows (default), cols, rowcol, triangles,
alttriangles, quads} — hipótesis abierta: `'points'` renderizaría estelas sin topointprims.
**Lección de medición:** en red viva con simulación, `n(tr)` derrapa (el buffer del trail también
arrastra slots muertos: 49664 → ~900 al tocar un par) — usar fingerprints diferenciales
back-to-back, no conteos absolutos.

**Auditoría del RESTO de la receta oficial (scratch + dump de `op.pars()`, 2026-09-29 noche):**
spherePOP: `radius` NO existe (reales `radx/y/z`; `cols`/`rows`/`freq` sí, Int); particlePOP:
`birth`/`lifevar`/`speedvar` NO (reales `birthrate`/`lifevariance`; `life`/`speed`/
`maxparticles` sí); noisePOP: `amplitude`/`harmonics` NO (real `amp`) pero **`period` SÍ existe
y aplica**; y **`renderPOP` NO EXISTE en el build** (ni entre los 89 POPs del build ni creable:
`create(renderPOP,...)` → NameError) — el render 3D real es geometryCOMP+renderTOP (C2) y para
POP→textura está `poptoTOP` (sin camera/pointscale). Moraleja del write/read: los pars Int
clampean (3.25→3) y los menús rechazan strings en silencio (C4) — el dump de `op.pars()` es el
que decide existencia; un write/read mal diseñado da falsos negativos.

---

## C9 — Ruido 4D animado (medido en `/pop_field`, 2026-09-29)

**`t4d_needs_4d_type` [V]:** el par `t4d` (tiempo del ruido) **sólo mueve puntos si `type` es
**4D** (`simplex4d`/`perlin4d`). Con `simplex3d` y `t4d` escalonado 0→3.5, el P del punto era
**idéntico**; con `simplex4d`, cambió. Es la forma de animar un campo sin simulación: escaloná
`t4d` (el reloj no corre en `execute_code`, C1/clock_stopped) y medí por punto con
`inspect_values` — el min/max de P es insensible porque cada punto se mueve distinto.

**`torusPOP_rad` [V]:** `rad` es XYZW (`radx`/`rady`); el grosor del tubo NO es `radz`: es
`scale`. `sprinklePOP.numpoints` muestrea la superficie que le entra (3000 pts sobre el toro).

---

## C10 — Simulación de partículas: el loop de feedback es obligatorio (medido en `/pop_sim_trails`, 2026-09-29 noche)

### `particle_feedback_loop` — sin `targetpop` cerrado, la integración se descarta
**Síntoma [V]:** `particlePOP` con `timeintegration=ON`, `initvelocityy=3`, y un
`forceradialPOP` aguas abajo con `globforcemult=1` + `globforcey=-14`: el atributo `PartForce_1`
llega a **-14** y `PartVel_1` a **3**, pero **P no se mueve jamás** (min/max clavados en el
emisor). La fuerza integrada a la salida no sirve: el integrador ya pasó.

**Contrato [V]:** el `particlePOP` integra posición **sólo si se cierra el loop de feedback**:
rama del stream aguas abajo a un `nullPOP` (`fb`) y `sim.par.targetpop = fb` (es un PAR, no una
conexión). El get_help lo dice ("*used in a Particle POP loop*") y la receta
`particle-system-pop` de la KB lo especifica con dos gotchas que resultaron ciertos: el target es
un **nullPOP** (no nullTOP) y la fuerza debe viajar ENTRE sim y el feedback. Evidencia al
cerrarlo: `P_1.min` de sim cae **-1.89 → -5.03** al escalar `globforcey` -6 → -14; `PartVel_1`
hasta -16.8; el terminal (estelas) acordeonea la caída **-3.45 → -10.11**.

**Regla (C1-friendly):** para probar la integración sin GUI ni reloj, escaloná la FUERZA
(`globforcey`) y la medición en **llamadas MCP separadas**: dentro de una llamada no corre nada
(C1/clock_stopped); entre llamadas el timeline sí corre, y `life` recicla la población. Cada
medición que registre `absTime.seconds` como evidencia de cuánto pasó.

### `particle_initialize_enferma` — `initializepulse` + `preroll` hinchan el buffer del loop
**Síntoma [V]:** con `preroll=1.0` + `initializepulse`, el poptoCHOP sobre sim reporta
**62k-103k samples** con `maxparticles=2000`, los rangos de P explotan y el trail ve 2-18 puntos.
**Contrato [V]:** NO usar `initializepulse`/`preroll` en builds MCP: el reciclado lo hace `life`
(1.2 s) contra el timeline. La población **viva** respeta el cap aunque el buffer del loop
arrastre slots muertos (30k): medir `PartId` (vivos), no `numSamples` (buffer), para hablar de
población.

### `popto_chop_part_channels` — los canales `Part*` engañan a un filtro por prefijo
**Contrato [V]:** el poptoCHOP sobre una cadena con particlePOP expone `P_0/1/2`,
`PartVel_0/1/2`, `PartId`, `PartAge`, `PartLifeSpan`, `PartDrag`, `PartMass`, `PartForce_0/1/2`.
Un filtro `name.startswith('P')` mezcla posición con velocidad/ids/fuerza: usar la lista
**exacta** de canales (esto sesgó la primera medición de la cámara).

### `sphere_pop_radz` — la esfera se achica por `radz` (execute_code); `cols`/`rows` no aplican
**Síntoma [V]:** `set_parameters {cols: 8, rows: 8}` respondía ok y al releer seguían en 20
(default, C4 otra vez). `radz` **existe** (el dump de la receta KB dice `radius`: miente, no
existe en este build).
**Regla:** esfera emisora chica por `execute_code`: `radx=rady=radz=0.3`.

### (abierto) `steppulse` no integra el estado
El par `steppulse` ("Step Pulse") del particlePOP **no movió** P ni edad en la sonda 5 (con loop
cerrado): la integración por pulsos queda sin explicar — la vía probada es la del timeline entre
llamadas. Si alguien necesita sim determinista frame a frame, retomar desde acá.

---

## C11 — GlslPOP para COLOREAR (medido en `/pop_color_trails`, 2026-09-29 noche)

### `glsl_compute_canonical_main` — el main se escribe COMPLETO: `id` y guardia incluidos
**Síntoma [V]:** un main sin declarar `id` falla con `"'id' : undeclared identifier"`. El template
del glslPOP lo muestra: `const uint id = TDIndex();` + guardia `if (id >= TDNumElements()) return;`.

### `glsl_input_attrs_por_helper` — los atributos de ENTRADA no son buffers: se leen con `TDIn_*`
**Síntoma [V]:** `PartVel[id]` → `"'PartVel' : undeclared identifier"` aunque el atributo llegue
por el stream. Se lee **`TDIn_PartVel()`** (helper por punto, con o sin args). La regla C3 de
`outputattrs` es para ESCRIBIR; leer no requiere declararlo (y el log del compilador vive en el
DAT perezoso `<name>_info`, C3).

### `color_es_atributo` — el color de render es `Color` float4 y se CREA con attr0name='color'
**Contrato [V]:** `attr0name` tiene menú {custom, n, **color**, tex, pointscale, linewidth}:
`attr0name='color'` + `attr0numcomps='4'` crea el atributo Color; `outputattrs='Color'`
(StrMenu) lo marca para escritura. NOTA: `glsl_analyze` sugirió `attr0name='custom' +
attr0customname='Color'` (valdable en 2025.31760) pero el menú del build vivo tiene la opción
directa — usarla. El material multiplica: para el rampa puro, pointsprite **blanco**
(colorr/g/b=1). Para pintar por velocidad, el glsl va ANTES del trail: la estela re-hornea
samples con el color del frame — el terminal muestra colores que shade ya no tiene (max 0.943
vs 0.626): HISTORIAL de color, la señal honesta de que la estela arrastra velocidad pintada.

### Gradables del color [V] (canales `Color_0/1/2` del poptoCHOP, lista EXACTA)
- Color presente y variando: rango de `Color_2` > 0.1.
- La palanca pinta: media de `Color_0` cambia (> 0.02) al escalar el uniform (`uSpeedScale`
  0.4 → 0.15: media 0.547 → 0.300).
- El trail arrastra historial: **valores distintos** (uniq) del terminal > shade, y max del
  terminal > max de shade. **`n` (numSamples) NO es la señal**: el buffer de shade arrastra
  slots muertos del loop (C10) y el trail sólo guarda historial reciente.

### `attributePOP_no_mapea` — attributePOP crea constantes; NO copia atributo→atributo [V]
Medido en `/pop_color_trails_attr` (2026-09-29 noche, 13/13):
- **`attr` (constantes) FUNCIONA**: `attr0name='color'` + `attr0numcomps='4'` crea el atributo
  `Color` (inspect_values: `pointAttributesChanged: ['Color']`) y el valor constante SOBREVIVE
  toda la cadena (tint → trail → topoints → null_render → render: poptoCHOP del terminal lo
  muestra intacto). Color fijo por red: la vía sin shaders.
- **`dup` (duplicar) y `ren` (renombrar) son INEFFECTIVOS en el build vivo**: read-back ok
  (`dup0name='PartVel'` queda escrito, el menú sí lo contiene) y CERO efecto — ni siquiera
  copian sobre un atributo destino YA CREADO por `attr`. No hay mapeo por punto con este nodo:
  el color variable necesita glslPOP (C11) u otro POP de mapping aún no explorado.
- Peculiaridades de las secuencias del attributePOP: no pueden volver a **0 bloques**
  (`Minimum size is 1 block`) — se deshabilitan **vaciando el nombre** del bloque.
- El poptoCHOP no expone el Color recién creado EN el nodo que lo crea: aparece **aguas
  abajo** (trail/topoints) — medir el terminal, no el creador.

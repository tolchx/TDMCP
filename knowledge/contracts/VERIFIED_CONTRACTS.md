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
alttriangles, quads} — **hipótesis CERRADA [V] con head-to-head (2026-09-30):** mismo frame,
misma red: clásico (`rows`→curl→`convertPOP`→terminal) **6938 px**/507 prims vs directo
(`points` + flags del trail, sin convertPOP) **7248 px**/507 prims — el directo no pierde
píxeles: gana ~4,5% y ahorra el nodo. Control: `rows` + flags del trail = **0 px** (las
polilíneas no dibujan sprites); `none`/`triangles` → 0 prims. Gradable correcto:
`numPrims()==numPoints()` es SIEMPRE 1:1 en rows/points (el trail ya trae sus primitivas);
lo que cambia es el TIPO — con `rows` son polilíneas. Los sprites del trail sin `pscale` son
de 1 px: para look con peso, mantener el convertPOP clásico.
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

### `poptoTOP_no_renderiza` — poptoTOP es conversión de DATOS, no un renderizador [V]
Probado en vivo (nube grid 12×12 → topointprims compartida, dos salidas, 2026-09-29 noche):
- **renderTOP clásico** (geometryCOMP+pointspriteMAT+cam): textura **480×270**, 1264 px con
  contenido, color del material, cámara 3D → lo que dibuja en pantalla.
- **poptoTOP** (par `pop` enlazado a la misma nube): textura **12×12** — UN píxel por PUNTO,
  con los atributos como canales (`attribscope='P'` mapea P.x/P.y normalizados a RGBA). Sin
  cámara, sin perspectiva, sin material. No llena la pantalla: mapea atributos a píxeles.
- Uso real: buffer GPU de atributos para samplers/glslTOP (formato hasta rgba32float, `dim`
  2d/3d, `layout` square/onerow/wrapped/popdim, `extract` point/primitive/vertex). Para
  renderizar puntos: **siempre geometryCOMP+renderTOP** (C2).
- Enlace: par `pop` acepta OP directo por `execute_code`; 28 pars.

---

## C12 — Instancing: fuente de datos y guardias (medido en `/pop_trails_floor`, 2026-09-30)

### `instancing_pop_crosscomp` — la fuente POP directa NO cruza COMPs [V]
**Síntoma [V]:** `geo_cubes.par.instancetop = op('/root/geo_data/tr_out')` (POP en OTRO
geometryCOMP) → **`geo_c.errors()` = "POP with point count info on GPU can only be the main
OP"** y 0 cubos dibujados (el render no marca error: mirar los errores del geometryCOMP).
**Contrato [V]:** la fuente de instancing POP sólo vale DENTRO de la misma COMP. Para datos de
otra COMP: **poptoCHOP** como fuente de canales (`instancetop = poptoCHOP`, selectores
`P_0/P_1/P_2` — nombres de canal CHOP, NO `P(0)`) — verificado: 0 errores y ~13k px de cubos.
Por eso la doc dice "CHOP = lo más común".

### `instancecolormode_menu` — el menú real no es 'op' (doc) [V]
`instancecolorop` + selectores `Color_0/1/2` pintan las instancias; `instancecolormode` se
elega del **menú vivo** (`menuNames`), no del valor 'op' que sugiere la doc de Hermes. Verificar
por color en el render: mean RGB azul-dominante + brightest ámbar con el rampa frío→caliente.

### Guardias para escenas MULTI-geometry [V]
Con `ren.par.geometry = [geoA, geoB]` (lista, C8) no hay UN solo terminal: las guardias son por
**toggle estructural** — flags `render` de cada chain (reflejan seguro, C1) y el toggle de
`instancing` (PAR) necesita **rebind de `ren.par.geometry` + cocinar** antes de leer. El color
por velocidad se gradable por **datos** (max `Color_0` del buffer del trail: el min es el piso
frío de los recién nacidos; min `PartVel_1`: la caída profundiza) — la cámara fija queda ciega
cuando la nube cae fuera del frustum. Phong: los pars de color son `diffr/g/b` (no `diffuser`).

### Addendum (2026-09-30): orientar instancias según PartVel (flechas) [V]
Verificado en `/pop_trails_floor` elevado (16/16, run 20260930-030437):

- **`instancer_euler_xz`**: los pars de Euler por instancia son `instancerx/y/z` (+ `instancerop`);
  los `instancerotu/v/w` son OTRO grupo (UV del rotate-to-vector, junto a `instancerotto*`).
  Las fórmulas de la skill (rx=degrees(atan2(dz,√(dx²+dy²))), rz=degrees(atan2(-dx,dy)))
  **verificadas contra numpy: maxdiff 0.0** calculadas en GLSL del glslPOP con
  `degrees(atan(y,x))`.
- **`glslpop_custom_attr`** (extiende C11/`color_es_atributo`): un attr PROPIO del glslPOP se
  configura con `attrNname='custom'` (es MENÚ) + `attrNcustomname='Rot'` + `attrNnumcomps='3'` y
  el out **NO se declara en el GLSL** — el glslPOP lo auto-declara por el config (declararlo
  igual compila dos veces o falla: en esta sesión compiló SIN declarar). El trail ARRASTRA el
  attr como arrastra `Color`: llega al poptoCHOP como `Rot_0/1/2`.
- **`curl_no_partvel`**: el curl 3D del noisePOP **NO toca `PartVel`** (escribe attrs propios:
  `curl3doutputattrscope`) — la "turbulencia" de la receta era inerte (PV_0/PV_2 exactamente 0
  con amp=1.0 verificado por readback). La variedad de dirección por partícula sale del
  **particlePOP**: `initvelocityx/z != 0` (velocidad inicial multi-eje).
- **`px_ciego_a_rotacion`**: el conteo de px es CIEGO a la rotación (cubos centro-simétricos:
  72694 px idénticos on/off; `PartId` como ángulo también dio 0 con caja simétrica). El gradable
  de la rotación es el **A/B congelado** (C1): diff medio del array y % de px cambiados
  (medido 0.0054 / 6% con el dardo; el px total con plantilla simétrica no sirve).
- **Plantilla asimétrica**: para VER la orientación la plantilla no puede ser simétrica
  (0.12³ invisible); dardo 0.12×0.45×0.04 (largo en +Y, el eje que alinea).
- El camino **rotate-to-vector** (`instancerottoop` + `instancerottox/y/z`='PartVel_0/1/2',
  `instancerottoposy` para el eje) también orienta (diff 0.0084) y es más barato de cablear:
  sin glslPOP ni attr — pero los ángulos no quedan inspeccionables en el buffer.

---

## C13 — poptoTOP → glslTOP: la nube como textura de datos (2026-09-30, `/pop_sim_trails`)

Pipeline verificado de punta a punta: `poptoTOP 'data' (par.pop=terminal, attribscope='P')` →
`glslTOP 'proc'` (pixel shader en `pixeldat`, uniform en la secuencia `vec`).

### `pixeldat_no_computedat` — el pixel shader del glslTOP va en `pixeldat` [V]
Los pars son TRES: `pixeldat` (pixel shader), `computedat` (compute — es donde va el shader del
**glslPOP**, no acá) y `vertexdat`. El glslTOP auto-crea sus DATs docked (`<nombre>_pixel` /
`_compute` / `_info`) al crearse. Síntoma del slot equivocado: errores vacíos y el output
**copiando la textura de entrada** sin procesar.

### `glsltop_pixel_main` — el pixel shader exige `out fragColor` + `TDOutputSwizzle` [V]
Síntoma [V]: un main tipo glslPOP (`fragColor = vec4(...)` sin declarar) **NO compila y no hay
error visible**: el output queda como passthrough del input (te hace dudar del pipeline, no del
shader). El template default que auto-crea el nodo lo muestra: `out vec4 fragColor;` +
`fragColor = TDOutputSwizzle(color);`. Uniforms: secuencia `vec` igual que el glslPOP
(`vec0name`/`vec0valuex`) y se leen con `uniform float uGain;` declarado en el shader.

### `poptotop_textura_cruda` — la textura trae valores CRUDOS; el rango va por uniform [V]
(REEPLAZA la creencia "renormaliza": poptoTOP NO re-normaliza) La textura trae atributos CRUDOS:
con `attribscope='P PartId'`, RGBA = (P.x, P.y, P.z, flag de vivo) — P.y crudo −4.9..0.4 en la
textura, el max idéntico al del poptoCHOP. **`PartId` no llega a ningún canal**: alpha es 0/1
(vivo) y los slots muertos del trail llegan como (0,0,0,0) — diluyen cualquier estadística del
buffer COMPLETO; la población viva se cuenta con `step(0.5, c.a)`. Síntoma del primer montaje [V]:
máscara sobre `c.b` (que es P.z, con negativos) → warm_frac ~0.02 plano para CUALQUIER uFrac.
La palanca va por uniforms del glslTOP: calibrando uLo/uHi con cuantiles VIVOS del buffer (p02/p98
del poptoCHOP), la fracción clasificada es LIBRE DE ESCALA (g=-6 vs g=-12: |Δ| < 0.03) pero SÍ ve
la demografía del buffer (post-reset: n_alive 4332→1728 Y la fracción sale de la banda madura).
`uFrac` es umbral sobre el valor NORMALIZADO, no un percentil: los extremos saturan (0.0 → ~0.01,
1.0 → 1.0 entre vivos) aunque la población derive. El tamaño de la textura es señal VIVA (6000→
14000 texels siguiendo al trail). `layout='onerow'` = 1 píxel por punto EN ORDEN; `'square'`
entrelaza por filas (rompe la correspondencia índice↔punto). `attribscope` controla qué entra
(con `'*'` entró `PartId` y saturó el shader).

Acceso a los uniforms: los bloques de la secuencia `vec` NO son `heat.par.vec2`
(`td.ParCollection` no expone los bloques como atributos, y `td.Par` no es subscriptable) — se
enumeran con `heat.pars('vec*')` y se escriben `vec2valuex`.

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
  copian sobre un atributo destino YA CREADO por `attr`. El mapeo por punto acá NO existe:
  el resolutor es el **rerangePOP** (abajo).
- Peculiaridades de las secuencias del attributePOP: no pueden volver a **0 bloques**
  (`Minimum size is 1 block`) — se deshabilitan **vaciando el nombre** del bloque.
- El poptoCHOP no expone el Color recién creado EN el nodo que lo crea: aparece **aguas
  abajo** (trail/topoints) — medir el terminal, no el creador.

### `rerangePOP_mapea` — el mapeador atributo→atributo sin glsl [V] (CERRADO, proyecto 8)
Cierre del hueco que dejó attributePOP (4 sondas sobre `/pop_color_trails_attr`, 2026-09-30;
**CERRADO a [V]** en `/pop_field_trails` 16/16, run 20260930-033443):
- **`rerangePOP` SÍ mapea atributo→atributo por punto**: `inputattrscope='PartVel'` +
  `outputattrscope='Color'` → el Color de salida ESPEJA PartVel (uniq 20, min/max idénticos,
  copia identidad con rangos default [0,1]→[0,1]) y crea el atributo él mismo.
- **El rango escalar aplica a TODAS las componentes** [V, proyecto 8]: NoiseGradient→Color con
  `from=[-0.5,0.5] → to=[0,1]` dio **corr(NoiseGradient_i, Color_i) = 1.0 exacta en las 3**
  componentes y salida = entrada + 0.5 TÉRMINO A TÉRMINO (spans idénticos desplazados) —
  mapeo lineal perfecto y uniforme, que es lo que el color necesita. (Queda abierto SOLO el
  caso de rangos DISTINTOS por componente con `parsize>1`.)
- Receta sin glsl: attributePOP CREA el attr (constante) y rerangePOP lo PUEBLA por punto;
  material BLANCO (multiplica el Color).
- `lookupchannelPOP` NO es el mapeador: su input es un CHOP (lookup index→canales de un CHOP),
  no atributo→atributo de un POP.

---

## C14 — Campo de estelas sin glsl (medido en `/pop_field_trails`, 2026-09-30, 16/16)

### `noise_gradient_attr` — el noisePOP expone el campo vectorial por punto [V]
`gradient=True` escribe `NoiseGradient_0..3` (spans ±2.5 con amp 0.4); `curl2d` escribe
`NoiseCurl2_0/1`; el modo noise plano NO escribe attrs nuevos. Ese vector es la "velocidad" de
un campo SIN simulación — la que se colorea y rutea sin glsl. Detectado por canales del
poptoCHOP (los attrs de un POP no se enumeran con `pointAttrs`: td.Par no lo expone).

### `td_slow_operation` — TD rechaza llamadas mientras se recupera [V]
Operaciones pesadas repetidas dentro de UNA `execute_code` (loops de settle + sleeps) agotan a
TD: responde "TouchDesigner is recovering from a slow operation. Wait 1.0s, then retry this
exact call" y falla TODA la cola en cascada. Reglas del build: calentamientos suaves (settle +
un sleep por llamada), y la guardia de propiedad del render AL FINAL de la corrida —
`render_cache_vs_data` hizo que el primer `numpyArray()` tras el rebind de cámara leyera 0
aunque `view_operator` veía contenido segundos después.
## C15 — Cuatro POPs de estructura, medidos en vivo (2026-09-30, batería reg-20260930-094856, 14/14)

Evidencia por build: `results/reg-20260930-094856/build-pop-<tipo>-report.json` (y el PNG del run).
Corridas individuales previas: transform `20260930-092753` · quantize `20260930-093549` ·
limit `20260930-093555` · sort `20260930-094803` · neighbor `20260930-094811` ·
connectivity `20260930-094654`.

### `poptochop_sprinkle_soltero` — sprinklePOP sin input alimenta a poptoCHOP [V]
El poptoCHOP vio `sprinklePOP` DIRECTO 0 canales y con un nullPOP intermedio también 0
(sonda hypo4); con `torusPOP → sprinklePOP` los canales `P_0..2` aparecen (n=300/400). El
sprinkle distribuye puntos SOBRE la geometría de entrada: sin input no hay nada que leer por
ese camino, aunque el POP "exista". Regla: todo POP generador de superficie va sobre una
geometría base (toro/grilla) antes de medirlo.

### `poptochop_doble_cook` — la primera lectura tras cambiar de POP puede venir rancia [V]
Cambiar `chk.par.pop` y hacer UN `cook(force=True)` devolvió `n=0` canales y `moved=0` que
no eran del dato: con `settle(2)` + doble cook + sleep la misma red dio los números correctos.
Refuerza C4 y la regla de medición: nunca confiar en la primera lectura tras rebind/re-cook.

### `grouppop_debugcolor` — debugcolor convierte la membresía de grupo en dato medible [V]
groupPOP con `grname='mitad'` + `attr0inattr='P.x'` + `attr0func='gte'` + `attr0value=0.0` +
`debugcolor=True` escribe Color=0.8 dentro / 0.2 fuera: sobre el toro 213/400 == exactamente
los puntos con P.x≥0 (medido; 18/36 en grilla). Sin `debugcolor` el grupo no deja canal
alguno: no hay otra forma de leer membresía por poptoCHOP. Nombres REALES (get_help live,
`results/20260930-090146/help/live-groupPOP.json`): `grname`, `entity` (point/primitive),
`attr0inattr/attr0func/attr0value` (lt/lte/gt/gte/eq/ne), `thinenabled/thinoutrange/
thinrangestart/thinrangelength`, `pattern0pattern` ('[0-17]' etc.).

### `transformpop_group_sin_poblacion_no_filtra` — grupo vacío o inexistente mueve TODO [V]
`transformPOP.group='mitad'` (poblado por groupPOP) mueve EXACTAMENTE los marcados:
moved_08=213==dentro, moved_02=0. Pero `group='noexiste'` o `group=''` mueven 400/400 —
el mismo efecto que sin filtro. Un agente que escriba el nombre mal obtiene el opuesto
silencioso de lo que quiere. (Addendum C12: los strings de grupo no se validan.)

### `transformpop_mapeo_exacto` — T/R/S es una matriz, punto a punto, con pivot real [V]
Sobre grilla determinista 6x6: rz=90 da `P' = (-y, x, z)` con max err 0.0; con pivot
(2.2,0,0) da `P' = (2.2-y, x-2.2, z)` con max err 0.0; tx=10 se suma después del pivot
(cx: 0.052 → 2.201 → 12.201). La rotación Z también intercambia las distribuciones de N:
pstdev(N_0) 1.0851↔1.0992 (swap exacto). Una lectura ANTES de setear tx dio cx=0.052 y
"ancho colapsado" que no era del operador (el pivot se midió con el tx viejo).

### `quantizepop_inplace` — scope de salida vacío NO es no-op: cuantiza el mismo atributo [V]
quantizePOP con `outputattrscope=''` (DEFAULT) aplicó round 0.25 EN SITIO: salida
[-0.5,-0.25,0,0.25,0.5] idéntica al caso `outputattrscope='P'` (elemento a elemento, sonda
noop). Con scope 'P': exactamente 5 niveles y `out==round(v/0.25)*0.25` con err<1e-6.
floor 0.3: `out==floor(v/0.3)*0.3` err 0.0 y BAJA los negativos fuera del rango de entrada
(32/64 puntos con |out|>|in|; 0.5→0.3, −0.3571→−0.6). Nombres REALES (live-quantizePOP.json):
`quantize0/quantstep0` (sufijo 0 por parsize; menú real off/floor/round/ceiling/gt/gteq/eq/
neq/lteq/lt — la doc decía otro orden), `attrdefaultval0..3`.

### `limitpop_loop_ventana` — 'loop' NO envuelve en [min,max]: shift por una ventana [V]
limitPOP clamp: max_x=0.3, min_x=-0.3 y saturan EXACTAMENTE los |P.x| fuera del rango
(16+16, err 0.0); sólo-min deja volar el techo (0.5 vuelve) con el piso en −0.3.
`maxtype0='loop'` con max0=0.3 (sólo máximo activo): los valores >0.3 se desplazan UNA
VENTANA COMPLETA w=max0−min0=0.6 → 0.5→−0.1, 0.3571→−0.243 (err<1e-4), NO quedan dentro
de [−0.3,0.3]; los valores bajo el mínimo pasan derechos (mintype0='off'). Nombres REALES
(live-limitPOP.json): `mintype0/maxtype0/min0/max0/positive0` (menú off/clamp/loop/zigzag).

### `neighborpop_arrays_y_avg` — la vecindad por distancia y el promedio opt-in [V]
Grilla 6x6 (spacing 0.2) + maxdistance 0.3 + maxneighbors 8: NumNebrs 3 (4 esquinas) a 8
(16 interiores), n=36. Con `nebroutput='nebr'`: llegan `Nebr_0_..7_` (índices),
`NebrP_0_..` (posición del vecino i-ésimo) y `Dist_0_..` con dodist (max 0.2828=√2·0.2).
`nebroutput='avg'` NO promedia nada sin `nebrptattrs` (default '' → P crudo, max 0.5);
con `nebrptattrs='P'` P pasa al promedio de vecinos: esquina raw (±0.5,±0.5) → (0.4,∓0.4)
con nn=3, interior (0.1,0.1) → (0.1,0.1). NumNebrs TAMBIÉN se promedia en modo avg
(interior muestra 12.0 = suma de 8 vecinos+query). Nombres REALES (live-neighborPOP.json):
`nebrtype/maxdistance/maxneighbors/nebroutput/nebrs/numnebrs/dodist/nebrptattrs`.

### `connectivitypop_tabla_prims` — reconecta sin tocar puntos; el cerrojo sólo entra por firstdim [V]
Grilla 4x4 (16 pts, 9 quads nativos) re-conectada (prims medidos): points=16, lines=12,
linestrips=4, triangles=18, alttriangles=18, quads=9, none=0; los PUNTOS no cambian en
ningún modo. `firstdimclosed` en lines: 12→16 (+1 cerrojo por FILA); `seconddimclosed`
NO agrega prims (16→16, medido dos veces) y linestrips cerradas tampoco (4→4). Nombres
REALES (live-connectivityPOP.json): `surftype` (mismo menú que trailPOP: none/points/lines/
linestrips/linestripperplane/zigzagperplane/spiralperplane/triangles/alttriangles/quads),
`firstdim/seconddim/firstdimclosed/seconddimclosed/reorderpoints`.

### `pop_help_no_existe` — casing sensible en tipos POP: `mathmixPOP` y `lookupattributePOP` [V]
`get_help {'types':['mathMixPOP','lookupAttributePOP']}` respondió verbatim
`"error": "Not found", "code": "unknown_operator_type"` porque en TD los tipos internos
son **totalmente en minúsculas antes de 'POP'**: `mathmixPOP` y `lookupattributePOP`.
Con el casing correcto (`mathmixPOP`, `lookupattributePOP`), `get_help` y `create_operator`
responden **exitosamente** en TouchDesigner 2025.32460 (verificado en vivo con OP Snippets
oficiales `mathmixPOP.tox` y `lookupattributePOP.tox`). Ambos operadores **SÍ existen** y son
fundamentales: `mathmixPOP` tiene 26 parámetros y soporta más de 70 operaciones matemáticas, y
`lookupattributePOP` realiza lookups arbitrarios atributo→atributo.
Los nombres reales del resto salieron de `get_help {'types':[...],'verbose':true}` (firma
validada; `operator_type` no existe) + `get_parameters(path, include_defaults=true,
include_menus=true)` sobre instancias vivas — los valores de menú del help estático venían
stale ("menuDataStale: 2025.33070 vs build 2025.32460").

## C16 — Seis POPs de topología y patrones, medidos en vivo (2026-09-30, batería reg-20260930-131003, 20/20)

### `facetpop_unique_prims_intactas` — unique des-duplica puntos y NUNCA toca primitivas [V]
grid 4x4 (16 pts, 9 quads): `operation='unique'` abre a 36 pts (9 prims intactas); toro
(800 pts, 800 quads): 800→3200 = 4 puntos por quad. `cusp` depende del ángulo: con el
default real `angle=20` NO corta el toro continuo (800→800, las normales no superan el
umbral) y con angle=1 sí (→3200): menor ángulo = más cortes. `conspoints` colapsa por
distancia con prims intactas: dist=0.3 deja 16 pts (el espaciado 1/3 > 0.3), dist=0.5
funde TODO a 1 punto, dist=0.0001 deja 16. Nombres REALES (live-facetPOP.json):
`operation` (menú none/unique/cusp/conspoints), `angle` (default 20.0, la KB decía 89.5),
`dist` (default 0.0001), `technique` (bruteforce/sharedmemory/spatialgrid/...).

### `subdividepop_escalado_exacto` — iterations es scaling de topología determinístico [V]
grid 4x4 (16/9): it0 identidad 16/9, it1 EXACTO 49 pts / 72 prims, it2 EXACTO 169/288
(los quads se multiplican x4 por nivel: 36→144). El bounding box NO cambia (P_0 y P_1 en
[−0.5, 0.5]) y la superficie plana queda plana (P_2 max abs = 0 en it1 y con crease).
`creaseweight=1` desplaza los puntos (la nube ya no coincide) sin cambiar los conteos
(49/72). Nombres REALES (live-subdividePOP.json): `iterations`, `creaseweight`,
`simplecoeffs`, `cpureadback`.

### `triangulatepop_toggle_necesario` — sin `triangulatequads=on` NO triangula nada [V]
El toggle viene **false** en el build vivo (2025.32460): con off, grid 4x4 pasa INTACTA
(16 pts, 9 quads). Con on: 9→18 tris en la grilla, 800→1600 en el toro (x2 exacto),
SIEMPRE con los puntos intactos. `mode='concave'` sobre quads convexos da el mismo 18
(el modo importa en polígonos cóncavos). La KB no documentaba el par. Nombres REALES
(live-triangulatePOP.json): `mode` (convex/concave), `triangulatequads`, `lsmaxverts`,
`setmaxiter`, `maxiter`.

### `extrudepop_jaula_siempre` — la jaula existe incluso con distance=0 [V]
grid 3x3 (9 pts, 4 quads) → 25 pts / 20 prims INCLUSO con `distance=0` (8 caras copiadas
+ 12 quads laterales); grid 4x4 → 52/45. `distance` escala la altura: rango P_2 = [0,
distance] con axis z (d=1 → [0,1], d=2 → [0,2]) y la base en 0. `axis='y'` mueve el rango
al eje (P_1 = [−0.5, 2.5] con d=2; P_2 plano). `taper=0.5` deforma sin cambiar conteos
(25/20). Nombres REALES (live-extrudePOP.json): `axis` (normal/x/y/z), `distance`,
`taper`, `peredge`, `maxprimsperpoint`, `normal` (none/pointNormals/vertNormals).

### `patternpop_genera_por_indice` — ramp/sin exactos; el random no depende de numpoints [V]
Generator (sin input): ramp 4 pts → P_0 [0, 1/3, 2/3, 1] (err < 2e-8), 6 pts paso 0.2;
`reverse0` invierte; `tolow0/tohigh0=10/20` remapea exacto (0→10, 1→20). Tabla de prims
con 6 pts: linestrip=1, lines=5 (n−1), points=6, none=0 (con 4 pts: 3 y 4). sin 2 ciclos
en 8 pts cuadra con math.sin(2π·2·i/7) punto a punto (err 3.4e-7). `Tex` rampstartend
reproduce el ramp en Tex_0. `type='random'` es determinístico por seed (2 lecturas
iguales, cambia 3≠9) y genera POR ÍNDICE: los primeros 4 valores son idénticos con
numpoints 4 y 8. Fuera de checks (no deducido): `type='index'` produce [0,2,0,2] en 4 pts.
Nombres REALES (live-patternPOP.json): `type0/1/2` por parsize (menú zero/one/ramp/
.../sin/cos/tri/square/pulse/random/randomcycle/index), `numcycles0..2`, `seed`,
`outputattrscope` default 'P' — el 'set' del generador SÍ escribe.

### `randompop_set_scope_noop` — el 'set' de randomPOP contradice el default in-place de la familia [V]
Sobre grilla 3x3 con `combineop='add'`, `amp0=1`: deltas P punto a punto uniformes en
[0,1] (9/9), determinístico por seed, cambia con la semilla (3≠7). `combineop='set'` con
`outputattrscope=''` (default del op) es NO-OP: P vuelve EXACTO a la grilla base — lo
contrario que quantizePOP/limitPOP, que con scope vacío aplican en sitio. Con
`outputattrscope='P'` el set escribe uniformes en [0,1]. **amp NO escala ni acota el
uniforme**: con la misma seed, amp=0.5 produce los MISMOS valores que amp=1.0 (delta máx
medido 0.97 > 0.5). `type='gaussian'` con amp=1 ≈ N(0,1) (n=200: media 0.083, stdev
1.033, rango 6.73). `extrapts` MULTIPLICA los puntos: total = N·max(1, extrapts)
(9→18 con e=2, 9→27 con e=3, estables re-cocinando; e=1 deja 9). Nombres REALES
(live-randomPOP.json): `type` (none/twovalues/uniform/gaussian/insidesphere/direction/
exponential/lognormal/cauchylorentz/customramp), `combineop` (set/add/mult/
translatealongnormal), `seed`, `amp0`, `valuea0/valueb0`, `extrapts`.

## C17 — Seis POPs de población y superficies, medidos en vivo (2026-10-02, batería reg-20261002-022418, 26/26)

### `camara_lookat_canonica` — apuntar la cámara con rx/ry a mano NO apunta; el mecanismo canónico es lookat + traslación [V]
En un sandbox limpio (320x240), apuntar manualmente con `rx/ry` calculadas hacia el objetivo
produjo render NEGRO en TODAS las configs probadas (frente, top, iso arriba/abajo, triangulado,
perfil invertido, constant y pointsprite) — incluso el auto-torus del geometryCOMP fresco no
dibujó. Con `cam.par.lookat = geo` y traslación iso (2,2,2) el mismo torus da 62,473 px. Mirar
el anillo del revolve desde el eje Y con up=+Y también da 0 px (singularidad del up). REGLA del
gauntlet: cámara = `lookat` al geometryCOMP + traslación (iso 2,2,2 o al-centroide+z); NUNCA
rotar a mano.

### `grouppop_poblacion_inmutable` — thin etiqueta, no elimina; el multiset de puntos es invariable [V]
Grid 5x4 + groupPOP `removethin=on`: numPoints/numPrims y el poptoCHOP dan SIEMPRE 20 pts /
12 prims (base/range/step activo) — la membresía es un metadato invisible para el conteo.
thin range [0-5) mueve un SUBCONJUNTO ESTRICTO bimodal (dy exactamente {0, 1.2}) pero N NO es
reproducible entre cooks (5 y 3 medidos; el orden de índices inestable); thin step 2 SÍ es
exacto (10/20 en todas las corridas). `debugcolor` cuantiza Color en 2 valores exactos
(0.2/0.8) y el valor A acompaña SOLO a los movidos (pairing por índice). Grupo 'ghost' sin
miembros MUEVE TODO (20/20, C15 reproducido en la red 5c).

### `grouppop_bound_sin_efecto_api` — el bound del groupPOP no excluye a nadie vía API (contrato ABIERTO) [abierto]
La secuencia `bound` se escribe estilo Sequence: `gp.par.bound.sequence.numBlocks = N` (el
objeto tiene numBlocks/insertBlock/destroyBlock/blocks/blockSize/blockParGroups/sortBlocks).
`numBlocks=0` lanza `tdError: Minimum size is 1 block. Value:0 Type:<class 'int'>.` (verbatim)
y `destroyBlock(0)` tampoco baja de 1: PISO de 1 bloque. En 4 configs (bsphere 0.01..5, bbox
0.1..20, punto trasladado tx=10, invert) NINGUNA excluye un punto (20/20 siempre dentro,
err='' sin errores). Queda ABIERTO cómo se excluye vía API (¿requiere inattr='P' por bloque?
¿UI?). `remunusedpoints` figura en get_help (catálogo 2025.33070) pero NO existe en el build
vivo 2025.32460: help stale.

### `proximity_conteos_exactos` — el grafo es distancia pura y los conteos son reproducibles [V]
Grid 3x3 spacing 0.2 (9 pts, 4 quads): `maxdist=0.21` + `duplines='avoid'` = EXACTAMENTE 12
aristas ortogonales (6 h + 6 v, cero diagonales: 0.2828 > 0.21). `donothing` DOBLA: 24 = 12x2
cada arista aparece una vez por sentido (no "mantiene la primera"). Umbral: @0.10 → 0 aristas,
@0.29 → 20 (12 + 8 diagonales exactas). `maxlinesperpoint=1` reduce (8 medidos) y es
determinístico. `output='points'` conserva el conteo de aristas como prims de punto (9/12).
`cpureadback` OFF (default) BASTA para leer conteos (OFF=ON=12). Nombres REALES:
`maxdist`, `maxlinesperpoint`, `duplines` (donothing/avoid/delete), `output` (lines/points),
`cpureadback`, `linelength`.

### `revolve_topologia_exacta` — el barrido conserva el radio del perfil: 2·divs pts / divs quads [V]
PatternPOP 2 pts ramp (radios 0.2..0.5) linestrip + revolve divs=20: 40 pts (2 filas x 20 col)
/ 20 quads; radios sqrt(x²+z²) EXACTOS {0.2, 0.5} (err < 1e-3): cada circunferencia hereda el
radio del punto del perfil. Tabla surftype 2x20: quads=20, rows=2 (las circunferencias como
linestrips), cols=20, points=40, none=0, triangles=40. divs escala exacto: 4 → 8 pts/4 prims,
8 → 16/8. autopivot ON vs OFF con perfil colineal al eje: misma topología y mismos radios (el
pivote automático coincide con el eje Y). N (3ch) y Tex (2ch) de serie. Nombres REALES:
`axis` (auto/x/y/z), `autopivot`, `px/py/pz` (pivote), `surftype`, `divs`, `normal`, `texture`.

### `tubepop_cono_y_caps` — radx/rady son los radios de los EXTREMOS (cono) y endcaps suma cols-2 [V]
tubePOP autonomo, cols=8 rows=4 quads: EXACTO 32 pts / 24 prims (rejilla rows x cols, U
cerrada, sin duplicados); default cols=40 rows=10 → 400/360 = (rows-1)*cols. `radx` es el
radio en y=-1 y `rady` en y=+1 con interpolación lineal EXACTA en las filas (0.2→0.467→0.733
→1.0): el "Radius XYZW" del help es en realidad cono (radz/radw NO existen en vivo: help
stale). `height` escala el eje (4 → Y=[-2,2] con XZ=[-0.5,0.5]); `orient` x/y/z mueve el eje
(mismo perfil de radios sobre cada eje). `closedu=False` DUPLICA la columna del seam: +rows
pts (36 vs 32) con las mismas 24 prims. `endcaps` es Toggle ['off','on'] y agrega EXACTAMENTE
cols-2 prims (6 con cols=8; una tapa de abanico) SIN crear puntos. Atributos: default SOLO P
(normal=vertNormals/texture=vert de serie no llegan al poptoCHOP); `normal='pointNormals'`
crea N y `texture='point'` crea Tex. Tabla surftype 8x4: rows=4, cols=8, triangles=48,
points=32, quads=24.

### `topologypop_specpop` — la topología de B se aplica sobre los puntos de A (ref vivo, copy no congela) [V]
A (grid 3x3 surftype='none', tx=5: 9 pts / 0 prims) + B (grid 3x3 quads) + topologyPOP con
`primsourcemode='specpop'`, `primspop=B`: resultado 9 pts / 4 quads. P viene del INPUT (rango
P_X [4,6], el de A trasladado) y los atributos del primsource (N, Tex) están accesibles en el
resultado. `topology='ref'` es VIVO: cambiar B (con cook explícito) none→triangles→quads lleva
el resultado a 0/8/4 prims. `topology='copy'` NO congela: tras copiar, B en none lleva el
resultado a 0 prims (la copia se rehace por cook; es copia de buffers, no snapshot).
`maxpointsmode='custom'` con maxpoints=5 recorta el input a 5 pts manteniendo las 4 quads,
determinístico. OJO: grid 3x3 con `surftype='rows'` da 0 prims estables (3 linestrips solo si
la dirección lo permite); usar none/triangles/quads para discriminadores. Nombres REALES:
`primsourcemode` (input/specpop), `primspop`, `topology` (ref/copy), `maxpointsmode`
(input/custom), `maxpoints`, `vertattrmode`/`primattrmode` (none/primsource/specpop).

### `lookuptexturepop_override_y_texels` — sin override el attr no aparece; el muestreo es exacto por texel con interpolate off [V]
noiseTOP 8x8 (seed fija) + grid 3x3 + lookuptexturePOP (`top=nz`,
`lookupindexattr0='P(0)'`): sin `overrideautoattr` NO aparece ningún atributo nuevo (testigo
lt2: solo N/P/Tex); con `overrideautoattr=True + outputattrscope='Color' + attrtype='color'`
se crea el attr Color de 4 canales (sorpresas del build vivo 2025.32460: el scope automático
no escribe y `fromlow/tolow` del help no aplican al attr). `interpolate=False` muestrea
EXACTO por texel: cada Color_0 medido es un valor de la matriz del TOP (pertenencia al
conjunto de 59 texels únicos); el índice es función de P (trasladar el grid cambia el muestreo
dentro del conjunto y al restaurar tx vuelven EXACTAMENTE los valores base). El lookup sigue
al TOP asignado: constantTOP 0.9 → los 9 Color_0 = 0.898 (±1 LSB: los TOPs de 8 bits
cuantizan 0.9 → 229/255). `lookupindexoffset0=0.125` desplaza el patrón y 0 lo restaura
exacto. Determinismo: dos lecturas completas idénticas. Nombres REALES: `top`, `attrclass`,
`overrideautoattr`, `outputattrscope` (StrMenu con P/N/Color/Color.rgb/Tex/PointScale/...),
`attrtype` (float/double/int/uint/color/dcolor/dir/ddir), `attrnumcomps`,
`lookupindexattr0/1/2` (default 'P(0)'/'P(1)'), `lookupindexoffset0/1/2`, `indexunit`
(normalized/pixelindex), `pixelcentered0..2`, `inputextend0..2`, `interpolate`, `channelmask`
(Int bitmask 15 = RGBA).

---

## C18 — Arquitectura POP oficial extraída de OP Snippets (2026-10-05)

Evidencia: 102 componentes `.tox` analizados en `Samples/Learn/OPSnippets/Snippets/POP/`
(TouchDesigner build 2025.32460).

### `pop_data_model_hierarchy` — Clases de atributos y metadata de dimensión [V]
- **Jerarquía de atributos:** Puntos (Points: escalares o vectores float3/4 como `P`), Primitivas
  (Primitives: conectividad como polígonos/líneas y attrs por primitiva), y Vértices (Vertices:
  attrs por unión vértice-primitiva).
- **Notación de componentes y Swizzling:** Se soporta indexación formal `P(0)`, `P(1)`, `P(2)`,
  swizzling vectorial estándar `.xyz`, `.rgba`, y para atributos de usuario o dimensiones
  arbitrarias la notación canónica `.i0123` (ej. `Polar.i012`, `Timecode.i0123`).
- **Dimensión como metadata (`dim`):** POPs matriciales (`gridPOP`, `planePOP`) emiten metadata
  de dimensión implícita (ej. 2D o 3D con slices). Las dimensiones se componen río abajo al
  copiar (`copyPOP` de un círculo 1D sobre un grid 2D genera estructura de 3 dimensiones).
- **POPs sin atributo P:** Es un patrón válido y oficial. Se crean nubes puras de datos/atributos
  sin posiciones espaciales usando `pointPOP`, `patternPOP`, `selectPOP`, o activando
  `Delete Input Attributes` en la página Common. Son los "uniforms" o tablas de lookup ideales
  para alimentar `mathmixPOP` o `mathcombinePOP`.

### `mathmix_mathcombine_uniforms` — Mezclado matemático y uniformes sin overhead [V]
- **`mathmixPOP`:** Soporta más de 70 operaciones matemáticas (`sin`, `mix`, `cross`, `dot`,
  `smoothstep`, `clamp`, etc.). Puede procesar múltiples inputs (`input0` mantiene nombres,
  `input1` prefija `in1_`).
- **Atributos Built-in con guión bajo (`_`):** Operadores como `mathPOP`, `mathmixPOP`,
  `mathcombinePOP`, `lookupattributePOP` exponen atributos automáticos precalculados que
  comienzan con `_` (ej. `_index`, `_weight`).
- **Página Uniform:** Permite inyectar valores constantes (1 a 4 floats) desde expresiones, CHOPs
  o bindings sin necesidad de instanciar un canal por punto en GPU, evitando el costo de memoria
  de atributos completos.

### `particle_trail_lifecyle` — Identidad persistente en sistemas de partículas [V]
- **`PartId` & Don't Reuse Point Id:** En simulaciones `particlePOP`, para construir estelas
  coherentes mediante `trailPOP`, `pointidreuse` debe configurarse en `'none'` (menú real
  `['loop', 'unused', 'none']` correspondiente a "Don't Reuse Point Id"). Esto garantiza que el
  atributo `PartId` no se recicle cada ciclo de vida (evitando artefactos de teletransportación
  de estelas al expirar `maxparticles`).
- **Conexión por ID en `trailPOP`:** Cuando la cuenta de puntos es dinámica cuadro a cuadro,
  activar `trailPOP.par.attrmatch = True` y apuntar `trailPOP.par.attrname = 'PartId'`.

### `field_pop_parameter_override` — Inyección paramétrica de campos por punto [V]
- **Convención de anulación paramétrica:** `fieldPOP` permite definir un campo por punto (ej.
  desde un `pointPOP`). La regla fundamental es que los nombres de los atributos de entrada
  deben coincidir exactamente con el nombre del parámetro del `fieldPOP` que modifican
  (ej. atributo `radx` anula el parámetro `radx`; `P` anula los parámetros `tx`, `ty`, `tz`).
- **Nombres reales de salida en `fieldPOP` [V]:** El toggle `weight=True` crea el atributo `Weight`.
  El toggle `signeddistance=True` crea el atributo **`Dist`** (NO `SignedDistance`).

### `ray_pop_intersection_attrs` — Detección de colisiones y atributos de rayo [V]
- En `rayPOP` (Input 0 = origen/dirección de rayos, Input 1 = geometría de colisión), al activar
  los toggles de medición se generan en GPU los siguientes atributos exactos [V]:
  - `dist=True` crea el canal de distancia **`RayDistance`**.
  - `hitnormal=True` crea el vector normal de impacto **`RayHitNormal`**.
  - `numhits=True` crea el conteo de impactos **`RayNumHits`**.
- La combinación `rayPOP` + `mathmixPOP` es el estándar en OP Snippets para rebotes físicos
  sin requerir bucles pesados de shaders en CPU ni simulaciones lentas.



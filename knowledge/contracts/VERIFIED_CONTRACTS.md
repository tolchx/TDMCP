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
> Runs (0 fallos): `/curl_field` `results/20260929-025128` · `/particle_swirl` (arreglada)
> `results/20260929-025059`.
>
> **2026-09-29 (pase 3):** C4 suma que un arg mal nombrado se ignora en silencio
> (`list_operators` quiere `path`, no `parent_path` → default `/project1`). Runs 0 fallos:
> `results/20260929-030521` (swirl) · `results/20260929-030548` (curl) ·
> `results/20260929-030806` (regresión) · `results/20260929-030833` (F3.6).
>
> **2026-09-29 (ciclo diario):** re-verificado en vivo el arg mal nombrado (`parent_path` →
> `Path not found: /project1`; `path` → 7 ops en `/curl_field`) y fijada la regla del **único dueño de
> la medición**: el programa inyectado `tools/gauntlet/td_chain.py` (vía `td_probe.chain_source(root)`)
> y el wrapper `Gauntlet.offline()`; ejecutable con `tools/gauntlet/check_single_home.py` (0
> violaciones) y `python tools/gauntlet/td_probe.py` (5/5). Suite completa PASS
> (`results/20260929-032041`).

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

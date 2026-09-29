# Pase 2 — segunda red POP en frío: el playtest de la receta

**Fecha:** 2026-09-29 · **TD** 2025.32460 · **TDMCP** 1.1.55 · **Windows 11**

**Objetivo del pase.** La receta de POP→render existía en prosa (`td-pop-render-pipeline` +
`VERIFIED_CONTRACTS.md`) pero nadie la había ejecutado **en frío**. Construir una red POP **nueva y
distinta** (sin tocar `/particle_swirl`) siguiéndola al pie de la letra, y registrar cada punto donde
no alcanza, falla o miente.

**Resultado.** Se construyó `/curl_field` (campo de puntos desplazado por **curl-noise** escrito a
mano, grilla 3D 16³). Run canónico: **`results/20260929-025128`** — **0 fallos**. Y aparecieron **7
hallazgos**, uno de ellos grave: **la receta estaba mal en su punto central, y su verificación
anterior era falsa.** Con eso se **arregló también `/particle_swirl`** (run
**`results/20260929-025059`**, 0 fallos).

---

## 1. La red construida — `/curl_field`

Distinta al enjambre esférico de `/particle_swirl` en las tres capas:

| | `/particle_swirl` | `/curl_field` |
|---|---|---|
| emisor | `spherePOP` (esfera, 252 pts) | `gridPOP` 3D 16×16×16 (4096 pts) |
| shader | swirl + glow (uTime, uSwirl) | **curl-noise** a mano (hash + diferencias finitas), uniforms uTime/uAmount/uScale |
| look | azul (0.25, 0.6, 1.0), 8 px | **rosa/magenta** (1.0, 0.45, 0.85), 5 px |

```
/curl_field
  geo (geometryCOMP)
    grid_emit (gridPOP, cols/rows/slices=16, dimension='rowscolsslicesalways', size 4³)
      → topoints (convertPOP, convert='topointprims')
        → glsl_curl (glslPOP + shader_compute textDAT)
          → null_render (nullPOP, display+render)
    pointsprite_mat
  cam (tz=5) · light · ren (640×480) → null_view · check (poptoCHOP)
```

Verificación (run `20260929-025128`): 4096 pts · **4096 prims** (una por punto) · `glsl_curl.errors()`
vacío · 13 canales en `poptoCHOP` · uTime y uAmount **mueven P** (firma por `poptoCHOP`) · Cd vivo ·
render **12289 px** a 640×480 · PNG PIL **148×111, 1199 px**, media `[0.261, 0.119, 0.222]`, más
brillante `[251, 113, 214]` (magenta) · `get_errors(/curl_field)` = 0.

---

## 2. Hallazgos sobre la receta (el entregable)

| # | tipo | área | hallazgo | evidencia |
|---|---|---|---|---|
| 1 | **lie (grave)** | `points_need_deleteprims` | la receta manda `convert='deleteprims'` y afirma que **eso dibuja**. `deleteprims` deja **0 primitivas → render negro**. Lo que dibuja es **`topointprims`**. El gradable `numPrims()==0` estaba **al revés** | `/curl_field` 4096 pts: `deleteprims` **0 px** / 0 prims · `topointprims` **6353 px** / 4096 prims |
| 2 | **false-verification** | `render_flag_on_terminal` + auto-torus | `geometryCOMP` auto-crea `torus1` (**800 pts/800 prims**, display+render) y el renderTOP **lo dibuja**. La "verificación" de `/particle_swirl` (35/35 PASS, px>500) medía **el torus**: las partículas nunca se dibujaron | apagar el flag `render` del torus lleva `/particle_swirl` de **81572 px → 0** |
| 3 | **trap** | `geometryCOMP` auto-torus | la receta dice "borrá el torus1" pero **su propio script de referencia nunca lo hacía** | `geo.children` de `/particle_swirl` contiene `torus1`; `build_particle_fx.py` no lo borra |
| 4 | **lie** | `set_parameters` en glslPOP | responde ok pero **no aplica los `vecNvaluex`** (quedan en el default **0.5**). Los `vecNname` sí aplican | quería uAmount=0.9/uScale=1.6 → leí 0.5/0.5; corregido por `execute_code` |
| 5 | **gap** | `glslPOP` secuencia `vec` | arranca en **`numBlocks=1`**; para N>1 uniforms hay que subirla, por `execute_code`. La receta solo mostraba 2 uniforms y no lo mencionaba | `numBlocks` default = 1; con 3 seteado a mano |
| 6 | **nuance** | `glslPOP` DATs dockeados | **no existen al crear el nodo** (`children=[]`); aparecen (<name>_info, <name>_compute) al cocinar/enlazar. La skill `td-glsl-shaders` manda "escribí el shader en `<name>_compute`" — inestable | `auto_children_before_bind=[]` / `after_bind=['glsl_curl_info','glsl_curl_compute']` |
| 7 | **lie** | `pointsprite_pars` | el tamaño del sprite **no** lo controla `attensizenear`: es **`pointsize`** (default **1.0** ≈ 2 px). La doc oficial ya lo decía y la receta la ignoró | `pointsize` 1→641 px · 2→1742 · 3→3324 · 4→5313; `attensizenear` **1/8/60 → 488 px idéntico**. `perspective`+pointsize 1 → 300758 px |

### Cómo se encontró el #7 (mirar la doc que ya tenías)

Con `/particle_swirl` "arreglada" el render daba **632 px**: correcto pero casi invisible. La receta
decía "subí/bajá `attensizenear`". Barrí `attensizenear` 8/12/16 → **632 px idéntico**. La doc
oficial del `pointspriteMAT` (ya descargada en `results/20260928-222507/`) dice: *"Constant Point
Size `pointsize` … specifies the **number of pixels wide** the sprite will be"*. Probé `pointsize`
1/2/3/4 → 641/1742/3324/5313 px. **`attensizenear` queda inerte porque `attenpscale` (que mezcla
constante↔atenuado) es 0 por defecto.**

### Cómo se encontró el #1 (el camino importa)

1. El build **verde por números** (puntos, atributos, animación) daba **0 px**. El pitfall de la
   receta decía "flags, binding o lectura sin asentar".
2. Flags, binding, cámara, material: **idénticos** a `/particle_swirl` (diff en vivo). `px` seguía 0.
3. Diff de `/particle_swirl`: tenía un `torus1` **de más**. Toggle de su flag `render`:
   **81572 → 0 px**. La red "verificada" dibujaba el torus.
4. Con eso claro, el problema real era el terminal: **0 primitivas**. A/B en vivo en `/curl_field`:
   `deleteprims` → 0 px, `topointprims` → 6353 px.

> Nota metodológica: en el paso 3 el primer intento de toggle **no cambió nada** porque el `settle()`
> estaba cableado a `/curl_field` y `numpyArray()` devolvió el **frame cacheado** de swirl. Hay que
> cocinar **la cadena de la red que estás midiendo**.

---

## 3. Correcciones aplicadas

* `tools/gauntlet/build_pop_curlfield.py` — red nueva, re-ejecutable, **con la receta corregida**
  (`topointprims`) y un experimento A/B que prueba el hallazgo #1 en cada corrida.
* `tools/gauntlet/build_particle_fx.py` + **`/particle_swirl`** — **arreglada** (el usuario lo pidió
  tras ver el hallazgo #2): borra el auto-torus, `convert='topointprims'`, `numBlocks=2`, valores de
  uniform por `exec_code`, radio 1.5 y `pointsize=3`. Run `20260929-025059` (0 fallos). Antes: render
  del torus (81572 px). Ahora: **3324 px de partículas reales**, y `render=false` en el terminal lo
  lleva a 0 (guard en el build: "los px son nuestros").
* `knowledge/contracts/VERIFIED_CONTRACTS.md` — `points_need_deleteprims` → **`points_need_pointprims`**
  (con la evidencia); nuevos `autotorus_masks_render`, `numBlocks`/docks perezosos; `set_parameters`
  ampliado a los `vecNvaluex`; checklist C5 con "apagá el terminal y confirmá que cae a 0".
* `skills-hermes/td-pop-render-pipeline` — la receta reescrita (era el artefacto bajo prueba).
* `skills-hermes/td-pop-family` — corregida la afirmación de `deleteprims` + el auto-torus.
* `skills-hermes/td-glsl-shaders` — docks perezosos, `numBlocks`, `TDPerlinNoise` no existe en compute.
* `skills-hermes/td-live-verification` — Regla 1.5 "verificá de qué son los píxeles" + `settle()`
  cableado a otra red.

## 4. Pendiente / riesgo abierto

* El `settle()` de la receta sigue siendo **no parametrizable** (paths cableados): candidato a
  convertirse en helper `settle_chain(root)` en `td_probe.py`. Un `settle()` cableado a otra red
  devuelve el **frame cacheado** (nos pasó midiendo swirl).
* **Nada valida que los píxeles sean "de la cadena"** salvo el guard nuevo (apagar el terminal y
  exigir 0 px). Vale la pena que sea un helper estándar de verificación, no un check ad-hoc.
* Los `vecNvaluex` no se pueden setear por `set_parameters`: escribir por `exec_code` debería ser la
  regla por defecto en los scripts de build, no la excepción.

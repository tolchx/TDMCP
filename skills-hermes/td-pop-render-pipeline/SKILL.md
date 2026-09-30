---
name: td-pop-render-pipeline
description: "Use when a POP/GLSL effect must actually appear on screen. geometryCOMP + renderTOP + pointspriteMAT, point primitives, flags del terminal — build y verificación por números."
---

> **Adaptación Hermes.** Estas skills son del repo oficial `TouchDesigner/TDMCPSkills`
> y asumen el MCP oficial corriendo en TD. En Hermes las 26 tools del oficial se
> llaman **`mcp_tdmcp_<tool>`** (ej. `get_help` → `mcp_tdmcp_get_help`,
> `list_operators` → `mcp_tdmcp_list_operators`); los nombres "pelados" que
> aparecen en el texto son de Claude Code/Codex: traducilos con ese prefijo.
> Cargá **`td-general` primero** en cualquier tarea de TouchDesigner.

> **Verificado en vivo (2026-09-28/29, TD 2025.32460 + TDMCP 1.1.55).** Esta receta se ejecutó
> **en frío** construyendo una red nueva (`/curl_field`, campo curl-noise 16³) sin copiar el
> enjambre: run `results/20260929-014634`, **0 fallos**. En ese pase se descubrió que **la versión
> anterior de esta receta estaba mal** en su punto central (ver §1). Detalle: secciones C1–C5 de
> `knowledge/contracts/VERIFIED_CONTRACTS.md` o la tool offline `contracts`. Metodología de
> medición: skill **`td-live-verification`**. Recetas específicas de **estelas (trailPOP)** y
> **campos 4D animados (noisePOP t4d)**: skill **`td-pop-trails-fields`**.

---

# POP → render: la receta que dibuja

Una red de POPs puede estar **perfecta en los datos y no dibujar nada**. Estos son los puntos que
hay que cumplir, en orden — y cómo verificar cada uno.

## 1. Estructura mínima (verificada) — ¡lo que dibuja son las PRIMITIVAS!

```
/effect
  geo (geometryCOMP)                 ← BORRÁ el torus1 que auto-crea (POP 800 pts/800 prims) y COMPROBÁ
    gridPOP | spherePOP ...          ← emisor (superficie o grilla)
      → convertPOP (convert='topointprims')     ← cada punto CON su primitiva de punto
        → glslPOP (+ textDAT del shader)
          → nullPOP 'null_render'     ← TERMINAL del chain: display=true Y render=true
    pointspriteMAT                    ← geo.par.material = ./pointsprite_mat
  cam (cameraCOMP, tz=5)
  light (lightCOMP)
  ren (renderTOP)  →  null_view (nullTOP)
  check (poptoCHOP, par pop → geo/null_render)
```

**Contrato `points_need_pointprims` [V]:** un POP se dibuja **por sus primitivas**. El generador
entrega una **superficie** (`spherePOP` defaults = 252 pts / 500 prims; `gridPOP` 16² = 400 pts /
361 prims). La conversión que sirve es **`convertPOP(convert='topointprims')`** ("Points to Point
Primitives") — o directamente `gridPOP.par.surftype='points'`.

⚠️ **`convert='deleteprims'` NO dibuja.** Deja **0 primitivas** y el render sale **negro** (0 px).
Medido en `/curl_field` (4096 puntos): `deleteprims` → 0 prims → **0 px**; `topointprims` → 4096
prims → **6353 px**. Este error estuvo en la receta original.

**Contrato `autotorus_masks_render` [V]:** el `geometryCOMP` auto-crea `torus1` (POP, **800 pts /
800 prims**, `display=render=true`) y **el renderTOP lo dibuja**. Si no lo borrás, tu `px>500` está
midiendo **el torus, no tus partículas**. Evidencia: en `/particle_swirl` (dada por verificada
35/35), apagar el flag `render` del torus lleva el render de **81572 px a 0**. Borralo **y** validá
que lo que ves es tu cadena.

**Contrato `render_flag_on_terminal` [V]:** el geometryCOMP dibuja el draw-stream del nodo con
`render=true`. Con `render=false` el render sale **negro** aunque todo lo demás esté bien.
`display=true` solo no alcanza. Las flags van en el terminal del chain (`null_render`), **no** en el
`nullTOP` del viewer.

## 2. Bindings del renderTOP (OP-pars → solo por `execute_code`)

```python
geo.par.material = op('/effect/geo/pointsprite_mat')
ren.par.camera   = op('/effect/cam')
ren.par.geometry = op('/effect/geo')
# la luz: el par se llama 'lights' (plural) en este build; resolverlo por nombre
for p in ren.pars():
    if p.name.lower().startswith('light'):
        setattr(ren.par, p.name, op('/effect/light')); break
```

`set_parameters` **rechaza** valores OP y expresiones (ver `td-general`). `resolutionw/h` sí son
constantes y van por `set_parameters`.

## 3. Material: el look de partículas

`pointspriteMAT` con, **verificado**:

| Par | Valor | Por qué |
|---|---|---|
| **`pointsize`** | **el tamaño** (p. ej. `2`–`4`) | **default 1.0 ≈ 2 px**: "los puntos no se ven" casi siempre es esto. En `constatten` son píxeles |
| `sizingmodel` | `constatten` | menú de **2**: `constatten` (píxeles, predecible) · `perspective` (mundo; con pointsize 1 llena la pantalla) |
| `blending`, `srcblend`, `destblend` | `true`, `sa`, `one` | aditivo: partículas luminosas; el color del punto (`Cd` del shader) llega al sprite |
| `colorr/g/b` | color base | multiplica el `Cd` |

❗ **`attensizenear` NO controla el tamaño** (creencia vieja, refutada 2026-09-29). Con
`attenpscale=0` (default) los pars de atenuación quedan inertes: `attensizenear` 1/8/60 dan el
**mismo** render. El tamaño es **`pointsize`** — la doc oficial ya lo decía.

⚠️ **`set_parameters` puede no aplicar un par y responder ok** (pasó con `attensizenear` **y con
los `vecNvaluex` del glslPOP**, que quedaron en 0.5). Escribí por `execute_code`, **releé** y assertá:

```python
mat.par.sizingmodel = 'constatten'; mat.par.pointsize = 3.0   # NO attensizenear
assert mat.par.pointsize.eval() == 3.0
```

## 4. Uniforms del glslPOP: `numBlocks`

La secuencia `vec` **arranca con `numBlocks=1`**. Para más de un uniform hay que subirla **primero**
y **por `execute_code`** (no es constante):

```python
s.par.vec.sequence.numBlocks = 3      # uTime, uAmount, uScale
s.par.vec0name = 'uTime'; s.par.vec0valuex.expr = 'absTime.seconds'
s.par.vec1name = 'uAmount'; s.par.vec1valuex.val = 0.9   # valor por exec_code, NO set_parameters
```

Los `vecNname` sí se pueden poner por `set_parameters`; los **valores** `vecNvaluex` no.

## 5. Gradables (antes de decir "listo")

1. **Números antes que píxeles.** `poptoCHOP` con ≥3 canales (P/Cd/N) y, escalonando el uniform de
   animación (`uTime`), los canales P **cambian**. Hay un retraso de un cook: **asentá antes de
   leer** (`td-live-verification`).
2. **Primitivas.** `term.numPoints() > 0` **y** `term.numPrims() == term.numPoints()` (una primitiva
   por punto). Si `numPrims()==0` **no va a dibujar**.
3. `renderTOP.errors()` y `glslPOP.errors()` vacíos; `geo.children` **sin** `torus*`.
4. **Píxeles.** `ren.numpyArray()` con `>500` encendidos (a 640×480) tras asentar. Después apagá el
   flag `render` del terminal y confirmá que baja a 0 → los píxeles son tuyos.
5. **Captura** `view_operator` → PNG decodificado con **PIL** (px, color medio, bbox).

## Pitfalls

- **"La red está bien pero el render es negro"** → en este orden: (a) `numPrims()==0`
  (`deleteprims` en vez de `topointprims`), (b) flags del terminal, (c) binding
  `geometry`/`camera`, (d) lectura sin asentar.
- **"Dibuja pero no sé si es mío"** → auto-torus (`autotorus_masks_render`). Toggle del flag
  `render` del terminal: si el render no cae a 0, no es tuyo.
- **"El uniform no anima"** → ver `td-live-verification`: el reloj puede estar parado y la lectura
  sin asentar devuelve el estado anterior. Verificá por `poptoCHOP`, no por píxeles.
- **`TDPerlinNoise()` no existe en compute shaders** → escribí el ruido a mano (hash + interpolación)
  o pasá una textura por sampler.
- **El render dejó de actualizarse tras muchas iteraciones** (solo rewire/flags sobre el mismo
  geometryCOMP) → reconstruí el chain/la red; el estado wedgeado se cura con un build limpio.
- **Scripts de build propios**: agregá `if __name__ == "__main__":` — si no, importarlo ejecuta el
  build completo (y su `sys.exit()` mata al importador).

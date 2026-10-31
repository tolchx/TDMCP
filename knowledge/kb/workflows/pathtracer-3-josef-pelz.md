---
id: "pathtracer-3-josef-pelz"
title: "PathTracer 3.0.1 (Josef Pelz) — Flujo Completo con POPs, PT_GEO, PT_MAT y PT_LIGHT"
category: "workflow"
tags: ["pathtracer", "josef pelz", "PT_FAM", "PT_GEO", "PT_MAT", "PT_LIGHT", "POPs", "DLSS", "raytracing", "PBR", "volumetric haze", "caustics"]
touchdesigner_version: "2025.32460+"
---

# PathTracer 3.0.1 (Josef Pelz) — Flujo Completo de Trabajo con POPs en TouchDesigner

## 1. Visión General de la Arquitectura (`PT_FAM`)

**PathTracer 3.0.1** de Josef Pelz (`PT_FAM.tox`) es un motor de path tracing en tiempo real basado íntegramente en **POPs (Point Operators)** y `glslPOP` (con soporte de hardware ray queries en Windows y BVH por software en macOS), integrado con **NVIDIA DLSS Ray Reconstruction** (`DlssTOP.dll`) y modo de acumulación progresiva (`Accumulate`).

El sistema `PT_FAM` registra 4 operadores personalizados (ubicados internamente en `/project1/PT_FAM/PT_OPs/`):

| Componente | Tipo Base | `parentshortcut` | Función Principal |
|---|---|---|---|
| **`Pathtracer`** | `baseCOMP` | `PT` | Motor de trazado de rayos, cámara física (DOF), mundo/HDRI, niebla volumétrica (`Haze`), denoiser (`Dlss` / `Accumulate`) y salidas AOV (`out1..out8`). |
| **`PT_GEO`** | `geometryCOMP` | `PTGeo` | Adaptador de geometría POP: recibe un `POP` por cable (Input 0) o por parámetro `Geometry` (`POP`, `gltfinCOMP`, `fbxCOMP`), aplica su transformación 3D y asigna un `PT_MAT`. |
| **`PT_MAT`** | `baseCOMP` | `PTMat` | Material físico PBR con `Transmission`, absorción Beer-Lambert (`Absorptioncolor`/`Absorptiondistance`), `Dispersion`, `Clearcoat`, `Sheen`, `Thinfilm`, `Opacity`/`Cutout`, `Emitstrength`, `Pointradius`, `Linewidth` y mapas TOP / `substanceTOP`. |
| **`PT_LIGHT`** | `geometryCOMP` | `PTLight` | Fuente de luz física que apunta hacia **`-Z`**: `Point`, `Spot` (con `Projectormap` Gobo), `Rect` (etiqueta UI `"Rectangle"`), `Disk`, `Sphere`, `Sun` o `Mesh` (cualquier `POP` como malla emisiva). |

---

## 2. Reglas de Oro para Construcción vía MCP / Python

### Regla 1: `allowCooking = True` al clonar `PT_GEO`, `PT_MAT` o `PT_LIGHT`
Dentro de `/project1/PT_FAM/PT_OPs/`, los maestros `PT_GEO`, `PT_MAT` y `PT_LIGHT` vienen con **`allowCooking = False`**. Cuando se instancian con `parent.copy(...)` desde Python, **siempre** debes habilitar `allowCooking = True`:
```python
geo = p1.copy(op('/project1/PT_FAM/PT_OPs/PT_GEO'), name='pt_geo_mi_objeto')
geo.allowCooking = True
geo.bypass = False
geo.render = True
```

### Regla 2: Auto-descubrimiento por hermanos (`Siblings`) y `render` Flag
- Por defecto, `Pathtracer.par.Geometry = '*'` y `Pathtracer.par.Lights = '*'`.
- El `Pathtracer` encuentra automáticamente todos los `PT_GEO` y `PT_LIGHT` ubicados en el **mismo COMP padre** que tengan tanto su parámetro `Render` (`par.render == True`) como su **flag de render de TouchDesigner** (`op.render == True`) encendidos.
- **Modo de compatibilidad nativa TD (`td_geo` y `TDLight`):** También renderiza automáticamente cualquier `geometryCOMP`, `gltfinCOMP`, `fbxCOMP`, `pbrMAT`, `phongMAT`, `lightCOMP`, `environmentlightCOMP` y cualquier **`POP` suelto con `op.render = True`** que sea hermano del `Pathtracer`.

### Regla 3: Nombres Internos de Menús (`menuNames`)
- **`PT_LIGHT.par.Type`**: `'Point'`, `'Spot'`, **`'Rect'`** *(¡no `'Rectangle'`!)*, `'Disk'`, `'Sphere'`, `'Sun'`, `'Mesh'`.
- **`Pathtracer.par.Method`**: **`'Dlss'`**, `'Accumulate'`.
- **`Pathtracer.par.Quality`**: `'Dlaa'`, `'Quality'`, `'Balanced'`, `'Performance'`, `'Ultraperformance'`.
- **`Pathtracer.par.OutputsNshow`**: `'Shaded'`, `'Albedo'`, `'Normal'`, `'Depth'`, `'Motion'`, `'Roughness'`, `'Material'`, `'Emission'`.

### Regla 4: Parche de Compatibilidad en TouchDesigner `2025.32460`
`PT_FAM.tox` (`3.0.1`) fue guardado en `2025.33230`. En `2025.32460`:
1. El nodo `tri` dentro de `PT_GEO`, `PT_LIGHT/mesh` y `Pathtracer/scene/td_geo` se carga como `baseCOMP` vacío; debe reemplazarse por un `triangulatePOP` (`tri.par.triangulatequads = True`) conectado `has_faces -> tri -> xf`.
2. `POP.numPrims(max=True, primType=...)` devuelve `-1` cuando hay `0` primitivas de ese tipo; debe envolverse en `max(..., 0)` en las expresiones de `PT_GEO` y usar `> 0` en `Pathtracer/py/scene._with()`.
*(La herramienta MCP `td_setup_pathtracer3` aplica este parche automáticamente).*

---

## 3. Primitivas POP Soportadas y Atributos por Punto/Vértice

`PT_GEO` separa automáticamente cualquier `POP` de entrada en tres salidas internas (`faces`, `lines`, `points`):

1. **Superficies (`triangles` y `quads`):** Se triangulan mediante `triangulatePOP(triangulatequads=True)`. Si no tienen atributo `N`, `PT_GEO/nrm` calcula normales de vértice.
2. **Nubes de Puntos (`pointPrims`):** Cualquier `POP` con primitivas de punto (`gridPOP(surftype='points')`, `particlePOP`, `convertPOP(convert='topointprims')`) se traza como **esferas analíticas exactas**. Su radio es el atributo `PointScale` (si existe y `>= 0`) o `PT_MAT.par.Pointradius` (default `0.05`).
3. **Líneas y Line Strips (`lines` y `lineStrips`):** `circlePOP`, `linePOP`, `trailPOP` se convierten en **tubos cilíndricos 3D** con tapas esféricas/planas mediante `Pathtracer/scene/tubes`. Su diámetro es `2 * PointScale` (si existe y `>= 0`) o `PT_MAT.par.Linewidth` (default `0.02`).

### Tabla de Atributos POP Leídos por `PT_GEO`

| Atributo POP | Tipo | Comportamiento en el PathTracer |
|---|---|---|
| `P` | `vec3` | Posición 3D del punto. |
| `N` | `vec3` | Normal de superficie (si falta en caras, se calcula automáticamente). |
| `Tex` | `vec2` / `vec3` | Coordenadas UV para todos los mapas de textura del `PT_MAT`. |
| `Color` | `vec3` / `vec4` | **Multiplica** el `Basecolor` del `PT_MAT`. |
| `Roughness` | `float` | **Reemplaza** el `Roughness` del `PT_MAT` por punto/vértice/primitiva. |
| `Metallic` | `float` | **Reemplaza** el `Metallic` del `PT_MAT` por punto/vértice/primitiva. |
| `Transmission` | `float` | **Reemplaza** el `Transmission` del `PT_MAT` por punto/vértice/primitiva. |
| `Emit` | `float` | **Reemplaza** el `Emitstrength` del `PT_MAT` por punto/vértice/primitiva. |
| `PointScale` | `float` | **Reemplaza** `Pointradius` (esferas) o mitad de `Linewidth` (tubos) por punto. |
| `PartVel` (o `par.Velocity`) | `vec3` | Vector de velocidad por punto para los vectores de movimiento 3D de DLSS. |

---

## 4. Características Avanzadas del Renderizador

- **Cáusticas de Vidrio (`Pathtracer.par.Glassshadows = True`):** Permite que los rayos de sombra atraviesen superficies refractivas (`Transmission > 0`, `Roughness` bajo), proyectando cáusticas coloreadas por la absorción Beer-Lambert (`Absorptioncolor`, `Absorptiondistance`) del vidrio.
- **Niebla Volumétrica (`Pathtracer.par.Hazedensity > 0`):** Medio participativo con dispersión anisotrópica (`Hazeanisotropy` `-0.9` a `0.9`), caída por altura (`Hazefalloff`, `Hazeheight`) y ruido 3D heterogéneo (`Hazevariation`, `Hazescale`, `Hazedrift`) o textura 3D (`Hazetexture`). Cada `PT_LIGHT` tiene un toggle `Haze` para decidir si ilumina la niebla.
- **Salidas AOV (`Pathtracer.seq.Outputs`):** Permite exportar simultáneamente hasta 8 conectores TOP (`out1..out8`) con `Shaded`, `Albedo`, `Normal`, `Depth`, `Motion`, `Roughness`, `Material` o `Emission`. Después de cambiar `pt.seq.Outputs.numBlocks` por Python, invocar `pt.op('views/outputs').module.sync(pt)`.
- **Picking Espacial en GPU (`pick()`):** `pt.op('py/scene').module.pick(pt, u, v, ctrl=False)` devuelve el operador material (`PT_MAT` / `pbrMAT`) bajo las coordenadas normalizadas `(u, v)`, y con `ctrl=True` devuelve el objeto geométrico (`PT_GEO` / `geometryCOMP` / `POP`).

---

## 5. Estabilidad Temporal en Animación, Humo Volumétrico (`Haze`) y Optimización a 60 FPS (Contrato C23)

### 5.1 Estabilidad Temporal en Escenas POP Animadas (`0` frames caídos)
1. **Activar LBVH Síncrono (`Pathtracer/scene.par.Software = 1`):**
   - En TouchDesigner `2025.32460`, el rebuild asíncrono de la estructura de aceleración Vulkan de hardware (`colpop` / `rayQueryEXT`) sobre POPs animados deja ~25% de los frames vacíos (la geometría desaparece por un frame).
   - Fijar `pt.op('scene').par.Software = 1` fuerza el uso del **LBVH síncrono en GPU (`scene/bvh/tree` + `scene/bvh/items`)**, eliminando por completo los parpadeos (`0/24` frames caídos).
2. **`allowCooking = True` recursivo en sub-COMPs:**
   - Al clonar `Pathtracer`, `PT_GEO`, `PT_MAT` o `PT_LIGHT`, habilitar `allowCooking = True` tanto en el nodo raíz como en todos sus hijos `COMP` (`for c in node.findChildren(type=COMP): c.allowCooking = True`).
3. **Continuidad orbital en `glslPOP` y guardia de precisión de tiempo:**
   - Usar siempre `float t = mod(uTime, 3600.0);` para evitar pérdida de precisión float32 cuando `absTime.seconds` supera varias horas.
   - En movimientos orbitales/vórtices (`theta = baseAngle + t * omega`), $\omega$ debe depender **únicamente del radio/anillo base fijo de la partícula (`id`)**, nunca de una coordenada variable con el tiempo ($\Delta\theta \approx t \cdot \Delta\omega$ produce saltos caóticos de ~700°/frame).
   - Dejar `PT_GEO.par.Velocity = ''` cuando el conteo de puntos es constante para que `PT_GEO/pts_cache` (`cachePOP`) calcule diferencias exactas de posición cuadro a cuadro para DLSS.

### 5.2 Receta Verificada de Humo Volumétrico Turbulento (`Haze` + Gobo `Spot`)
- **Iluminación volumétrica selectiva (`PT_LIGHT.par.Haze`):**
  - **Apagar `par.Haze = False`** en luces de área grandes (`Type = 'Rect'`) de relleno para que iluminen y refracten en las superficies de vidrio sin lavar el contraste del humo.
  - **Encender `par.Haze = True`** únicamente en luces puntuales/direccionales (`Sphere` en el núcleo + `Spot` cenital con un `noiseTOP` animado conectado a `Projectormap` como Gobo volumétrico).
- **Configuración de `Pathtracer` (página `Atmosphere`):**
  - `Hazedensity = 0.14`, `Hazeanisotropy = 0.68` (dispersión frontal Mie).
  - `Hazevariation = 1.0`, `Hazescale = 2.6` (100% de turbulencia FBM 3D para bocanadas de humo densas y huecos oscuros).
  - `Hazesamples = 4`, `Hazemultiple = False` (dispersión simple para alto contraste).
  - Deriva 3D continua ascendente en remolino:
    - `Hazedriftx.expr = "0.35 * math.sin((absTime.seconds % 3600.0) * 0.4)"`
    - `Hazedrifty.expr = "-0.38 * (absTime.seconds % 3600.0)"`
    - `Hazedriftz.expr = "0.35 * math.cos((absTime.seconds % 3600.0) * 0.4)"`
- **Evitar bloqueo central:** No situar una esfera grande en `(0, y, 0)` directamente bajo el `Spot` cenital con `Glassshadows = True`, ya que eclipsa el haz volumétrico del Gobo.

### 5.3 Optimización para 60 FPS en Tiempo Real (`9 FPS / 130 ms` → `60 FPS / 15 ms`)
1. **Medición real de FPS:** Con `project.realTime = True`, `absTime.frame` salta cuadros para seguir el reloj; medir siempre con `performCHOP['fps']`, `performCHOP['msec']` y `op('Pathtracer1/trace/flex').gpuCookTime`.
2. **Piso de 2 triángulos sin línea de horizonte (`rows=2, cols=2, sizex=45, sizey=45`):**
   - Un `gridPOP` por defecto (`20×20` = `722` triángulos) + `spherePOP` poligonal (`500` triángulos) cargaban `1,226` primitivas en el LBVH de triángulos (`scene/faces`).
   - Fijar `floor_pop.par.rows = 2, cols = 2, sizex = 45.0, sizey = 45.0` reduce el piso a **`2` triángulos** y elimina la línea horizontal de corte del horizonte al fondo.
   - Usar exclusivamente **esferas analíticas (`pointPrims`)** en lugar de `spherePOP` poligonales (`scene/faces` baja de `1,226` a `6` primitivas).
3. **Presupuesto de partículas y parámetros de `Pathtracer` para 60 FPS (`1280×720`):**
   - **Esferas analíticas refractivas con `Glassshadows` + `Haze`:** **`64` a `96` esferas** (`8×8` a `8×12`) con radio compensado (`PointScale` `0.075–0.145`).
   - **`Samples = 1`** (1 SPP por cuadro reconstruido temporalmente por DLSS Ray Reconstruction; `Samples = 3` triplica el tiempo de GPU).
   - **`Bounces = 4`**, **`Hazesamples = 4`**, **`Method = 'Dlss'`**, **`Quality = 'Balanced'`** (reduce `trace/flex` de `95.33 ms` a `9.70 ms` y alcanza `58–60 FPS` constantes).

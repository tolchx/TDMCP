# PathTracer 3.0.1 (Josef Pelz, `PT_FAM`) — Documentación, Pruebas Empíricas y Builder MCP

## 1. Visión General de la Arquitectura (`PT_FAM`)

**PathTracer 3.0.1** de Josef Pelz (`PT_FAM.tox`) es un motor de path tracing Monte Carlo en GPU basado íntegramente en **POPs (Point Operators)** y `glslPOP` (con soporte de hardware ray queries en Windows y BVH por software en macOS), integrado con **NVIDIA DLSS Ray Reconstruction** (`DlssTOP.dll`) y modo de acumulación progresiva (`Accumulate`).

El sistema `PT_FAM` registra los operadores en `/project1/PT_FAM/PT_OPs/`:

| Componente | Tipo Base | `parentshortcut` | Función Principal |
|---|---|---|---|
| **`Pathtracer`** | `baseCOMP` | `PT` | Motor de trazado de rayos, cámara física (DOF), mundo/HDRI, niebla volumétrica (`Haze`), denoiser (`Dlss` / `Accumulate`) y salidas AOV (`out1..out8`). |
| **`PT_GEO`** | `geometryCOMP` | `PTGeo` | Adaptador de geometría POP: recibe un `POP` por cable (Input 0) o por parámetro `Geometry` (`POP`, `gltfinCOMP`, `fbxCOMP`), aplica su transformación 3D y asigna un `PT_MAT`. |
| **`PT_MAT`** | `baseCOMP` | `PTMat` | Material físico PBR con `Transmission`, absorción Beer-Lambert (`Absorptioncolor`/`Absorptiondistance`), `Dispersion`, `Clearcoat`, `Sheen`, `Thinfilm`, `Opacity`/`Cutout`, `Emitstrength`, `Pointradius`, `Linewidth` y mapas TOP / `substanceTOP`. |
| **`PT_LIGHT`** | `geometryCOMP` | `PTLight` | Fuente de luz física que apunta hacia **`-Z`**: `Point`, `Spot` (con `Projectormap` Gobo), `Rect` (etiqueta UI `"Rectangle"`), `Disk`, `Sphere`, `Sun` o `Mesh` (cualquier `POP` como malla emisiva). |

---

## 2. Reglas de Oro y Contrato C23 (`VERIFIED_CONTRACTS.md`)

1. **`allowCooking = True` al clonar `PT_GEO`, `PT_MAT` o `PT_LIGHT`**:
   Dentro de `/project1/PT_FAM/PT_OPs/`, los maestros vienen con **`allowCooking = False`**. Al instanciar con `parent.copy(...)` desde Python, **siempre** habilitar `node.allowCooking = True`, `node.bypass = False` y (en `PT_GEO`/`PT_LIGHT`) `node.render = True`.
2. **Auto-descubrimiento por hermanos (`Siblings`) y `render` Flag**:
   Por defecto, `Pathtracer.par.Geometry = '*'` y `Pathtracer.par.Lights = '*'`. El `Pathtracer` descubre todos los `PT_GEO` y `PT_LIGHT` en el mismo COMP padre con `par.render == True` y `op.render == True`, además de operadores nativos de TouchDesigner (`geometryCOMP`, `gltfinCOMP`, `fbxCOMP`, `pbrMAT`, `phongMAT`, `lightCOMP`, `environmentlightCOMP`, y cualquier `POP` suelto con `op.render = True`).
3. **Nombres Internos de Menús (`menuNames`)**:
   - **`PT_LIGHT.par.Type`**: `'Point'`, `'Spot'`, **`'Rect'`** *(¡no `'Rectangle'` ni `'Area'`!)*, `'Disk'`, `'Sphere'`, `'Sun'`, `'Mesh'`.
   - **`Pathtracer.par.Method`**: **`'Dlss'`**, `'Accumulate'`.
   - **`Pathtracer.par.Quality`**: `'Dlaa'`, `'Quality'`, `'Balanced'`, `'Performance'`, `'Ultraperformance'`.
   - **`Pathtracer.par.OutputsNshow`**: `'Shaded'`, `'Albedo'`, `'Normal'`, `'Depth'`, `'Motion'`, `'Roughness'`, `'Material'`, `'Emission'`.
4. **Parche Automático de Compatibilidad en TouchDesigner `<= 2025.32460`**:
   `PT_FAM.tox` (`3.0.1`) fue guardado en `2025.33230`. En `2025.32460`:
   - El nodo `tri` dentro de `PT_GEO`, `PT_LIGHT/mesh` y `Pathtracer/scene/td_geo` se carga como `baseCOMP` vacío; debe reemplazarse por un `triangulatePOP` (`tri.par.triangulatequads = True`) conectado `has_faces -> tri -> xf`.
   - `POP.numPrims(max=True, primType=...)` devuelve `-1` cuando hay `0` primitivas de ese tipo; debe envolverse en `max(..., 0)` en las expresiones de `PT_GEO` y usar `> 0` en `Pathtracer/py/scene._with()`.
   *(La herramienta MCP `td_setup_pathtracer3` aplica este parche automáticamente).*

---

## 3. Primitivas POP y Atributos por Punto/Vértice

`PT_GEO` separa automáticamente cualquier `POP` de entrada en tres salidas internas (`faces`, `lines`, `points`):

- **Superficies (`triangles` y `quads`):** Se triangulan mediante `triangulatePOP(triangulatequads=True)`. Si no tienen atributo `N`, `PT_GEO/nrm` calcula normales de vértice.
- **Nubes de Puntos (`pointPrims`):** Cualquier `POP` con primitivas de punto (`gridPOP(surftype='points')`, `particlePOP`, `convertPOP(convert='topointprims')`) se traza como **esferas analíticas exactas**. Su radio es el atributo `PointScale` (si existe y `>= 0`) o `PT_MAT.par.Pointradius` (default `0.05`).
- **Líneas y Line Strips (`lines` y `lineStrips`):** `circlePOP`, `linePOP`, `trailPOP` se convierten en **tubos cilíndricos 3D** con tapas mediante `Pathtracer/scene/tubes`. Su diámetro es `2 * PointScale` (si existe y `>= 0`) o `PT_MAT.par.Linewidth` (default `0.02`).

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

## 4. Batería de 6 Pruebas Empíricas en TouchDesigner (`PASS` / 0 Errores)

Todas las pruebas fueron ejecutadas contra TouchDesigner `2025.32460` en vivo vía MCP (`127.0.0.1:13316`):

| Test | Escenario Verificado | Samples | `mean_lum` | `std_lum` | Veredicto |
|---|---|---:|---:|---:|---|
| **Test 1** | Primera escena (`PT_GEO` + `PT_MAT` + `PT_LIGHT` `Rect`) + `pick(u,v)` (`picked_mat="/project1/pt_mat_sphere"`, `picked_obj="/project1/pt_geo_sphere"`) | 132 | 87.06 | 62.66 | `PASS` |
| **Test 2** | Escena híbrida nativa TD (`geometryCOMP` + `pbrMAT` + `lightCOMP` + `torusPOP` suelto con `render=True`) | 122 | 49.69 | 45.73 | `PASS` |
| **Test 3** | Galería de materiales PBR (`Transmission=1.0`, `Absorptioncolor`, `Clearcoat`, `Thinfilm`) + `Glassshadows=True` (cáusticas) | 140 | 97.18 | 53.78 | `PASS` |
| **Test 4** | Esferas POP analíticas (`gridPOP(surftype='points')`) + tubos 3D (`circlePOP`) + atributos por punto (`Color`, `Roughness`, `Metallic`, `PointScale`, `Emit`) | 152 | 101.79 | 56.50 | `PASS` |
| **Test 5** | Niebla volumétrica (`Hazedensity=0.06`, `Hazeanisotropy=0.6`) + `Spot` con Gobo (`Projectormap`) + `Mesh` Light (`torusPOP`) | 150 | 65.74 | 43.25 | `PASS` |
| **Test 6** | Multi-AOV (`Outputs` sequence: `out1=Shaded`, `out2=Normal`, `out3=Albedo`, `out4=Depth`) sincronizado vía `views/outputs.module.sync(pt)` | 204 | 133.05 | 55.20 | `PASS` |

---

## 5. Uso del Builder en Vivo `td_setup_pathtracer3` (Pilar 26)

La herramienta MCP `td_setup_pathtracer3` construye y verifica en una sola llamada estudios completos con PathTracer 3.0.1:

```json
{
  "parent_path": "/project1",
  "pt_fam_path": "/project1/PT_FAM",
  "preset": "studio_caustics",
  "method": "Accumulate",
  "resolution": [1280, 720],
  "bounces": 8,
  "glass_shadows": true,
  "enable_aovs": true
}
```

Presets soportados:
- **`studio`**: Suelo optimizado (`2×2` = `2` triángulos, `45×45` sin línea de horizonte) + esfera con `Clearcoat` + `PT_LIGHT` (`Rect`).
- **`vortex_haze_60fps`**: Vórtice animado de `64` esferas analíticas traslúcidas (`8×8` en `glslPOP` con velocidad angular kepleriana estable) + humo volumétrico turbulento 3D (`Hazevariation=1.0`, `Hazescale=2.6`, `Hazemultiple=False`, `Hazedrift` ascendente) + `Spot` cenital con Gobo `noiseTOP` + LBVH síncrono (`Software=1`) calibrado para **60 FPS** (`Samples=1`, `Bounces=4`, `Hazesamples=4`, `Quality='Balanced'`).

---

## 6. Estabilidad Temporal en Animación, Humo Volumétrico (`Haze`) y Optimización a 60 FPS (Contrato C23)

1. **LBVH Síncrono en GPU (`Pathtracer1/scene.par.Software = 1`) para POPs Animados:**
   - En TouchDesigner `2025.32460`, el rebuild asíncrono de la estructura de aceleración Vulkan de hardware (`colpop` / `rayQueryEXT`) deja ~25% de los cuadros vacíos cuando un POP cambia de posición cada frame.
   - Fijar `pt.op('scene').par.Software = 1` activa el **LBVH síncrono en GPU (`scene/bvh/tree` + `scene/bvh/items`)** de PathTracer (`0` frames caídos en secuencias de 12 y 24 cuadros).
2. **Continuidad Orbital en Shaders `glslPOP`:**
   - Usar siempre `float t = mod(uTime, 3600.0);` para preservar precisión float32 tras horas de ejecución.
   - La velocidad angular $\omega_i$ debe depender únicamente del radio/anillo base fijo de la partícula (`id`), nunca de una coordenada dependiente del tiempo, y `PT_GEO.par.Velocity` se deja en `''` para que `PT_GEO/pts_cache` (`cachePOP`) calcule vectores de movimiento exactos para DLSS.
3. **Humo Volumétrico Turbulento (`Haze`) e Iluminación Selectiva:**
   - Apagar **`par.Haze = False`** en luces de área grandes (`Rect`) para que iluminen las esferas de vidrio sin lavar el contraste del humo.
   - Encender **`par.Haze = True`** únicamente en luces puntuales/focalizadas (`Sphere` en el núcleo + `Spot` cenital con un `noiseTOP` animado en `Projectormap`).
   - Configurar `Hazedensity = 0.14`, `Hazeanisotropy = 0.68`, `Hazevariation = 1.0`, `Hazescale = 2.6`, `Hazesamples = 4`, `Hazemultiple = False` y deriva `Hazedrift` en espiral ascendente.
4. **Presupuesto de 60 FPS en Tiempo Real (`9 FPS / 130 ms` → `60 FPS / 15 ms`):**
   - Medir siempre los FPS reales con `performCHOP['fps']` y `performCHOP['msec']` (ya que con `project.realTime = True`, `absTime.frame` salta cuadros).
   - Reducir el piso `gridPOP` a `rows = 2, cols = 2` (**`2` triángulos**) y `sizex = 45.0, sizey = 45.0` (elimina la línea de corte del horizonte y baja `scene/faces` de `1,226` a `6` primitivas).
   - Usar **`64` a `96` esferas analíticas (`pointPrims`)** con `PointScale` compensado (`0.075–0.145`), `Samples = 1`, `Bounces = 4`, `Hazesamples = 4` y `Quality = 'Balanced'`, reduciendo `trace/flex` de **`95.33 ms` a `9.70 ms`**.

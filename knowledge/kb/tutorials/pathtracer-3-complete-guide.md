---
id: "pathtracer-3-complete-guide"
title: "Guía Completa y Pruebas Empíricas de PathTracer 3.0.1 (Josef Pelz) en TouchDesigner"
category: "tutorial"
tags: ["pathtracer", "josef pelz", "tutorial", "PT_FAM", "PT_GEO", "PT_MAT", "PT_LIGHT", "POPs", "DLSS", "AOV", "haze", "caustics"]
source_video: "https://www.youtube.com/watch?v=E4zUpBiYQqE"
source_docs: "https://pathtracer.josefpelz.com"
---

# Guía Completa y Pruebas Empíricas de PathTracer 3.0.1 (Josef Pelz)

Basada en la transcripción completa del tutorial oficial de lanzamiento (`https://www.youtube.com/watch?v=E4zUpBiYQqE`, 26:21), las 18 páginas de la documentación oficial (`https://pathtracer.josefpelz.com`) y 6 pruebas empíricas verificadas en vivo en TouchDesigner `2025.32460`.

---

## 1. Resumen del Tutorial Oficial de Josef Pelz (`E4zUpBiYQqE`)

1. **`[00:00 - 02:27]` Introducción y Flujo con `PT_FAM`:**
   - `PT_FAM.tox` utiliza el sistema `TDFam`: al arrastrarlo al proyecto expone `Pathtracer`, `PT_GEO`, `PT_MAT` y `PT_LIGHT` bajo la familia `PT` en el OP Create Dialog (Tab).
   - Requiere el plugin `DlssTOP.dll` (basado en `TouchEngine-DLSS` de Buchwald / NVIDIA NGX) ubicado por defecto en `Documents/Derivative/Pathtracing/DlssTOP.dll`.
2. **`[02:27 - 05:31]` Modos de Denoising (`Dlss` vs `Accumulate`) y Picking Interactivo:**
   - `Dlss`: Denoising temporal en tiempo real con **DLSS Ray Reconstruction** y calidades `Dlaa` (nativa), `Quality` (1.5x), `Balanced` (1.7x), `Performance` (2.0x) y `Ultraperformance` (3.0x).
   - `Accumulate`: Acumula muestras progresivamente mientras la escena está estática hasta `Maxsamples` (`0` = infinito).
   - Con el visor del `Pathtracer` activo, **Click izquierdo** selecciona en la red el material (`PT_MAT`) del píxel clickeado, y **Ctrl + Click izquierdo** selecciona el objeto (`PT_GEO`).
3. **`[05:31 - 08:23]` `PT_GEO`, Transformaciones, Instancing y Vectores de Velocidad:**
   - `PT_GEO` es un `geometryCOMP` completo: soporta traslación, rotación, escala, jerarquías padre-hijo e **Instancing** en su página `Instance`.
   - Calcula vectores de movimiento 3D automáticamente cuando el conteo de puntos es constante o el objeto se mueve por transformación; si la topología cambia cada frame (ej. sistemas de partículas con nacimientos/muertes), usa el atributo POP nombrado en `Velocity` (default `PartVel`).
4. **`[08:23 - 13:34]` `PT_MAT` y Sobreescritura por Atributos POP:**
   - Además de PBR estándar (`Basecolor`, `Metallic`, `Roughness`, `Ior`), incluye `Transmission` con ley de **Beer-Lambert** (`Absorptioncolor`, `Absorptiondistance`), `Dispersion` cromática, `Clearcoat`, `Sheen` (terciopelo), `Thinfilm` (iridiscencia en nm), `Opacity` / `Cutout` y `Emitstrength` (`Emitlights = True` activa muestreo directo de triángulos/esferas/tubos emisivos).
   - Permite conectar un `substanceTOP` directamente al parámetro `Substance` para mapear todos los canales PBR automáticamente.
   - Los atributos POP `Color`, `Roughness`, `Metallic`, `Transmission`, `Emit` y `PointScale` sobreescriben los valores del material punto por punto.
5. **`[13:34 - 18:10]` Esferas Analíticas (`pointPrims`) y Tubos 3D (`lineStrips`):**
   - Las nubes de puntos (`pointPrims`) se trazan como esferas analíticas perfectas (`Pointradius` / `PointScale`).
   - Las líneas (`lines` / `lineStrips`) se convierten en tubos 3D (`Linewidth` / `PointScale`).
6. **`[18:10 - 22:09]` `PT_LIGHT`, Cáusticas (`Glassshadows`) y Niebla Volumétrica (`Haze`):**
   - `PT_LIGHT` soporta luces analíticas (`Point`, `Spot`, `Rect`, `Disk`, `Sphere`, `Sun`) y luces de malla arbitraria (`Mesh`).
   - `Spot` soporta un `Projectormap` (TOP Gobo) que proyecta texturas tanto en superficies como a través de la niebla volumétrica (`Haze`).
7. **`[22:09 - 26:21]` Compatibilidad Nativa TD, AOVs y Optimización (`Optimize` / `Lockinput`):**
   - `Pathtracer` renderiza nativamente `geometryCOMP`, `gltfinCOMP`, `fbxCOMP`, `pbrMAT`, `phongMAT`, `lightCOMP`, `environmentlightCOMP` y `POP`s sueltos con `render = True`.
   - El botón `Optimize` especializa las constantes del shader (`trace/trace`) para ganar ~30–40% de FPS una vez que las características de la escena están fijas.

---

## 2. Resumen de las 6 Pruebas Empíricas Verificadas en Vivo

Todas las pruebas fueron ejecutadas y verificadas con `0` errores en TouchDesigner `2025.32460` (código completo en `C:/Users/Tolch/Documents/AI_Code/PachTracer_POPs/tests/run_pathtracer_tests.py`):

1. **Test 1 — Escena Inicial y Picking GPU (`PASS`, `mean_lum=87.06`):**
   - `spherePOP` + `gridPOP` -> `PT_GEO` + `PT_MAT` (`Clearcoat=1.0`) + `PT_LIGHT` (`Type='Rect'`, `Strength=80.0`, `rx=-90`).
   - Verificado `pt.op('py/scene').module.pick(pt, 0.5, 0.45, ctrl=False)` -> `/project1/pt_mat_sphere` y `ctrl=True` -> `/project1/pt_geo_sphere`.
2. **Test 2 — Compatibilidad Nativa TD (`PASS`, `mean_lum=49.69`):**
   - `geometryCOMP` (`torus1`) + `pbrMAT` + `gridPOP`/`transformPOP` suelto con `render=True` + `lightCOMP` nativo renderizados a través de `Pathtracer1/scene/td_geo`.
3. **Test 3 — Showroom `PT_MAT` y Cáusticas `Glassshadows` (`PASS`, `mean_lum=97.18`):**
   - 4 esferas: Oro (`Metallic=1, Roughness=0.08`), Vidrio (`Transmission=1, Ior=1.52, Absorptiondistance=0.6` + `Glassshadows=True`), Terciopelo Iridiscente (`Sheen=1, Thinfilm=0.8, Thinfilmthickness=480`), y Neón Emisivo (`Emitstrength=18, Emitlights=True`).
4. **Test 4 — Tubos 3D, Esferas Analíticas y Atributos por Punto (`PASS`, `mean_lum=101.79`):**
   - `circlePOP` + `noisePOP` -> `PT_GEO` (`Linewidth=0.055`) + `gridPOP(surftype='points')` -> `glslPOP` (`Color`, `PointScale`, `Roughness`, `Metallic` por punto).
5. **Test 5 — Niebla Volumétrica (`Haze`), Spotlight `Projectormap` y `Mesh` Light (`PASS`, `mean_lum=65.74`):**
   - `Hazedensity=0.14, Hazeanisotropy=0.55, Hazevariation=0.35` + `Spot` con `rampTOP` radial como Gobo + `Mesh` light con `torusPOP`.
6. **Test 6 — Multi-Canal AOVs (`Shaded`, `Normal`, `Depth`, `Albedo`) + DOF (`PASS`, `mean_lum=133.05`):**
   - `pt.seq.Outputs.numBlocks = 4` + `pt.op('views/outputs').module.sync(pt)` + `viewer = True` en `out1..out4`, generando los 4 pases simultáneamente.
7. **Test 7 — Vórtice Animado de Esferas Analíticas Traslúcidas + Humo Volumétrico FBM 3D (`Haze`) a 60 FPS (`PASS`, `0` frames caídos, `58–60 FPS`, `15.0–17.3 ms/frame`):**
   - Activado `Pathtracer1/scene.par.Software = 1` (LBVH síncrono en GPU) eliminando el ~25% de frames vacíos del BLAS asíncrono de hardware en POPs animados.
   - Configurado humo turbulento 3D (`Hazedensity=0.14, Hazeanisotropy=0.68, Hazevariation=1.0, Hazescale=2.6, Hazesamples=4, Hazemultiple=False` + deriva espiral `Hazedrift`) con iluminación volumétrica selectiva (`Haze=False` en luces `Rect` de relleno, `Haze=True` en luz `Sphere` del núcleo + `Spot` cenital con `noiseTOP` Gobo en `Projectormap`).
   - Optimizado de `9.0 FPS` (`130.0 ms`, `trace/flex=95.3 ms`) a **`58–60 FPS`** (`15.0–17.3 ms`, `trace/flex=9.7 ms`) reduciendo el piso a `2×2` (`2` triángulos, `sizex=45, sizey=45` sin línea de horizonte), usando `64` esferas analíticas (`8×8` en `glslPOP` con `mod(uTime, 3600.0)` y $\omega_i$ fijo por anillo) y fijando `Samples=1, Bounces=4, Quality='Balanced'`.

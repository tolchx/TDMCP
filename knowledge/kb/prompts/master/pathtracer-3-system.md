---
id: "pathtracer-3-system"
title: "Sistema PathTracer 3.0.1 (Josef Pelz) con POPs, Materiales PBR Avanzados, Luces Físicas y Haze Volumétrico"
project_type: "rendering"
complexity: "experto"
application: "produccion_visual"
touchdesigner_min_version: "2025.32460"
hardware: "GPU NVIDIA RTX (con DLSS Ray Reconstruction) o GPU compatible con Vulkan Ray Queries / BVH"
performance: "30-60 fps interactivo con DLSS, o acumulación progresiva sin límite de muestras"
validation:
  - "PT_FAM cargado y parcheado para compatibilidad con 2025.32460 (triangulatePOP + max(numPrims, 0))"
  - "Todos los PT_GEO, PT_MAT y PT_LIGHT clonados tienen allowCooking = True y render = True"
  - "Pathtracer1 sin errores recursivos (pt.errors(recurse=True) == '')"
  - "Evaluación visual PASS en out1 (rango dinámico y contraste verificados)"
---

# Prompt Maestro: {{title}}

## Objetivo
Construir desde cero en `/project1` un sistema completo de **PathTracer 3.0.1 (Josef Pelz)** utilizando los componentes de `PT_FAM` (`Pathtracer`, `PT_GEO`, `PT_MAT`, `PT_LIGHT`) combinados con operadores **POP (`spherePOP`, `gridPOP`, `circlePOP`, `noisePOP`, `glslPOP`)**, materiales físicos avanzados (metales, vidrio refractivo con absorción Beer-Lambert y cáusticas `Glassshadows`, terciopelo con `Sheen` y `Thinfilm`, geometría emisiva), iluminación física (`Rect`, `Spot` con Gobo, `Mesh` light) y niebla volumétrica (`Haze`).

## Reglas Críticas del Contrato C23 (Obligatorias)
1. **Parche de Compatibilidad `2025.32460`:** Si `PT_FAM` fue guardado en `2025.33230` y corre en `2025.32460`, asegurar que el nodo `tri` dentro de `PT_GEO`, `PT_LIGHT/mesh` y `Pathtracer/scene/td_geo` sea un `triangulatePOP` con `triangulatequads = True` conectado `has_faces -> tri -> xf`, y que las llamadas `numPrims(max=True, primType=...)` tengan guardia `max(..., 0)`. (O usar la herramienta MCP `td_setup_pathtracer3` que lo aplica automáticamente).
2. **`allowCooking = True` en cada copia:** Las plantillas en `/project1/PT_FAM/PT_OPs/{PT_GEO, PT_MAT, PT_LIGHT}` tienen `allowCooking = False`. Inmediatamente después de `parent.copy(...)`, ejecutar `new_op.allowCooking = True` y `new_op.render = True`.
3. **Nombres internos exactos de menús (`menuNames`):**
   - `PT_LIGHT.par.Type`: `'Point'`, `'Spot'`, **`'Rect'`** *(nunca `'Rectangle'`)*, `'Disk'`, `'Sphere'`, `'Sun'`, `'Mesh'`.
   - `Pathtracer.par.Method`: **`'Dlss'`**, `'Accumulate'`.
   - `Pathtracer.par.Quality`: `'Dlaa'`, `'Quality'`, `'Balanced'`, `'Performance'`, `'Ultraperformance'`.
4. **Orientación `-Z`:** `PT_LIGHT` y `cameraCOMP` apuntan hacia `-Z`. Una luz sobre la escena en `(0, 3, 0)` necesita `rx = -90` para apuntar hacia `-Y`.
5. **Shader dinámico durante el armado:** Mantener `pt.par.Optimizedfor = ''` mientras se agregan o modifican materiales, luces o primitivas para que `trace/flex` renderice al instante sin recompilar.
6. **Estabilidad temporal en animación POP (`Software = 1`):** En TouchDesigner `2025.32460`, activar siempre `pt.op('scene').par.Software = 1` para usar el **LBVH síncrono en GPU** de PathTracer y evitar que el rebuild asíncrono de hardware (`colpop`) descarte ~25% de los cuadros en POPs animados. En shaders `glslPOP`, usar `float t = mod(uTime, 3600.0);` y velocidades angulares $\omega_i$ fijas por anillo/radio base.
7. **Humo volumétrico turbulento (`Haze`) selectivo:** Desactivar `par.Haze = False` en luces `Rect` de relleno para no lavar el contraste, y activar `par.Haze = True` únicamente en luces puntuales/focalizadas (`Sphere` + `Spot` cenital con `noiseTOP` conectado a `Projectormap` como Gobo), usando `Hazevariation = 1.0`, `Hazescale = 2.6`, `Hazemultiple = False` y deriva `Hazedrift` animada.
8. **Presupuesto de 60 FPS en tiempo real (`1280x720`):** Configurar el piso `gridPOP` con `rows = 2, cols = 2, sizex = 45.0, sizey = 45.0` (**`2` triángulos**, sin línea de corte de horizonte), usar **esferas analíticas (`pointPrims`, `64–96` partículas)** en lugar de mallas `spherePOP`, y fijar en `Pathtracer`: `Samples = 1`, `Bounces = 4`, `Hazesamples = 4`, `Method = 'Dlss'`, `Quality = 'Balanced'`.

## Script de Referencia Verificado (`td_execute` / `live.exec_code`)

```python
root = op('/project1')
fam = root.op('PT_FAM') or root.loadTox('C:/Users/Tolch/Documents/AI_Code/PachTracer_POPs/PT_FAM_32460_patched.tox')
m_pt = fam.op('PT_OPs/Pathtracer')
m_geo = fam.op('PT_OPs/PT_GEO')
m_mat = fam.op('PT_OPs/PT_MAT')
m_light = fam.op('PT_OPs/PT_LIGHT')

# 1. Pathtracer + Cámara + Salida
pt = root.op('Pathtracer1') or root.copy(m_pt, name='Pathtracer1')
pt.allowCooking = True
pt.par.Optimizedfor = ''
pt.par.Panelresolution = False
pt.par.Resolutionw, pt.par.Resolutionh = 1280, 720
pt.par.Method = 'Dlss'
pt.par.Quality = 'Quality'
pt.par.Samples = 2
pt.par.Bounces = 10
pt.par.Glassshadows = True
pt.par.Hazedensity = 0.04

cam = root.op('cam1') or root.create(cameraCOMP, 'cam1')
cam.par.tx, cam.par.ty, cam.par.tz = 0.0, 1.5, 5.0
cam.par.rx, cam.par.ry, cam.par.rz = -12.0, 0.0, 0.0
pt.par.Camera = 'cam1'

null_out = root.op('null1') or root.create(nullTOP, 'null1')
if not null_out.inputConnectors[0].connections:
    pt.outputConnectors[0].connect(null_out.inputConnectors[0])

# 2. Piso POP -> PT_GEO + PT_MAT
flr_pop = root.create(gridPOP, 'floor_pop')
flr_pop.par.sizex, flr_pop.par.sizey = 8.0, 8.0
geo_flr = root.copy(m_geo, name='pt_geo_floor')
geo_flr.allowCooking = True
geo_flr.par.rx = -90.0
flr_pop.outputConnectors[0].connect(geo_flr.inputConnectors[0])

mat_flr = root.copy(m_mat, name='pt_mat_floor')
mat_flr.allowCooking = True
mat_flr.par.Basecolorr, mat_flr.par.Basecolorg, mat_flr.par.Basecolorb = 0.75, 0.75, 0.78
mat_flr.par.Roughness = 0.55
geo_flr.par.Material = mat_flr

# 3. Esfera de Vidrio con Absorción Beer-Lambert
sph_pop = root.create(spherePOP, 'sph_pop')
sph_pop.par.radx = sph_pop.par.rady = sph_pop.par.radz = 0.5
geo_glass = root.copy(m_geo, name='pt_geo_glass')
geo_glass.allowCooking = True
geo_glass.par.ty = 0.5
sph_pop.outputConnectors[0].connect(geo_glass.inputConnectors[0])

mat_glass = root.copy(m_mat, name='pt_mat_glass')
mat_glass.allowCooking = True
mat_glass.par.Transmission = 1.0
mat_glass.par.Roughness = 0.0
mat_glass.par.Ior = 1.52
mat_glass.par.Absorptioncolorr, mat_glass.par.Absorptioncolorg, mat_glass.par.Absorptioncolorb = 0.2, 0.85, 0.95
mat_glass.par.Absorptiondistance = 0.6
geo_glass.par.Material = mat_glass

# 4. Luz de Área Rectangular (PT_LIGHT)
lt = root.copy(m_light, name='pt_light_key')
lt.allowCooking = True
lt.par.Type = 'Rect'
lt.par.tx, lt.par.ty, lt.par.tz = 0.0, 3.2, 0.0
lt.par.rx = -90.0
lt.par.Sizew, lt.par.Sizeh = 1.2, 1.2
lt.par.Strength = 90.0

pt.par.Reset.pulse()
```

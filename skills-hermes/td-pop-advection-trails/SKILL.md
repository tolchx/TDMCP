---
name: td-pop-advection-trails
description: "Use when implementing 3D particle flowfield advection, curl noise vector fields, and continuous motion trails using TouchDesigner POPs (particlePOP, noisePOP, fieldPOP, trailPOP, lookuptexturePOP). Based on verified 2025/2026 patterns from Paketa12 and The NODE Institute."
---

# 3D Particle Flowfield Advection & Trails with POPs

> **Verificado en TouchDesigner 2025.32460 + TDMCP 1.1.55.**
> Patrón extraído de la deconstrucción y verificación en vivo de `/project1/tut_paketa12_advection`.

## Arquitectura Canónica del Pipeline

```
[spherePOP / gridPOP] (Emisor base: radio ~0.5, 16x16)
       │
       ▼ (input 0)
┌─► [particlePOP] (timeintegration=ON, targetpop=./tgt, pointidreuse='none')
│      │
│      ▼
│   [noisePOP: curl] (type='simplex3d', curl3d=True, amp0=0.55, period=1.3)
│      │
│      ▼
│   [fieldPOP: bounds] (mode='sphere', radx/y/z=1.2, weight=True)
│      │
│      ▼
│   [transformPOP: damp] (sx=sy=sz=0.985)
│      │
│      ▼
└── [nullPOP: tgt] ── (cierre del feedback loop del particlePOP)
       │
       ▼
    [lookuptexturePOP: color_map] ◄── [rampTOP] (mapeo a atributo Color)
       │
       ▼
    [trailPOP: trail] (length=8 frames, attrmatch=True, attrname='PartId')
       │
       ▼
    [convertPOP: topoints] (convert='topointprims')
       │
       ▼
    [nullPOP: null_out] (display=True, render=True)
       │
 (geometryCOMP) ── material: [pointspriteMAT / lineMAT (aditivo)]
       │
 [renderTOP] ◄── [cameraCOMP] + [lightCOMP]
```

---

## Parámetros Reales y Contratos Críticos

### 1. Motor de Advección (`particlePOP` + `targetpop`)
- **`timeintegration = True`**: Imprescindible. Si está apagado, las partículas nacen pero la velocidad no integra la posición.
- **`targetpop = op('./tgt')`** (**Contrato C10**): Sin el lazo cerrado apuntando al `nullPOP`, la simulación descarta las fuerzas integradas.
- **`pointidreuse = 'none'`**: Crucial cuando se usan estelas. Si se reutilizan IDs (`'loop'`), las partículas que reencarnan unen erróneamente sus estelas con la posición del nacimiento anterior.

### 2. Campo Solenoidal (`noisePOP`)
- **`curl3d = True`**: Genera un campo de velocidad con divergencia cero $\nabla \cdot \vec{v} = 0$, evitando compresión o vacío artificial de partículas.
- **`amp0`**: Escala la velocidad de advección (valores típicos: 0.3 a 0.7).
- **`tz.expr = 'absTime.seconds * 0.12'`**: Anima el campo en el tiempo para que las líneas de flujo evolucionen orgánicamente.

### 3. Confinamiento Espacial (`fieldPOP` + `transformPOP`)
- **`fieldPOP`**: Define un campo de influencia esférico (`mode='sphere'`) que atenúa la velocidad fuera de un radio seguro.
- **`transformPOP` (`sx=sy=sz=0.985`)**: Amortigua suavemente la dispersión centrífuga manteniendo la masa de partículas dentro del frustum de cámara.

### 4. Estelas Temporales (`trailPOP`)
- **`attrmatch = True`** y **`attrname = 'PartId'`**: Asocia las muestras temporales a la misma partícula a lo largo de los cuadros.
- **`length = 8`** y **`lengthunit = 'frames'`**: Longitud de la estela en fotogramas.
- **`surftype = 'points'`**: Genera puntos individuales a lo largo de la estela ideales para renderizado con `pointspriteMAT` aditivo (**Contrato C8**). Para polilíneas continuas, usar `surftype = 'rows'` y sombreado con `lineMAT`.

### 5. Renderizado (**Contratos C2**)
- **`convertPOP` (`convert='topointprims'`)**: Obligatorio. En POPs, el rasterizador dibuja primitivas, no puntos sin primitivas.
- **`pointspriteMAT`**:
  - `pointsize = 3.0` (fija el tamaño en píxeles).
  - `blending = True`, `srcblend = 'sa'`, `destblend = 'one'` (mezcla aditiva luminosa).
- **`geometryCOMP`**: Eliminar siempre el `torus1` creado por defecto para evitar enmascaramiento (**Contrato C2**).

---

## Verificación Numérica en Vivo

Tras cablear y parametrizar la red, ejecutar el bucle `settle()` de estabilización (**Contrato C1**):

```python
for _ in range(6):
    op('geo/sim').cook(force=True)
    op('geo/null_out').cook(force=True)
    op('ren').cook(force=True)
    time.sleep(0.04)

nout = op('geo/null_out')
ren = op('ren')

assert nout.numPoints() > 1000, "Población de partículas insuficiente"
assert nout.numPrims() > 1000, "Faltan primitivas de renderizado"
assert 'Color' in [a.name for a in nout.pointAttributes], "Falta atributo Color"
assert 'PartId' in [a.name for a in nout.pointAttributes], "Falta atributo PartId"

# Validación de píxeles encendidos en render
arr = ren.numpyArray()
lit_pixels = int((arr[:, :, :3].max(axis=2) > 0.01).sum())
assert lit_pixels > 5000, "RenderTOP vacío o negro"
```

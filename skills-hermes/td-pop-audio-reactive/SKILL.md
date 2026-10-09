---
name: td-pop-audio-reactive
description: "Use when creating real-time audio-reactive 3D point clouds, particle deformations, and audio-driven visual structures with TouchDesigner POPs (audiospectrumCHOP, choptoTOP, lookuptexturePOP, mathmixPOP, spherePOP, pointspriteMAT). Modern 2025/2026 GPU pipeline replacing legacy SOP-based audio visuals."
---

# Audio-Reactive GPU Point Clouds with POPs

> **Verificado en TouchDesigner 2025.32460 + TDMCP 1.1.55.**
> Patrón extraído de la deconstrucción y verificación en vivo de `/project1/tut_audio_pops`.

## Arquitectura del Pipeline Audio-a-POP

```
[audiooscillatorCHOP / audiodeviceinCHOP]
                    │
                    ▼
       [audiospectrumCHOP: FFT 256 bins]
                    │
                    ▼
         [choptoTOP: spec_tex] (256x1, float32)
                    │
                    └─────────────────────────┐
                                              ▼ (input 1 TOP)
[spherePOP: base_sphere] ────────► [lookuptexturePOP: audio_sample] (attr: AudioAmp)
 (freq=16, 2562 pts)                          │
                                              ▼
                                     [lookuptexturePOP: color_sample] ◄── [rampTOP: color_ramp]
                                              │
                                              ▼
                                     [mathmixPOP: displace] (amultbaddc: P * AudioAmp + P)
                                              │
                                              ▼
                                     [noisePOP: turb] (curl3d=True, amp0=0.15)
                                              │
                                              ▼
                                     [convertPOP: topoints] (convert='topointprims')
                                              │
                                              ▼
                                     [nullPOP: null_out] (display=True, render=True)
                                              │
                                        (geometryCOMP) ── material: [pointspriteMAT]
                                              │
                                        [renderTOP] ◄── [cameraCOMP] + [lightCOMP]
```

---

## Parámetros Reales y Contratos Críticos

### 1. Dominio de Audio (CHOP -> TOP)
- **`audiospectrumCHOP`**:
  - `mode = 'visual'`: Genera distribución logarítmica/perceptual adecuada para visuales.
  - `highfreqboost = 0.75`: Compensa la caída natural de energía en frecuencias agudas.
  - `outlength = 256`: Resolución espectral suficiente sin sobrecargar el ancho de banda.
- **`choptoTOP`**:
  - `dataformat = 'r'`: Almacena el espectro como textura de canal único rojo.
  - `format = 'rgba32float'`: Imprescindible para evitar el redondeo a 8 bits y conservar picos dinámicos.
  - `outputresolution = 'custom'`, `resolutionw = 256`, `resolutionh = 1`.

### 2. Muestreo de Espectro en POPs
- **`lookuptexturePOP`**:
  - `overrideautoattr = True` y `outputattrscope = 'AudioAmp'`.
  - `attrtype = 'float'`, `attrnumcomps = 1`.
  - Mapea las coordenadas normalizadas del punto para muestrear los 256 bins espectrales en GPU.

### 3. Deformación Radial No Destructiva (`mathmixPOP`)
- Para evitar que la geometría colapse a 0 cuando el audio está en silencio:
  - Usar la operación combinada **`amultbaddc`** ($A \cdot B + C$):
    - `comb0scopea = 'P'`
    - `comb0scopeb = 'AudioAmp'`
    - `comb0scopec = 'P'`
    - `comb0result = 'P'`
  - Esto produce la transformación $P_{out} = P \cdot AudioAmp + P = P \cdot (1 + AudioAmp)$, preservando la esfera base y expandiendo dinámicamente según la energía sonora.

### 4. Densidad de Puntos en `spherePOP`
- En modo `'geodesic'`, la resolución no se controla por `rows`/`cols`, sino por **`freq`** (**Contrato C6/C10**):
  - `freq = 5` → 252 puntos.
  - `freq = 16` → 2,562 puntos.

### 5. Renderizado (**Contrato C2**)
- **`convertPOP` (`convert='topointprims'`)**: Obligatorio para generar primitivas de punto rasterizables.
- **`pointspriteMAT`**: `pointsize = 3.5`, `blending = True`, `srcblend = 'sa'`, `destblend = 'one'` (aditivo brillante).
- **`geometryCOMP`**: Eliminar el toroide por defecto `torus1` (**Contrato C2**).

---

## Verificación Numérica en Vivo

```python
for _ in range(6):
    op('spectrum').cook(force=True)
    op('spec_tex').cook(force=True)
    op('geo/null_out').cook(force=True)
    op('ren').cook(force=True)
    time.sleep(0.04)

nout = op('geo/null_out')
ren = op('ren')

assert nout.numPoints() > 2000, "Puntos de la esfera insuficientes"
assert nout.numPrims() > 2000, "Faltan primitivas de punto"
assert 'AudioAmp' in [a.name for a in nout.pointAttributes], "Falta atributo AudioAmp"
assert 'Color' in [a.name for a in nout.pointAttributes], "Falta atributo Color"

arr = ren.numpyArray()
lit_pixels = int((arr[:, :, :3].max(axis=2) > 0.01).sum())
assert lit_pixels > 5000, "RenderTOP negro o vacío"
```

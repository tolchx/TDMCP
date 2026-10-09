---
name: td-pop-blend-morphing
description: "Morphing multi-objetivo e interpolación geométrica en GPU (blendPOP, cacheblendPOP, cachePOP) con ponderación baricéntrica y blending temporal."
---

# Morphing Multi-Objetivo e Interpolación Geométrica en GPU

Guía técnica y contratos analíticos verificados en vivo contra TouchDesigner 2025.32460 para la interpolación espacial multi-objetivo (shape morphing) y blending temporal de cuadros en GPU mediante `blendPOP` y `cacheblendPOP`.

---

## 1. Operadores Principales y Modelo de Datos

| Operador | Familia / Tipo | Función Principal | Salida Canónica |
| :--- | :--- | :--- | :--- |
| **`gridPOP` / `transformPOP`** | Geometría Base | Provee geometrías fuente con topología coincidente | Atributos `P`, `N`, `Tex` |
| **`blendPOP`** | Morphing / Interpolation | Combina linealmente $N$ fuentes según pesos normalizados | Atributos interpolados en GPU |
| **`cachePOP`** | Buffer Temporal | Almacena un historial continuo de cuadros de puntos en GPU | Ring buffer en VRAM |
| **`cacheblendPOP`** | Temporal Blend | Muestrea e interpola sub-frames entre estados cacheados | Flujo continuo interpolado |
| **`convertPOP`** | Primitives | Asigna primitivas de punto para visualización | `topointprims` (1 prim por punto) |

---

## 2. Tipos de Blending y Fórmulas Matemáticas (`blendPOP`)

`blendPOP` evalúa la combinación lineal de atributos directamente en shaders de compute:

### Modos de `blendtype`
- **`proportional` (por defecto para morphing baricéntrico):**
  Calcula la combinación convexa ponderada de las fuentes conectadas:
  $$\vec{P}_{\text{blend}} = \sum_{k=0}^{M-1} w_k \vec{P}_k$$
- **`avg`:** Promedio simple de todas las fuentes: $\frac{1}{M} \sum \vec{P}_k$.
- **`add` / `mul` / `min` / `max`:** Operaciones algebraicas punto a punto sobre los componentes correspondientes.
- **`differencing`:** Computa el vector desplazamiento relativo respecto a la fuente base: $\Delta \vec{P} = \vec{P}_1 - \vec{P}_0$.

### Contratos Numéricos Verificados en Vivo
1. **Identidad en Extremos:**
   - Para $w_A = 1.0, w_B = 0.0$: $\|\vec{P}_{\text{blend}} - \vec{P}_A\| \equiv 0.000000$ exacto.
   - Para $w_A = 0.0, w_B = 1.0$: $\|\vec{P}_{\text{blend}} - \vec{P}_B\| \equiv 0.000000$ exacto.
2. **Punto Medio Lineal:**
   - Para $w_A = 0.5, w_B = 0.5$: $\vec{P}_{\text{blend}} \equiv 0.5 \vec{P}_A + 0.5 \vec{P}_B$ con error absoluto $< 10^{-6}$.
3. **Tri-Blend Baricéntrico Multivariante:**
   - Con 3 fuentes $A, B, C$ y pesos $w = [0.2, 0.3, 0.5]$ ($0.2 + 0.3 + 0.5 = 1.0$):
     $$\vec{P}_{\text{blend}} = 0.2 \vec{P}_A + 0.3 \vec{P}_B + 0.5 \vec{P}_C$$
     Error euclidiano $|\Delta \vec{P}| < 10^{-5}$ en todos los 441 puntos de la nube.

---

## 3. Blending Temporal en VRAM (`cacheblendPOP`)

`cacheblendPOP` lee cuadros indexados desde un `cachePOP` sin necesidad de duplicar redes:

```python
c = geo.create(cachePOP, 'cache')
c.par.cachesize = 10
c.par.active = True

cb = geo.create(cacheblendPOP, 'cacheblend')
cb.par.cachepop = c
cb.par.cache.sequence.numBlocks = 1
cb.par.cache0index = 0.0    # Cuadro en el buffer
cb.par.cache0weight = 1.0   # Peso de interpolación
cb.par.interp = 'on'        # Habilita interpolación sub-frame
```

---

## 4. Arquitectura de Red Canónica

```text
src_a (gridPOP plana, Z = 0) ──┐
src_b (transformPOP, Z = 4) ──┼──> blendPOP 'blend' (proportional, w=[0.2, 0.3, 0.5])
src_c (transformPOP, X = 6) ──┘        │
src_b ──> cachePOP ──> cacheblendPOP   ▼
                               attributePOP 'color_map'
                                       │
                                       ▼
                               convertPOP 'topoints' (convert='topointprims')
                                       │
                                       ▼
                               nullPOP 'null_render' ──> geometryCOMP ──> renderTOP
```

---

## 5. Trampas Frecuentes y Cableado en Python

1. **Cableado de Múltiples Entradas:**
   La tool `build_network` al recibir múltiples conexiones con el mismo destino (`{"from": "a", "to": "blend"}, {"from": "b", "to": "blend"}`) puede sobreescribir el conector 0 en lugar de expandir entradas.
   **Regla obligatoria:** En Python, cablee explícitamente usando conectores dedicados:
   ```python
   bl.inputConnectors[0].connect(ga)
   bl.inputConnectors[1].connect(gb)
   bl.inputConnectors[2].connect(gc)
   ```
2. **Coincidencia de Recuento de Puntos:**
   Si las geometrías difieren en número de puntos, configure `lengthmismatchaction` (`repeat` o `cycle`) para evitar recortes indeseados en los buffers de cómputo.

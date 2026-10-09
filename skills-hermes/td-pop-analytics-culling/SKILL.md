---
name: td-pop-analytics-culling
description: "Reducción paralela en GPU (analyzePOP), prefix scan acumulativo (accumulatePOP) y culling condicional/stream compaction (deletePOP) en redes POP."
---

# Reducción Paralela en GPU, Estadísticas y Culling Condicional

Guía técnica y contratos analíticos verificados en vivo contra TouchDesigner 2025.32460 para la reducción estadística de nubes de puntos (`analyzePOP`), escaneo prefijo paralelo (`accumulatePOP`) y filtrado/culling condicional en GPU (`deletePOP`).

---

## 1. Operadores Principales y Modelo de Datos

| Operador | Familia / Tipo | Función Principal | Salida Canónica |
| :--- | :--- | :--- | :--- |
| **`gridPOP`** | Generator | Genera grilla paramétrica regular para sondeo | Atributos `P`, `N`, `Tex` |
| **`analyzePOP`** | Reduction / Stats | Reduce el flujo de puntos a estadísticas globales | Atributos `Avg`, `Min`, `Max`, `Size`, `Sum` |
| **`accumulatePOP`** | Parallel Scan | Computa sumas prefijas continuas a lo largo del flujo | Atributo `Scan` float3 |
| **`deletePOP`** | Stream Compaction | Descarta puntos según predicados relacionales o volúmenes | Flujo compactado (`numPoints()` reducido) |
| **`convertPOP`** | Primitives | Asigna primitivas de punto para visualización de partículas | `topointprims` (1 prim por punto) |

---

## 2. Reducción Paralela en GPU (`analyzePOP`)

`analyzePOP` ejecuta reducciones paralelas en árbol directamente en shaders de compute para extraer métricas espaciales globales de nubes masivas sin transferir datos a CPU:

### Parámetros Principales
- **`inputattrs`:** Atributo objetivo (ej. `'P'`).
- **`avg = True`:** Computa el centroide medio ponderado de la nube:
  $$\vec{\mu} = \frac{1}{N} \sum_{i=1}^N \vec{P}_i$$
  **Contrato verificado:** Para una grilla simétrica en $[-1, 1]^2$, $\|\vec{\mu}\| < 10^{-5}$ ($0.000000$ error exacto).
- **`min = True` / `max = True`:** Límites inferior y superior del bounding box:
  $$\vec{P}_{\min} = (-1.0, -1.0, 0.0), \quad \vec{P}_{\max} = (1.0, 1.0, 0.0)$$
  **Contrato verificado:** Error absoluto $< 10^{-5}$ respecto a las dimensiones de la grilla.
- **`size = True`:** Dimensiones espaciales del bounding box $\vec{S} = \vec{P}_{\max} - \vec{P}_{\min}$:
  $$\vec{S} = (2.0, 2.0, 0.0) \pm 10^{-5}$$
- **`sum = True`:** Suma vectorial no normalizada de todos los elementos.

---

## 3. Prefix Scan Acumulativo (`accumulatePOP`)

`accumulatePOP` implementa un algoritmo de escaneo prefijo paralelo en GPU (patrón Blelloch / Hillis-Steele):

### Modos de Escaneo (`scantype`)
- **`inclusive`:** $\text{Scan}[i] = \sum_{k=0}^i \vec{P}_k$.
- **`exclusive`:** $\text{Scan}[i] = \sum_{k=0}^{i-1} \vec{P}_k$ con $\text{Scan}[0] = \vec{0}$.

### Propiedades y Contratos Matemáticos Verificados
1. **Relación de Recurrencia:**
   $$\text{Scan}[i] = \text{Scan}[i-1] + \vec{P}[i]$$
   **Contrato verificado:** Error máximo $|\text{Scan}[i] - (\text{Scan}[i-1] + \vec{P}[i])| < 10^{-6}$ verificado sobre la totalidad de los 441 puntos sondeados.
2. **Conservación de Simetría:**
   En una distribución geométrica impar con centro en el origen, la suma acumulativa al llegar al último punto colapsa exactamente al vector nulo: $\|\text{Scan}[N-1]\| < 10^{-4}$.

---

## 4. Culling Condicional y Stream Compaction (`deletePOP`)

`deletePOP` elimina puntos en tiempo real reindexando los buffers de cómputo en GPU mediante compactación de flujo:

### A. Filtrado por Atributos (`attr`)
- **Configuración:**
  - `entity = 'point'`
  - `attr.sequence.numBlocks = 1`
  - `attr0inattr = 'P(1)'` (o componente axial)
  - `attr0func = 'lt'` (`lt`, `lte`, `gt`, `gte`, `eq`, `ne`)
  - `attr0value = 0.0`
- **Contrato verificado:**
  - En una grilla 21x21 en $[-1, 1]$, el corte por semiplano inferior ($P_1 < 0.0$) descarta exactamente las 10 filas inferiores ($10 \times 21 = 210$ puntos) y retiene con precisión determinista las 11 filas superiores ($11 \times 21 = 231$ puntos).
  - Cota inferior analítica: $\min(P_1) \ge 0.0$ ($0.000000$ tolerancia) en todos los puntos supervivientes, sin fugas ni bleeding de coordenadas.

### B. Culling por Volúmenes Bounding (`bound`)
- **Configuración:**
  - `bound.sequence.numBlocks = 1`
  - `bound0enabled = True`
  - `bound0type = 'boundingsphere'` (o `'boundingbox'`)
  - `bound0scalex = 1.2`, `scaley = 1.2`, `scalez = 1.2` ($R = 0.6$)
- **Contrato verificado:**
  - Segmenta limpiamente el flujo entre la corona exterior ($328$ puntos) y el núcleo interior ($109$ puntos con `bound0invert = True`).

---

## 5. Arquitectura de Red Canónica

```text
gridPOP 'grid' (21x21 = 441 pts)
    ├──> analyzePOP 'stats' (Avg, Min, Max, Size, Sum) ──> poptoCHOP 'check_an'
    ├──> accumulatePOP 'accum' (Scan) ─────────────────> poptoCHOP 'check_ac'
    └──> deletePOP 'cull' (P(1) < 0.0 -> 231 pts)
            │
            ▼
         attributePOP 'color_map' (color RGBA format)
            │
            ▼
         convertPOP 'topoints' (convert='topointprims')
            │
            ▼
         nullPOP 'null_render' (display=True, render=True)
            ▲
            │ (pointspriteMAT con pointsize=4.5)
         geometryCOMP 'geo' ──> renderTOP 'ren' (960x540) ──> nullTOP 'null_view'
```

---

## 6. Buenas Prácticas y Trampas Frecuentes

1. **Bloques en Secuencias de TouchDesigner:**
   `sequence.numBlocks` no admite tamaño 0. Para desactivar temporalmente un filtro de atributo sin remover el bloque, vacíe la cadena: `dl.par.attr0inattr = ''`.
2. **Evaluación de Cero en Python:**
   Nunca use expresiones como `(d.get("val") or default) >= 0.0` para verificar valores de coma flotante en tests: en Python, `0.0 or default` evalúa al valor default (`False`). Use siempre `d.get("val") is not None and d.get("val") >= 0.0`.
3. **Conversión a Point Primitives:**
   Tras un culling con `deletePOP`, los polígonos originales de la grilla quedan fracturados o descartados. Es imperativo usar `convertPOP(convert='topointprims')` para garantizar que los puntos supervivientes se dibujen como partículas individuales.

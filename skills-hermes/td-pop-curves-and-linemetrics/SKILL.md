---
name: td-pop-curves-and-linemetrics
description: "Curvas paramétricas, resampling por longitud de arco y métricas analíticas en GPU (curvePOP, linePOP, lineresamplePOP, linemetricsPOP, linebreakPOP, linedividePOP, linesmoothPOP)."
---

# Curvas Paramétricas y Métricas de Línea en POPs (GPU)

Guía técnica y contratos verificados en vivo contra TouchDesigner 2025.32460 para la generación, remuestreo, cálculo de derivadas y renderizado de splines y curvas continuas en GPU sin conversiones a SOPs.

---

## 1. Operadores Principales y Modelo de Datos

| Operador | Familia / Tipo | Función Principal | Salida Canónica |
| :--- | :--- | :--- | :--- |
| **`curvePOP`** | Generator | Genera splines analíticas continuas multi-segmento | 1000 pts / 1 linestrip, `Curve` y `P` |
| **`linePOP`** | Generator | Subdivisión lineal/cardinal entre puntos de control | `(divs+1)` pts / 1 linestrip |
| **`lineresamplePOP`** | Modifier | Remuestrea curvas a paso uniforme de arco o subdivisiones | Puntos equidistantes en GPU |
| **`linemetricsPOP`** | Analyzer / Attr | Calcula tangentes 3D unitarias, curvatura y longitudes | `Tan`, `Curv`, `DistStartNorm`, `LineStripLength` |
| **`linesmoothPOP`** | Filter | Suaviza atributos o trayectorias con filtro Gaussiano/Box | Trayectoria filtrada |
| **`linebreakPOP`** | Topology | Rompe linestrips por distancia o cada N muestras | Segmentación en múltiples prims |
| **`linedividePOP`** | Subdivider | Inserta vértices y atributos de control por borde | Subdivisión geométrica fina |

---

## 2. Generación Paramétrica (`curvePOP` y `linePOP`)

### `curvePOP` — Curvas Analíticas Multi-Segmento
- **Dimensión (`parsize`):**
  - `'1'`: Función escalar $y = f(u)$, donde $P_0 = u \in [0, 1]$ y $P_1 = \text{val}$.
  - `'3'` o `'4'`: Curva espacial 3D o 4D en coordenadas cartesianas.
- **Segmentos (`seg.sequence.numBlocks`):**
  - Cada segmento $k$ define:
    - `seg<k>type`: `'constant'`, `'linear'`, `'easein'`, `'easeout'`, `'easeinout'`, `'bezier'`.
    - `seg<k>u`: Posición $u$ acumulada del final del segmento (ej. `0.5`, `1.0`).
    - `seg<k>endval0`: Valor objetivo al alcanzar `seg<k>u`.
- **Topología canónica:**
  - Produce siempre `numPrims() == 1` (`linestrip`). Lo que dibuja es la primitiva que enlaza los puntos en GPU.

### `linePOP` — Líneas entre Puntos de Control
- Con $K$ puntos de control y $D$ divisiones (`divs`), el conteo exacto de puntos es:
  $$\text{numPoints} = (K - 1) \cdot D + 1$$
- Con `closed = True`, el conteo escala al doble exacto ($2 \cdot D$).
- Con `output = 'ctrlpoints'`, opera en modo passthrough devolviendo únicamente los puntos de control ($K$ pts).

---

## 3. Remuestreo por Longitud de Arco (`lineresamplePOP`)

Las curvas paramétricas naturales sufren de velocidades variables (puntos amontonados en curvaturas pronunciadas). `lineresamplePOP` rectifica la distribución:

- **Modo Divisiones (`resamplemethod = 'linestrip'`):**
  - Fija exactamente `resampledivs = N`, produciendo $N + 1$ puntos por linestrip.
- **Modo Distancia de Arco (`resamplemethod = 'dist'`):**
  - Fija `resamplemaxdist = d`, garantizando un paso de muestreo espacial homogéneo $\Delta s \le d$.
  - Elimina el aliasing espacial al instanciar geometría o calcular velocidades de partículas.

---

## 4. Métricas Geométricas en GPU (`linemetricsPOP`)

`linemetricsPOP` evalúa la geometría diferencial de las curvas directamente en shaders de compute:

1. **Tangentes 3D Unitarias (`tangent = True`):**
   - Produce canales `Tan_0`, `Tan_1`, `Tan_2`.
   - Contrato verificado: $\|\vec{T}_i\| = \sqrt{\text{Tan}_0^2 + \text{Tan}_1^2 + \text{Tan}_2^2} = 1.0 \pm 10^{-4}$ para todo vértice de la curva.
2. **Curvatura Escalar (`curvature = True`):**
   - Produce canal `Curv` ($\kappa = \|\frac{d\vec{T}}{ds}\| \ge 0$). Mide el grado de flexión de la curva.
3. **Coordenada de Arco Normalizada (`diststartnorm = True`):**
   - Produce `DistStartNorm` $\in [0.0, 1.0]$, monótono creciente estricto ($s_0 = 0.0$, $s_{\text{last}} = 1.0$).
   - Ideal para ramps de color, texturizado UV 1D, o desfases temporales en animaciones.
4. **Longitud Total del Linestrip (`primlen = True`):**
   - Produce canal `LineStripLength`, idéntico a la suma de las distancias discretas $\sum \text{DistNext}$.

---

## 5. Arquitectura de Red y Render Canónico

```text
curvePOP 'curve' (parsize='1', segs=2) 
   │
   ▼
lineresamplePOP 'resample' (linestrip, divs=60)
   │
   ▼
linemetricsPOP 'metrics' (tangent=True, diststartnorm=True, curvature=True)
   │
   ├──> poptoCHOP 'check' (telemetría numérica de derivadas y longitud)
   │
   ▼
nullPOP 'null_render' (display=True, render=True)
   ▲
   │ (material pointspriteMAT con pointsize=4.5 o lineMAT)
geometryCOMP 'geo' ──> renderTOP 'ren' (960x540) ──> nullTOP 'null_view'
```

### Contratos de Render Verificados
- **Primitivas requeridas:** Las curvas deben mantener `numPrims() >= 1`.
- **Materiales compatibles:**
  - `pointspriteMAT`: Renderiza cada muestra de la curva como un sprite circular suave (ideal para nubes de puntos guiadas por curvas).
  - `lineMAT`: Renderiza el strip poligonal continuo con grosor uniforme.
- **Guardia de propiedad (`render_is_ours`):**
  - Desactivar `render = False` en el nodo terminal de la red POP debe reducir los píxeles iluminados a exactamente 0.

---

## 6. Gotchas y Errores Frecuentes

1. **Indexación de canales en Python de TD:**
   - Usar siempre `chan.vals[i]` o `list(chan.vals)` en lugar de `chan[i]`. `chan[i]` en TD evalúa según el tiempo/frame y puede arrojar `Index invalid or out of range`.
2. **Sincronización GPU→CPU con `poptoCHOP`:**
   - Al crear o modificar nodos POP río arriba, `poptoCHOP` requiere un ciclo de cook forzado (`for _ in range(4): op.cook(force=True); chk.cook(force=True); time.sleep(0.04)`) para asegurar que los buffers de GPU se lean en memoria CPU sin arrojar `None` en canales recién instanciados.
3. **Verificación booleana de float 0.0:**
   - En Python `0.0 or 99` devuelve `99`. Si se comprueba un error numérico `len_err` que es exactamente `0.0`, nunca usar `(d.get('len_err') or default) < tol`; utilizar `d.get('len_err') is not None and d.get('len_err') < tol`.

---
name: td-pop-deformations-twist
description: "Deformaciones espaciales aceleradas en GPU (twist, bend, shear, squash, taper), modulación por peso y conservación volumétrica/radial en POPs (twistPOP, rerangePOP)."
---

# Deformaciones Espaciales en GPU y Modulación por Atributos (twistPOP)

Guía técnica y contratos verificados en vivo contra TouchDesigner 2025.32460 para la ejecución de deformaciones geométricas no lineales en GPU (`twist`, `bend`, `shear`, `squash`, `taper`) moduladas por pesos continuos generados con `rerangePOP`.

---

## 1. Operadores Principales y Modelo de Datos

| Operador | Familia / Tipo | Función Principal | Salida Canónica |
| :--- | :--- | :--- | :--- |
| **`tubePOP` / `gridPOP`** | Generator | Genera malla paramétrica base cilíndrica o plana | Atributo `P` float3 |
| **`rerangePOP`** | Modifier / Map | Remapea coordenadas (ej. $P_1$) a pesos normalizados | Atributo `Weight` ($[0.0, 1.0]$) |
| **`twistPOP`** | Spatial Deformation | Aplica deformaciones no lineales en GPU | `P` deformado |
| **`attributePOP`** | Formatting | Crea o formatea canales visuales (ej. `color` RGBA) | Atributo `Color` float4 |
| **`convertPOP`** | Primitives | Convierte vértices de malla a primitivas de punto | `topointprims` (1 prim por punto) |

---

## 2. Modos de Deformación de `twistPOP` (`op`)

`twistPOP` implementa cinco transformaciones espaciales analíticas directamente en shaders de compute:

### A. Torsión Planar (`twist`)
- **Eje primario (`paxis`):** Eje longitudinal sobre el que se aplica la rotación (típicamente `'y'`).
- **Rotación:** El ángulo de giro de cada punto depende de su posición en `paxis` y del peso escalar:
  $$\theta(\vec{x}) = \text{strength} \cdot \text{Weight}(\vec{x})$$
- **Conservación Radial Exacta:** Para un cilindro de radio $R$, la distancia radial en el plano perpendicular $XZ$ es estrictamente invariante:
  $$r = \sqrt{x^2 + z^2} = R$$
  **Contrato verificado:** Error radial $|\sqrt{x^2 + z^2} - R| < 10^{-5}$ en el 100% de los puntos de la geometría.
- **Confinamiento por Peso:**
  - Donde $\text{Weight} = 0.0$ (base): Desplazamiento nulo $\|\vec{P} - \vec{P}_0\| \equiv 0.000000$.
  - Donde $\text{Weight} = 1.0$ (tope) con $\text{strength} = 180^\circ$: El desplazamiento euclidiano es exactamente el diámetro:
    $$\Delta P = 2R = 1.0 \pm 10^{-4}$$

### B. Cizalladura Analítica (`shear`)
- **Eje primario (`paxis = 'y'`) y secundario (`saxis = 'x'`):**
  Desplaza las coordenadas transversales de forma directamente proporcional a la coordenada axial:
  $$x' = x + k \cdot y, \quad y' = y, \quad z' = z$$
- **Contrato verificado:** Con $k = 1.0$ en un cilindro $y \in [-1, 1]$, el extremo superior ($y = 1$) se desplaza $\Delta x = +1.0$ y el extremo inferior ($y = -1$) se desplaza $\Delta x = -1.0$, ensanchando el span en $X$ a $2.994 \approx 1.0 + 2k$.

### C. Flexión Angular (`bend`)
- **Curvatura sobre plano secundario (`paxis = 'y'`, `saxis = 'z'`):**
  Curva la columna longitudinalmente en el plano $YZ$, proyectando un arco continuo con ensanchamiento lateral en $Z$.
- **Contrato verificado:** Con $\text{strength} = 90^\circ$, el span de la geometría en el eje secundario $Z$ se dilata de $1.0$ a más de $2.05$.

### D. Squash & Stretch (`squash`)
- **Preservación volumétrica tridimensional:**
  Estira o comprime el eje primario mientras escala inversamente los ejes ortogonales para preservar el volumen del cuerpo:
  $$y' = y \cdot (1 + k), \quad x' = \frac{x}{\sqrt{1 + k}}, \quad z' = \frac{z}{\sqrt{1 + k}}$$
- **Contrato verificado:** Con $\text{strength} = 1.0$ ($1+k = 2.0$), la altura en $Y$ se duplica exactamente de $2.0$ a $4.0$ mientras que el radio en $X$ se comprime a la mitad ($0.5 \to 0.25$).

---

## 3. Generación y Mapeo de Pesos (`rerangePOP`)

Para modular de forma continua cualquier deformación sin escalones bruscos:

```python
rr = geo.create(rerangePOP, 'weight_ramp')
rr.par.inputattrscope = 'P(1)'       # Coordenada Y de los puntos
rr.par.fromlow0 = -1.0
rr.par.fromhigh0 = 1.0
rr.par.tolow0 = 0.0                  # Base fijada (sin deformación)
rr.par.tohigh0 = 1.0                 # Tope libre (máxima deformación)
rr.par.outputattrscope = 'Weight'
rr.par.overrideautoattr = True
```

Luego se asigna en `twistPOP`:
```python
tw.par.weightattr = 'Weight'
```

---

## 4. Arquitectura de Red Canónica

```text
tubePOP 'tube' (rad=0.5, h=2.0, 21x21 = 441 pts)
    │
    ▼
rerangePOP 'weight_ramp' (P(1) en [-1, 1] -> Weight en [0, 1])
    │
    ▼
twistPOP 'twist_op' (op='twist', paxis='y', strength=180, weightattr='Weight')
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

## 5. Reglas de Validación y Sincronización GPU-to-CPU

1. **Latencia de Cocinado GPU-to-CPU:**
   Al sondear con `poptoCHOP`, TouchDesigner requiere múltiples ciclos de sincronización antes de leer los buffers de memoria:
   ```python
   for _ in range(4):
       pop_op.cook(force=True)
       chk.cook(force=True)
       time.sleep(0.04)
   ```
2. **Acceso a Canales en TD Python:**
   Siempre acceder mediante `list(chk['P_0'].vals)` o `chk['P_0'].vals[i]`. La indexación directa `chk['P_0'][i]` evalúa por línea de tiempo/frames y arroja excepciones de índice.
3. **Guardia de Render Activo (`render_is_ours`):**
   Garantiza que el renderTOP esté mostrando efectivamente la geometría deformada: apagar `null_render.render = False` debe colapsar los píxeles iluminados a `0`.

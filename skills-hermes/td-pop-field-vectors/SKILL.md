---
name: td-pop-field-vectors
description: "Campos analíticos Signed Distance Fields (SDF), campos vectoriales de velocidades solenoidal (curl noise 3D/4D), modulación de fuerzas y confinamiento espacial en GPU (fieldPOP, noisePOP, mathmixPOP)."
---

# Campos Vectoriales y Confinamiento por SDF en POPs (GPU)

Guía técnica y contratos verificados en vivo contra TouchDesigner 2025.32460 para la generación de campos escalares Signed Distance Fields (SDF), campos de velocidades 3D solenoidales (vorticidad pura con divergencia nula $\nabla \cdot \vec{V} = 0$) y confinamiento estricto de fuerzas en GPU sin fugas numéricas.

---

## 1. Operadores Principales y Modelo de Datos

| Operador | Familia / Tipo | Función Principal | Salida Canónica |
| :--- | :--- | :--- | :--- |
| **`fieldPOP`** | Analyzer / SDF | Evalúa geometrías analíticas (esfera, caja, toro, tubo) | Atributos `Dist` (SDF float) y `Weight` ($[0, 1]$) |
| **`noisePOP`** | Vector Field | Genera campos de velocidades 3D/4D incompresibles | Atributo `CurlVel` ($\vec{V} = \nabla \times \vec{\Psi}$) |
| **`mathmixPOP`** | Operator / Math | Modula aceleraciones o velocidades por peso de campo | `FieldForce = CurlVel * Weight` |
| **`attributePOP`** | Formatting | Crea y formatea atributos de color RGBA | `Color` float4 |
| **`convertPOP`** | Primitives | Garantiza primitivas de punto para cada vértice | `topointprims` (1 prim por punto) |

---

## 2. Campos Analíticos y SDF (`fieldPOP`)

`fieldPOP` evalúa la distancia con signo respecto a primitivas implícitas directamente en memoria GPU:

### Modos Soportados (`mode`)
`sphere`, `box`, `torus`, `tubeinfinite`, `tubecapped`, `tuberounded`, `capsule`, `xplane`, `yplane`, `zplane`, `parabola`, `lineprojection`.

### Parámetros Críticos y Contratos
- **`signeddistance = True` / `sdoutputattr = 'Dist'`:**
  - Para una esfera de radio $R$ centrada en el origen:
    $$\text{Dist}(\vec{x}) = \|\vec{x}\| - R$$
  - **Contrato verificado:** Error absoluto $|\text{Dist}_{\text{GPU}} - (\|\vec{x}\| - R)| < 10^{-5}$ en todos los puntos sondeados.
  - Interior: $\text{Dist} < 0$. Frontera: $\text{Dist} = 0$. Exterior: $\text{Dist} > 0$.
- **`outputattr = 'Weight'` / `transitionrange = d`:**
  - Calcula el peso ponderado de influencia espacial.
  - Con `transitiontype = 'smoothstep'`: genera una curva $S$ Hermite cúbica suave que transiciona de $1.0$ a $0.0$ a lo largo de la banda de transición $[R - d, R + d]$.

---

## 3. Campos Vectoriales Solenoidales (`noisePOP` con `curl3d`)

El flujo de fluidos incompresibles requiere que la divergencia del campo de velocidades sea nula:
$$\nabla \cdot \vec{V} = 0$$

Al activar `curl3d = True` en `noisePOP`:
1. TouchDesigner computa el rotacional analítico de un campo potencial vectorial $\vec{\Psi}$:
   $$\vec{V} = \nabla \times \vec{\Psi}$$
2. Por identidad de cálculo vectorial, la divergencia de cualquier rotacional es idénticamente cero:
   $$\nabla \cdot (\nabla \times \vec{\Psi}) \equiv 0$$
3. **Efecto dinámico:** Las partículas o muestras advectadas por este campo nunca se concentran artificialmente en sumideros infinitos ni desaparecen en vacíos, conservando el volumen de flujo.

---

## 4. Confinamiento Espacial de Fuerzas (`mathmixPOP`)

Para contener turbulencias o aceleraciones dentro de un volumen específico (por ejemplo, dentro de una esfera o toro sin afectar el espacio circundante):

```text
gridPOP / particlePOP ──> fieldPOP (SDF + Weight) ──> noisePOP (CurlVel)
                                                             │
                                                             ▼
                                                    mathmixPOP 'modulate'
                                                    (mult: CurlVel * Weight -> FieldForce)
```

### Contratos Numéricos Verificados
- **Cero fugas en el exterior:** En puntos donde `Weight == 0.0`, el vector resultante $\|\vec{F}\| = 0.000000$ exacto.
- **Transmisión plena en el núcleo:** En puntos interiores donde `Weight > 0.8`, la aceleración activa promedio $\|\vec{F}\| > 0.5$.
- **Visualización por Color:** Mapeando `FieldForce` a `Color` con `attributePOP`, los vórtices se iluminan dinámicamente según su aceleración local.

---

## 5. Arquitectura de Red Canónica

```text
gridPOP 'grid' (21x21 en [-1, 1])
    │
    ▼
fieldPOP 'field' (sphere, rad=0.6, signeddistance=True, weight=True)
    │
    ▼
noisePOP 'curl' (simplex3d, curl3d=True, amp=1.0, scope='CurlVel')
    │
    ▼
mathmixPOP 'modulate' (mult: CurlVel * Weight -> FieldForce)
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

## 6. Gotchas de Implementación

1. **Resolución de nombres en scripts inyectados:**
   - La macro `CHAIN` inyecta automáticamente `ROOT = "..."`, pero NO define alias como `GEO`. Dentro de fragmentos inyectados para `execute_code`, referenciar siempre `op(ROOT + '/geo')`.
2. **Generación de atributos multicanal:**
   - Para generar un atributo de color válido en GPU que `renderTOP` y los materiales lean correctamente, preferir `attributePOP` con `attr0name = 'color'` y `attr0numcomps = '4'` en lugar de `mathmixPOP` escalar.
3. **Guardia de Render (`render_is_ours`):**
   - Asegurarse de que el `geometryCOMP` tenga su auto-creado `torus1` destruido antes de evaluar píxeles lit, o el torus enmascarará el render de los puntos del campo.

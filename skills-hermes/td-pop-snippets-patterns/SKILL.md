---
name: td-pop-snippets-patterns
description: "Patrones arquitectónicos y recetas canónicas extraídas de los 102 Operator Snippets oficiales de POPs (TouchDesigner 2025.32460). Cubre Math Mix multi-input, Lookup Attribute, partículas con estelas persistentes, inyección de campos paramétricos y POPs sin posición P."
---

# Patrones Canónicos Extraídos de OP Snippets (POPs)

Este documento condensa la arquitectura y reglas de diseño oficiales de Derivative extraídas de los 102 componentes `.tox` en `Samples/Learn/OPSnippets/Snippets/POP`.

---

## 1. Reglas Estructurales y Modelo de Datos

### Clases de Atributos
1. **Points (Puntos):** Datos continuos en GPU por cada muestra (`P`, `N`, `Color`, `Tex`, atributos custom).
2. **Primitives (Primitivas):** Definen la conectividad de los puntos (`polygons`, `lines`, `point primitives`). Lo que se dibuja en pantalla son las primitivas.
3. **Vertices (Vértices):** La asignación de un punto a una posición de una primitiva. Permiten valores discontinuos por cara o esquina.

### Swizzling y Nomenclatura Canónica
- **Formal indexado:** `P(0)`, `P(1)`, `P(2)`.
- **Vectorial clásico:** `P.xyz`, `Color.rgba`.
- **Indexación universal `.i0123`:** Para cualquier atributo no espacial ni de color, Derivative prescribe el uso de `.i0123` (donde `i` es índice):
  - `Polar.i012` para latitud, longitud y radio.
  - `Tex.i01` para coordenadas UV.
  - `Date.i012` o `Timecode.i0123`.

### Metadatos de Dimensión (`dim`)
- Los generadores bidimensionales o tridimensionales (`gridPOP`, `planePOP`) transportan un atributo de metadata llamado dimensión (`dim`).
- **Composición:** Cuando se usa `copyPOP` (ej. copiar un círculo 1D sobre los puntos de una grilla 2D), la metadata de dimensión se compone a 3 dimensiones automáticamente río abajo.

### POPs sin Atributo `P` (Nubes Puras de Atributos)
- Es una práctica recomendada crear nubes de datos sin posiciones `P`:
  - Usando `pointPOP` (un solo punto para actuar como *Uniform* o fuente de fuerza).
  - Usando `patternPOP` o `selectPOP` (descartando `P`).
  - Activando `Delete Input Attributes` en la página *Common*.
- Estas nubes actúan como tablas puras de datos en GPU para alimentar operadores matemáticos o de lookup sin reservar memoria innecesaria de geometría.

---

## 2. Mezclado Matemático y Lookups

### `mathmixPOP` — Más de 70 Operaciones Matemáticas
- Tipo interno: **`mathmixPOP`** (en minúsculas antes de `POP`).
- **Multi-Input:**
  - `input0`: Sus atributos entran directamente con sus nombres originales.
  - `input1`: Se prefijan automáticamente como `in1_<nombre>` (ej. `in1_P`, `in1_Color`).
- **Atributos Built-in (`_`):**
  - Genera atributos automáticos precalculados que inician con guión bajo (`_index`, `_weight`).
- **Página Uniform:**
  - Permite recibir de 1 a 4 floats constantes desde CHOPs, expresiones o bindings (`uVal`) utilizables en la página *Combine* sin costo de almacenamiento de buffer por punto.

### `lookupattributePOP` — Mapeo Atributo-a-Atributo Directo
- Tipo interno: **`lookupattributePOP`** (en minúsculas antes de `POP`).
- Mapea un atributo de búsqueda (0 a 1 o por índice de punto) del Input 0 contra los atributos del Input 1 (curva o tabla de referencia).
- Evita el uso de TOPs, texturas intermedias o CHOPs cuando se necesita mapear datos entre dos corrientes de puntos en GPU.

---

## 3. Simulación de Partículas y Estelas

### Ciclo de Vida y Persistencia de ID (`PartId`)
- Al conectar `particlePOP` a `trailPOP`, las estelas pueden saltar o conectarse erróneamente cuando se alcanza el límite `maxparticles`.
- **Regla oficial:**
  - En `particlePOP`: Configurar `pointidreuse = 'none'` (opción del menú para *Don't Reuse Point Id*, donde el menú completo es `['loop', 'unused', 'none']`).
  - En `trailPOP`: Configurar `attrmatch = True` y `attrname = 'PartId'` para que el historial conecte únicamente puntos con la misma identidad temporal.

### Inyección Paramétrica en Campos (`fieldPOP`)
- Para definir campos múltiples por puntos (ej. un campo por cada punto de un `pointPOP`), Derivative utiliza **coincidencia estricta de nombres**:
  - Un atributo llamado `radx` en la entrada anula automáticamente el parámetro `radx` del `fieldPOP`.
  - El atributo `P` de la entrada anula automáticamente los parámetros `tx`, `ty`, `tz` del campo.

---

## 4. Recetas de Red Canónicas

### Receta 1: MathMix Multi-Input con Uniforms
```text
gridPOP 'grid1' (rows=20, cols=20) ───────────────> Input 0 ─┐
                                                              ├──> mathmixPOP 'mathmix1' ──> nullPOP
circlePOP 'circ1' (Delete Input Attr, custom Col) ─> Input 1 ─┘
```
- `mathmix1.par.comb0oper = 'mix'`
- `mathmix1.par.comb0scopea = 'P'`
- `mathmix1.par.comb0scopeb = 'in1_P'`
- `mathmix1.par.comb0scopec = 'uBlend'` (Uniform definido en la página Uniform).

### Receta 2: Lookup de Color Directo por Curva
```text
noisePOP 'cloud' (posiciones dispersas) ──────> Input 0 ─┐
                                                          ├──> lookupattributePOP 'lookup1' ──> nullPOP
curvePOP 'palette' (Color asignado a lo largo) ─> Input 1 ─┘
```
- `lookup1.par.lookupindexattr = 'P.y'`
- `lookup1.par.lookup0valueattr = 'Color'`
- `lookup1.par.lookup0outputattrscope = 'Color'`

---
name: td-visual-aesthetics
description: "Principios de diseño visual, recetas de estética y rúbrica de verificación para TouchDesigner. Elimina el arte por defecto de programador mediante composición deliberada, iluminación de 3 puntos, paletas armónicas y acabados profesionales."
---

# Estética Visual y Calidad de Render en TouchDesigner

Un sistema o red de TouchDesigner no está completo simplemente porque los nodos no arrojen errores de cocinado. La corrección se juzga en la **imagen resultante**. Los operadores de TouchDesigner en sus valores por defecto producen lo que se conoce como *"programmer art"*. Esta habilidad define el flujo de trabajo, las técnicas y las recetas para crear visuales con intención, contraste y acabado profesional.

---

## 1. Regla de Oro: Enfoque Output-First

Antes de construir cualquier cadena de TOPs o escena de render 3D:
1. Crea el operador terminal `out1` (un `outTOP` o `nullTOP` nombrado `out1`).
2. Activa su flag de **Display** (`display=True`): esto proyecta la salida en el fondo del canvas de TouchDesigner (*Backdrop TOP*).
3. Conecta cada fase intermedia a `out1` mientras desarrollas. El usuario (y tú a través de `capture_top`) evalúa el progreso visual en cada paso.
4. **Nunca des por terminada una tarea visual con un frame negro o vacío (`Quality: FAIL`).**

---

## 2. Eliminar los Vicios del Look por Defecto ("Kill the Default Look")

| Defecto Típico de Programador | Corrección Profesional Obligatoria |
|---|---|
| **Phong gris en geometría con luz por defecto** | Elegir material con intención: `pbrMAT` con color base de paleta y rugosidad variada, o `constantMAT` para gráficos planos. |
| **Una sola luz blanca centrada donde nació** | Construir un rig de iluminación: 3 puntos (Key, Fill, Rim) o una luz clave dramática con fill coloreado. |
| **Sujeto centrado en el origen, cámara estática** | Elegir encuadre, distancia focal (`fov`) y ángulo de cámara. Aplicar regla de tercios. |
| **Noise TOP crudo por defecto** | Moldear el ruido (`period`, `harmonics`, `exponent`), recortar niveles y colorear con `lookupTOP` + rampa de paleta. |
| **Ciclo de tono arcoíris (Rainbow hue cycle)** | Mantener la paleta de color fija. Animar valores, posiciones o escalas, nunca el tono (`hue`). |
| **Rotación lineal a velocidad constante** | Suavizar movimientos con `filterCHOP` o `lagCHOP`. Desincronizar fases. |
| **Amplitud de audio mapeada cruda a brillo/escala** | Filtrar con `lagCHOP` (subida rápida, caída lenta) y definir siempre un valor piso (*floor*). |
| **Bloom saturado en toda la pantalla** | Subir `bloomthreshold` para que solo florezcan los brillos especulares y acentos reales. |
| **Todo igualmente brillante, enfocado y ruidoso** | Imponer jerarquía: un sujeto protagonista, un fondo calmo y espacio negativo. |

---

## 3. Orden de los 5 Pases de Construcción

Construye siempre en este orden estricto:

```
1. Composición y Cámara ──► 2. Iluminación y Valor ──► 3. Paleta de Color ──► 4. Movimiento ──► 5. Acabado (Finishing)
```

1. **Composición y Cámara:** Encuadre, lente (`fov`), espacio negativo, regla de tercios y siluetas.
2. **Iluminación y Valor:** Estructura de oscuros, medios y claros. Haz la prueba de entrecerrar los ojos (*squint test*) en monocromo; el sujeto debe distinguirse claramente.
3. **Paleta de Color:** Limitar a 3-5 colores clave. Usar un `tableDAT` con colores hacia un `rampTOP` y mapear mediante `lookupTOP`. Mantener la saturación general por debajo de 0.6.
4. **Movimiento:** Animación por capas (fBm: deriva lenta + detalle rápido), curvas de aceleración y desaceleración.
5. **Acabado:** Pipeline en formato de coma flotante (`rgba16float` o `rgba32float`), anti-aliasing (`aa8` o superior), tone mapping (`acesapprox`), viñeteado suave y grano de película ligero (2-4%) para evitar bandas en gradientes.

---

## 4. Las 8 Recetas de Looks (Look Recipes)

### 1. High-Key Editorial (Revista / Moda / Minimalista)
- **Fondo:** Campo brillante ligeramente tintado (0.92-0.97, nunca blanco puro 1.0).
- **Sujeto:** Sujeto OSCURO que sostiene la lectura; la lógica de valor se invierte.
- **Luz:** Sombras suaves (`soft2d`), sin resplandor (sin Bloom). Grano mínimo (2%). Un solo acento saturado.

### 2. Neon Glow Lines (Cyberpunk / Láser / Vector)
- **Fondo:** Casi negro (0.02-0.05).
- **Líneas:** 1 o 2 tonos neón con núcleos blanco puro (aditivo).
- **Luz y Acabado:** Bloom agresivo con umbral alto (~0.7), viñeteado y grano. El acento es la propia fuente de luz.

### 3. Filmic 3D Scene (Cinematográfico)
- **Materiales:** `pbrMAT` + `environmentlightCOMP` (con `dimmer` bajo) + rig de 3 luces.
- **Cámara:** Niebla de cámara (`fog=exp`) tintada hacia el fondo; profundidad de campo mediante Depth en Luma Blur.
- **Color y Acabado:** Grado de color con Tone Map `acesapprox` y paleta complementaria (teal & orange / deep sea).

### 4. Organic Feedback Painting (Pintura Generativa / Fluido)
- **Bucle:** `feedbackTOP` con un `levelTOP` dentro (`opacity` 0.90-0.98 como decaimiento) y un micro-`transformTOP` (escala 1.002, rotación 0.1°).
- **Color:** El `lookupTOP` con la paleta de color DEBE ir FUERA del bucle de feedback (dentro del bucle se degrada o satura en pocos cuadros).
- **Resolución:** Fijar resolución estricta dentro del bucle para garantizar rendimiento de 60 FPS.

### 5. Particle Nebula (Cosmos / Partículas)
- **Geometría:** Sprites instanciados o POP particles con `pointspriteMAT`.
- **Mezcla:** Aditiva, con brillo bajo por partícula individual; color mapeado según velocidad o tiempo de vida.
- **Cámara:** Órbita suave con micro-ruido de cámara en mano; Bloom en acentos densos.

### 6. Pastel Gradient Field (Etereal / Meditativo)
- **Gradientes:** Rampa grande y suave (`rampTOP`) combinada con ruido de baja frecuencia y bajo contraste mediante `displaceTOP`.
- **Valores:** Paleta pastel cálida; sin negros puros ni blancos puros. Deriva hipnótica muy lenta.
- **Acabado:** Grano moderado (6-10%) para evitar banding de color en gradientes sutiles. Sin bloom.

### 7. Monochrome Architectural (Estructural / Brutalista)
- **Geometría:** Formas duras, una luz clave tipo cono con sombras suaves `soft2d`.
- **Paleta:** Casi monocroma (grises y negros) con un posible acento ácido en un solo elemento.
- **Cámara:** Lente larga (teleobjetivo, fov estrecho) y amplio espacio negativo.

### 8. Data / HUD Graphic (Interfaces FUI / Dashboard)
- **Materiales:** `constantMAT` plano combinado con `lineMAT` para aristas y estructuras vectoriales.
- **Color:** Fondo oscuro, un solo color acento para el canal activo.
- **Tipografía:** Renderizada con `textTOP` alineada a rejilla. Movimientos secos con transiciones claras, sin oscilaciones orgánicas.

---

## 5. Rúbrica de Auto-Evaluación Visual

Usa `capture_top` en `out1` y verifica cada criterio antes de declarar completada una tarea visual:

- [ ] **Punto Focal:** ¿Hay un sujeto claro identificable en el primer segundo?
- [ ] **Squint Test:** ¿La imagen mantiene siluetas claras al entrecerrar los ojos o en escala de grises?
- [ ] **Rango Dinámico:** ¿Están presentes oscuros, medios y claros sin quemar blancos ni empastar sombras innecesariamente?
- [ ] **Paleta:** ¿Los colores responden a una paleta intencional y no a ruido aleatorio de arcoíris?
- [ ] **Separación Fondo-Figura:** ¿El sujeto se separa nítidamente del fondo por valor, color o profundidad?
- [ ] **Evolución Temporal:** ¿Se esperó a que los sistemas de partículas y feedback se estabilizaran antes de juzgar el fotograma?
- [ ] **Sin Vicios por Defecto:** ¿Se eliminaron los materiales Phong grises, ruidos sin filtrar y luces por defecto?

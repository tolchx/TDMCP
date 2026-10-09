---
name: td-pop-top-to-pop
description: "Conversión de texturas 2D en nubes de puntos 3D reactivas (toptoPOP), trazado vectorial de contornos (tracePOP), y relieve volumétrico Z por luminancia en GPU."
---

# Top-to-POP y Trace POP: Nubes de Puntos y Relieve 3D desde Texturas (GPU)

Guía técnica y contratos verificados en vivo contra TouchDesigner 2025/2026 para la conversión de texturas 2D (video en vivo, webcam, ruido generativo o gráficos vectoriales) en nubes de puntos 3D reactivas y curvas poligonales en GPU.

---

## 1. Operadores Clave del Pipeline TOP $\to$ POP

| Operador | Familia / Tipo | Función Principal | Configuración Crítica |
| :--- | :--- | :--- | :--- |
| **`toptoPOP`** | Converter / Generator | Muestrea un TOP 2D y emite puntos en GPU | `surftype='points'`, `input0chanscope='r g b a'`, `input0attrscope='Color'` |
| **`tracePOP`** | Vectorizer / Contour | Traza contornos vectoriales sobre umbrales de canal | `channel='alpha'` o `rgbmax`, `threshold=0.5`, `twodimensions='contourls'` |
| **`mathmixPOP`** | Operator / Math | Mapea canales de color a componentes espaciales | `comb0scopea='Color(0)'` $\to$ `comb0result='P(2)'` (relieve Z) |
| **`convertPOP`** | Primitives | Garantiza primitivas de punto para cada vértice | `convert='topointprims'` (Contrato C2) |
| **`pointspriteMAT`** | Material | Shading acelerado de partículas con blending aditivo | `pointsize=3.0`, `blending=add` |

---

## 2. Arquitectura de Relieve Volumétrico Z (`toptoPOP`)

```text
noiseTOP / moviefileinTOP (textura 2D de alta resolución)
       │
       ▼
toptoPOP (surftype='points', overrideresx=True, resx=120, resy=120)
       │  - Emite grilla regular de 14,400 puntos en X/Y
       │  - Escribe atributos Color_0..3 en cada punto
       ▼
mathmixPOP (comb0oper='mult', scopea='Color(0)', scopeb='0.75', result='P(2)')
       │  - Desplaza coordenada P.z proporcional a la luminancia
       ▼
noisePOP (turbulencia 3D opcional)
       │
       ▼
convertPOP (convert='topointprims')
       │
       ▼
nullPOP (null_render) -> geometryCOMP -> renderTOP
```

---

## 3. Contratos y Gotchas Verificados en Vivo

1. **Control de Presupuesto en `toptoPOP` (`overrideresx`/`overrideresy`):**
   - Si no se sobreescribe la resolución, `toptoPOP` genera un punto por cada píxel del TOP. Una textura 1920×1080 crearía $2.07 \times 10^6$ puntos, saturando el presupuesto de cocinado si luego se conectan operadores de búsqueda o CPU.
   - **Regla:** Activar siempre `overrideresx = True` y `overrideresy = True` fijando dimensiones equilibradas (ej. 100×100 a 256×256 para 10k–65k puntos).

2. **Indexación de Componentes en `mathmixPOP`:**
   - Para direccionar canales específicos de color o posición, usar notación de subíndice `Color(0)` (canal Rojo / luminancia) y `P(2)` (eje Z).
   - `comb0oper = 'mult'` escala el valor normalizado $[0, 1]$ a la profundidad volumétrica deseada en unidades métricas de mundo.

3. **Primitivas de Punto (Contrato C2):**
   - Aunque `toptoPOP` tenga `surftype='points'`, muchos renderers y materiales esperan primitivas de punto explícitas. Interpolar `convertPOP` con `convert='topointprims'` antes del terminal para garantizar $N_{\text{puntos}} \equiv N_{\text{prims}}$ (1:1).

4. **Trazado de Siluetas y Tipografías con `tracePOP`:**
   - Ideal para convertir `textTOP` o máscaras en siluetas vectoriales de alambre en 3D.
   - Para bordes limpios, configurar `inside = 'above'` y filtrar ruido de alta frecuencia con `filterdist = 0.05`.

---
name: td-operator-gotchas
description: "Catálogo exhaustivo de trampas, nombres de parámetros abreviados y comportamientos contra-intuitivos en TouchDesigner 2025/2026. Previene errores críticos en TOPs, CHOPs, POPs, MATs, DATs e Instancing."
---

# Trampas de Operadores y Parámetros en TouchDesigner (Gotchas)

En TouchDesigner existen numerosos parámetros con nombres abreviados, defaults que actúan de forma inesperada o requisitos sutiles que pueden romper un proyecto silenciosamente. Este catálogo documenta cada una de estas peculiaridades, verificadas en TouchDesigner 2025.33230+.

---

## 1. Principios Universales

1. **Referenciar siempre a `null*`, nunca a nodos activos:**
   - Termina toda cadena en un operador Null (`nullTOP`, `nullCHOP`, `nullPOP`).
   - Apunta las referencias y expresiones hacia ese Null. Si insertas o borras filtros intermedios, nada aguas abajo se romperá.
2. **Los parámetros de referencia a OP NO se actualizan al renombrar:**
   - Si un Select TOP apunta a `constant1` y renombras este a `bg_source`, el Select TOP quedará apuntando al nombre antiguo roto. Si renombras un nodo, debes buscar y actualizar todas las referencias textuales.
3. **Los valores de Menú son tokens en minúsculas, no las etiquetas visibles:**
   - `ortho` (no `orthographic`), `deg` (no `degrees`), `aa8` (no `aa8high`), `chanpercol` (no `Channel per Column`).
4. **Demanda de Cocinado (Cook Model):**
   - Los operadores dependientes del tiempo solo cocinan cuando algo exige su salida: un visor activo, un Render/Out TOP, o un script CHOP Execute. Una cadena quieta suele ser una cadena no demandada, no una cadena rota.

---

## 2. Trampas en TOPs (Texturas e Imágenes)

- **`compositeTOP`:**
  - El parámetro `operand` por defecto es `multiply`.
  - Al usar `over`, **Input 0 es el PRIMER PLANO (foreground)** y los inputs siguientes van por debajo (el inverso de una pila de capas habitual).
- **`constantTOP`:**
  - Nace blanco con alpha 1.0 por defecto; para un fondo transparente vacío, fija `colorr=0, colorg=0, colorb=0, alpha=0`.
- **`feedbackTOP`:**
  - El parámetro `top` debe nombrar el `nullTOP` de salida que cierra el lazo.
  - En el fotograma de reset toma la resolución de su entrada; en cuadros posteriores toma la del objetivo. Si difieren, la resolución cambiará en el segundo frame.
- **`renderTOP`:**
  - La cámara por defecto es `cam1`, luces y geometrías por defecto son `*`.
  - Si vas a aplicar Bloom o Tone Mapping posterior, el `format` del render debe ser de coma flotante (`rgba16float` o `rgba32float`); de lo contrario, todo se recorta a 1.0 antes del post-proceso.
- **`rgba8fixed` vs Formatos Float:**
  - `rgba8fixed` (el formato estándar por defecto) recorta los valores estrictamente a `0.0 - 1.0`. Texturas de datos, simulaciones y HDR requieren `rgba16float` o `rgba32float`.
- **`moviefileinTOP`:**
  - Los pulsos de recarga (`reloadpulse`) o cambio de archivo surten efecto al avanzar de fotograma en el timeline.
- **`glslTOP`:**
  - Tiene exactamente 3 conectores de entrada. Para 4 o más entradas o lectura de buffers POP, usa `glslmultiTOP`.

---

## 3. Trampas en CHOPs (Canales y Datos)

- **`selectCHOP`:**
  - El parámetro para referenciar otros CHOPs se llama **`chops` (en plural)**, no `chop`.
- **`parameterCHOP`:**
  - Viene con `custom=1` (activo) y `builtin=0` (inactivo) por defecto. Para leer parámetros integrados como `tx`, `ty`, debes activar `builtin`.
- **`lagCHOP`:**
  - No existe el parámetro `lag`. Son dos: `lag1` (tiempo de subida) y `lag2` (tiempo de bajada).
- **`logicCHOP`:**
  - En el modo `convert`, solo la opción `bound` lee los límites `boundmin` / `boundmax`. Las opciones `gt`, `lt`, etc., comparan entre entradas, no contra un umbral constante.
- **`timerCHOP`:**
  - **¡Peligro crítico!** Viene con `cycle=0` (apagado) y `cyclelimit=1` con `maxcycles=4`. Un temporizador periódico se detendrá misteriosamente al cuarto ciclo a menos que actives `cycle=1` y desactives el límite.
- **`audiodeviceinCHOP`:**
  - Se llama exactamente `audiodeviceinCHOP` (no existe `audiodevinCHOP`).
- **`absTime.seconds` en Shaders/CHOPs:**
  - Nunca manejes animaciones de larga duración usando directamente `absTime.seconds` en la GPU. Conforme el número crece, los floats pierden precisión y el movimiento empieza a dar saltos visibles. Usa osciladores cíclicos (seno/coseno), `beatCHOP` o `absTime.frame % periodo`.

---

## 4. Trampas en POPs (GPU Point Operators 2025+)

- **`rectanglePOP`:**
  - Los parámetros de tamaño son **`sizeu` y `sizev`**, NO `sizex` o `sizey`. Intentar asignar `sizex` falla silenciosamente sin avisar.
- **El Toroide Fantasma de `geometryCOMP`:**
  - Al crear un nuevo `geometryCOMP`, TouchDesigner crea automáticamente un `torus1` SOP en su interior con su **flag de Render encendido**. Si construyes una red POP sin borrar ese toroide, el Render TOP renderizará ambos. **Borra siempre el `torus1` inicial.**
- **Puntos sin Primitivas de Punto:**
  - Los puntos puros en el espacio no se renderizan solos. En los generadores POP (`gridPOP`, etc.), asegúrate de que el parámetro de conectividad genere primitivas de punto (*Point Primitives*).
- **Atributo de Color en POPs:**
  - En POPs el color es **`Color` (`float4`)**, NO el clásico `Cd` de SOPs.
- **`particlePOP` y `feedbackPOP`:**
  - Requieren el ciclo de vida: pulsar `initializepulse`, luego `startpulse`. Al alterar atributos o topología aguas arriba, hay que reiniciar.
- **Capacidad Máxima de Partículas:**
  - Si `maxparticles < birthrate * life`, las partículas se destruirán antes de cumplir su tiempo de vida programado.
- **`glslPOP` y Uniforms:**
  - En `glslPOP`, los uniforms se auto-declaran desde la página Vectors. Volver a declararlos dentro del shader provoca un error de compilación por redeclaración.
  - Con `outputaccess=writeonly` (por defecto), el shader no puede leer los búferes de salida; usa `TDIn_P()` para leer los puntos de entrada o cambia a `readwrite`.

---

## 5. Trampas en MATs e Instancing

- **`pbrMAT`:**
  - `metallic` y `roughness` nacen en 1.0 (apariencia de cromo oxidado). Para materiales dieléctricos normales, pon `metallic=0` y ajusta `roughness`.
  - Requiere obligatoriamente un `environmentlightCOMP` o renderizará casi completamente negro.
- **`pointspriteMAT`:**
  - Es el único material capaz de dar dimensión y textura a sprites de partículas. Con cualquier otro material, los puntos renderizan como píxeles individuales de 1 px.
- **Instanciación Directa desde POPs:**
  - En la página Instance de `geometryCOMP`, asigna directamente el `nullPOP` en `instanceop`.
  - En los selectores escribe: `P(0)`, `P(1)`, `P(2)` para traslación, y `Color(0)`, `Color(1)`, `Color(2)` para color. **No hagas conversión a `poptoCHOP`** (evita la costosa copia de GPU a CPU).

# Estudio Exhaustivo: Embody, Envoy y TDXN (TouchDesigner + Agentes de IA)

Este documento recoge la investigación técnica profunda sobre **Embody**, el servidor MCP **Envoy**, el formato de serialización de redes **TDXN v2.1** (TouchDesigner eXternal Network) y el tutorial oficial de YouTube presentado por **Elburz Sorkhabi** (Interactive & Immersive HQ) junto a **Dylan Roscover** (The Experience Company / TEC).

---

## 1. El Tutorial de YouTube: "Using an AI Agent Inside TouchDesigner"

### Contexto y Producción
- **Canal / Autor:** Interactive & Immersive HQ (Elburz Sorkhabi) con la participación directa del desarrollador Dylan Roscover.
- **Video URL:** `https://youtu.be/3DHewZQTGHQ?si=kk6aXebiVWQaPf9A`
- **Herramientas en juego:** TouchDesigner 2025+, Embody 6.x `.tox`, Envoy MCP Server, Claude Code / Cursor / Windsurf, y Git.

### Flujo Central y Conceptos Clave Demostrados en el Video

1. **Instalación sin Fricción:**
   - Se descarga el componente `Embody.tox` desde los releases de GitHub (`https://github.com/dylanroscover/Embody/releases`) o se ejecuta un bootstrap de una sola línea en el Textport de TouchDesigner.
   - Al soltar el `.tox` en la red de TouchDesigner, se lanza automáticamente el **Setup Wizard**:
     - Selección de cliente de IA (Claude Code, Cursor, Windsurf, OpenCode, Gemini CLI, etc.).
     - Configuración del puerto de Envoy (puerto por defecto `9870`, o escaneo ascendente si está ocupado).
     - Creación automática del entorno virtual Python (`.venv`) local del proyecto emparejado exactamente con el intérprete de TouchDesigner.
     - Generación automática del archivo de configuración `.mcp.json` en la raíz del repositorio de Git.

2. **El Problema que Resuelve (Binario `.toe` vs Texto Diffable):**
   - Históricamente, TouchDesigner almacena los proyectos como archivos binarios `.toe` o `.tox`.
   - En control de versiones (Git), un archivo `.toe` binario genera merge conflicts imposibles de resolver y diffs opacos (blobs binarios que inflan el repositorio).
   - Para un agente de IA, inspeccionar o generar un `.toe` directamente es imposible; requiere llamadas RPC una a una para cada operador, parámetro y cable, lo que consume miles de tokens y múltiples turnos de conversación.
   - **Solución Embody:** Externalización jerárquica a disco. Cada COMP seleccionado se exporta como un archivo YAML `.tdxn` y cada DAT como `.py`, `.json`, `.xml` o `.glsl`. Git puede ver línea por línea qué operador cambió, qué parámetro se modificó y qué cable se reconectó.

3. **Construcción Asistida por IA: ABBA Video Mixer:**
   - En el tutorial, Elburz y Dylan guían a un agente (ej. Claude Code con Envoy) pidiéndole en lenguaje natural construir un **Mezclador de Video ABBA**:
     - Canal A: Fuente de video / generador (ej. Noise TOP o Movie File In).
     - Canal B: Segunda fuente de video.
     - Módulo de Mezcla: Composite TOP o Cross TOP con control de crossfade (0 a 1).
     - Controles de Nivel / Color: Level TOPs para balancear gamma, brillo y contraste de cada canal.
     - Terminal de Salida: `out1` (Out TOP con flag de display activo para proyectar en el fondo de la red).
     - Interfaz de Parámetros: Custom Parameters en el COMP contenedor (`Crossfade`, `BlendMode`, `MasterLevel`).
   - El agente no solo crea los nodos, sino que los posiciona con la rejilla canónica de 200 unidades, conecta los cables en flujo horizontal (de izquierda a derecha), conecta los parámetros con expresiones, y ejecuta pruebas de render.

4. **Ciclo de Verificación y Cierre:**
   - El agente ejecuta `capture_top` sobre `out1`.
   - Envoy evalúa los píxeles capturados y emite un veredicto de calidad: rechaza frames negros o vacíos (`Quality: FAIL`), obligando al agente a depurar si faltan flags de display/render, si las resoluciones son 0, o si un shader falló.
   - Una vez verificado el resultado visual, Embody guarda automáticamente la red en disco como `.tdxn`, permitiendo hacer `git commit` inmediato con un mensaje limpio y descriptivo del cambio.

---

## 2. Deconstrucción Arquitectónica: Embody, Envoy, TDXN y Convoy

Dylan Roscover articula el sistema en cuatro pilares:

```
┌────────────────────────────────────────────────────────────────────────┐
│                          EMBODY ECOSYSTEM                              │
├─────────────────────┬───────────────────┬──────────────────────────────┤
│ 1. ENVOY (MCP)      │ 2. TDXN (FORMAT)  │ 3. EMBODY (CORE)             │
│ Velocidad Hacia     │ El Sustrato       │ Velocidad Lateral            │
│ Adelante: 70 tools  │ Redes TD como     │ Externalización automática,  │
│ para que la IA cree,│ YAML diffable,    │ sincronización bidireccional │
│ conecte y depure.   │ conciso y legible.│ con disco y Git.             │
├─────────────────────┴───────────────────┴──────────────────────────────┤
│ 4. CONVOY (LAN RELAY)                                                  │
│ Velocidad Hacia Afuera: Orquestación multi-nodo en red local.          │
└────────────────────────────────────────────────────────────────────────┘
```

### A. TDXN v2.1 (TouchDesigner eXternal Network)
TDXN es una especificación estructurada en YAML que describe una red completa en texto plano:
- **`type_defaults`**: Si 10 `baseCOMP` comparten expresiones de tamaño y posición (`resizecomp: =me`), se declaran una sola vez en el bloque de defaults en lugar de repetirse 10 veces.
- **`par_templates` (`$t`)**: Plantillas reutilizables de páginas de parámetros custom (ej. metadata de Build, Version, Autor). Los operadores referencian la plantilla con `$t: template_name` y solo aportan sus valores concretos.
- **Shorthand de Expresiones (`=`)**: En lugar de objetos verbosos `{"mode": "expression", "expr": "..."}`, una expresión se indica directamente con prefijo `=`: `opacity: =parent().par.Speed / 10`.
- **Shorthand de Bindings (`~`)**: Los enlaces bidireccionales se indican con prefijo `~`: `chan: ~op('null1')['chan1']`.
- **Flags como Listas Compactas**: `flags: [display, viewer, lock]` en lugar de 10 booleanos independientes.
- **Conexiones Simplificadas**: `inputs: [noise1, level1]` donde la posición en el array mapea directamente al índice del connector de entrada.
- **Scripts Multilínea Limpios**: DATs de texto usan el bloque literal de YAML (`|`), permitiendo diffs línea a línea sin secuencias de escape `\n`.
- **Ahorro de Tokens:** Reduce entre **20x y 90x** el costo de tokens frente a múltiples llamadas `get_op` + `query_network`.

### B. Envoy MCP Server (70 Herramientas)
Envoy implementa un conjunto masivo de herramientas organizadas por disciplinas operativas:

1. **Gestión de Operadores:**
   - `create_op`, `create_extension`, `delete_op`, `copy_op`, `rename_op`, `get_op`, `query_network`, `find_children`, `cook_op`.
   - *Protección:* Auto-posiciona operadores y ubica automáticamente los DATs acoplados (*docked*) ~30 unidades por debajo del host.

2. **Control de Parámetros:**
   - `set_parameter`: Soporta valores, expresiones `=`, bindings `~`, modos, crecimiento automático de secuencias (`const5name` expande a 6 bloques), y rechaza valores de menú inválidos sugiriendo los tokens permitidos.
   - `get_parameter`: Modo compacto o detallado, búsqueda global por patrón/expresión.
   - `describe_op_type`: Introspección completa de cualquier tipo de operador **antes de crearlo** (nombres exactos de parámetros, estilos, valores por defecto, etiquetas).

3. **Contenido de DATs:**
   - `get_dat_content`, `set_dat_content`.
   - `edit_dat_content`: Edición quirúrgica de subcadenas (`old_string` -> `new_string`) evitando reescribir scripts enteros.

4. **Datos Reducidos de CHOPs y POPs:**
   - `get_chop_data`: En lugar de volcar 2,400 floats de un CHOP de 4 canales x 600 muestras, devuelve resumen estadístico (`min`, `max`, `mean`, `std`, `first`, `last`) y diferencias relativas (`compare_to`).
   - `get_pop_data`: Devuelve metadata de atributos (P, N, Color, etc.) en ~0.02 ms sin bloquear el bus GPU->CPU. Protege la lectura de muestras crudas con límite de seguridad (`max_points`).

5. **Layout y Rejilla Canónica:**
   - `get_network_layout`, `set_op_position`, `layout_children`.
   - Invariantes: Flujo de izquierda a derecha (positivo en X), separación calculada por `size + gap` redondeada al múltiplo de 200, y docked DATs acoplados debajo.

6. **Anotaciones:**
   - `create_annotation`, `get_annotations`, `set_annotation`, `get_enclosed_ops`.

7. **Rendimiento, Diagnóstico y Ejecución:**
   - `get_op_errors`: Detecta errores de cocinado, tracebacks de Python en scripts (invisibles a `op.errors()`) y errores de compilación GLSL (`shaderErrors`).
   - `get_project_performance`: FPS del proyecto, tiempo de cuadro, memoria GPU/CPU, frames perdidos y top hotspots.
   - `run_soak_test`: Prueba de estrés continua en segundo plano para verificar estabilidad de framerate.
   - `execute_python`: Ejecución con linter integrado que emite advertencias de layout (`LAYOUT WARNING`) o de threading (`THREADING WARNING`).

8. **Captura y Verificación Visual:**
   - `capture_top`, `capture_op`: Captura de imágenes con evaluación de calidad por software (determina `PASS` o `FAIL` si el frame es negro, plano o transparente).

9. **Operaciones en Lote:**
   - `batch_operations`: Ejecuta múltiples acciones en una sola transacción atómica con un solo paso de Undo (`Ctrl+Z`).

10. **Convoy (LAN Work Relay):**
    - Herramientas `convoy_*` para descubrir, sincronizar y disparar builds en nodos remotos en una red local de confianza.

---

## 3. Matriz Comparativa: Derivative Official vs Envoy vs tolchx-TDMCP

| Capacidad / Dimensión | Derivative Official MCP (Port 13316) | Dylan Roscover's Envoy (Port 9870) | Nuestro tolchx-TDMCP (`server.py`) |
|---|---|---|---|
| **Arquitectura de Ejecución** | Integrado en TD (C++/Python runtime) | Componente `.tox` residente en TD + puente stdio | Híbrido: Servidor MCP externo (FastMCP) + puente HTTP a TD |
| **Cantidad de Herramientas** | 26 herramientas live | 70 herramientas live | 21 offline (KB/POPs/GLSL) + 12 live tools |
| **Operación Offline / Sin TD** | ❌ No funciona sin TD abierto | ⚠️ Bridge provee estado básico y lanzamiento | ✅ 100% operativo (KB, GLSL analyzer, POP matrix, contratos) |
| **Formato de Red / Archivos** | ❌ Ninguno nativo en MCP (solo RPC individual) | ✅ TDXN v2.1 YAML completo (export/import/diff) | ⚠️ Soporte preliminar TDN -> ampliable a TDXN v2.1 |
| **Verificación de Calidad Visual** | ❌ Solo captura de imagen sin juicio | ✅ `capture_top` con veredicto de píxeles (`PASS/FAIL`) | ⚠️ Captura cruda -> requiere veredicto automático |
| **Layout y Posicionamiento** | ❌ Básico (`set_node_position`) | ✅ Rejilla 200, fórmula `size+gap`, auto-hug docked DATs | ⚠️ Reglas en KB -> formalizable en código |
| **Diagnóstico de Errores** | ⚠️ `get_errors` básico (`op.errors()`) | ✅ Traza scripts de DATs + errores de shader GLSL | ⚠️ Básico -> requiere integración profunda |
| **Lectura Eficiente CHOP/POP** | ❌ Vuelca datos o requiere script | ✅ Resúmenes estadísticos compactos (`get_chop_data`) | ⚠️ Via `execute_code` -> parametrizable como herramienta |
| **Edición Quirúrgica de DATs** | ❌ Solo sobreescritura completa | ✅ `edit_dat_content` (reemplazo de subcadenas) | ⚠️ Sobreescritura -> útil incorporar reemplazo puntual |
| **Orquestación Multi-Nodo** | ❌ No disponible | ✅ Convoy LAN relay | ❌ No prioritario para workstation única |

---

## 4. Oportunidades Clave para Complementar Nuestro MCP (`tolchx-TDMCP`)

Para convertir nuestro sistema en la suite de desarrollo más potente y versátil para TouchDesigner, extraemos las siguientes ventajas de Envoy/Embody:

1. **Adopción Completa del Formato TDXN v2.1:**
   - Estandarizar nuestras herramientas `td_export_tdn`, `td_import_tdn`, `td_read_tdn` para cumplir estrictamente la especificación TDXN v2.1 de Embody.
   - Esto permite que un agente trabajando en `tolchx-TDMCP` genere redes completas en YAML en un solo turno, ahorrando hasta un 90% de llamadas y tokens.

2. **Inclusión de Skills de Alto Valor Artístico y de Estabilidad:**
   - **`td-visual-aesthetics`**: Protocolo para eliminar el "default programmer art" (tablas de composición, iluminación de 3 puntos, paletas armónicas con Lookup TOP, y las 8 recetas de looks: High-key, Neon, Filmic 3D, Feedback orgánico, Nebulosa de partículas, etc.).
   - **`td-operator-gotchas`**: Registro de parámetros abreviados y comportamientos contra-intuitivos en TD 2025/2026 (`rectanglePOP` usa `sizeu/sizev`, `renderTOP` usa `format` flotante para bloom, el toroide por defecto en `geometryCOMP`, etc.).
   - **`td-embody-tdxn`**: Reglas para estructurar proyectos con externalización a disco y flujos de trabajo en Git.

3. **Verificación de Render con Veredicto Automático:**
   - Implementar un evaluador de calidad visual tras cada llamada de render/captura que confirme si la salida es negra, estática o válida.

4. **Reglas Canónicas de Layout y Docked DATs:**
   - Incorporar la fórmula de espaciado dinámico `next = prev + size + gap` (con gap >= 200 redondeado a múltiplo de 200) y el centrado de DATs asociados a ~30 unidades bajo el nodo host.

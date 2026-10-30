# td-knowledge — capa de conocimiento para TouchDesigner (offline + live)

MCP server por **stdio en Python puro (stdlib, sin dependencias)**. Trabaja en dos modos, en el
mismo proceso y sin bridge (:44444 retirado):

* **22 tools offline** — responden con la KB curada **sin** TouchDesigner abierto.
* **35 tools live** — hablan MCP contra el **server oficial de Derivative** (`127.0.0.1:13316/mcp`)
  para operaciones de alto nivel sobre el proyecto vivo; si TD está cerrado devuelven un error claro.

## Tools offline (22)

| Tool | Qué responde |
|---|---|
| `kb_info` | Provenance del KB: qué assets, cuándo, cuántos docs (1,302), módulos TS extraídos y resumen de la matriz POP. |
| `kb_taxonomy` | Qué hay en la base (conteos por familia / trust tier / source type) + índice de docs. |
| `kb_search` | Búsqueda FTS5 (BM25 + snippet) con filtros por familia y **trust tier**: `official`, `empirical`, `community`, `live-verified`. |
| `kb_get` | Documento completo por nombre/slug, con paginado. |
| `pop_matrix` | Matriz POP **medida en vivo** (97 tipos): qué se crea, qué cocina, inputs requeridos, params medidos, errores. |
| `ops_doc` | Doc curado de un operador (cualquier familia) enriquecido con **topología** (`topology.json`: `inputCount`, `isMultiInput`, `inputs`, `outputs`, `connectsTo`, `warnings`) y `creation_defaults`. |
| `ops_params` | Lista de parámetros de un tipo (nombre, label, tipo, default, página). |
| `validate_pop_pars` | Valida pre-flight nombres de parámetros para **cualquier familia** (`POP`, `TOP`, `CHOP`, `SOP`, `DAT`, `MAT`, `COMP`) contra `pop_matrix.json`, `ops_doc` y `python_api`. Detecta propiedades OP pasadas como par (`display`, `render`, `bypass`, `lock`), prefijos de tuplas (`sizex/y/z`), bloques de secuencia (`numBlocks`) y advertencias de co-dependencia (`outputresolution='custom'`, `globforcemult`, `timeintegration`, `triangulatequads`). |
| `pop_knowledge` | Datos POP y topología empírica: `patterns`, `wiki_params`, `pop_inventory`, `validation`, `glsl_library`, `glsl_pops_reference`, `glsl_curriculum`, `pop_chains`, `pop_networks`, `pop_parameters`, `real_world_topology`, `pop_rules`, `attribute_rules`, `bridges`, `pop_style`. |
| `resolve_operator` | Lenguaje natural (ES/EN) → tipo de operador canónico + **conceptos arquitectónicos** (`CONCEPTS`), alias de parámetros/atributos y plantillas sugeridas. |
| `templates` | Plantillas de red (`NETWORK_TEMPLATES` + `POP_NETWORK_TEMPLATES` + `pop-chains.json`) y 17 specs arquitectónicas (`boids`, `SPH`, `field volumes`, `DMX`…): `action=list\|get`. |
| `recipes` | Recetas builder verificadas + 30 recetas `glslTOP` (Book of Shaders) con gotchas y código: `action=list\|get`. |
| `workflows` | 43 workflows de producción completos (`.md`) + 43 grafos JSON (`workflows/graphs/*.json`): `action=list\|get`. |
| `tutorials` | 28 tutoriales paso a paso + suite completa `pop_tutorial` (`INDEX`, `TUTORIAL_KNOWLEDGE` y lecciones `01`..`06`): `action=list\|get`. |
| `glsl_solutions` | Catálogo de soluciones y fixes a errores frecuentes del compilador GLSL en TouchDesigner. |
| `python_api` | Referencia offline de la API Python de las clases de operador (TOP/CHOP/SOP/DAT/POP): parámetros, métodos y docstrings sin TD abierto. |
| `discovery` | Bitácora empírica y cheatsheets de TouchDesigner (27 fuentes: `discovery-log`, `pop-parameter-mapping`, `TD_PARAMETER_CHEATSHEET`, `POPs_KNOWLEDGE`, `POPs_CORRECTIONS`, `PERFORMANCE`, `docs_internal`, contratos, etc.). |
| `master_prompts` | Directivas maestras para orquestación de sistemas complejos (`particles-experto-feedback-sim`, `pathtracer-system`, `validate-and-fix`). |
| `glsl_rules` | Reglas GLSL verificadas en vivo (POP y TOP), por id de regla o búsqueda libre. |
| `glsl_analyze` | Análisis **estático** de un shader o snippet: POP R1–R4 / F1 (`void main`) / F4 (`TDNumElements(k)`) / multi-input `TDIn_*`, TOP R1–R4 / T4 (`uniform0name`) / T10 (`sTD2DInputs`), y Python R6 (`.numPoints()` método) / f-string backslash / bare math. |
| `glsl_curriculum` | Currículum estructurado GLSL (`glsl_curriculum.json` con `entry='<id>'` y `learning_path=true`) + librería POP + 79 shaders sueltos. |
| `contracts` | **Contratos verificados en vivo** contra TD 2025.32460 + TDMCP 1.1.55, servidos desde `contracts/VERIFIED_CONTRACTS.md` (versionado, no derivado). |

## Tools live (35) — requieren TD con el `.tox` oficial activo (`127.0.0.1:13316`)

| Tool | Qué hace (y por qué complementa al oficial) |
|---|---|
| `td_status` | ¿Está TD vivo? proyecto, build (`runningBuild` + `buildMismatch`), fps, estado del reloj (`power`, `timelinePlay`, `realTime`, `cookingVerdict`) y versión del server oficial. |
| `find_in_ops` | Busca un texto en **todo** un subárbol (con presupuesto `max_nodes`/`max_sec`): contenido de DATs, **expresiones** de parámetros, nombres de par, comentarios y nombres de operador en una sola llamada. |
| `auto_layout` | Ordena los operadores por **capas topológicas** (sin cruces): lee el cableado, calcula las posiciones localmente y las aplica con `reposition_operators`. `dry_run: true` para previsualizar. |
| `smart_connect` | Conecta dos operadores eligiendo el **índice de input** según la familia que espera el destino (`topology.json` + KB + docs del build). |
| `tdn_export` | Exporta una red a **TDN v1.4** (JSON versionable en git) leyendo el proyecto en vivo. |
| `tdn_diff` | Compara dos `.tdn` **sin TD**: operadores agregados/quitados y cambios de parámetros, tipos, flags y cableado. |
| `tdxn_export` | Exporta una red completa a **TDXN v2.1 YAML** (estándar Embody diffable). |
| `tdxn_build` | Construye una red completa en TouchDesigner a partir de **TDXN v2.1 YAML** (operadores, conexiones, `=expr`, `~bind`, DATs y flags en un solo turno). |
| `eval_render_frame` | Evalúa calidad visual de una imagen o TOP en vivo: detecta frames negros, planos o transparentes emitiendo veredicto `PASS`/`FAIL` y métricas de luminancia y contraste. |
| `get_op_errors_deep` | Diagnóstico profundo de un COMP y sus hijos (con presupuesto `max_nodes`/`max_sec`): errores de cocinado, advertencias y trazas de compilación GLSL en DATs `_info`. |
| `td_measure` | Mide en vivo el rango real de canales CHOP (`min`, `max`, `mean`, `range`, si es constante/normalizado y `suggested_scale`/`suggested_offset`), geometría POP/SOP (`numPoints`, `numPrims`, `bounds`, atributos), resolución TOP o contenido DAT. |
| `td_glsl_apply` | Pipeline GLSL atómico en vivo: valida estáticamente el shader (`glsl_analyze`), crea el `textDAT` + `glslPOP`/`glslcopyPOP`/`glslTOP` + `infoDAT`, auto-extrae y configura `uniforms` (incluyendo `=expr`), `Create Attributes` (`attr` sequence, `custom`, `numcomps`), `outputattrs` y `outputaccess`, conecta inputs y verifica la compilación con líneas de error. |
| `td_explore_project` | Radiografía rápida de un contenedor o proyecto en una sola llamada (con presupuesto `max_nodes`/`max_sec`): conteos por familia y tipo, sub-COMPs, shaders GLSL, `customPars`, errores activos y top operadores por `cookTime`. |
| `td_compare_networks` | Compara en vivo dos contenedores COMP (`path_a` vs `path_b`): operadores exclusivos de cada lado, diferencias de parámetros no-default y diferencias de cableado. |
| `td_spatial_context` | Contexto espacial de la UI de TouchDesigner: pane activo, ruta abierta en el editor, operador actual (`currentChild`), selección múltiple y estado del timeline. |
| `td_build_pop_render` | Construye en 1 llamada el pipeline completo de renderizado POP (`geometryCOMP` con eliminación de `torus1` + fuente/esfera POP + `convertPOP(topointprims)` + `nullPOP` con `display`/`render` + `cameraCOMP` + `pointspriteMAT`/`constantMAT`/`pbrMAT` + `renderTOP` + `nullTOP`), corre 4 pasadas de cook y evalúa el frame. |
| `td_instantiate_template` | Instancia en vivo cualquier plantilla de red (`network_templates.json`, `pop-chains`, `custom_templates`) o receta (`recipes`) en una sola llamada: crea contenedores y operadores, expande bloques de secuencia (`numBlocks`), aplica parámetros/expresiones, cablea y ordena el layout. |
| `td_verify_network` | Verificación integral en 1 llamada (Gauntlet vivo): fuerza 4 pasadas de cook (`settle`), audita ownership de `geometryCOMPs` (`torus1` borrado, `display`/`render` activos, `numPoints`/`numPrims > 0`), detecta `NaN`/`Inf` en POPs/CHOPs, corre `get_op_errors_deep` y `eval_render_frame`, y devuelve veredicto `PASS`/`FAIL` con `actionable_fixes`. |
| `td_profile_network` | Profiler de rendimiento y cuellos de botella en vivo: mide `cookTime` CPU, `gpuCookTime` y memoria por nodo, calcula el % del presupuesto de frame (`16.67ms` a 60fps) y detecta anti-patrones (`copyPOP` masivo sin instancing, SOPs en pipeline POP, TOPs >4K, readbacks GPU→CPU). |
| `td_scaffold_component` | **Pilar 6**: encapsula un COMP como módulo profesional con Custom Parameters tipados, bindings/expresiones hacia hijos, Python Extension (`reinitextensions`) y exportación `.tox`. |
| `td_wire_reactive` | **Pilar 7**: mide en vivo un canal CHOP, construye la cadena `selectCHOP` → `mathCHOP` (auto-calibrado) → `lagCHOP` → `nullCHOP` y lo vincula al parámetro/uniform destino. |
| `td_frame_camera_to_geo` | **Pilar 8a**: calcula el bounding box 3D mundial combinado de los POPs/SOPs activos y auto-encuadra matemáticamente la `cameraCOMP` (`tx, ty, tz, near, far`). |
| `td_visual_diff` | **Pilar 8b**: compara dos TOPs o PNGs píxel a píxel (`mean_abs_diff`, `changed_pixels_pct`, `psnr_db` y veredicto `SIGNIFICANT_CHANGE` / `SUBTLE_CHANGE` / `IDENTICAL_NO_OP`). |
| `td_control_simulation` | **Pilar 9**: resetea atómicamente todos los nodos temporales (`feedbackPOP`, `particlePOP`, `feedbackTOP`, `trailPOP`, `cachePOP`, `speedCHOP`), avanza $N$ pasos de pre-roll y diagnostica `STABLE_DYNAMIC`, `STABLE_STATIC`, `EMPTY`, `EXPLODING` o `NAN_CORRUPTED`. |
| `td_harvest_pattern` | **Pilar 10**: cosecha un contenedor vivo hacia `knowledge/custom_templates/<name>.json` + `.tdxn`, quedando disponible al instante en `templates` y `td_instantiate_template`. |
| `td_build_control_panel` | **Pilar 11**: construye un panel UI de control y monitoreo Perform-ready (`containerCOMP` con cabecera, visor `opviewerCOMP` conectado al TOP de salida, dock de `parameterCOMP`s interactivos y `windowCOMP` opcional). |
| `td_render_contact_sheet` | **Pilar 12**: visión temporal multi-frame; avanza la red $N$ muestras espaciadas por `step_frames`, compone una hoja de contacto PNG ($R \times C$) con barra de progreso temporal y calcula métricas de movimiento (`ANIMATING` / `STATIC` / `BLANK`). |
| `td_setup_audio_analyzer` | **Pilar 13**: construye un analizador de audio multi-banda (`baseCOMP` con fuente `test_oscillator`/`file`/`device`/`op`, filtros por banda, envolventes RMS, normalización y `lagCHOP` hacia `out_audio` con canales `bass`, `mid`, `high`, `rms`, `kick`) y vincula bindings opcionales. |
| `td_setup_scene_switcher` | **Pilar 14**: switcher maestro de escenas con crossfade suave (`switchTOP` `blend=True` + `filterCHOP`) y Smart Cooking automático (`chopexecuteDAT` que apaga `allowCooking` en escenas inactivas fuera de la transición). |
| `td_preset_manager` | **Pilar 15**: gestor e interpolador de presets de estado para cualquier COMP (`capture`, `list`, `apply`, `delete`, `blend` lineal con `alpha = 0.0..1.0` entre dos presets). |
| `td_setup_gpu_instancing` | **Pilar 16**: configura GPU Hardware Instancing en `geometryCOMP` mapeando `P(0..2)`, `Color`, `Scale` y `N(0..2)` desde fuentes POP/CHOP/TOP/SOP con cámara, material y `renderTOP` opcionales. |
| `td_setup_postfx_chain` | **Pilar 17**: rack modular GPU de post-procesamiento y LookDev (`baseCOMP` con Bloom/Glow, Feedback Trail, Color Grading y Custom Parameters expuestos). |
| `td_setup_io_bridge` | **Pilar 18**: hub de I/O para shows en vivo (OSC, MIDI, DMX/Art-Net, UDP) con generadores de señal loopback de prueba para validación inmediata. |
| `td_record_movie` | **Pilar 19**: grabador determinístico de animaciones/loops cocinando paso a paso al FPS objetivo y codificando GIF animado con métricas de archivo y verificación visual. |
| `td_heal_network` | **Pilar 20**: médico y cirujano autónomo de redes: repara trampas de `torus1`, flags `display`/`render` apagados, `outputresolution='custom'` sin dimensiones, cámaras desconectadas y NaNs en simulación, con soporte `dry_run` y verificación post-cura. |

## Watchdog

`healthcheck.py` verifica KB + tools + MCP oficial. **No imprime nada si todo está bien**
(patrón watchdog para crons `no_agent`); si algo falla, una línea con el problema.

## Construir o empaquetar los assets (`kb/`)

`kb/` no está versionado en git (es data derivada + documentación de terceros), pero `build_assets.py` funciona de forma **autónoma** aunque el repositorio viejo ya no exista en disco:

```bash
# 1. Reindexar en modo standalone (si kb/ ya existe en disco y el repo viejo fue borrado)
python knowledge/build_assets.py

# 2. Exportar un archivo ZIP portable de respaldo antes de borrar el repo viejo
python knowledge/build_assets.py --export-archive C:/ruta/backup/td-knowledge-kb.zip

# 3. Restaurar kb/ en cualquier máquina nueva desde el archivo ZIP (sin necesitar el repo viejo)
python knowledge/build_assets.py --import-archive C:/ruta/backup/td-knowledge-kb.zip
```

## Correr y verificar

```bash
python knowledge/server.py                 # servidor stdio (habla MCP por stdin/stdout)
python knowledge/server.py --selftest      # corre las 22 tools offline con args de prueba
python knowledge/test_protocol.py          # handshake + tools/list (57 tools) + llamadas por protocolo
python knowledge/test_live.py              # prueba end-to-end en vivo contra TouchDesigner (:13316, 37 stages)
```

Verificado en Windows 11 · Python 3.10 / 3.13 · TouchDesigner 2025.32460 · TDMCP 1.1.55.

> **Nota de layout (2026-09-28).** La instalación `AI_Code\TDMCP\TDMCP-1.1.55` se retiró:
> ahora TODO vive en este repo — `knowledge/` (código + KB), `component/` (el `.tox` oficial),
> `skills-hermes/`, `tools/` y `docs/`. Las rutas viejas que aparezcan abajo son históricas.

# TDMCP oficial (Derivative) vs. TDMCP propio — informe de testeo en vivo

**Fecha:** 2026-09-28 · **TD abierto:** 2025.32460, `.toe` = `TDMCP.1.toe` (demo oficial) · **Puerto oficial:** 13316
**Evidencia cruda:** `docs/tdmcp-oficial-evidence/` (tools/list de ambos, respuestas de las 5 baterías, PNGs)
**Scripts de testeo:** `tmp/mcp_probe_official.py`, `tmp/tdmcp_client.py`, `tmp/official_battery2/3/4.py`, `tmp/official_caps*.py`, `tmp/official_grid.py`

---

## 1. Resumen ejecutivo

El oficial **no es "el tuyo pero de Derivative"**: son dos cosas de naturaleza distinta.

* **El oficial es un transporte/runtime.** Un `.tox` que corre el MCP *dentro* de TouchDesigner (Python bundled, streamable-HTTP en `127.0.0.1:13316`), sin proceso externo, sin Node, sin bridge. 26 tools, todas de lectura/escritura del proyecto vivo.
* **El tuyo es una plataforma de conocimiento.** 107 tools (102 `td_*` + 4 `wt_*` + `tool_batch`) sobre Node/TS vía **bridge HTTP separado** (webserver DAT en TD, puerto 44444), y lo valioso no es el transporte: es la **capa de conocimiento** (matriz POP, reglas GLSL POP/TOP, templates, recetas, tutoriales, TDN, patch engine, validadores).

**Conclusión:** conviene **usar el oficial como base (transporte + runtime) y montar tu capa de conocimiento encima**. No al revés. Detalles en §7.

---

## 2. Método

| Batería | Qué probó | Resultado |
|---|---|---|
| `mcp_probe_official.py` | handshake MCP + `tools/list` de ambos servidores | 26 tools oficiales (v1.1.55) vs 107 propios (v3.0.0) |
| `official_battery2/3.py` | CRUD real, wiring, params, errors, DAT, perf, docs, help | 40+ llamadas, todas con resultado estructurado |
| `official_battery4.py` | modo `search` de params, undo, base64 inline | **falso positivo** (ver §12) + undo verificado |
| `official_config.py` | páginas MCP/Tune/Docs del componente | config real leída |
| curl | guards de seguridad (Origin, LAN) | 403/200 verificados |
| `official_caps2/grid.py` | grid temporal de frames, record CHOP, file-sync de DAT | los 3 funcionan, PNGs adjuntos |

Latencia medida: **3–95 ms** por llamada (p50 ≈ 20 ms). Al ser in-process, no hay hop de red al bridge.

---

## 3. Arquitectura

| | **Oficial (Derivative)** | **Propio** |
|---|---|---|
| Dónde corre el server | **dentro de TD**, Python bundled | proceso **Node/TS externo** (stdio) |
| Cómo llega a TD | **ninguno** (mismo proceso) | bridge HTTP propio: webserver DAT + `POST /exec`, `/parameters/set`… en `:44444` |
| Instalación por proyecto | arrastrar 1 `.tox` + `Active` | bridge `.tox` en TD **+** Node **+** registrar el server en cada cliente |
| Dependencias | ninguna extra | Node 18+, `@modelcontextprotocol/sdk`, `better-sqlite3`, zod, `td-api` |
| Transporte MCP | streamable-HTTP | stdio |
| Tools | 26 | 107 |
| Versión / cadencia | 1.1.51 → **1.1.55 en 7 días** | 3.0.0 |
| Actualización | botón **Update** en el componente (verifica contra el manifest del release) | manual (git + build) |
| Autor | Derivative Inc. (con alpha testers de los MCPs comunitarios) | propio |

Fricción operativa: el tuyo necesita que **cada** proyecto tenga el bridge + un Node corriendo; el oficial solo el `.tox`. En la sesión actual de TD **el bridge propio no estaba levantado** (`netstat`: solo `13316`) — o sea, hoy usás el oficial y tu plataforma está apagada.

---

## 4. Qué tiene el oficial que el tuyo no (verificado en vivo)

| Capacidad | Evidencia |
|---|---|
| **`get_help` lee del build vivo**: nombres de par, tipo, label, `menuNames`, summary, y un resumen del operador | `noiseTOP` → 4 pars con menús; `lfoCHOP` → `wavetype` con 6 valores |
| **Catálogo completo por familia** | `get_help {family:"POP"}` → los 98 POPs del build |
| **`get_docs` con docs offline de la versión instalada** + fallback web + drill por sección | `source:"local"`, páginas `Matrix Class` (Members/Methods), `Noise TOP` (Parameters - Noise Page) |
| **Errores estructurados que se auto-corrigen** | `invalid_menu_value` + `valid_values:[12 opciones]`; `wrong_operator_type` + `expected/actual`; `operator_not_found` + path; `capture_busy` + `retry_after` |
| **Undo real por tool call** | `ui.undo.undoStack` = `['MCP execute_code', 'MCP set_parameters /hermes_hp3/lvl', 'MCP create_operator /hermes_hp3', …]` — **una entrada por llamada**, Ctrl+Z la revierte |
| **Feedback visual**: panea el network editor al operador tocado y lo hace parpadear (ámbar=edición, azul=inspección, violeta=vista) | parámetros `Followactive/Followtime` activos |
| **`view_operator` con grid temporal** (hasta 9 frames, `step`, `delay_frames`, `pre_pulses` en el mismo tick) | job async → PNG de 960×180 con **3 frames de distinto brillo** (`docs/tdmcp-oficial-evidence/grid_temporal.png`) |
| **`inspect_values` con `sample_grid` NxN + stats por canal** | grid 8×8 RGBA de un TOP |
| **`inspect_values` con `record_seconds`** (trailCHOP async) para ver *si un CHOP realmente tickea* | 33 muestras de `lfoCHOP` = senoide completa |
| **File-sync de DAT a disco** (el workflow "código en disco + verificación en vivo") | escribió `code/glsl/shader.glsl`, dejó `file`+`syncfile=1`+`language=glsl` |
| **`execute_code` devuelve `output` *y* `variables`** (introspección del scope) + traceback formateado | `{"variables":{"result":4.0}}` |
| **Annotations** (network boxes) con color/tamaño | `annotation` creado en el sandbox |
| **Rate limiting** (threshold 5 s / cooldown 1 s), **request log**, **inline images**, **node following** | página Tune del componente |
| **Seguridad** (ver §6) | 403 a Origin hostil y a la IP de LAN |
| **Skills oficiales** (19, prefijo `td-`) + instalador por host | `TDMCPSkills` clonado: `td-general`, `td-pop-family`, `td-glsl-shaders`, … |

Y algo que vale más que cualquier tool: la respuesta del server **se autodenuncia cuando está desactualizado** — `menuDataVersion: "TouchDesigner 2025.33070"` + `menuDataStale: "…pero TD corre 2025.32460"`. Ese nivel de rigor es la respuesta a "por qué es oficial".

---

## 5. Qué tiene el tuyo que el oficial no

**El oficial no tiene nada de esto** (es su límite declarado: "building networks from scratch has not been our focus", y los skills "go lighter on autonomous network building"):

* **Conocimiento POP**: `td_pops_query`, `td_pop_validate`, `td_knowledge_query`, `td_get_family_hints`, `td_catalog`, `td_ops_query`.
* **GLSL POP/TOP de verdad**: `td_glsl_analyze`, `td_glsl_apply` (pre-valida y compila), `td_glsl_top_analyze`, `td_glsl_top_recipe`, `td_glsl_curriculum` + `docs/GLSL_POP_RULES.md`, `glsl_pops_reference.json`, `pop_matrix.json`.
* **Validación y verificación propias**: `td_validate`, `td_verify_wiring`, `td_syntactic_check`, `td_smoke_test`, `td_perf_budget`, `td_measure`, `td_healthchain`, `td_complexity_check`.
* **TDN** (red como JSON versionable): `td_tdn_export/import/diff/git_setup` — versionar redes con git es algo que el oficial no ofrece.
* **Patch engine con rollback**: `td_patch_plan/preview/apply/variations`.
* **Historial/undo del bridge**: `td_history*`, `td_undo/redo` (el oficial resuelve esto mejor: undo nativo de TD).
* **Contexto y navegación**: `td_spatial_context`, `td_get_focus`, `td_selection`, `td_navigate_to`, `td_pane`, `td_read_textport`, `td_clear_textport`.
* **Ciclo de proyecto**: `td_project_lifecycle` (save/load/undo/redo/undo-block), `td_snapshot_scene`, `td_compare_networks`, `td_explore_project`.
* **Plantillas/recetas/tutoriales/workflows** y `td_import_toe_dir` (rebuild desde `.toe.dir`).
* **Memoria e integración**: `td_memory_save/recall`, `td_run_prompt`, `tool_batch`, y los 4 `wt_*` de WebToe.
* `td_compare_mcps` — **desactualizado**: compara contra TWOZERO y no menciona al oficial.

Traducción: el oficial cubre bien el **"tocar el proyecto vivo"**; tu plataforma cubre el **"saber cómo se hace bien"**. Son complementarios.

---

## 6. Seguridad del oficial (verificado, no leído)

| Prueba | Resultado |
|---|---|
| `POST` con `Origin: http://evil.example.com` | **403** ✅ |
| `POST` con `Origin: http://127.0.0.1:13316` | 200 ✅ |
| `POST` sin `Origin` | 200 ✅ |
| `POST` a la IP de LAN (`192.168.0.101:13316`) | **403** ✅ |
| `netstat` | `0.0.0.0:13316 LISTENING` ⚠️ |

⚠️ **Matiz real:** el README promete "socket bound to 127.0.0.1 en TD 2025.33060+". Con **2025.32460** el socket **sí escucha en todas las interfaces** (un port scan de la LAN lo ve) y la protección es el guard de aplicación (403). Impacto práctico: bajo, pero **conveniente bloquear el puerto en el firewall de Windows** o subir de build.

Config actual del componente: `Port=13316`, `Addressscope=localhost`, `Usehttps=0`, `Auth=0` (correcto para localhost-only: no hace falta auth), `Auto-accept deletion=ON`, `Inline Images=OFF`, `Image cache=.claude/cache`, `Rate limiting=ON`, `Follow Active=ON`, `Docs Source=Auto`, `Install For=agy`, `Install Scope=project`.

---

## 7. Bugs y observaciones del beta (candidatos a Issues/Discussions de Derivative)

> ⚠️ **Corregido el 2026-09-28 (ver §12).** Un primer pase reportó un bug en el modo `search`
> de `get_parameters`: fue **un falso positivo propio** (el sandbox tenía todos los parámetros en
> default y `search.include_defaults` es `false`). El modo `search` **funciona**. Lista final:

1. **BUG menor — args mal tipados devuelven `internal_error` sin estructura.** `get_parameters {search: "yolo"}` → `'str' object has no attribute 'get'`; `reposition_operators {positions: [...]}` → `'list' object has no attribute 'keys'`. Contradice la promesa de errores estructurados; debería ser `invalid_argument` (con la forma esperada, como hace `set_parameters`). Ambos verdes en RIG B de `verify_issues.py`, con sus controles en la forma correcta.
2. **Doc vs. comportamiento — `view_operator`.** La descripción dice "returned inline as base64", pero con **Inline Images OFF (default)** el bloque `image` **no viene**: solo la ruta del PNG en `.claude/cache/`. Con ON llega el PNG inline (verificado: 14 KB). La descripción no menciona la dependencia de la página Tune.
3. **`edit_operator` rename duplicado** → `code: "internal_error"` con mensaje "Invalid or duplicate operator name." (debería ser un código propio tipo `name_conflict` + el nombre en conflicto).
4. **Observación** — `build_network` crea **todo** bajo `parent_path`: no se puede crear un COMP y sus hijos en la misma llamada (los hijos salen al padre). Fácil de pisar.
5. **Observación** — `menuDataStale`: el catálogo de menús viene del release 2025.33070; en un build menor puede haber valores distintos.
6. **Observación menor** — `get_parameters` con `search: {}` (vacío) no entra en modo search: cae al modo normal y devuelve `parameters: {}`. Coherente, pero no documentado.

---

## 8. Licencia — qué te habilita

`LICENSE.md` = **Shared Use License** + **TDMCP Tool Terms of Use**:

* Uso y modificación **solo junto a TouchDesigner**, y solo siendo licenciatario de TD.
* **Se puede compartir/redistribuir una versión modificada** si se conservan el aviso y las condiciones.
* **No** se puede usar el nombre/marcas de Derivative Inc. para avalar productos derivados.
* Prohibido redistribuir TDMCP *como producto*.

→ **Podés reusar partes y conceptos del oficial dentro de tu propio server** (con el aviso) y adaptar tus cosas encima. No podés presentar el resultado como avalado por Derivative. El post lo dice explícito: *"meant as a reference implementation… The license allows you to use its parts and concepts in your own TouchDesigner MCP server"*.

---

## 9. Recomendación

**Base = oficial. Tus cosas = capa encima. No al revés.**

Por qué:

1. **Tu bridge es la parte que el oficial hace mejor y la que más te cuesta.** El webserver DAT + `:44444` + Node es donde vivieron los bugs de contrato (el `/parameters/set` que fallaba en silencio), el harness, el cron watchdog y los 37 ítems de backlog. El oficial lo elimina por construcción: mismo proceso, sin transporte que mantener.
2. **Tu valor no es el transporte, es el know-how.** KB POP/GLSL, validadores, TDN, patch engine, recetas: son **datos + lógica pura**, portables a cualquier transporte. Nada de eso se pierde si cambia el runtime.
3. **El oficial gana en lo que es commodity y en lo que exige estar dentro de TD**: undo nativo, feedback visual, docs de *tu* versión, `get_help` del build vivo, seguridad evaluada, auto-update, soporte oficial.
4. **El inverso es inviable**: no vas a reimplementar in-process el undo, el scope de seguridad y el catálogo de menús por build; y Derivative no va a absorber 107 tools.
5. **El riesgo de depender del oficial es manejable**: la licencia permite reusar sus partes, y su interfaz puede cambiar en beta (5 releases en 7 días) — por eso conviene **envolver** sus 26 tools en lugar de copiar su código.

**Plan por fases**

* **Fase 0 (hoy, 10 min):** registrar el oficial en Hermes (`mcp_servers.tdmcp.url = http://127.0.0.1:13316/mcp`) e instalar las 19 skills `td-*` en `~/AppData/Local/hermes/skills/`. Quedás operativo con el oficial desde Hermes, sin Node.
* **Fase 1:** reportar los bugs de §7 en `TouchDesigner/TDMCP/issues` (piden feedback y citan version + save build).
* **Fase 2 (el port real):** convertir tus 107 tools en **dos capas**:
  * *Offline* (sin TD): KB, validadores GLSL POP/TOP, TDN, templates/recetas, análisis estático, `import_toe_dir` → siguen siendo tuyos, sin depender de ningún bridge.
  * *Live* (envuelven al oficial): crud/params/errors/screenshot/perf/dat/chop pasan a llamar las 26 tools del oficial en vez de tu bridge. Desaparece `w2t_server.py`, el bridge DAT, el puerto 44444 y el Node como dependencia de transporte.
* **Fase 3:** retirar el bridge propio y actualizar `td_compare_mcps` (que hoy ignora al oficial) o borrarlo.

**Lo que NO conviene hacer:** mantener dos transports corriendo en el mismo proyecto (dos `.tox`, dos puertos, dos fuentes de verdad del undo). Si querés comparar en vivo, usá dos TD separados con `Server Name` distinto (dos servidores con el mismo nombre se tapan entre sí — pitfall documentado por Derivative).

---

## 10. Anexo — Cómo reconectar la evidencia

> Copias canónicas de estos scripts: `tools/` (en este repo).
> (ahí también está `adapt_td_skills.py`, que re-adapta las skills oficiales a Hermes, y
> `restore_config_comments.py`, que restaura los comentarios del `config.yaml`).
> Estado de la migración y pitfalls: `extras\README.md`.

```bash
# handshake + tools/list del oficial (26) y del propio (107)
python tmp/mcp_probe_official.py          # oficial
python tmp/probe_mine.py                  # propio (node mcp/dist/index.js)

# baterías (necesitan TD abierto con el .tox activo en 13316)
python tmp/official_battery3.py           # CRUD/wiring/params/errors/DAT/perf
python tmp/official_battery4.py           # search (bug), undo, inline PNG
python tmp/official_grid.py               # grid temporal + record CHOP
python tmp/official_config.py             # config de las páginas MCP/Tune
```

## 11. Fase 0 ejecutada (2026-09-28)

* **Hermes**: `mcp_servers.tdmcp` → `http://127.0.0.1:13316/mcp` (`timeout: 300`).
  Verificado con `hermes mcp test tdmcp`: **26 tools, 969 ms**. Las tools aparecen como
  **`mcp_tdmcp_<tool>`** en **sesiones nuevas** (no hay hot-reload).
* **19 skills `td-*`** adaptadas a Hermes (description `Use when …` + banner con el prefijo
  `mcp_tdmcp_`) → `~/AppData/Local/hermes/skills/touchdesigner/td-*`.
* **Todo consolidado en** este repo: `knowledge/`, `component/`, `skills-hermes/`, `tools/`, `docs/` (README, skills, clone con
  `.git` de TDMCPSkills, reportes + evidencia, scripts de testeo).
* **Pitfall de Hermes detectado**: `hermes config set` borra **todos** los comentarios del
  `config.yaml` (4896 → 2978 bytes) — restaurar desde el backup con inserción de texto, y
  ojo con `hermes mcp add`, que es interactivo y cuelga un tool call no-TTY.
* **TD quedó limpio**: `/` = `TDMCP / local / perform`, 0 errores, `Inlineimages` restaurado a OFF.


---

## 12. Enmienda — un falso positivo mío, y la lista final de bugs

**Qué pasó.** El primer pase declaró "`get_parameters` en modo `search` siempre devuelve 0" tras 6
variantes con `results: []`. Antes de publicarlo revisé el `inputSchema` y encontré la causa: en
`search`, **`include_defaults` es `false` por defecto**, y el sandbox usado en ese test
(`/hermes_hp2`, creado y buscado en la misma corrida) tenía **todos** los parámetros en default.
`scanned_ops > 0` con `results: []` era, entonces, el comportamiento correcto.

**Re-verificación** (`tmp/verify_issues.py`, evidencia `tmp/issues_evidence.json`, sandbox `/hermes_i`
con `src.resolutionw=512` —default 256— y `lvl.brightness1` con `expr = absTime.seconds % 2`):

| llamada `search` | resultado |
|---|---|
| `{"name": "res*"}` | ✅ `/hermes_i/src.resolutionw = 512` |
| `{"name": "res*", "include_defaults": true}` | ✅ todos los `resolution*` de los 4 ops |
| `{"value": "512"}` | ✅ `src.resolutionw` |
| `{"expr": "*absTime*"}` | ✅ `lvl.brightness1` con su expresión |
| `{"op_type": "noiseTOP"}` | ✅ `src.resolutionw` (`scanned_ops: 1`) |
| `{"name": "*", "include_defaults": true, "limit": 5}` | ✅ listado amplio |
| `{"op_type": "noiseTOP", "name": "res*"}` | ✅ `src.resolutionw` |

**Conclusión: el modo `search` funciona y está bien diseñado.** El control sin `search` mostraba
`resolutionw {value: 512, default: 256}` y `brightness1 {expr: …}`, así que el estado era el esperado.

**Lección registrada**: antes de declarar "bug" en un MCP, leer el `inputSchema` del tool —
los defaults de los filtros son parte del contrato. Un `scanned_ops > 0` con 0 resultados
también es la firma de un filtro que (correctamente) sólo mira no-defaults.

### Lista final de bugs a reportar (3, todos verificados con repro mínimo)

1. **Args mal tipados** → `internal_error` con `AttributeError` crudo (`get_parameters.search` como
   string; `reposition_operators.positions` como lista). Controles en la forma correcta: verdes.
2. **`view_operator`** → sin bloque `image` con `Inline Images=OFF` (el default), aunque la
   descripción promete "returned inline as base64".
3. **`edit_operator` rename duplicado** → `internal_error` en vez de un código de conflicto.

Draft listo para publicar en `extras/reportes/2026-09-28-tdmcp-oficial-vs-propio/issues/`.

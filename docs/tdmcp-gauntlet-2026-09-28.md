# Gauntlet TDMCP oficial — veredicto de la migración (2026-09-28)

**Pregunta:** ¿el stack nuevo (núcleo oficial `TDMCP.tox` 1.1.55 + skills oficiales `td-*`)
construye bien sistemas de nodos dentro de componentes, o el valor seguía estando en el MCP viejo?

**Respuesta corta: sí, construye mejor — pero el salto lo dan las skills, no las tools. El núcleo
oficial ejecuta, corrige y se auto-verifica; la capa de conocimiento propia sigue siendo la que
aporta el "saber cómo". La migración queda confirmada con las dos capas operando.**

Ejecutado por Codebuff vía MCP HTTP (`127.0.0.1:13316/mcp`) sobre TD **2025.32460** con el
`.tox` oficial 1.1.55. Toda la evidencia cruda: `tools/gauntlet/results/<run>/` (un `.jsonl` por
fase con args/latencia/respuesta de cada llamada + `*-summary.json`).

---

## 1. Resultados por fase

| Fase | Qué probó | Resultado | p50 / p95 |
|---|---|---|---|
| F1 Smoke | handshake, `tools/list`, `project_info`, sanity noise→blur→null, captura | **PASS** — 26 tools, server 1.1.55, errores estructurados (`operator_not_found`) | 22 / 34 ms |
| F2 API core | `build_network` multi-hop, errores estructurados, undo, file-sync GLSL, `sample_grid`, `record_seconds`, grid temporal, `get_help`/`get_docs` + **los 6 wrappers live de `knowledge/live.py`** | **PASS** — 26 asserts, incl. `tdn_diff` detectando el op agregado | 26 / 39 ms |
| F3 N1 — cadena TOP | `noise→feedback→blur→null` con loop canónico `out1→trail` dentro de baseCOMP | **PASS** — 15 calls, grid temporal del trail capturado | 22 / 38 ms |
| F3 N2 — reloj audio | containerCOMP: `audiodevicein→spectrum→analyze` + texto reloj (expr) + cross-family CHOP→par TOP por expresión + anotación | **PASS** — 8 ops, par animado verificado entre lecturas, 0 errores | 33 / 57 ms |
| F3 N3 — módulo + clon | baseCOMP con `inTOP`, custom pars, `parentshortcut`, referencia `parent().par.Blur`; clon `copy_to` + par `clone` + override 0.6 con master en 0.05 | **PASS** — herencia y override verificados | 24 / 33 ms |
| F3 N4 — extensión Python | `PWM_LFO` (clase en textDAT) + binding + promote + reinit + state-output readonly | **PASS** — `ext.PWM_LFO` viva, `Update()/Init()` verificados | 26 / 37 ms |
| F3 N5 — mini-render | renderTOP + cam/light/geometry + pbrMAT + environmentlight + env map | **PASS** — bindings verificados, 0 errores, PNG + grid | 41 / 143 ms |
| F3 N6 — GLSL POP | `glsl_analyze` (offline) dicta los params → build en vivo → verificación GPU→CPU (`poptoCHOP`: P escalada por uScale, Cd=(1,.5,.25,1)) | **PASS** — el shader compiló a la primera con los params del analyzer | 22 / 45 ms |
| F4 A/B | mismos niveles sin skills (solo schema) | **naive FALLA** (ver §3) | 25–29 ms |
| F5 Hermes | registro `tdmcp` + `td-knowledge`, 19 skills, healthcheck, protocolo | **PASS** (fix de encoding en `test_protocol.py`) | — |

Firma útil encontrada: un PNG de render vacío/negro pesa **~215 bytes**; con contenido real
≥1.6 KB. Sirve como grader barato de "¿renderizó algo?".

## 2. Los errores estructurados guiaron cada corrección (lo que el viejo no hacía)

Cada fallo de la Fase 3 vino con el dato para arreglarlo en una llamada:

- `trail has 1 input(s), to_index=1 out of range` + `index_out_of_range` → topología correcta del loop de feedback.
- `unknown operator type: audioDeviceInCHOP` → el catálogo es lowercase (`audiodeviceinCHOP`); `get_help` lo confirmó.
- `Parameter not found: fontsize` → `get_help` dio los pars reales (el par de fuente es un menú `font`/`fontautosize`).
- `Cannot cast value to a numeric object. Set .expr member instead.` → contrato claro: **`set_parameters` solo constantes; expresiones por `execute_code` (`p.expr`)**.

## 3. A/B — con skills vs sin skills (la respuesta a tu pregunta original)

| Métrica | N2 guiado | N2 naive | N3 guiado | N3 naive |
|---|---|---|---|---|
| Llamadas MCP | 17 | 20 | 26 | 13 |
| Errores de tool | 2* | 5+ | 4* | 3+ |
| Graders esenciales | **0 fallos** | compuesto sin fondo (sin `to_index`), reloj en CONSTANT | **0 fallos** | custom pars no-op, referencia rota |

\* los del guiado son errores esperados del test de errores estructurados (F2/N1) o del propio sondeo; los de naive son fallos reales de construcción.

Lo que el modo naive **no logró**: tipos audio correctos, wiring del composite al input correcto,
expresión cross-family (no sabe que `set_parameters` no acepta strings-expr), texto en modo
EXPRESSION, custom pars (schema no obvio = no-op silencioso), clonado (no existe `duplicate_to`).
Lo que sí logró: CRUD básico y wiring familia-a-familia — igual que tu MCP viejo sin su KB.

**Conclusión:** el núcleo oficial es mejor *runtime* de construcción que el bridge viejo
(latencia ~25 ms in-process, undo nativo, errores que se autocorrigen), y las skills oficiales son
las que cierran la brecha de conocimiento. Sin skills, el oficial solo es comparable al tuyo.

## 4. Hallazgos del núcleo (issues redactados en `docs/issues-filed/`)

Todos los repros re-verificados en vivo sobre sandbox limpio antes de redactar (run `verify-issues`, con control positivo en cada caso):

1. **`edit_custom_parameters` con schema equivocado responde `success: true` con `added: []`** — no-op silencioso. → [issue-04](issues-filed/issue-04-edit-custom-parameters-wrong-schema-silent-success.md)
2. **`annotation` acepta un argumento desconocido (`text` en create)** — crea la caja sin texto y con `success: true`. El schema pide `comment`. → [issue-05](issues-filed/issue-05-annotation-unknown-text-arg-creates-empty-box.md)
3. **Expresiones en `set_parameters` devuelven `internal_error`** con mensaje útil pero sin código estructurado ni nombre del par. → [issue-06](issues-filed/issue-06-set-parameters-expression-string-internal-error.md)
4. **Tipos mal escritos → `unknown_operator_type` sin sugerencia** del tipo canónico más cercano (case-fold o difflib lo arreglaría). → [issue-07](issues-filed/issue-07-unknown-operator-type-no-closest-match.md)
5. **Gap de skill de render:** `environmentlightCOMP` sin inputs (env map por par `envlightmap`), `renderTOP` sin auto-setup, bindings OP solo por `execute_code`. → [skills-proposal](issues-filed/skills-proposal-render-network-recipe.md) (para `TDMCPSkills`, no es bug del server).
6. Nota de API (no bug): en 2025.32460, `ui.undo` es objeto (`ui.undo.undo()`), `numchans` no existe (usar `len(chans())`), `absTime.datetime` no existe.
7. `menuDataStale` operativo en cada `get_help` (catálogo 2025.33070 vs TD 32460) — comportamiento por diseño, visible y honesto.

## 5. Qué queda de tu investigación (estado final de la migración)

| Capa | Estado |
|---|---|
| Núcleo oficial `.tox` 1.1.55 | **Validado** en 5 niveles + API core. Es la base. |
| 19 skills `td-*` (Hermes) | Instaladas y cargadas; fueron decisivas en N4 (coreografía exacta de extensiones). |
| `td-knowledge` (20 tools: 14 offline + 6 live) | **Verificado en producción** en F2 (`find_in_ops`, `auto_layout`, `smart_connect`, `tdn_export/diff`, `td_status`). La KB (29 MB) y el server funcionan; el registro Hermes ya apunta a este repo. |
| Scripts del gauntlet | `tools/gauntlet/` re-ejecutables (`f1…f4`, `gauntlet_client.py`), logs por run. **Hoy es además el test de regresión del `.tox`**: `python tools/gauntlet/run_regression.py` (ver `tools/gauntlet/README.md`), con baseline y diff de entorno/veredictos para corridas antes/después de actualizar. |

**Pendientes recomendados:** (a) publicar los drafts §4 en `TouchDesigner/TDMCP/issues` (los 4 issues + la propuesta de skill ya están redactados en `docs/issues-filed/`); (a2) actualizar `glsl_analyze`/KB con los hallazgos del N6: el menú real de `attr0name` espera `custom` lowercase, `outputattrs` debe listar los atributos que existen en la entrada (P) para que el preamble los declare, y `poptoCHOP`/`glslPOP` de 2025.32460 se referencian por par (sin inputs / sin auto-dock);
(b) portar los pitfalls de §2 a `skills-hermes/` (o PR a TDMCPSkills): lowercase de tipos audio,
`.expr` por `execute_code`, `comment` en annotation, schema de `edit_custom_parameters`,
`copy_to` para clonar, coreografía de render; (c) considerar el A/B de `f4_ab.py` como test de
regresión al actualizar el `.tox`.

## 6. Evidencia

- Logs: `tools/gauntlet/results/20260928-*/<fase>.jsonl` (una línea por llamada con args, ms y respuesta).
- Resúmenes: `.../<fase>-summary.json`; comparación A/B: `tools/gauntlet/results/f4-ab-comparison.json`.
- PNGs: `n1_trail_grid.png`, `n2_clock.png`, `n3_module.png`, `n5_render.png`, `n5_render_grid.png`, `grid_temporal.png` (runs finales de cada fase).
- Notas previas de testeo del oficial: `docs/community-test-notes-2026-09-28.md` (baseline del que parte este gauntlet).

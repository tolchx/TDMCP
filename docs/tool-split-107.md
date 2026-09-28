# port/ — la capa de conocimiento propia, montada sobre el MCP oficial

> **⚠️ FUENTE ÚNICA DE VERDAD (2026-09-28).** El **código** de `td-knowledge` vive en
> **`<repo>\knowledge\`** (el clon del fork, con git)
> y **desde ahí corre todo**: Hermes (`mcp_servers.td-knowledge`), el watchdog (`td_mcp_verify.py`)
> y los tests. La **KB** (30 MB de datos) vive al lado: `tolchx-TDMCP\knowledge\kb\` (ignorada por git).
> En esta carpeta ya **no hay copia del código ni de la KB**: quedaba una duplicada y se borró para
> que no puedas editar la copia equivocada. Acá viven la doc del port, las skills, la evidencia y
> los scripts de testeo. *(Las carpetas vacías `kb/` y `td-knowledge/` son restos que Windows no
> deja borrar por un handle; se van solas al reiniciar.)*

Esta carpeta es el resultado del **port** (Fase 2): de las **107 tools** del MCP propio
(`AI_Code/Touchdesigner_MCP/Main`) se preserva lo que el oficial **no tiene**, y todo lo que
el oficial hace mejor se delega en él.

## Por qué así

| Capa | Quién la sirve | Por qué |
|---|---|---|
| **Live** (crear/editar/leer TD) | **MCP oficial** `tdmcp` (26 tools, dentro de TouchDesigner) | mismo proceso que TD: undo nativo, errores estructurados, docs del build vivo. Cero bridge, cero Node |
| **Conocimiento** (KB, reglas, validadores, planificación) | **este port** `td-knowledge` (14 tools, Python puro) | funciona **con TouchDesigner cerrado**; es el know-how acumulado, no el transporte |

```
extras/port/
├── build_assets.py          # extrae los assets del repo original (idempotente)
├── kb/                      # datos (NO va a git: ver .gitignore)
│   ├── knowledge_brain.db   #   1048 docs curados (FTS5/BM25 + trustTier)
│   ├── pop_matrix.json      #   97 tipos POP medidos en vivo (2987 params)
│   ├── ops/operators/       #   doc por operador (507 archivos, 7 familias)
│   ├── pops/                #   patterns, wiki_params, inventory, validation, glsl_library
│   ├── rules/*.md           #   reglas GLSL POP/TOP verificadas en vivo + cheatsheets
│   └── ts-extract/ts-data.json  # 99 sinónimos, family hints, 14 templates, 5 recetas
└── td-knowledge/
    ├── server.py            # MCP por stdio, Python 3 stdlib (sin deps, sin Node, sin TD)
    ├── test_protocol.py     # test real por protocolo MCP (handshake + tools/list + calls)
    └── selftest_protocol.json
```

## Uso

```bash
# 1. (re)construir la KB desde el repo original — solo si el repo cambió
python build_assets.py --repo "<user-home>/Documents/AI_Code/Touchdesigner_MCP/Main"

# 2. correr el server a mano (stdio MCP)
python td-knowledge/server.py            # kb/ se autodetecta un nivel arriba
python td-knowledge/server.py --selftest # corre las 14 tools con args de prueba

# 3. test por protocolo (handshake + tools/list + 8 llamadas reales)
python td-knowledge/test_protocol.py
```

## Las 14 tools offline

`kb_info` (provenance) · `kb_taxonomy` · `kb_search` (BM25 sobre 1048 docs, filtrable por
familia y trustTier) · `kb_get` · `pop_matrix` (97 tipos POP medidos) · `ops_doc` ·
`ops_params` · `pop_knowledge` (patterns/wiki_params/inventory/validation/glsl_library) ·
`resolve_operator` (99 tipos con sinónimos ES/EN) · `templates` (14) · `recipes` (5) ·
`glsl_rules` (6 POP + 12 TOP) · `glsl_analyze` (análisis estático) · `glsl_curriculum`.

`glsl_analyze` es un puerto fiel de las reglas verificadas: POP **R1** (la salida no se lee),
**R2** (`TDIndex()` + guarda), **R3** (atributos nuevos → `attr0name='Custom'` + `attr0customname` +
`attr0numcomps`, con la tabla de componentes) y **R4** (`outputaccess='readwrite'`); TOP **R1**
(declaración de salida explícita) y **R2** (`.st/.xy`, nunca `.uv`); Python **R6**
(`numPoints()`/`numPrims()`/`bounds()`/`points()` son métodos).

## Los 107 tools: a dónde fue cada uno

- **43 → offline** (este port): toda la KB, validadores estáticos, planificación, TDN,
  `.toe.dir`, WebToe.
- **30 → oficial**: reemplazo 1:1 (`create_operator`, `set_parameters`, `execute_code`,
  `view_operator`, `get_help`, `get_docs`, `inspect_values`, …).
- **20 → envolver el oficial**: huecos reales que el oficial no cubre y valen un wrapper
  (`td_search` dentro de DATs/expresiones, `td_auto_layout`, `td_smart_connect`, TDN
  export/import/diff, `td_glsl_apply` = analizar offline + `set_dat_content(file_content)`).
- **14 → descartar**: piezas del bridge (history/undo propios, healthchain, watch), memoria
  (vive en Hermes/Mnemosyne), `tool_batch`, `td_report_bug`.

Detalle completo por tool: `../reportes/2026-09-28-tdmcp-oficial-vs-propio/informe de testeo.md`
(§7 y §12) y `tools_mapping.json` en el repo original (`tmp/`).

## Nota de licencia

La KB mezcla contenido de `docs.derivative.ca` (tier `official`) con material propio medido en
vivo (`live-verified`/`empirical`) y de terceros (`community`). Por eso **`kb/` no se publica**:
se reconstruye localmente con `build_assets.py`, que copia desde el repo privado. El código del
port sí se publica (es nuestro). Si el fork se distribuye, conservar `LICENSE.md` del oficial —
la *Shared Use License* prohíbe usar el nombre de Derivative como aval y exige mantener el aviso.

## Publicado en el fork

`github.com/tolchx/TDMCP`: `knowledge/` (este server, sin `kb/`), `skills-hermes/`,
`component/` (el `.tox` oficial 1.1.55 + `TDMCP.json`, SHA-256 verificados contra los assets
del release) y `docs/` con las notas de testeo y los 3 issues presentados.

Los nombres de las tools van **sin** el prefijo `td_`: el server ya se llama `td-knowledge`, así
que en Hermes quedan `mcp_td_knowledge_kb_search`, `mcp_td_knowledge_pop_matrix`, etc.

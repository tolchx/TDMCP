# td-knowledge — capa de conocimiento para TouchDesigner (offline + live)

MCP server por **stdio en Python puro (stdlib, sin dependencias)**. Trabaja en dos modos, en el
mismo proceso y sin bridge:

* **14 tools offline** — responden con la KB curada **sin** TouchDesigner abierto.
* **6 tools live** — hablan MCP contra el **server oficial de Derivative** (`127.0.0.1:13316/mcp`)
  para lo que necesita el proyecto vivo; si TD está cerrado devuelven un error claro.

## Tools offline (14)

| Tool | Qué responde |
|---|---|
| `kb_info` | Provenance del KB: qué assets, cuándo, cuántos docs, tier de confianza. |
| `kb_taxonomy` | Qué hay en la base (conteos por familia / trust tier / source type) + índice de docs. |
| `kb_search` | Búsqueda FTS5 (BM25 + snippet) con filtros por familia y **trust tier**: `official`, `empirical`, `community`, `live-verified`. |
| `kb_get` | Documento completo por nombre/slug, con paginado. |
| `pop_matrix` | Matriz POP **medida en vivo** (97 tipos): qué se crea, qué cocina, inputs requeridos, params medidos, errores. |
| `ops_doc` | Doc curado de un operador (cualquier familia): summary, inputs, parámetros, use cases, troubleshooting. |
| `ops_params` | Lista de parámetros de un tipo (nombre, label, tipo, default, página). |
| `pop_knowledge` | Datos POP no oficiales: `patterns` (mapas de red reales), `wiki_params`, `pop_inventory`, `validation`. |
| `resolve_operator` | Lenguaje natural (ES/EN) → tipo de operador canónico, con score y familia sugerida. |
| `templates` | 14 plantillas de red con wiring, parámetros y builder Python. |
| `recipes` | 5 recetas builder verificadas, con `gotchas`. |
| `glsl_rules` | Reglas GLSL verificadas en vivo (POP y TOP), por id de regla. |
| `glsl_analyze` | Análisis **estático** de un shader o snippet: R1/R2/R3/R4 de POP (lectura de la salida, `TDIndex()`/guarda, atributos a crear con sus params), R1/R2 de TOP, y uso de propiedades vs métodos en Python. |
| `glsl_curriculum` | Ejemplos GLSL POP con fuentes citadas. |

## Tools live (6) — requieren TD con el `.tox` oficial activo

| Tool | Qué hace (y por qué no la tiene el oficial) |
|---|---|
| `td_status` | ¿Está TD vivo? proyecto, build, fps, versión del server oficial. Conviene llamarla primero. |
| `find_in_ops` | Busca un texto en **todo** un subárbol: contenido de DATs, **expresiones** de parámetros, nombres de par, comentarios y nombres de operador. Una sola llamada (corre dentro de TD). El oficial busca operadores por tipo/nombre, no dentro de DATs ni expresiones. |
| `auto_layout` | Ordena los operadores por **capas topológicas** (sin cruces): lee el cableado, calcula las posiciones localmente y las aplica con `reposition_operators`. `dry_run: true` para verlas sin mover nada. |
| `smart_connect` | Conecta dos operadores eligiendo el **índice de input** según la familia que espera el destino (lo lee de la KB y, si no está, de los docs del build). Si las familias no son compatibles avisa antes de intentar. |
| `tdn_export` | Exporta una red a **TDN v1.4** (JSON versionable en git) leyendo el proyecto en vivo. |
| `tdn_diff` | Compara dos `.tdn` **sin TD**: operadores agregados/quitados y cambios de parámetros, tipos, flags y cableado. |

## Watchdog

`healthcheck.py` verifica KB + tools + MCP oficial. **No imprime nada si todo está bien**
(patrón watchdog para crons `no_agent`); si algo falla, una línea con el problema.

## Construir los assets

`kb/` no está versionado (es data derivada + documentación de terceros). Se reconstruye con:

```bash
python build_assets.py --repo /ruta/al/origen
# --dest por defecto: la carpeta de este script
```

Copia los datasets curados, extrae los datos de TypeScript vía `node` (sinónimos, plantillas,
recetas) y escribe `kb/manifest.json`. `TD_KNOWLEDGE_REPO` y `TD_KNOWLEDGE_KB` permiten fijar las
rutas por entorno.

## Correr

```bash
python server.py                 # servidor stdio (habla MCP por stdin/stdout)
python server.py --selftest      # corre las 14 tools con args de prueba
python test_protocol.py          # handshake + tools/list + llamadas reales por protocolo
```

## Registrar (ejemplo: Hermes Agent)

```yaml
mcp_servers:
  td-knowledge:
    command: C:/Users/<user>/AppData/Local/Programs/Python/Python313/python.exe
    args: [C:/ruta/a/knowledge/server.py]
    enabled: true
```

## Cómo se usa junto al oficial

1. **Antes de tocar nada**: `td_kb_search` / `td_ops_doc` / `td_glsl_rules` para leer las reglas;
   `td_pop_matrix` para saber si un POP necesita input.
2. **Al escribir código**: `td_glsl_analyze` (offline) antes de crear/compilar el operador.
3. **En vivo**: las 26 tools de TDMCP para crear, cablear, setear parámetros, ver errores,
   muestrear valores y capturar el visor. Validaciones: `get_help` antes de `set_parameters`.

Verificado en Windows 11 · Python 3.10 / 3.13.

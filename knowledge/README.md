# td-knowledge — capa de conocimiento offline para TouchDesigner

MCP server por **stdio en Python puro (stdlib, sin dependencias)**: no necesita TouchDesigner
abierto, ni un bridge, ni Node. Complementa a **TDMCP** (el MCP oficial, que sí trabaja en vivo
dentro de TouchDesigner): este server responde lo que se puede responder **sin** la aplicación.

## Tools (14)

| Tool | Qué responde |
|---|---|
| `td_kb_info` | Provenance del KB: qué assets, cuándo, cuántos docs, tier de confianza. |
| `td_kb_taxonomy` | Qué hay en la base (conteos por familia / trust tier / source type) + índice de docs. |
| `td_kb_search` | Búsqueda FTS5 (BM25 + snippet) con filtros por familia y **trust tier**: `official`, `empirical`, `community`, `live-verified`. |
| `td_kb_get` | Documento completo por nombre/slug, con paginado. |
| `td_pop_matrix` | Matriz POP **medida en vivo** (97 tipos): qué se crea, qué cocina, inputs requeridos, params medidos, errores. |
| `td_ops_doc` | Doc curado de un operador (cualquier familia): summary, inputs, parámetros, use cases, troubleshooting. |
| `td_ops_params` | Lista de parámetros de un tipo (nombre, label, tipo, default, página). |
| `td_pop_knowledge` | Datos POP no oficiales: `patterns` (mapas de red reales), `wiki_params`, `pop_inventory`, `validation`. |
| `td_resolve_operator` | Lenguaje natural (ES/EN) → tipo de operador canónico, con score y familia sugerida. |
| `td_templates` | 14 plantillas de red con wiring, parámetros y builder Python. |
| `td_recipes` | 5 recetas builder verificadas, con `gotchas`. |
| `td_glsl_rules` | Reglas GLSL verificadas en vivo (POP y TOP), por id de regla. |
| `td_glsl_analyze` | Análisis **estático** de un shader o snippet: R1/R2/R3/R4 de POP (lectura de la salida, `TDIndex()`/guarda, atributos a crear con sus params), R1/R2 de TOP, y uso de propiedades vs métodos en Python. |
| `td_glsl_curriculum` | Ejemplos GLSL POP con fuentes citadas. |

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

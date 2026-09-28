# tools/ — batteries para testear el TDMCP oficial

Scripts re-ejecutables que usé para evaluar **TDMCP 1.1.55** (ver
`docs/community-test-notes-2026-09-28.md`):

| Script | Qué hace |
|---|---|
| `tdmcp_client.py` | Cliente MCP mínimo (HTTP + JSON-RPC) que usan los demás. |
| `official_battery3.py` / `official_battery4.py` | Batería de tools: CRUD, wiring, parámetros, errores estructurados, file-sync de DATs, undo, imagen inline. |
| `official_grid.py` | Captura en grid temporal (`view_operator frames`) + `inspect_values record_seconds`. |
| `official_config.py` | Lee las páginas MCP/Tune/Docs del componente. |
| `official_caps2.py` | `get_help` / `get_docs` / catálogo POP + `build_network`. |
| `mcp_probe_official.py` | `tools/list` de un server corriendo → JSON. |
| `probe_td_api.py` / `probe_td_api2.py` | Verifican la API Python de TD que usa `knowledge/live.py`. |
| `adapt_td_skills.py` | Adapta TDMCPSkills al formato de skills del host (se usó para Hermes). |
| `restore_config_comments.py` | Restaura los comentarios del `config.yaml` después de que `hermes config set` los borra. |

Las rutas van como placeholders (`<install>`, `<repo>`, `<user-home>`): editá las constantes del
encabezado antes de correrlos. Necesitan TouchDesigner abierto con el componente TDMCP activo en
el puerto **13316**.

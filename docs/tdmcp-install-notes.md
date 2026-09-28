> **Nota de layout (2026-09-28).** La instalación `AI_Code\TDMCP\TDMCP-1.1.55` se retiró:
> ahora TODO vive en este repo — `knowledge/` (código + KB), `component/` (el `.tox` oficial),
> `skills-hermes/`, `tools/` y `docs/`. Las rutas viejas que aparezcan abajo son históricas.

# extras/ — todo lo nuestro viviendo junto al TDMCP oficial

Esta carpeta acompaña a la instalación oficial **TDMCP 1.1.55**
(`<install>`), que es la base elegida:
el MCP oficial como **transporte/runtime** dentro de TouchDesigner y nuestra
capa de conocimiento (KB POP/GLSL, TDN, patch engine, validadores) **encima**.

```
TDMCP-1.1.55\   (RETIRADO 2026-09-28 — layout historico, ya no existe)
├── TDMCP.tox / TDMCP.toe     ← el componente oficial (arrastrar al root del proyecto)
├── README.md · CHANGELOG.md · LICENSE.md   ← del oficial
├── code\                     ← DATs file-synced por el MCP (ej. code/glsl/*.glsl)
├── .claude\ .agents\ .tdmcp\ ← instaladores de skills del oficial por host
└── extras\                   ← NUESTRO
    ├── README.md                           (este archivo)
    ├── skills\td-*\SKILL.md                (19 skills oficiales adaptadas a Hermes)
    ├── TDMCPSkills-src\                    (clone del repo oficial, con .git → git pull)
    ├── reportes\2026-09-28-tdmcp-oficial-vs-propio\
    │   ├── informe de testeo.md
    │   └── evidencia\                      (tools/list de ambos, respuestas de test, PNGs)
    └── scripts-testeo\                     (cliente MCP + baterías re-ejecutables)
```

## Estado (2026-09-28) — Fase 0 completada

| Cosa | Dónde | Estado |
|---|---|---|
| MCP oficial registrado en Hermes | `mcp_servers.tdmcp` en `config.yaml` → `http://127.0.0.1:13316/mcp` | ✅ `hermes mcp test tdmcp` → 26 tools |
| 19 skills `td-*` instaladas en Hermes | `~/AppData/Local/hermes/skills/touchdesigner/td-*` | ✅ visibles en `skills_list` |
| Copia re-instalable de las skills | `extras\skills\` | ✅ |
| Clone del repo de skills (para updates) | `extras\TDMCPSkills-src\` (`git pull`) | ✅ |
| Informe + evidencia | `extras\reportes\...` | ✅ |

## Cómo se usa el oficial

1. **En cada proyecto de TD**: arrastrar `TDMCP.tox` al **root** del proyecto y en su
   página **MCP** pulsar **Active**. Con el default `Addressscope=localhost` y
   `Auth=0` alcanza (el guard devuelve 403 fuera de loopback).
2. **En Hermes**: nada más — al abrir una sesión nueva las 26 tools aparecen como
   **`mcp_tdmcp_<tool>`** (`mcp_tdmcp_get_help`, `mcp_tdmcp_create_operator`, …).
   El `Server Name` del componente (`touchdesigner`) no afecta al prefijo de Hermes:
   el prefijo lo pone la clave del config (`tdmcp`).
3. **Orden de trabajo** (según `td-general`): `project_info` → `td-build-planning`
   → construir con las skills de familia → `td-review-network` → `td-network-cleanup`.

## Pitfalls verificados

| Pitfall | Detalle |
|---|---|
| **`hermes config set` borra TODOS los comentarios** del `config.yaml` | 4896→2978 bytes. Hacer backup antes; restaurar con `extras/scripts-testeo/restore_config_comments.py` (parte del backup e inserta el bloque nuevo sin re-dumpear el YAML). |
| `hermes mcp add <n> --url …` es **interactivo** (pregunta por auth) | Se cuelga en un tool call no-TTY. Usar `hermes config set mcp_servers.<n>.url …`. |
| `patch`/`write_file` **se niegan** a tocar `config.yaml` | Guard de seguridad (correcto). La vía oficial es `hermes config set` o editar el archivo a mano. |
| Dos TD abiertos con el mismo `Server Name` | Se tapan entre sí. Cambiar `Server Name` en uno. |
| TD < 2025.33060 y "localhost only" | `netstat` igual muestra `0.0.0.0:13316` (el bind a 127.0.0.1 llega después); el guard es a nivel app. Conviene regla de firewall. |
| `view_operator` y el base64 | Con **Inline Images=OFF** (default) devuelve sólo la **ruta** del PNG. Prenderlo en la página Tune para recibirlo inline. |
| `delete_operator` | **Auto-accept deletion=ON** por default: borra sin diálogo. Ojo con paths calculados. |
| `get_parameters` en modo `search` | **No es bug**: `search` sólo mira parámetros **no-default** (`include_defaults: false` por default). Si tu sandbox está todo en default te da `results: []` con `scanned_ops > 0` — pasar `include_defaults: true`. |
| `set_parameters` | Llamar **`get_help` primero** (los nombres abreviados de TD son impredecibles); con un valor de menú inválido devuelve `invalid_menu_value` + la lista de válidos. |
| Undo | Cada tool call = **una entrada** en `ui.undo` (`'MCP set_parameters /…'`) → Ctrl+Z la revierte entera. |
| `file_content` de `set_dat_content` | La ruta es **relativa a la carpeta del proyecto** (sandbox), no absoluta. |
| `build_network` | Crea **todo** bajo `parent_path`; no se puede crear un COMP y sus hijos en la misma llamada. |

## Actualizar las skills oficiales

```bash
cd "<install>\extras\TDMCPSkills-src"
git pull                       # trae skills nuevas / cambios
python ..\scripts-testeo\adapt_td_skills.py   # re-adapta a Hermes (description "Use when…" + banner de prefijo)
```
El script escribe en `~/AppData/Local/hermes/skills/touchdesigner/` y en `extras\skills\`.
Ojo: si el repo agrega una skill nueva, hay que sumarle su `description` al dict `DESCS`.

## Re-ejecutar los tests (TD abierto con el .tox activo)

```bash
cd "<install>\extras\scripts-testeo"
python official_battery3.py    # CRUD, wiring, params, errores, DAT, perf
python official_battery4.py    # search, undo, inline PNG
python official_grid.py        # grid temporal de frames + record CHOP
python official_config.py      # config de las páginas MCP/Tune/Docs
```
Los sandboxes de prueba (`/hermes_*`) se crean y se borran solos: **dejar el proyecto limpio**.

## Publicación — fork `tolchx/TDMCP`

**Fuente única de verdad del código: el clon del fork en `AI_Code\TDMCP\tolchx-TDMCP\`**
(`knowledge/` = server + tools; `knowledge/kb/` = los 30 MB de datos, ignorados por git).
Hermes y el watchdog corren **desde ahí**. Para avanzar: editás en el clon, `git push`, listo.
Esta carpeta `extras\` es la **instalación oficial** (el `.tox`), más skills/evidencia/reportes.

El port y las skills viven también en el fork `github.com/tolchx/TDMCP`:

| En el fork | Qué |
|---|---|
| `component/` | `.tox` oficial **1.1.55 sin modificar** + `TDMCP.json`, con los SHA-256 verificados contra los assets del release |
| `knowledge/` | el server offline (`server.py`, `build_assets.py`, `test_protocol.py`) — **sin** `kb/` (data derivada + docs de terceros) |
| `skills-hermes/` | las 19 skills adaptadas (+ `LICENSE-TDMCPSkills.md`) |
| `docs/` | notas de testeo + los 3 issues presentados |
| `FORK-NOTES.md` | qué agrega el fork y qué no es (no avalado por Derivative) |

Para actualizar: copiar de `extras/port` a `tolchx-TDMCP/knowledge` y `git push origin main`.

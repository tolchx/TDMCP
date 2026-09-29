---
name: td-comp-architecture
description: "Use when creating COMPs or structuring a project. baseCOMPs, extensions, custom pars, parent shortcuts, modularidad."
---

> **Adaptación Hermes.** Estas skills son del repo oficial `TouchDesigner/TDMCPSkills`
> y asumen el MCP oficial corriendo en TD. En Hermes las 26 tools del oficial se
> llaman **`mcp_tdmcp_<tool>`** (ej. `get_help` → `mcp_tdmcp_get_help`,
> `list_operators` → `mcp_tdmcp_list_operators`); los nombres "pelados" que
> aparecen en el texto son de Claude Code/Codex: traducilos con ese prefijo.
> Cargá **`td-general` primero** en cualquier tarea de TouchDesigner.

---

# Component Architecture

How to structure COMPs for modularity, reusability, and clean hierarchy.

## COMP Types

- `baseCOMP` — general container, extensions, custom pars. Most common for modules. Always set `display=true` after creating
- `containerCOMP` — has a UI panel, use for anything with a visual interface
- `geometryCOMP` — renders geometry, contains SOPs/POPs + MATs, has instancing support

## Parent Shortcuts

Every COMP that others reference should have a `parentshortcut`. Set on the COMP itself.

- CamelCase, capital first: `Project`, `Render`, `Camera`, `MyModule`
- Depth-independent — `parent.Project` works from any nesting level
- Refactor-safe — reparenting doesn't break references
- Always prefer over `../../` or `parent(2)`

## In/Out Operators

COMPs use in/out ops to define their boundaries:
- `inTOP`/`outTOP`, `inCHOP`/`outCHOP`, `inSOP`/`outSOP`, `inDAT`/`outDAT`
- `in*` receives data from external wires into the COMP
- `out*` sends data out of the COMP
- **Create the in* op before wiring** — a fresh baseCOMP has no input connectors until an in* op exists inside
- **Default input** — wire a default source to any in\* operator's input 0. When nothing is connected externally to the parent COMP, the in\* outputs this default instead. Works for all in\* types (inTOP, inCHOP, inSOP, inDAT)

## Custom Parameters

Use `edit_custom_parameters` tool — the schema is `{ "path", "page": "<page name>", "add": [...],
"edit": [...], "delete": [...], "sort": [...], "rename": [...], "delete_page": true }`. Each `add`
entry: `{ "name", "type", "label", "default", "min", "max", "clampMin", "clampMax", "normMin",
"normMax", "menuNames", "menuLabels", "size", "section" }` with `type` one of `Float, Int, Str,
Toggle, Menu, Pulse, Header, OP, COMP, TOP, CHOP, SOP, DAT, MAT, File, Folder, XY, XYZ, XYZW, RGB,
RGBA`. Name = code identifier, Label = human-readable display. Custom pars persist in .tox — never
create via init scripts.

⚠️ **Verified trap (2026-09-28):** a wrong envelope (`{"action": "add", "parameters": [...]}`) is
NOT rejected — the tool answers `success: true` with `added: []` and creates nothing. Check `added`
in the response (or verify with `get_parameters`) before building on the new pars.

- `enableExpr` — grey out conditionally: `par.enableExpr = 'me.par.SomeToggle'`
- `startSection` — visual divider above a parameter
- **Pulse from Python**: `comp.par.PulseName.pulse()`, not `comp.pulse('PulseName')`

## State Output Pattern

Expose computed state as readonly custom pars with expressions to extension `@property` methods. Downstream ops reference pars, never extension properties directly. Visible in UI, linkable, accessible via parameterCHOP.

## Extensions

For Python-driven components, see the `td-python-extension` skill. Use `get_operator_info(path, include_extensions=true)` to inspect existing COMPs — returns extension classes, promoted method signatures, clone sources, and config COMP contents.

## Network Size

- **Create sub-baseCOMPs whenever a functional group feels self-contained** — like splitting code into functions. Don't wait until a network is too big; decompose early when a group of operators has a clear purpose (e.g. "bat collision", "score detection")
- Each sub-COMP is self-contained: inCHOP → processing → outCHOP
- Parent COMP wires sub-COMPs in sequence, handles state/switching logic
- ~20 operators per COMP is a practical guideline, but the real signal is "does this group have a clear single responsibility?"

## Clone Pattern

When two sub-COMPs have identical networks but different parameter values (e.g. bat1/bat2 detection), use **clones**:
- Build the master baseCOMP with custom parameters for all variable values
- Internal network references `parent().par.Paramname`
- Create the copy with `edit_operator {"path": "/master", "copy_to": "/", "name": "master2",
  "nodeX": ..., "nodeY": ...}` — a full deep copy in one call (verified: the copy arrives with the
  master's whole internal network). There is no `duplicate_operator` tool
- Set `clone` parameter on the copy to point at the master: `set_parameters {"clone": "/master"}`
- The clone then inherits the master's internal network; only custom par values differ — override
  them per-clone with `set_parameters` (master keeps its own values; verified live)

## Self-Contained Components

- Keep everything inside one parent COMP — processing chain, materials, utilities
- Don't spill operators up to the parent level
- Use nulls at chain endpoints for stable internal references
- Use `./operatorName` for child references, `operatorName` for siblings

## geometryCOMP Specifics

- Delete auto-created torus immediately after creating
- Output nullPOP needs `display=true render=true`
- Material pattern: `materialMAT → null_material`, reference as `./null_material`
- For instancing: see `td-geometry-instancing` skill

### Verificado en vivo (2026-09-29)

- **El geometryCOMP dibuja el draw-stream del nodo con `render=true`**, y ese nodo es el **terminal
  del chain** (el `nullPOP` de salida), no el `nullTOP` del viewer. `display=true` solo **no**
  dibuja: hacen falta ambos. Con `render=false` el renderTOP sale negro aunque los datos estén bien.
- **El renderer es `renderTOP`** (familia TOP) y sus bindings `camera` / `geometry` / `lights` son
  OP-pars: solo por `execute_code`. El par de la luz es **`lights` (plural)** en este build —
  resolverlo iterando `ren.pars()` por `name.lower().startswith('light')`.
- **Una superficie no es una nube de puntos**: para partículas, `convertPOP(convert='topointprims')`
  antes del material (`spherePOP` default = 252 pts / 500 prims → con `topointprims`, 252 pts / 252
  prims y **se dibuja**). ❗ `deleteprims` deja 0 prims y el render sale **negro** — no sirve para
  hacer partículas visibles.
- Receta completa + gradables: skill **`td-pop-render-pipeline`**. Contratos:
  `contracts` (`section='render_flag_on_terminal'`).

## Pitfalls

- **Inventing tool arguments** — there is no `duplicate_operator`/`copy_operator`; cloning goes
  through `edit_operator.copy_to`. Unknown args are ignored, not rejected (see Custom Parameters
  above)
- **No in* op before wiring** — baseCOMP has no connectors until you create one inside
- **ext0object as expression** — must be constant mode string, not expression
- **Forgetting reinitextensions** — edited extension code doesn't reload automatically
- **Editing clone-controlled internals** — changes silently revert, customize via external ops only
- **Relative paths across COMPs** — use parent shortcuts instead
- **Custom par naming** — uppercase first letter, then lowercase + digits only. `Campadding` not `camPadding` or `CAMpadding`

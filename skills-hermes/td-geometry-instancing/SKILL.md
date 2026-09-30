---
name: td-geometry-instancing
description: "Use when instancing geometry. geometryCOMP, fuentes de datos (CHOP/DAT/TOP/POP), transforms, texturas."
---

> **Adaptación Hermes.** Estas skills son del repo oficial `TouchDesigner/TDMCPSkills`
> y asumen el MCP oficial corriendo en TD. En Hermes las 26 tools del oficial se
> llaman **`mcp_tdmcp_<tool>`** (ej. `get_help` → `mcp_tdmcp_get_help`,
> `list_operators` → `mcp_tdmcp_list_operators`); los nombres "pelados" que
> aparecen en el texto son de Claude Code/Codex: traducilos con ese prefijo.
> Cargá **`td-general` primero** en cualquier tarea de TouchDesigner.

---

# Geometry Instancing

Render one piece of geometry many times with per-instance transforms, colors, and textures via geometryCOMP instancing.

## Data Sources

`instanceop` accepts any operator family — pick based on data characteristics:

- **tableDAT** — static/hand-authored. Set `instancefirstrow=names`
- **CHOP** — animated/procedural (LFO, noise, soptoCHOP). Most common
- **TOP** — texture-driven, large instance counts
- **POP — direct** — only when the POP lives in the SAME geometryCOMP as the instanced geo. Point a transform source OP at a `nullPOP` and reference point attributes with `P(0)/P(1)/P(2)` (position), `attrib_name(i)`, etc. e.g. `instancetop=null_positions`, `instancetx=P(0)`, `instancety=P(1)`, `instancetz=P(2)`. **Cross-COMP does not work** [V]: a POP source in another geometryCOMP errors on the geometryCOMP ("POP with point count info on GPU can only be the main OP") and draws 0 instances — the render itself shows no error, so check the COMP
- **POP via poptoCHOP** — the path for data in another COMP (and whenever you need the channels elsewhere anyway). `instancetop` = the poptoCHOP, selectors are CHOP channel names `P_0/P_1/P_2` — NOT `P(0)`. Verified cross-COMP: 0 errors, instances draw

Split sources: `instancetop` (translate), `instancerop` (rotate), `instancesop` (scale). `instanceop` is the default fallback. Each accepts a POP directly (same geometryCOMP only) — use `P(n)`/attrib syntax in the channel selectors; with a CHOP source use channel names.

## Core Parameters

- `instancing` = `true`, `instanceop` = data source OP
- `instancecountmode` = `oplength` (auto-detect, default)
- `instancefirstrow` = `names` for DAT headers. **Must be lowercase**
- `instanceactive` — per-instance on/off channel

## Transform Channels

Each group has an OP override + X/Y/Z channel selectors:

- **Translate**: `instancetop`, `instancetx/ty/tz`
- **Rotate**: `instancerop`, `instancerx/ry/rz`
- **Scale**: `instancesop`, `instancesx/sy/sz`
- **Pivot**: `instancepop`, `instancepx/py/pz`
- **Rotate-to-vector**: `instancerottoop`, `instancerottox/y/z`
- **Rotate-up**: `instancerotupop`, `instancerotupx/y/z`
- **Transform order**: `instxord` (default: SRT), `instrord` (default: `rx ry rz` = intrinsic xyz)

Channel selectors map to CHOP channel names or DAT column headers.

## Rotate-to-Vector

Orient instances along a direction vector instead of Euler angles.

- `instancerottoforward` — local axis to align. Default `-Z`. Set `posy` for tubes/cylinders
- `instancerottoorder` — `rottoxform` (default), `rotaterotto`, `rottorotate`
- `instancerottoop` + `instancerottox/y/z` — direction source
- `instancerotupop` + `instancerotupx/y/z` — up vector (needed when direction is co-linear with default up)

**Scale caveat**: `instancesy` may not apply correctly in all `instancerottoorder` modes. Fall back to Euler angles if needed.

## Euler Angles from Direction Vectors

To align Y-axis geometry (tube) with direction (dx, dy, dz), with default `instrord` (intrinsic xyz):
- `rx = atan2(dz, sqrt(dx² + dy²))`, `ry = 0`, `rz = atan2(-dx, dy)`

Changing `instrord` changes which formula is correct. Use `functionCHOP(atan2)` + `mathCHOP(chanop=len)` for compiled computation.

## Color & Texture

- `instancecolorop` + `instancer/g/b/a`, `instancecolormode` — pick from the live menu (`menuNames`); the doc's `op` is not a real entry [V]
- `instancetexcoordop` + `instanceu/v/w`, `instancetexs` (TOP array), `instancetexindexop` + `instancetexindex`

## Common Patterns

- **Static** — tableDAT → `instanceop`, `instancefirstrow=names`
- **Animated** — lfoCHOP → mathCHOP → nullCHOP → `instanceop`
- **POP-driven (direct, same COMP)** — POP → nullPOP → `instancetop`/`instanceop`, channels `P(0)/P(1)/P(2)`. No poptoCHOP round-trip — but it fails if the POP is in another geometryCOMP
- **POP-driven (CHOP, cross-COMP)** — POP → nullPOP → poptoCHOP → nullCHOP → `instanceop`, selectors `P_0/P_1/P_2`. Required when the data lives in another COMP (or the channels are needed elsewhere)
- **TOP-driven** — noiseTOP → `instanceop`, pixel data drives transforms

## Pitfalls

- **`instancefirstrow` not set** — first row treated as header or vice versa
- **Menu values not lowercase** — `"Names"` silently becomes wrong entry
- **Channel name mismatch** — selectors must exactly match CHOP/DAT names
- **Missing `instanceop`** — no data source = no instances
- **Instance OP paths from geometryCOMP** — OP reference params resolve from inside the COMP. `../sibling` won't work. Use parent shortcut expressions: `{"expr": "parent.Shortcut.op('chop_name')"}`
- **POP source in another geometryCOMP** — the geometryCOMP errors with "POP with point count info on GPU can only be the main OP" while the render looks fine and draws 0 instances. Route the data through a poptoCHOP with `P_0/P_1/P_2` selectors (C12 in `knowledge/contracts/VERIFIED_CONTRACTS.md`)

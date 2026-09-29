---
name: td-mat-family
description: "Use when assigning or creating materials. constantMAT, pbrMAT, pointspriteMAT, glslMAT, lineMAT, blending."
---

> **Adaptación Hermes.** Estas skills son del repo oficial `TouchDesigner/TDMCPSkills`
> y asumen el MCP oficial corriendo en TD. En Hermes las 26 tools del oficial se
> llaman **`mcp_tdmcp_<tool>`** (ej. `get_help` → `mcp_tdmcp_get_help`,
> `list_operators` → `mcp_tdmcp_list_operators`); los nombres "pelados" que
> aparecen en el texto son de Claude Code/Codex: traducilos con ese prefijo.
> Cargá **`td-general` primero** en cualquier tarea de TouchDesigner.

---

# Materials

Materials control how geometry appears when rendered by a renderTOP.

## Material Types

- **constantMAT** — flat color, no lighting. Simplest, cheapest. Good for debug, UI, flat graphics
- **phongMAT** — classic diffuse+specular lighting. Maps for diffuse, specular, normal, bump, emit
- **pbrMAT** — physically based rendering. Metallic/roughness workflow, environment maps. Requires environmentlightCOMP with map TOP (see PBR Setup below)
- **pointspriteMAT** — renders points as camera-facing quads with configurable size. Essential for particle rendering
- **glslMAT** — custom GLSL vertex/pixel shaders. Full control. Load `td-glsl-shaders` skill for shader code
- **lineMAT** — renders line primitives (proximityPOP/linePOP graphs, edges). Per-line color, pixel or world width
- **wirePOP** — wireframe rendering via material wireframe toggle

## When to Use What

- **Flat particles/points** → pointspriteMAT (set `pointsize`, optional `colormap` texture)
- **Lit geometry** → pbrMAT (default choice) or phongMAT
- **Unlit solid color** → constantMAT
- **Custom shading** → glslMAT
- **Debug/wireframe** → constantMAT with `wireframe=true`

## pointspriteMAT

Renders each point as a camera-facing square. Without this, points render as single pixels.

- `pointsize` — sprite size in pixels (default 1)
- `colormap` — optional TOP texture mapped onto each sprite
- `alpha` — global opacity multiplier
- `blending` — enable for transparency
- `sizingmodel` — `constant/attenuate` or `attrib`. Attenuate scales with distance

### Verificado en vivo (2026-09-29): el look de partículas

| Par | Valor probado | Por qué |
|---|---|---|
| **`pointsize`** | **el tamaño del sprite** (default **1.0** ≈ 2 px) | es el par que hay que tocar: si los puntos se ven como puntitos, subí `pointsize` (2–4). Medido: 1→641 px · 2→1742 · 3→3324 · 4→5313 |
| `sizingmodel='constatten'` | tamaño en **píxeles** (predecible) | `perspective` escala en **mundo**: con `pointsize=1` llenó 300758/307200 px |
| `attensizenear` / `attensizefar` | **inertes con `attenpscale=0`** (default) | **no** controlan el tamaño — 1/8/60 dan el mismo render (refutado 2026-09-29) |
| `blending=true` + `srcblend='sa'` + `destblend='one'` | aditivo | partículas que se suman (glow); el `Cd` del punto llega al sprite |
| `colorr/g/b` | color base | multiplica el color del punto |

⚠️ `set_parameters` **no fijó `attensizenear`** aunque devolviera ok: escribí los valores por
`execute_code` y **releé** (`mat.par.pointsize.eval()`). Receta completa del pipeline POP→render
en la skill `td-pop-render-pipeline`; contratos en `contracts` (`section='pointsprite_pars'`).

## Placement

- **Inside geometryCOMP** — reference as `./mat_name`. Material lives with its geometry
- **Sibling level** — reference by name only (`mat_name`). Shared across geometryCOMPs
- **Naming**: `mattype_purpose` (e.g. `pointsprite_particle`, `pbr_surface`, `constant_debug`)
- Always use `get_help` before setting parameters — par names vary between MAT types

## PBR Setup

pbrMAT renders completely black without an environment light:
1. Create `environmentlightCOMP` inside the geometryCOMP (or sibling)
2. Create a map TOP — `moviefileinTOP` with `file` = `app.samplesFolder + '/Map/CloudyOcean_2Kx1K_8bit.tif'`, or a `constantTOP` for a quick flat env
3. Assign it to the **`envlightmap`** parameter (verified name, `parType: TOP`)
4. POP geometry using pbrMAT also needs `normalPOP` with `tang=alwayscompute` — PBR lighting requires tangent vectors

⚠️ `environmentlightCOMP` has **no input connectors** (verified 2026-09-28): you cannot wire the map
TOP to it — `wiring {to: envlight}` fails. The map goes through the `envlightmap` par, and because
that par is OP-valued it must be set via `execute_code` (`op('envlight').par.envlightmap =
op('envmap')`), not `set_parameters`.

## Render Network Setup (verified coreography)

The full assembly of a minimal 3D render — none of this is documented elsewhere in the skills, and
all of it was probed live against TD 2025.32460:

1. **The renderer is `renderTOP`** (TOP family). There is NO `renderCOMP` — `create_operator` with it
   fails `unknown_operator_type`.
2. **`renderTOP` auto-creates nothing** — a fresh one has zero children. Create `cameraCOMP`,
   `lightCOMP`, `geometryCOMP` (and the env rig from PBR Setup) as **siblings**, then bind the
   renderTOP's `camera` / `light` / `geometry` OP parameters.
3. **OP-valued bindings via `execute_code`**: `op('ren').par.camera = op('cam')` (same for
   `geometry`; `set_parameters` refuses string values there). Resolution goes through `set_parameters`
   (`resolutionw`/`resolutionh`) since those are plain ints.
4. **Guaranteed-visible test render**: set the pbrMAT's `constantr/g/b` (RGB components, ~0.9) —
   `constant=1` renders unlit-bright even with a black env map. Useful as a gradable "did it render"
   check before investing in lighting.
5. **Empty-render detector**: a `view_operator` PNG of ~200 bytes is a black/empty render (real
   content starts around 1.6 KB). Check camera binding and light/env first.

## glslMAT Setup

**From scratch** — creating a glslMAT auto-docks three DATs: `<name>_vertex`, `<name>_pixel`, `<name>_info`.

1. Delete `_pixel` docked DAT
2. Rename `_vertex` → `<name>_shader` (stays docked to MAT)
3. Write combined shader with `#ifdef TD_VERTEX_SHADER` / `#ifdef TD_PIXEL_SHADER` guards
4. Set both `vdat` and `pdat` to the renamed DAT
5. Keep `_info` docked for compile error visibility
6. Assign via `./mat_name` when inside a geometryCOMP

**From pbrMAT/phongMAT** — pulse `outputshader` on the existing material. This creates a glslMAT with all built-in uniforms and shader code pre-populated in separate vertex/pixel DATs. Better starting point when extending PBR-style materials — modify the generated shaders instead of writing from scratch.

Layout follows the GLSL DAT sandwich pattern (see `td-node-layout` skill). Load `td-glsl-shaders` skill for shader code, uniforms, and templates.

## Pitfalls

- **Points invisible** — using constantMAT/pbrMAT for point-only geometry. Use pointspriteMAT
- **Wrong path prefix** — `./` means child, no prefix means sibling. Match placement to reference
- **Blending off** — transparent materials need `blending=true` on the MAT
- **pbrMAT renders black** — missing environmentlightCOMP with an environment map TOP. Always include one (assignment via the `envlightmap` par — see PBR Setup)
- **No `renderCOMP`** — the renderer is `renderTOP`, and it auto-creates no children; bind camera/light/geometry as siblings (see Render Network Setup)
- **PBR on POPs missing tangents** — normalPOP `tang` must be `alwayscompute`, otherwise lighting fails
- **pbrMAT `metallic` defaults to 1** — must explicitly set `metallic=0` for non-metallic surfaces, otherwise geometry looks like chrome
- **pbrMAT reads vertex Tex, not point Tex** — glslPOP writes point attributes, but pbrMAT samples `basecolormap` from vertex Tex coords. Use `attributeconvertPOP` (`convertop=pointtovert`) to convert. See `td-pop-family` skill
- **glslMAT on POPs: `Cd`/`N` silent failure** — referencing `Cd` or `N` as vertex attributes silently kills rendering (geometry vanishes, no errors). Use `TDPointColor()` for vertex color, derive normals via `dFdx/dFdy(worldPos)` in fragment shader
- **lineMAT per-line color** — `linecoloratt='Color'` reads per-primitive `Color` (RGBA incl alpha). Without it, lines use flat `colorr/g/b`
- **lineMAT width vanishes under normalized camera** — `widthaffectedbyfov=ON` scales width with orthowidth; normalizing the cam (orthowidth 1920→1.0) makes lines sub-pixel/invisible. Fixed-resolution output: `widthaffectedbyfov=OFF` + pixel widths

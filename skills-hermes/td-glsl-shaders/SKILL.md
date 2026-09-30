---
name: td-glsl-shaders
description: "Use when writing GLSL or creating glslTOP/glslMAT/glslPOP. Pixel, compute, vertex, uniforms, DATs dockeados."
---

> **Adaptación Hermes.** Estas skills son del repo oficial `TouchDesigner/TDMCPSkills`
> y asumen el MCP oficial corriendo en TD. En Hermes las 26 tools del oficial se
> llaman **`mcp_tdmcp_<tool>`** (ej. `get_help` → `mcp_tdmcp_get_help`,
> `list_operators` → `mcp_tdmcp_list_operators`); los nombres "pelados" que
> aparecen en el texto son de Claude Code/Codex: traducilos con ese prefijo.
> Cargá **`td-general` primero** en cualquier tarea de TouchDesigner.

---

# GLSL Shaders

Custom GPU shaders in TouchDesigner. Three contexts: TOP (image processing), MAT (materials), POP (particle compute). See `reference.md` for built-in uniforms, functions, and template shaders.

## Contexts

- `glslmultiTOP` (prefer over glslTOP) — image processing, procedural textures, compute. Supports >3 inputs and POP buffer reads
- `glslMAT` — custom materials with vertex + pixel shaders, TD lighting system
- `glslPOP` / `glsladvancedPOP` — per-point GPU compute on particle data (see td-pop-family skill). Compute shader API (`P[idx]`, `TDIn_P()`, `N[idx]`) documented in td-pop-family `reference.md`. For `glsladvancedPOP` (multi-class, index buffer, extra outputs), see `glsladvancedPOP.md`. Custom attributes via attr sequence — buffer name is `Color` (capital C), auto-declared (see td-pop-family skill)

## Naming Conventions

- Uniforms `uName`, Samplers `sName`, Functions `CapitalCase()`, Locals `camelCase`, Constants `UPPER_SNAKE`
- Input index defines at top: `#define TEX_FEEDBACK 0`

## Docked DAT Pattern (glslTOP/glslmultiTOP)

Creating a glslmultiTOP auto-docks `<name>_pixel`, `<name>_compute`, `<name>_info` and auto-wires
`pixeldat` to `<name>_pixel`.

**Name the TOP at creation** (`glsl_<shader>`) so the docks inherit the prefix
(`glsl_<shader>_pixel`, …) and `pixeldat` is already correct — no rename, no repoint. (Docked refs
snapshot at creation; renaming the TOP later does NOT follow them.)

1. Create the glslmultiTOP with its final name `glsl_<shader>`.
2. Delete the unused mode dock (`_compute` for a pixel shader).
3. Write/sync the shader into `<name>_pixel` (already wired to `pixeldat`).
4. Keep `<name>_info` for compile-error visibility.

**Which DAT slot [V]** (C13 in `knowledge/contracts/VERIFIED_CONTRACTS.md`): the PIXEL shader
goes in `pixeldat`; `computedat` is the glslPOP-style compute slot (that's where a glslPOP's
shader goes, not here). Symptom of the wrong slot [2026-09-30, `/pop_sim_trails` monitor]:
`.errors()` comes back EMPTY and the output COPIES the input texture unprocessed — it reads as
a wiring problem, not a shader problem.

**glslPOP/glslcopyPOP**: los DATs dockeados (`<name>_compute`, `<name>_ptCompute`, `<name>_info`)
**NO existen al crear el nodo** — aparecen perezosamente al cocinar/enlazar `computedat` [V]. O sea:
justo cuando querés escribir el shader, no están. El flujo que funciona **siempre** es un **textDAT
hermano** con `language='glsl'` + `glslPOP.par.computedat = op(...)` (verificalo con
`get_operator_info` qué hijos quedaron realmente creados). Si en algún momento querés usar el dock,
primero forzá un cook y comprobá que existe. `glslcopyPOP` es la excepción: su `_ptCompute` sí es
obligatorio (TDCopyIndex). Borrá los dockeados que no uses si aparecen.

**glslMAT**: See `td-mat-family` skill for docked DAT setup and placement. Use `#ifdef TD_VERTEX_SHADER` / `#ifdef TD_PIXEL_SHADER` guards in combined shader DAT. See `reference.md` for MAT vertex/pixel functions and templates.

## Uniforms

Up to 32 uniform vectors via operator parameters (`vec0name`, `vec0valuex`, etc.).

**TOP/MAT**: uniforms are NOT auto-declared. Setting `vec0name=uTime` does nothing unless the shader has `uniform float uTime;`. TD infers the type from the GLSL declaration.

**Color uniforms → Colors page (TOP/MAT)**: for a `uniform vec4` color, use the **Colors** sequence (`color0name` + `color0rgbr/g/b` + `color0alpha`) instead of the Vectors page — a 4-component RGBA uniform with a color-picker swatch. Same rule: type is inferred from the GLSL declaration, so declare `uniform vec4 uName;` or it reads zero. (Samplers live on the **Samplers** page, fixed arrays on **Arrays**.)

**POP (glslPOP/glslcopyPOP)**: uniforms ARE auto-declared as `float`. Do NOT redeclare them — causes "Redeclaration" compile error. Cannot override the type to `vec3` etc.; use constants or sampler inputs for multi-component data.

To use N uniforms, first set the sequence block count, then access `vec0name`, `vec1name`, etc.

### Verificado en vivo (2026-09-28/29, glslPOP en TD 2025.32460)

- **Los cambios de DAT y de uniforms se aplican con un cook de RETRASO.** Editar el shader (o
  `vec0valuex`) y medir al instante devuelve el estado *anterior* — el falso diagnóstico típico es
  "el uniform no está conectado" (evidencia: `P = pos*2.0` no cambió P; al restaurar el DAT, el cook
  siguiente mostró exactamente el doble). Cociná en cadena y releé (`settle()`): ver
  `td-live-verification`.
- **Enlazar `computedat` resetea la secuencia `vec`**: bindeá el DAT **primero** y seteá
  `vec0name`/`vec1name`/valores **después**.
- **`outputattrs` lista los atributos re-escritos**: si el shader escribe `P` hay que declarar
  `outputattrs='P'` o falla con `'P' : undeclared identifier`. Y para atributos nuevos, Create
  Attributes con `attr0name='custom'` (**lowercase**), `attr0customname='Cd'`, `attr0numcomps=4`.
- **La secuencia `vec` arranca en `numBlocks=1`** [V]: para N>1 uniforms, subila primero por
  `execute_code` (`glsl.par.vec.sequence.numBlocks = 3`). Y los **valores** `vecNvaluex` a veces **no**
  los aplica `set_parameters` (quedan en 0.5 aunque responda ok) → escribilos por `execute_code` y
  releélos.
- **`TDPerlinNoise()` no existe en compute shaders** [V] (sí en TOP/MAT): para ruido, escribí un hash
  + interpolación a mano, o pasá una textura por sampler. Un campo curl-noise entero se hace con
  diferencias finitas de un potencial de ruido.
- **Ruido/atributo vivo**: si `numPrims()==0` el nodo no dibuja por más que el shader corra. Después
  del `glslPOP` el atributo debe conservar las **primitivas de punto** del input.
- **DAT del shader**: el flujo que funcionó siempre con el MCP oficial fue **textDAT hermano** +
  `language='glsl'` explícito + `par.computedat = op(...)`. El auto-dock de DATs del glslPOP no es
  fiable entre builds: verificá con `get_operator_info` qué hijos quedaron realmente creados.
- **Animar un uniform**: `par.vec0valuex.expr = 'absTime.seconds'` (expresión) y valores constantes
  para lo que mueve el usuario. Para **verificar**, escaloná el valor a mano (`par.val = 0/3`) y
  compará por `poptoCHOP` — el reloj maestro puede estar parado en remoto.

### glslPOP `vec` vs `const` Sequences

- **`vec` sequence** — runtime uniforms, GPU reads value each frame. Use for any parameter that changes at runtime (expressions, custom pars, animated values)
- **`const` sequence** — baked into shader source, triggers full recompilation on every value change. Use ONLY for truly static compile-time constants
- **Wrong choice causes hard switching** — `const` with expression-driven values recompiles each frame and produces threshold jumps instead of smooth interpolation

## Key Rules

- **Always `TDOutputSwizzle()`** on all color outputs — wrong channel ordering without it
- **glslTOP pixel main needs `out vec4 fragColor;` declared** — see the verified main below (C13)
- **No `#version` statement** — TD auto-injects it
- **`texture()` not `texture2D()`** — old GLSL 1.20 names don't work
- **`nonuniformEXT()`** for dynamically-indexed sampler arrays (Vulkan requirement)
- **glslMAT always `TDDeform(TDPos())`** — raw TDPos() breaks instancing
- **`rgba32float` format** for data textures — 8-bit clamps to [0,1]
- **Expression-driven resolutions** — never hardcode `resolutionw`/`resolutionh`
- **Prefer nodes over GLSL** — use built-in operators for common operations (circleTOP for splats, noiseCHOP for motion, lookupCHOP for curves) instead of reimplementing in shaders. Reserve GLSL for operations that truly need custom GPU code (advection, pressure solving, etc.)

## glslTOP Pixel Main [V] (2026-09-30, `/pop_sim_trails` monitor, C13)

The pixel shader REQUIRES the output declared and swizzled — the exact shape the default docked
DAT template shows:

```glsl
out vec4 fragColor;

void main()
{
    vec4 c = texture(sTD2DInputs[0], vUV.st);
    fragColor = TDOutputSwizzle(vec4(/* r, g, b, a */));
}
```

- A glslPOP-style main (`fragColor = vec4(...)` WITHOUT declaring `out vec4 fragColor;`) does
  NOT compile — and there is **no visible error**: `.errors()` is empty and the output stays a
  passthrough of the input, so you doubt the pipeline instead of the shader. Read `<name>_info`
  for the compiler log.
- Unlike glslPOP attributes, the glslTOP pixel output is NOT auto-declared — write the `out`.
- Uniforms: same `vec` sequence as glslPOP (`vec0name`/`vec0valuex`, bump
  `par.vec.sequence.numBlocks` first), but TOP does NOT auto-declare them — the shader needs
  `uniform float uName;` (see Uniforms above). Access the blocks via `op.pars('vec*')`;
  `op.par.vec2` does not exist (`td.ParCollection` does not expose sequence blocks as attrs).

## Feedback Pattern

constantTOP (clear) → feedbackTOP → glslmultiTOP → nullTOP. feedbackTOP `top` par must reference the downstream null.
- feedbackTOP = 1 iteration per frame. Use `npasses` on glslmultiTOP for iterative solvers
- Close the feedback loop before compiling shaders that depend on it (2D/3D type mismatch otherwise)

## Sync to File

Sync the pixel DAT to disk — the fast way to author: edit the `.glsl` on disk, TD recompiles.
- One `set_dat_content(file_content, file_path, file_type='glsl')` call writes the file and sets
  `file`/`syncfile`. The auto-docked pixel DAT already has `language=glsl`; a textDAT you create
  yourself needs `language=glsl` set (`set_dat_content` doesn't set it).
- Path: `code/glsl/<comp>/<subcomp>/<dat_name>.glsl`
  (e.g. `/project1/MyEffect/glsl_raymarch_pixel` → `code/glsl/MyEffect/glsl_raymarch_pixel.glsl`)
- Once synced, **edit on disk** — don't round-trip through the DAT.

See the `td-dat-family` skill for the full canonical flow.

## Pitfalls

- **Uniforms not declared in shader** — compiles but reads zero
- **TDPerlinNoise() in GLSL POP** — not available in compute shaders, only TOP/MAT
- **Creating separate textDATs for glslTOP** — rename and reuse auto-created docked DATs
- **Not checking `<name>_info` for compile errors** — `.errors()` only shows "Compile failed"; read the docked infoDAT for actual line numbers and error details
- **Pixel shader written into `computedat`** — that slot is glslPOP-style compute; wrong slot = empty errors + output passthrough of the input (C13 `pixeldat_no_computedat`)
- **glslTOP main without `out vec4 fragColor;`** — does NOT compile and shows NO error: output stays passthrough of input; declare the out and wrap outputs with `TDOutputSwizzle()` (C13 `glsltop_pixel_main`)
- **feedbackTOP before wiring** — outputs 2D texture, causes 3D compile errors downstream
- **Inline noise functions** — use noiseTOP as sampler input instead
- **Delta time** — `me.time.step` doesn't exist, use `1.0/me.time.rate` or `absTime.stepSeconds`
- **`centroid` in GLSL** — reserved keyword in GLSL 4.60, use `ctr` or similar
- **glslmultiTOP has no `resolution` par** — use `resolutionw`/`resolutionh` + `outputresolution='custom'` (or `'useinput'`). Setting `resolution` errors with `'td.ParCollection' object has no attribute 'resolution'` and halts `build_network` mid-way

### Skills proposal: a 3D render network recipe (renderTOP + camera/light/geometry + pbrMAT + environmentlight)

**Target repo:** [TouchDesigner/TDMCPSkills](https://github.com/TouchDesigner/TDMCPSkills) (content-only skills; this is not a server bug — filed here because it is the piece that cost the most agent friction during testing).

**Environment**
- TDMCP **1.1.55** on TouchDesigner **2025.32460**, Windows 11
- Discovered while building a minimal render level in an automated gauntlet; verified live.

**Summary.** `td-mat-family` correctly warns that *pbrMAT without environment light renders black*,
but no `td-*` skill documents how to assemble that environment light, and the assembly has four
non-obvious traps that cost a full probe-and-retry cycle. A short recipe (in `td-mat-family` or a new
`td-render-family`) would close the last gap we hit where the skills could not answer and the agent
had to experiment against the live project.

**The four undocumented traps, verified live**

1. **`renderCOMP` does not exist.** The renderer is the TOP **`renderTOP`** (an easy slip when writing
   COMP-family code; `get_help {family: "COMP"}` lists no render COMP). A `create_operator` with
   `renderCOMP` fails with `unknown_operator_type`.
2. **`renderTOP` auto-creates nothing.** Fresh `renderTOP` has **zero children** (verified:
   `children == []`). Camera, light and geometry must be created as siblings and bound via the
   `camera` / `light` / `geometry` parameters.
3. **`environmentlightCOMP` has no inputs.** The environment map goes through the **`envlightmap`
   parameter** (`parType: TOP`), not through wiring — `wiring {to: envlight}` fails because the COMP
   has no input connectors. Also note `set_parameters` cannot set OP-valued parameters (see issue #6
   in this series); the binding is one `execute_code` line:
   `op('envlight').par.envlightmap = op('envmap')`.
4. **Light and material bindings via `set_parameters` strings fail.** `{"camera": "op('/x/cam')"}` is
   refused (strings are constants only); the same three bindings as `execute_code`
   (`ren.par.camera = op('...')`) work. For a guaranteed-visible test render without any env map,
   `pbrMAT` accepts `constantr/g/b` (RGB components) — a constant ~0.9 renders unlit-bright, useful
   as a gradable "did it render" check.

**Minimal verified recipe (all steps via TDMCP tools)**

```text
baseCOMP 'render_rig'
  siblings: renderTOP 'ren', cameraCOMP 'cam', lightCOMP 'light',
            geometryCOMP 'geo', environmentlightCOMP 'envlight', constantTOP 'envmap', nullTOP 'out1'
  geo children: pbrMAT 'materialMAT', (torus SOP) -> nullTOP 'null1'
```

```text
1. build_network: the seven siblings above, connections ren->out1
2. execute_code:  op('.../geo').par.material = op('.../geo/materialMAT')
                  create torus inside geo, connect torus -> null1
                  ren.par.camera = op('.../cam'); ren.par.geometry = op('.../geo')
                  light par likewise;  op('.../envlight').par.envlightmap = op('.../envmap')
3. set_parameters: geo/materialMAT { constantr/g/b, roughness }   # constants only
4. set_parameters: ren { resolutionw/resolutionh }
5. view_operator out1 -> PNG evidence (a ~215-byte PNG means empty/black render)
```

**Suggested skill addition** (drop-in for `td-mat-family` "PBR" section or a new `td-render-family`):

- Renderer = `renderTOP` (TOP family), no auto-created children — bind `camera`/`light`/`geometry` pars to sibling COMPs.
- Bindings and OP-valued pars (incl. `envlightmap`) go through `execute_code`, not `set_parameters`.
- `environmentlightCOMP` takes the env map via the `envlightmap` par; it has **no input connectors** — do not try to wire it.
- `pbrMAT` color params are RGB components (`constantr/g/b`, `basecolorr/g/b`); use `get_help` for the page.
- Debugging aid: a viewer capture of ~200 bytes is an empty/black render — check the light/env first.

**Why it matters:** this was the only gauntlet level the agent could not complete from the skills
alone; everything else (extensions, clones, cross-family expressions, feedback loops) was covered by
`td-comp-architecture` / `td-python-extension` / `td-top-family` / `td-build-planning`.

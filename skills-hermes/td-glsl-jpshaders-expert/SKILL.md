---
name: td-glsl-jpshaders-expert
description: Expert GLSL Shader system for TouchDesigner (glslmultiTOP, glslTOP, glslPOP, glslMAT) integrated with the JPShaders parameterized WebGL library (fullscreencode.com/jpshadereditor & jpconnect API). Use when creating, transpiling, debugging, or parameterizing GLSL shaders, instantiating JPShader visual nodes with credits and original web buttons, or scheduling GLSL shader scenes on the TouchDesigner Multi-Layer Timeline.
---

# TouchDesigner GLSL Expert & JPShaders Library Integration (`td-glsl-jpshaders-expert`)

## 1. Purpose & Capabilities
This skill equips an AI agent to act as a senior GLSL shader architect in TouchDesigner (`glslmultiTOP`, `glslTOP`, `glslPOP`, `glslMAT`) while leveraging two authoritative shader sources:
1. **Verified TDMCP GLSL Rules & Recipes** (`tolchx-TDMCP/knowledge/kb/rules/GLSL_TOP_RULES.md`, `GLSL_POP_RULES.md`, `glsl_top_recipes.json`).
2. **JPShaders Parameterized WebGL Library** ([JPShader Editor](https://fullscreencode.com/jpshadereditor/) & [JPConnect API Docs](https://fullscreencode.com/jpconnect/documentacion/#jpshader)), providing **770+ shaders** (565+ verified compiling shaders by `jpupper`, `iacode`, `Sistema`, `CarlosKernel`, etc.) with ready-made normalized `0.0..1.0` uniform parameters.

---

## 2. Mandatory Attribution & Web Button in GLSL Shader Nodes

Whenever the agent creates a GLSL shader node, COMP, or UI section using visuals from **JPShaders**:
1. **Credits to JPShaders:** Must visibly display credits to **JPShaders (`jpupper / FullScreenCode`)** and the specific shader author (`autor`).
2. **Visit Original Web Button:** Must include a clickable button (`Visitarweb` / **"🌐 Visitar Web Original JPShaders"**) in the GLSL Shaders Node section (`JPShaders GLSL` Custom Parameter page in TouchDesigner, and in any HTML/Studio inspector) that opens:
   - Shader URL: `https://fullscreencode.com/jpshadereditor/shader.html?shader=<nombre>`
   - Editor Root: `https://fullscreencode.com/jpshadereditor/`
   - API Docs: `https://fullscreencode.com/jpconnect/documentacion/#jpshader`

### TouchDesigner Custom Page Pattern (`JPShaders GLSL`)
```python
page = comp.appendCustomPage("JPShaders GLSL")

p_cred = page.appendStr("Creditos", label="Créditos JPShaders")[0]
p_cred.val = f"JPShaders ({author}) — fullscreencode.com"
p_cred.readOnly = True

p_url = page.appendStr("Weburl", label="URL Shader Original")[0]
p_url.val = f"https://fullscreencode.com/jpshadereditor/shader.html?shader={shader_name}"
p_url.readOnly = True

p_btn = page.appendPulse("Visitarweb", label="🌐 Visitar Web Original JPShaders")[0]
```
Wire `Visitarweb` to a `parameterexecuteDAT` (`onPulse`) that runs `ui.viewFile(parent().par.Weburl.eval())`.

---

## 3. JPShaders Ecosystem API & Local AgentSDK

### Live API Endpoints (VPS)
- **List all shaders:** `GET https://vps-4455523-x.dattaweb.com/jpshadereditor/api/shaders`
- **Get shader code & uniforms:** `GET https://vps-4455523-x.dattaweb.com/jpshadereditor/api/shaders/:nombre`
  - Returns `{ "_id", "nombre", "autor", "contenido", "uniforms", "uniformFormats", "passesData", "compiles" }`.
- **Get multi-pass plan:** `GET https://vps-4455523-x.dattaweb.com/jpshadereditor/api/include/plan?shader=:nombre`
- **Login (only required to publish new shaders):** `POST https://vps-4455523-x.dattaweb.com/jpconnect/api/auth/login` with `{"email": "...", "password": "..."}` -> Bearer JWT.

### One-Call Node Creation via `AgentSDK`
In `C:\Users\Tolch\Documents\AI_Code\Touchdesigner-Multi-Layer-Timeline\AgentSDK`:
```python
import sys
sys.path.append(r"C:\Users\Tolch\Documents\AI_Code\Touchdesigner-Multi-Layer-Timeline")
from AgentSDK import create_jpshader_node, list_jpshaders, fetch_jpshader

# Creates a baseCOMP with glslmultiTOP, 'JPShaders GLSL' custom page, credits,
# '🌐 Visitar Web Original JPShaders' button, and all uniform sliders wired:
info = create_jpshader_node(
    parent_path="/project1",
    shader_name="starnest",  # or sexygalacticdream, videosinte, purerxr, gen_3Dmap, gen_circularraymarching...
    resolution=(1280, 720)
)
```

### Highlighted Parameterized Shaders in Catalog
| Shader Name | Author | Parameterized Uniforms (`0.0 .. 1.0`) | Visual Style |
| :--- | :--- | :--- | :--- |
| `starnest` | `jpupper` | `iterations, formuparam, volsteps, stepsize, zoom, tile, speedx, speedy, brightness, darkmatter, distfading, saturation, ma1, ma2` | Deep 3D volumetric cosmic nebula |
| `sexygalacticdream` | `jpupper` | `freq1, freq2, freq3, faser, faseg, faseb` | Psychedelic radial interference & RGB phase waves |
| `videosinte` | `jpupper` | `v1, v1_amp, v2, v2_amp, v3, v3_amp, v4, v4_amp, faser, faseg, faseb, speed, e_force` | Analog video synthesizer wave matrix |
| `purerxr` | `jpupper` | `sc, sc2, seed, r1, g1, b1, flush, speed` | Organic cellular Voronoi / reaction-style RGB shift |
| `agua-nikos` | `jpupper` | `u_refraccion, u_relieve, u_profundidad, u_especular, u_brillo, u_causticas, u_espuma, u_radio, u_speed` | Interactive water caustics & ripples |
| `gen_3Dmap` | `iacode` | `shape, zoom, texturemix, texturesize, grid, gridsize, ambient, specular, rotationxy, rotationxz, rotationyz` | 3D raymarched terrain & geometric grid |
| `gen_circularraymarching` | `iacode` | `size, radialtile, ztile, speed, fas, rotate, offsetx, offsety` | Infinite radial raymarched tunnel |
| `gen_aesteticpolys` | `iacode` | `cant, poly1_puntas, poly1_size, poly1_diffuse, poly1_angle, poly2_puntas, polys_speed, poly2_angle` | Sacred geometry & rotating polygonal fields |
| `gen_anillos3D` | `iacode` | `rotx1, roty1, size1, tile1, gordura` | 3D interlocking torus rings |
| `gen_atomdistort` | `iacode` | `energia1, energia2, ite1, palette` | Atomic distortion & fractal energy fields |
| `cruz` / `altoshaderblast` / `Cobre` | `jpupper` | `u_time` driven | Raymarched SDF smooth unions & metallic copper waves |

---

## 4. WebGL (JPShader / ShaderToy) to TouchDesigner GLSL 3.30+ Transpilation Rules

When converting any WebGL fragment shader into TouchDesigner (`glslmultiTOP` / `glslTOP`):

1. **Remove WebGL Precision & `#ifdef GL_ES`:**
   - Strip `#ifdef GL_ES ... #endif` and `precision mediump float;` / `precision highp float;`.
   - Do **NOT** add `#version 330` (TouchDesigner auto-injects the `#version` header).
2. **Declare Explicit Pixel Output (Contract C13 / Regla 1):**
   ```glsl
   layout(location = 0) out vec4 fragColor;
   ```
3. **Map Built-In `time`, `resolution`, and Samplers via Header Macros:**
   ```glsl
   uniform float u_time;
   #define time u_time
   #define resolution (uTDOutputInfo.res.zw)
   #define u_resolution (uTDOutputInfo.res.zw)
   #define backbuffer sTD2DInputs[0]
   #define intext sTD2DInputs[0]
   ```
   - Why `#define resolution (uTDOutputInfo.res.zw)`? Because `gl_FragCoord.xy` in TouchDesigner is in pixel coordinates `(0..W, 0..H)`, so `gl_FragCoord.xy / resolution` evaluates to `0.0..1.0` identically to WebGL without rewriting UV math!
4. **Replace `texture2D` and `gl_FragColor`:**
   - `texture2D(sampler, uv)` $\rightarrow$ `texture(sampler, uv)`
   - `gl_FragColor = expr;` $\rightarrow$ `fragColor = TDOutputSwizzle(expr);`
5. **Bind Uniforms via the `vec` Sequence (Regla 5):**
   - Never use `const0name`/`const0value` for scripted float uniforms in `glslTOP` (fails to bind under scripted creation).
   - Always use `vec0name`/`vec0valuex`, `vec1name`/`vec1valuex`, etc.
   - **CRITICAL:** Before setting `vec1name`, `vec2name`, ..., first increase the sequence block count:
     ```python
     glsl.par.vec.sequence.numBlocks = 1 + len(custom_uniforms)
     ```

---

## 5. Verified GLSL POP Compute Shader Rules (`glslPOP`)

When writing GPU particle compute shaders in `glslPOP`:
1. **DAT Slot:** Bind shader textDAT to `glsl_pop.par.computedat` (NOT `pixeldat`). Set `text_dat.par.language = 'glsl'`. Bind `computedat` **before** setting `vec0name`/`vec0valuex` (binding `computedat` resets `vec` sequence!).
2. **Bounds Guard (Regla 2):**
   ```glsl
   void main() {
       const uint id = TDIndex();
       if (id >= TDNumElements()) return;
       vec3 pos = TDIn_P(0, id);
       P[id] = pos;
   }
   ```
3. **Write-Only Output Attributes (Regla 1 & 4):**
   - Never read from `P[id]` unless `glsl_pop.par.outputaccess = 'readwrite'`. Read input positions via `TDIn_P(0, id)`.
   - List modified existing attributes in `glsl_pop.par.outputattrs = 'P N'`.
4. **Creating New Custom Attributes (Regla 3):**
   - To output `Cd` (color) or custom attributes not present on the input POP, use the **Create Attributes** page:
     - `attr0name = 'Custom'` (or `'custom'`)
     - `attr0customname = 'Cd'`
     - `attr0numcomps = 4`
5. **Uniforms in `glslPOP`:**
   - Unlike `glslTOP`, `glslPOP` **auto-declares** uniforms from `vec0name` as `float`. Do **NOT** write `uniform float uName;` inside a `glslPOP` shader or it will fail with a `"Redeclaration"` error!
6. **Check Compiler Errors in `<name>_info` (Regla 5):**
   - Always read `op('<glsl_name>_info').text` after `cook(force=True)` to inspect the real GLSL compiler log.

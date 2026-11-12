---
name: td-pops-tops-scene-builder
description: Specialized guide and blueprints for AI agents to build complex 3D GPU Particle (POP) simulations and 2D Texture (TOP) post-processing pipelines in TouchDesigner 2025+, enforcing verified contracts C1-C23 and integrating scenes into the Multi-Layer Timeline.
---

# TouchDesigner POPs & TOPs Scene Builder (`td-pops-tops-scene-builder`)

## 1. Overview
TouchDesigner 2025+ introduces the **POP (Point Operator)** family for GPU-native geometry, point clouds, and particle simulations, replacing legacy CPU SOP bottlenecks. Combined with **TOP (Texture Operator)** post-processing chains (`feedbackTOP`, `bloomTOP`, `displaceTOP`, `lookupTOP`, `compositeTOP`), an AI agent can synthesize complex 3D audiovisual scenes that mount directly onto layers of the **TouchDesigner Multi-Layer Timeline (TD-MTL)**.

---

## 2. Verified Contracts for POPs & 3D Render Pipelines (C1–C23)

Always enforce these verified rules from `tolchx-TDMCP`:

1. **Contract C1 (4-Pass Settle):**
   - Stateful POP chains (`particlePOP`, `trailPOP`, `feedbackTOP`) require at least 4 sequential frame cooks before inspecting pixel output (`numpyArray()`).
2. **Contract C5 (Explicit Render Triplet):**
   - A `renderTOP` produces a black image unless three operators exist and are explicitly wired:
     - `geometryCOMP` (`render = True`, `display = True`) containing a `selectPOP` or SOP/POP with `render = True`
     - `cameraCOMP` (`tz = 4.0..6.0` so geometry is inside the frustum)
     - `lightCOMP`
3. **Contract C8 (POP Methods, Not Properties):**
   - In Python, `pop.numPoints()`, `pop.numPrims()`, `pop.bounds()` are **methods** (must be called with `()`).
4. **Contract C9 (`particlePOP` Emission & Primitives):**
   - Keep `keepinputprims` / point primitives intact when feeding downstream `trailPOP` or `glslPOP`. If `numPrims() == 0`, nothing renders in the viewport.
5. **Contract C14 (Float Pixel Format for Data & HDR):**
   - Set `format = 'rgba16float'` or `'rgba32float'` on `glslmultiTOP`, `feedbackTOP`, and `poptoTOP` to avoid `[0, 1]` 8-bit clamping.

---

## 3. Golden POP Scene Blueprints for Timeline Layers

### Blueprint A: Curl Turbulence & Motion Trails (`curl_vortex`)
```
spherePOP (rows=64, cols=64)
  └──► noisePOP (amp=0.45, tz=absTime.seconds*0.35)
        └──► forceRadialPOP (swirl / vortex force)
              └──► trailPOP (traillength=24)
                    └──► nullPOP ("null_particles")
                          └──► geometryCOMP ("geo_particles" via selectPOP)
                                └──► renderTOP (1920x1080, rgba16float)
```

### Blueprint B: Audio-Reactive POP Galaxy (`audio_reactive_pops`)
```
audiofileinCHOP / audiodeviceinCHOP
  └──► audiospectrumCHOP
        └──► mathCHOP (gain) ──► nullCHOP ("audio_ctrl")

gridPOP (rows=100, cols=100)
  └──► noisePOP (amp bound to op('audio_ctrl')['chan1'])
        └──► lookupPOP (color ramp mapped by point velocity/distance)
              └──► geoCOMP ──► renderTOP
```

### Blueprint C: Custom GPU Compute Attractor (`glslPOP` + `poptoTOP`)
```python
# Create textDAT with compute shader first:
code_dat = scene.create("textDAT", "attractor_code")
code_dat.par.language = "glsl"
code_dat.text = """
void main() {
    const uint id = TDIndex();
    if (id >= TDNumElements()) return;
    vec3 p = TDIn_P(0, id);
    float r = length(p.xy) + 0.001;
    float angle = atan(p.y, p.x) + uSwirl * (1.0 / r) * 0.02;
    P[id] = vec3(cos(angle) * r, sin(angle) * r, p.z * 0.98);
}
"""
glsl_pop = scene.create("glslPOP", "glsl_attractor")
glsl_pop.par.computedat = code_dat.name
glsl_pop.par.outputattrs = "P"
glsl_pop.par.vec.sequence.numBlocks = 1
glsl_pop.par.vec0name = "uSwirl"
glsl_pop.par.vec0valuex.expr = "1.2 + 0.5 * math.sin(absTime.seconds)"
```

---

## 4. Golden TOP Post-Processing Chains

Attach any of these TOP chains between `renderTOP` (or `jpshader_*` node) and the Timeline layer's `levelTOP` fader:

### 1. Feedback Motion Glow & Chromatic Trails
```
renderTOP
  ├──► feedbackTOP (targettop = "null_loop")
  │      └──► transformTOP (sx=1.004, sy=1.004, rz=0.15)
  │            └──► levelTOP (opacity=0.92, brightness1=-0.01)
  │                  └──► blurTOP (size=2)
  └──► compositeTOP (operand="add" or "screen")
         └──► nullTOP ("null_loop")
               └──► outTOP ("out1")
```

### 2. Displace Refraction + Color Lookup Grading
```
sourceTOP ──────────────────────► displaceTOP (displaceweightx=0.04, displaceweighty=0.04)
noiseTOP (period=2.5, mono=False) ──▲      │
                                           ▼
rampTOP (color palette) ────────► lookupTOP ──► outTOP
```

---

## 5. Mounting POP/TOP Scenes into the Multi-Layer Timeline

Use `TimelineSceneEngine.add_pop_scene_cue()` to build and schedule a POP+TOP scene in a single call:
```python
from AgentSDK import TimelineSceneEngine

engine = TimelineSceneEngine("/project1", "Multi_Layer_Timeline")
engine.add_pop_scene_cue(
    title="Scene02_POP_Vortex",
    preset="curl_vortex",
    layer=2,
    start_time=8.0,
    cue_length=16.0,
    fade_in=2.0,
    fade_out=2.0,
    resolution=(1920, 1080)
)
```

---
name: td-timeline-scene-orchestrator
description: Comprehensive AI Agent workflow for building complex multi-layer audiovisual shows, scheduling multimedia content (video, audio, images), orchestrating crossfades, and connecting generative POP/TOP/GLSL scenes inside TouchDesigner Multi-Layer Timeline (TD-MTL).
---

# TouchDesigner Multi-Layer Timeline — Scene & Multimedia Orchestrator (`td-timeline-scene-orchestrator`)

## 1. Overview & Architecture
**TD-MTL (`Multi_Layer_Timeline.tox`)** renders a 3D GPU-instanced multi-track timeline (`Cues`, `Layers`, `Time`, `RenderPick`). By design, the core component outputs timing, playhead position, and `Segment DAT` triggers, leaving visual compositing decoupled.

To empower an AI Agent to construct complete audiovisual shows in a single turn, this skill pairs TD-MTL with the **`TimelineSceneEngine` (`AgentSDK/timeline_scene_engine.py`)**, which automatically builds `/project1/Timeline_Scene_Compositor` and wires every cue's `Starttime`, `Cuelength`, and `Fadeinoutduration` to real-time TOP faders (`levelTOP` $\rightarrow$ `compositeTOP`).

---

## 2. Quick-Start Agent API (`TimelineSceneEngine`)

Inside TouchDesigner (or via TDMCP `execute_code`):
```python
import sys
sys.path.append(r"C:\Users\Tolch\Documents\AI_Code\Touchdesigner-Multi-Layer-Timeline")
from AgentSDK import TimelineSceneEngine

engine = TimelineSceneEngine(project_path="/project1", timeline_comp_name="Multi_Layer_Timeline")
```

### Facility 1: Placing Multimedia Content (Video / Images / HAP)
Creates a `moviefileinTOP` + `levelTOP` envelope fader inside `/project1/Timeline_Scene_Compositor` and registers the visual Cue block on the specified layer:
```python
engine.add_multimedia_cue(
    title="Intro_Video_Wall",
    file_path="C:/Media/show_intro.mp4",
    layer=0,
    start_time=0.0,
    cue_length=15.0,
    fade_in=1.5,
    fade_out=2.0
)
```

### Facility 2: Placing Parameterized JPShaders GLSL Visual Cues
Instantiates a parameterized GLSL shader node from the **JPShaders** library (with credits to JPShaders + button to visit `https://fullscreencode.com/jpshadereditor/`), overrides any uniform slider (`0.0..1.0`), and schedules it on the timeline:
```python
engine.add_jpshader_cue(
    shader_name="starnest",          # or sexygalacticdream, videosinte, purerxr, gen_circularraymarching...
    title="Cosmos_StarNest",
    layer=1,
    start_time=5.0,
    cue_length=20.0,
    fade_in=2.0,
    fade_out=2.5,
    params_override={"zoom": 0.42, "brightness": 0.55, "saturation": 0.90},
    resolution=(1920, 1080)
)
```

### Facility 3: Placing 3D GPU Particle (POP) + Post-FX (TOP) Scenes
Builds a complete 3D particle simulation (`spherePOP` $\rightarrow$ `noisePOP` $\rightarrow$ `forceRadialPOP` $\rightarrow$ `trailPOP` $\rightarrow$ `nullPOP` $\rightarrow$ `geometryCOMP` + `cameraCOMP` + `lightCOMP` $\rightarrow$ `renderTOP`), connects it to the master compositor, and places the cue block on the timeline:
```python
engine.add_pop_scene_cue(
    title="Nebula_Curl_Particles",
    preset="curl_vortex",            # 'curl_vortex' or 'radial_spiral'
    layer=2,
    start_time=12.0,
    cue_length=18.0,
    fade_in=2.5,
    fade_out=2.5,
    resolution=(1920, 1080)
)
```

### Facility 4: One-Call Full Show Generation
Generates a complete 4-layer showcase combining JPShaders and 3D POP particle systems:
```python
summary = engine.build_ai_showcase_timeline()
```

---

## 3. Envelope & Parameter Automation Math

### Automatic Cue Opacity Envelope (`FadeIn` / `FadeOut`)
Every cue placed via `TimelineSceneEngine` binds its `levelTOP.par.opacity` to the live timeline playhead $t$ (`select_CurrentTime[0]`):
$$\text{opacity}(t) = \text{clamp}\!\left(\frac{t - t_{\text{start}}}{\text{fade}_{\text{in}}}, 0, 1\right) \times \text{clamp}\!\left(\frac{t_{\text{end}} - t}{\text{fade}_{\text{out}}}, 0, 1\right)$$

### Normalized Cue Progress ($0.0 \rightarrow 1.0$) for Parameter Keyframing
To animate any shader uniform or POP force parameter across the duration of a cue $(t_{\text{start}}, L)$:
```python
# Normalized progress u in [0.0, 1.0] during the cue:
t_expr = "op('/project1/Multi_Layer_Timeline/select_CurrentTime')[0].eval()"
u_expr = f"clamp((({t_expr}) - {start_time}) / {cue_length}, 0.0, 1.0)"

# Example: sweep JPShader 'zoom' from 0.15 to 0.85 over the cue:
shader_comp.par.Zoom.expr = f"0.15 + 0.70 * ({u_expr})"
```

---

## 4. Preload Pulse & Zero-Drop Media Switching

When scheduling heavy high-resolution video files (`4K HAP / ProRes`):
1. Inside `Multi_Layer_Timeline/Time`, the `Segment DAT` feeds a master `Timer CHOP`.
2. Each segment emits a **preload pulse** (`onSegmentPreload`) ahead of `Starttime`.
3. Wire the preload callback to `mov.par.cuepulse.pulse()` and `mov.par.play = 0`, then set `mov.par.play = 1` on `onSegmentEnter`.

---

## 5. Multi-Layer Show Design Best Practices for AI Agents

1. **Layer Stratification Convention:**
   - **Layer 0 (Base Background):** Continuous generative shaders (`jpshader_starnest`, `jpshader_cobre`, `noiseTOP` landscapes) or background loop videos.
   - **Layer 1 (Midground Visuals):** Multimedia video clips (`moviefileinTOP`), reactive synthesizers (`jpshader_videosinte`, `jpshader_galactic`).
   - **Layer 2 (3D Volumetric / POPs Layer):** 3D GPU Particle systems (`POP` networks rendered with transparent alpha `rgba16float`) composited with `Add` or `Over`.
   - **Layer 3 (Foreground Overlays / Typography / Strobe Hits):** Short accent cues, kinetic titles, or raymarched foreground objects (`jpshader_raymarch`, `cruz`).
   - **Layer 4 (Control / OSC / DMX Triggers):** Non-visual cues (`Cuetype='TCP/IP'` or `'OSC'`) that fire lighting or audio cues via `Main_Callbacks_Template.py`.
2. **Overlap & Crossfades:**
   - Overlap adjacent cues by `1.5s–3.0s` and set matching `fade_out` on Cue A and `fade_in` on Cue B for butter-smooth visual transitions.
3. **Save Timeline State:**
   - Call `op('/project1/Multi_Layer_Timeline/Project').ext.Manager.SaveProject()` after programmatic cue generation so the JSON state persists in TD storage.

---
name: td-pop-collisions-deflectors
description: Build GPU particle collision, floor clamping, deflector planes, and ray reflection pipelines using TouchDesigner 2025/2026 POPs (particlePOP, limitPOP, rayPOP, mathmixPOP).
---

# TouchDesigner 2025/2026: POP Particle Collisions & Deflector Surfaces

## Overview
This skill provides production recipes and exact parameter rules for implementing GPU-based particle collisions, ground clamping, deflector surfaces, and analytical ray reflection in TouchDesigner 2025/2026 Point Operators (POPs).

Based on techniques by Jack DiLaura (Interactive & Immersive HQ), it eliminates CPU bottlenecks and GLSL shader authoring by combining `particlePOP` feedback loops with `limitPOP` vector clamping and `rayPOP` surface intersection queries.

---

## When to Use
- Implementing gravity, bouncing, ground collisions, and bounding limits on thousands/millions of GPU particles.
- Creating deflector obstacles (planes, spheres, complex meshes) where particles bounce or deflect.
- Calculating analytical reflection vectors ($R = I - 2(I \cdot N)N$), surface hit normals, and collision distances in real-time.
- Styling collision points or velocities via color mapping (`lookuptexturePOP`) and particle trails (`trailPOP`).

---

## Pipeline Architecture

```
[emit: circlePOP/gridPOP] ──> [sim: particlePOP] <───┐
                                      │              │
                                      ▼              │
                               [gravity: mathmixPOP] │
                                      │              │
                                      ▼              │
                             [floor_clamp: limitPOP] │
                                      │              │
                                      ▼              │
                                [damp: transformPOP] │
                                      │              │
                                      ▼              │
                              [tgt: nullPOP] ────────┘ (Simulation Feedback)
                                      │
                                      ▼ (Input 0: Particles)
                           [ray_deflect: rayPOP] <─── [deflector_plane: gridPOP] (Input 1: Deflector)
                                      │
                                      ▼
                           [color_map: lookuptexturePOP] <─── [ramp_tex: rampTOP]
                                      │
                                      ▼
                            [trail: trailPOP]
                                      │
                                      ▼
                         [topoints: convertPOP] (topointprims - Contract C2)
                                      │
                                      ▼
                            [null_out: nullPOP] (display=True, render=True)
```

---

## Key Parameters & Exact Rules

### 1. Particle Simulation Feedback
- `particlePOP` (`sim`):
  - `birth`: Particle generation rate per second.
  - `life`: Particle lifespan in seconds.
  - `vel0`, `vel1`, `vel2`: Initial ejection velocity vector.
  - `targetop`: `op('./tgt')` (Enables GPU feedback loop).

### 2. Gravity Force Injection (`mathmixPOP`)
- `comb0oper`: `'add'`
- `comb0scopea`: `'PartForce'`
- `comb0scopeb`: `'0 -9.8 0'` (or custom gravity acceleration in Y)
- `comb0result`: `'PartForce'`

### 3. Ground / Coordinate Clamping (`limitPOP`)
To constrain particles above a floor (e.g. $Y \ge 0.0$):
- `inputattrscope`: `'P'` (Must scope to point position attribute).
- `parsize`: `3` (3-channel vector for $X, Y, Z$).
- `mintype1`: `'clamp'` (Index 1 corresponds to $Y$; values: `'off'`, `'clamp'`, `'loop'`, `'zigzag'`).
- `min1`: `0.0` (Clamps $Y$ to 0.0 without affecting $X$ or $Z$).

### 4. Deflector Surface & Ray Reflection (`rayPOP`)
- **Input 0:** Particle stream (from `tgt` or `damp`).
- **Input 1:** Deflector surface geometry (e.g., `gridPOP`, `spherePOP`).
- `rayattrib`: `'PartVel'` (Crucial: uses particle velocity vector as incoming ray direction instead of normal `'N'`).
- `dist`: `True` (Generates point attribute `RayDistance`).
- `hitnormal`: `True` (Generates point attribute `RayHitNormal`).
- `doreflectedray`: `True` (Generates point attribute `RayReflect` containing reflected bounce vector).

### 5. Damping / Energy Loss (`transformPOP`)
- Insert within feedback loop after collision clamping:
  - `sx`: `0.98`, `sy`: `0.98`, `sz`: `0.98` to simulate kinetic friction and surface drag.

### 6. Trails and Render Primitives (Contract C2)
- `trailPOP` (`trail`):
  - `length`: Number of history samples (e.g., `6` or `10`).
  - `attrmatch`: `True`
  - `attrname`: `'PartId'` (Ensures trails track individual particles across frames).
- `convertPOP` (`topoints`):
  - `convert`: `'topointprims'` (Mandatory: creates point primitives required by `pointspriteMAT` / `renderTOP`).

---

## Python Live Construction Template

```python
from knowledge import live

COMP_PATH = "/project1/my_pop_collisions"
live.call("create_operator", {"type": "baseCOMP", "name": "my_pop_collisions", "parent_path": "/project1"})

# Geo container
live.call("create_operator", {"type": "geometryCOMP", "name": "geo", "parent_path": COMP_PATH})
# Contract C2: delete default torus1
live.call("destroy_operator", {"path": f"{COMP_PATH}/geo/torus1"})

geo_path = f"{COMP_PATH}/geo"

# Create POP nodes
live.call("create_operator", {"type": "circlePOP", "name": "emit", "parent_path": geo_path})
live.call("create_operator", {"type": "particlePOP", "name": "sim", "parent_path": geo_path})
live.call("create_operator", {"type": "mathmixPOP", "name": "gravity", "parent_path": geo_path})
live.call("create_operator", {"type": "limitPOP", "name": "floor_clamp", "parent_path": geo_path})
live.call("create_operator", {"type": "transformPOP", "name": "damp", "parent_path": geo_path})
live.call("create_operator", {"type": "nullPOP", "name": "tgt", "parent_path": geo_path})

live.call("create_operator", {"type": "gridPOP", "name": "deflector_plane", "parent_path": geo_path})
live.call("create_operator", {"type": "rayPOP", "name": "ray_deflect", "parent_path": geo_path})
live.call("create_operator", {"type": "trailPOP", "name": "trail", "parent_path": geo_path})
live.call("create_operator", {"type": "convertPOP", "name": "topoints", "parent_path": geo_path})
live.call("create_operator", {"type": "nullPOP", "name": "null_out", "parent_path": geo_path})

# Wiring feedback
live.call("wiring", {"from_path": f"{geo_path}/emit", "to_path": f"{geo_path}/sim", "to_index": 0})
live.call("wiring", {"from_path": f"{geo_path}/sim", "to_path": f"{geo_path}/gravity", "to_index": 0})
live.call("wiring", {"from_path": f"{geo_path}/gravity", "to_path": f"{geo_path}/floor_clamp", "to_index": 0})
live.call("wiring", {"from_path": f"{geo_path}/floor_clamp", "to_path": f"{geo_path}/damp", "to_index": 0})
live.call("wiring", {"from_path": f"{geo_path}/damp", "to_path": f"{geo_path}/tgt", "to_index": 0})

# Wiring deflector
live.call("wiring", {"from_path": f"{geo_path}/tgt", "to_path": f"{geo_path}/ray_deflect", "to_index": 0})
live.call("wiring", {"from_path": f"{geo_path}/deflector_plane", "to_path": f"{geo_path}/ray_deflect", "to_index": 1})
live.call("wiring", {"from_path": f"{geo_path}/ray_deflect", "to_path": f"{geo_path}/trail", "to_index": 0})
live.call("wiring", {"from_path": f"{geo_path}/trail", "to_path": f"{geo_path}/topoints", "to_index": 0})
live.call("wiring", {"from_path": f"{geo_path}/topoints", "to_path": f"{geo_path}/null_out", "to_index": 0})

# Parameter setup
setup_script = f"""
sim = op('{geo_path}/sim')
sim.par.birth = 2000
sim.par.life = 3.0
sim.par.vel1 = 2.0
sim.par.targetop = op('{geo_path}/tgt')

g = op('{geo_path}/gravity')
g.par.comb0oper = 'add'
g.par.comb0scopea = 'PartForce'
g.par.comb0scopeb = '0 -9.8 0'
g.par.comb0result = 'PartForce'

fc = op('{geo_path}/floor_clamp')
fc.par.inputattrscope = 'P'
fc.par.parsize = 3
fc.par.mintype1 = 'clamp'
fc.par.min1 = 0.0

dp = op('{geo_path}/deflector_plane')
dp.par.sizex = 10.0
dp.par.sizey = 10.0
dp.par.rx = 90.0

rp = op('{geo_path}/ray_deflect')
rp.par.rayattrib = 'PartVel'
rp.par.dist = True
rp.par.hitnormal = True
rp.par.doreflectedray = True

topoints = op('{geo_path}/topoints')
topoints.par.convert = 'topointprims'

nout = op('{geo_path}/null_out')
nout.display = True
nout.render = True
"""
live.call("execute_code", {"code": setup_script})
```

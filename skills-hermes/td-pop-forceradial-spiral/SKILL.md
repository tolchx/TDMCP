---
name: td-pop-forceradial-spiral
description: Build GPU particle vortex, spiral field simulations, and multi-attractor dynamics using TouchDesigner 2026 POPs (forceradialPOP, particlePOP, noisePOP, trailPOP).
---

# TouchDesigner 2026: Spiralling Particle Fields with Force Radial POP

## Overview
This skill provides production recipes and exact parameter rules for implementing GPU-accelerated particle spiral fields, swirling vortex dynamics, multi-force point specifications, and coherent particle trails in TouchDesigner 2026 Point Operators (POPs).

Replaces legacy SOP setups (Metaballs + Copy stamping + Force SOP) with 100% GPU compute operations via `forceradialPOP`, `particlePOP`, and `noisePOP`.

---

## When to Use
- Creating swirling vortexes, spiral galaxies, whirlpools, or rotational force fields on GPU particles.
- Generating multiple independent moving force centers simultaneously via `specpop` (Specification POP).
- Combining directional spiral spin with 4D turbulent noise on `PartForce`.
- Generating high-density coherent motion trails using `trailPOP` linked to `PartId`.
- Eliminando cuellos de botella de CPU al descartar `copySOP` stamping.

---

## Pipeline Architecture

```
[emit: pointgeneratorPOP] ──> [sim: particlePOP] <───────────────────────────┐
                                      │                                      │
                                      ▼                                      │
                    [spiral_force: forceradialPOP] <── [spec_null: nullPOP]  │
                                      │              (specpop multi-vortex)  │
                                      ▼                                      │
                         [turb_force: noisePOP]                              │
                                      │                                      │
                                      ▼                                      │
                                [tgt: nullPOP] ──────────────────────────────┘
                                      │
                                      ▼
                        [color_map: lookuptexturePOP] <─── [ramp_tex: rampTOP]
                                      │
                                      ▼
                              [trail: trailPOP] (attrmatch=True, attrname='PartId')
                                      │
                                      ▼
                           [topoints: convertPOP] (convert='topointprims' - Contract C2)
                                      │
                                      ▼
                             [null_out: nullPOP] (display=True, render=True)
```

---

## Key Parameters & Exact Rules

### 1. Spiral Force Setup (`forceradialPOP`)
- `radial`: `False` (turn off simple radial push/pull unless radial expansion is desired).
- `spiral`: `True` (enables tangential rotational force around the specified axis).
- `directionx`, `directiony`, `directionz`: Vector determining the axis of rotation (e.g., `directionz = 1.0` spins particles around the Z axis in the XY plane).
- `spiralstrength`: Rotational torque multiplier (e.g. `0.5` to `2.0`).
- `falloffradius`: Spatial reach of the force center (e.g. `0.6` - `1.5`).
- `falloff`: `'scurve'` (smooth easing) or `'inversedist'` (hyperbolic falloff).
- `specpop`: References a POP providing multiple attractor positions (each point becomes an active force source).

### 2. Multi-Force Point Specification (`specpop`)
Instead of duplicating operators, feed a stream of points into `forceradialPOP.par.specpop`:
- Source: `pointgeneratorPOP` with `numpoints = 16` to `64`.
- Motion: Animate positions with `noisePOP(combineop='add', combineattrscope='P', type='simplex4d', t4d=absTime.seconds * 0.15)`.
- Connect terminal of spec chain to `nullPOP('spec_null')` and assign to `fr.par.specpop = op('./spec_null')`.

### 3. Turbulence Force Injection (`noisePOP`)
- Insert between `forceradialPOP` and feedback `nullPOP('tgt')`:
  - `type`: `'simplex4d'`
  - `combineop`: `'add'`
  - `combineattrscope`: `'PartForce'` (adds velocity turbulence directly to particle force).
  - `amp`: `0.2` - `0.5`
  - `t4d.expr`: `'absTime.seconds * 0.2'`

### 4. Coherent Particle Trails (`trailPOP`)
- To prevent flickering or jumping between different particles:
  - `length`: Historical frame samples (`6` to `16`).
  - `attrmatch`: `True`
  - `attrname`: `'PartId'` (ensures points in the trail belong strictly to the same historical particle ID).

### 5. Render Primitives (Contract C2)
- Point clouds require point primitives to be drawn by `pointspriteMAT` / `renderTOP`:
  - `convertPOP` (`topoints`):
    - `convert`: `'topointprims'`
  - Ensure `null_out.display = True` and `null_out.render = True`.

---

## Python Live Construction Template

```python
from knowledge import live

COMP_PATH = "/project1/my_pop_spiral"
live.call("create_operator", {"type": "baseCOMP", "name": "my_pop_spiral", "parent_path": "/project1"})

# Geo container and remove default torus (Contract C2)
live.call("create_operator", {"type": "geometryCOMP", "name": "geo", "parent_path": COMP_PATH})
live.call("destroy_operator", {"path": f"{COMP_PATH}/geo/torus1"})
geo_path = f"{COMP_PATH}/geo"

# Base emitter
live.call("create_operator", {"type": "pointgeneratorPOP", "name": "emit", "parent_path": geo_path})

# Spec POP multi-attractors
live.call("create_operator", {"type": "pointgeneratorPOP", "name": "spec_emit", "parent_path": geo_path})
live.call("create_operator", {"type": "noisePOP", "name": "spec_noise", "parent_path": geo_path})
live.call("create_operator", {"type": "nullPOP", "name": "spec_null", "parent_path": geo_path})

# Particle simulation loop
live.call("create_operator", {"type": "particlePOP", "name": "sim", "parent_path": geo_path})
live.call("create_operator", {"type": "forceradialPOP", "name": "spiral_force", "parent_path": geo_path})
live.call("create_operator", {"type": "noisePOP", "name": "turb_force", "parent_path": geo_path})
live.call("create_operator", {"type": "nullPOP", "name": "tgt", "parent_path": geo_path})

# Trails and render primitives
live.call("create_operator", {"type": "trailPOP", "name": "trail", "parent_path": geo_path})
live.call("create_operator", {"type": "convertPOP", "name": "topoints", "parent_path": geo_path})
live.call("create_operator", {"type": "nullPOP", "name": "null_out", "parent_path": geo_path})

# Wiring
live.call("wiring", {"from_path": f"{geo_path}/spec_emit", "to_path": f"{geo_path}/spec_noise", "to_index": 0})
live.call("wiring", {"from_path": f"{geo_path}/spec_noise", "to_path": f"{geo_path}/spec_null", "to_index": 0})

live.call("wiring", {"from_path": f"{geo_path}/emit", "to_path": f"{geo_path}/sim", "to_index": 0})
live.call("wiring", {"from_path": f"{geo_path}/sim", "to_path": f"{geo_path}/spiral_force", "to_index": 0})
live.call("wiring", {"from_path": f"{geo_path}/spiral_force", "to_path": f"{geo_path}/turb_force", "to_index": 0})
live.call("wiring", {"from_path": f"{geo_path}/turb_force", "to_path": f"{geo_path}/tgt", "to_index": 0})

live.call("wiring", {"from_path": f"{geo_path}/tgt", "to_path": f"{geo_path}/trail", "to_index": 0})
live.call("wiring", {"from_path": f"{geo_path}/trail", "to_path": f"{geo_path}/topoints", "to_index": 0})
live.call("wiring", {"from_path": f"{geo_path}/topoints", "to_path": f"{geo_path}/null_out", "to_index": 0})

# Parameter execution
script = f"""
em = op('{geo_path}/emit')
em.par.shape = 'rectangle'
em.par.sizex = 2.0
em.par.sizey = 1.0

sem = op('{geo_path}/spec_emit')
sem.par.shape = 'rectangle'
sem.par.sizex = 2.0
sem.par.sizey = 1.0
sem.par.numpoints = 16

sno = op('{geo_path}/spec_noise')
sno.par.combineop = 'add'
sno.par.combineattrscope = 'P'
sno.par.amp = 0.35
sno.par.type = 'simplex4d'
sno.par.t4d.expr = 'absTime.seconds * 0.15'

sim = op('{geo_path}/sim')
sim.par.birthrate = 2000
sim.par.life = 3.0
sim.par.maxparticles = 20000
sim.par.targetpop = op('{geo_path}/tgt')

sf = op('{geo_path}/spiral_force')
sf.par.radial = False
sf.par.spiral = True
sf.par.directionz = 1.0
sf.par.falloffradius = 0.8
sf.par.spiralstrength = 0.8
sf.par.specpop = op('{geo_path}/spec_null')

tb = op('{geo_path}/turb_force')
tb.par.type = 'simplex4d'
tb.par.combineop = 'add'
tb.par.combineattrscope = 'PartForce'
tb.par.amp = 0.3
tb.par.t4d.expr = 'absTime.seconds * 0.2'

tr = op('{geo_path}/trail')
tr.par.length = 8
tr.par.attrmatch = True
tr.par.attrname = 'PartId'

topoints = op('{geo_path}/topoints')
topoints.par.convert = 'topointprims'

nout = op('{geo_path}/null_out')
nout.display = True
nout.render = True
"""
live.call("execute_code", {"code": script})
```

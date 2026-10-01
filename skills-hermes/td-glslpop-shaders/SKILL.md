---
name: td-glslpop-shaders
description: "Use when authoring verified compute shaders for POPs: curl noise, spring forces, boids/flocking, wave deformation, and particle dynamics."
---

> **Adaptación Hermes.** Estas skills asumen el MCP oficial corriendo en TD (o `td-knowledge`).
> En Hermes las 26 tools del oficial se llaman **`mcp_tdmcp_<tool>`**; si usás Claude Code o el MCP directo, usá los nombres directos.
> Cargá **`td-general` primero** en cualquier tarea de TouchDesigner.

# TD GLSL POP Shaders

Verified compute shader templates and formulas for TouchDesigner POP particle networks.

## Canonical POP Compute Shader Structure

```glsl
// Mandatory preamble functions provided by TouchDesigner:
// uint TDIndex()               -> index of the current point
// uint TDNumElements()         -> total number of points
// vec3 TDIn_P(int input, uint id)  -> input position
// vec4 TDIn_Cd(int input, uint id) -> input color

uniform float u_time;
uniform float u_speed;

void main() {
    const uint id = TDIndex();
    if (id >= TDNumElements()) return;
    
    vec3 p = TDIn_P(0, id);
    
    // Shader body: modify position, write to P[id]
    P[id] = p;
}
```

---

## 1. 3D Wave Deformation Shader

```glsl
uniform float u_time;
uniform float u_frequency;
uniform float u_amplitude;

void main() {
    const uint id = TDIndex();
    if (id >= TDNumElements()) return;
    
    vec3 p = TDIn_P(0, id);
    float dist = length(p.xz);
    float wave = sin(dist * u_frequency - u_time * 2.0) * u_amplitude;
    
    P[id] = vec3(p.x, p.y + wave, p.z);
}
```

---

## 2. Curl Noise Field Simulation

```glsl
uniform float u_time;
uniform float u_scale;
uniform float u_speed;

// Simple pseudo-noise derivative for curl field
vec3 snoise3(vec3 v) {
    return sin(v * 2.14 + u_time * u_speed) * cos(v.zxy * 1.71);
}

vec3 curlNoise(vec3 p) {
    const float e = 0.01;
    vec3 dx = vec3(e, 0.0, 0.0);
    vec3 dy = vec3(0.0, e, 0.0);
    vec3 dz = vec3(0.0, 0.0, e);

    vec3 p_x0 = snoise3(p - dx);
    vec3 p_x1 = snoise3(p + dx);
    vec3 p_y0 = snoise3(p - dy);
    vec3 p_y1 = snoise3(p + dy);
    vec3 p_z0 = snoise3(p - dz);
    vec3 p_z1 = snoise3(p + dz);

    float x = p_y1.z - p_y0.z - p_z1.y + p_z0.y;
    float y = p_z1.x - p_z0.x - p_x1.z + p_x0.z;
    float z = p_x1.y - p_x0.y - p_y1.x + p_y0.x;

    return normalize(vec3(x, y, z) / (2.0 * e));
}

void main() {
    const uint id = TDIndex();
    if (id >= TDNumElements()) return;
    
    vec3 p = TDIn_P(0, id);
    vec3 v = curlNoise(p * u_scale);
    
    P[id] = p + v * 0.02;
}
```

---

## 3. Spring Force & Damping

```glsl
uniform float u_stiffness;
uniform float u_damping;
uniform float u_dt;

void main() {
    const uint id = TDIndex();
    if (id >= TDNumElements()) return;
    
    vec3 currentPos = TDIn_P(0, id);
    vec3 restPos    = TDIn_P(1, id); // Input 1: rest mesh/grid
    
    vec3 displacement = currentPos - restPos;
    vec3 springForce = -u_stiffness * displacement;
    
    // Euler step with damping
    vec3 newPos = currentPos + springForce * (u_dt * u_dt) * (1.0 - u_damping);
    P[id] = newPos;
}
```

---

## Static Validation Checklist

Before applying any shader to TouchDesigner:
1. Run `glsl_analyze` with `{ code: "...", family: "pop" }`.
2. Ensure `outputattrs` lists every attribute written (`P`, `Cd`, etc.).
3. Ensure the range guard `if (id >= TDNumElements()) return;` is present.
4. Verify uniforms match the parameter configuration on the `glslPOP` node.

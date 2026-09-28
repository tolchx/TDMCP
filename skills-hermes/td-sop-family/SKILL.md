---
name: td-sop-family
description: "Use when SOPS are needed (preferir POPs para GPU). Geometría procedural CPU."
---

> **Adaptación Hermes.** Estas skills son del repo oficial `TouchDesigner/TDMCPSkills`
> y asumen el MCP oficial corriendo en TD. En Hermes las 26 tools del oficial se
> llaman **`mcp_tdmcp_<tool>`** (ej. `get_help` → `mcp_tdmcp_get_help`,
> `list_operators` → `mcp_tdmcp_list_operators`); los nombres "pelados" que
> aparecen en el texto son de Claude Code/Codex: traducilos con ese prefijo.
> Cargá **`td-general` primero** en cualquier tarea de TouchDesigner.

---

# SOP Networks

CPU-based geometry operators. SOPs are the traditional geometry family — procedural modeling, deformation, boolean operations. For GPU-accelerated point work, prefer POPs (see td-pop-family skill).

## When to Use SOPs vs POPs

- **Always prefer POPs over SOPs** — even for simple shapes (torus, grid, sphere). POPs run on GPU, are animation-ready, and avoid CPU bottlenecks
- **SOPs only when no POP equivalent exists**: boolean operations, UV unwrapping, specific polygon operations
- For parametric shapes: use gridPOP → glslPOP with a compute shader instead of torusSOP/sphereSOP
- **Avoid SOPs inside geometryCOMPs** when POPs exist — use spherePOP not sphereSOP

## Common Generators

- `gridSOP` — structured grid
- `sphereSOP` — sphere
- `boxSOP` — box
- `tubeSOP` — tube/cylinder
- `circleSOP` — circle/arc/ellipse
- `lineSOP` — line
- `curveSOP` — NURBS/Bezier curves
- `textSOP` — 3D text geometry
- `scriptSOP` — Python-generated geometry

## Common Processing

- `transformSOP` — translate/rotate/scale
- `noiseSOP` — noise displacement
- `facetSOP` — cusp, consolidate, compute normals
- `convertSOP` — between polygon/mesh/NURBS
- `booleanSOP` — union/intersect/subtract
- `copySOP` — copy to template points
- `deleteSOP` — remove primitives/points
- `mergeSOP` — combine geometry
- `switchSOP` — select between inputs
- `nullSOP` — chain endpoint

## SOP to POP Conversion

`soptoPOP` converts SOP geometry into the POP family for GPU processing.

## Pitfalls

- **CPU-bound** — SOPs run on CPU, not GPU. Large meshes are slow
- **Using SOPs where POPs exist** — sphereSOP inside geometryCOMP won't render properly with POP instancing
---
name: td-glslpop-create
description: "Use when creating GLSL POP operator networks in TouchDesigner. Procedural compute shaders, SSBO attributes, wiring and parameters."
---

> **Adaptación Hermes.** Estas skills asumen el MCP oficial corriendo en TD (o `td-knowledge`).
> En Hermes las 26 tools del oficial se llaman **`mcp_tdmcp_<tool>`** (ej. `create_operator` → `mcp_tdmcp_create_operator`,
> `set_parameters` → `mcp_tdmcp_set_parameters`); si usás Claude Code o el MCP directo, usá los nombres directos.
> Cargá **`td-general` primero** en cualquier tarea de TouchDesigner.

# TD GLSL POP Create

Specialized skill for creating GLSL POP operator networks in TouchDesigner.

## When to Use
- User asks to create `glslPOP`, `glsladvancedPOP`, or `glslcopyPOP` operators
- User asks to build particle systems with custom GLSL compute shaders
- User asks to wire GLSL POP compute pipelines

## Quick Reference — Operator Types

| Family | Operator | Purpose |
|--------|----------|---------|
| POP | `glslPOP` | Basic GLSL compute shader (`P`, `Cd`, `N` attributes) |
| POP | `glsladvancedPOP` | Advanced GLSL (multi-class, extra outputs, index buffer) |
| POP | `glslcopyPOP` | GLSL copy with template input (`ptcomputedat`) |
| TOP | `glslTOP` / `glslmultiTOP` | GLSL pixel/vertex/compute shader |

---

## Step-by-Step: Create a glslPOP Network (TDMCP Tools)

### 1. Create source POP + textDAT + glslPOP + nullPOP

```json
// Tool: create_operator
{ "operator_type": "boxPOP", "name": "source", "parent_path": "/project1" }
{ "operator_type": "textDAT", "name": "shader_code", "parent_path": "/project1" }
{ "operator_type": "glslPOP", "name": "glsl1", "parent_path": "/project1" }
{ "operator_type": "nullPOP", "name": "out1", "parent_path": "/project1" }
```

### 2. Write Shader Code into DAT

```json
// Tool: set_parameters (o escribir DAT con file-sync / execute_code)
```

```glsl
// shader_code textDAT
uniform float u_time;

void main() {
    const uint id = TDIndex();
    if (id >= TDNumElements()) return;
    
    vec3 pos = TDIn_P(0, id);
    float wave = sin(pos.x * 3.0 + u_time) * 0.15;
    P[id] = pos + vec3(0.0, wave, 0.0);
}
```

### 3. Critical Parameters (Live-Verified)

```json
// Tool: set_parameters
{
  "operator_path": "/project1/glsl1",
  "parameters": {
    "computedat": "shader_code",
    "outputattrs": "P"
  }
}
```

> [!IMPORTANT]
> **Outputattrs es obligatorio:** Si `outputattrs` está vacío, `P[id] = ...` falla con `'P' : undeclared identifier`.
> Si vas a escribir color además de posición: `outputattrs = "P Cd"`.
> Si vas a escribir atributos nuevos que no vienen de la entrada, debés crearlos en la página **Create Attributes** (`attr0name="custom"`, `attr0customname="Color"`).

### 4. Wire the Pipeline

```json
// Tool: connect_operators (o smart_connect)
{ "from_operator": "/project1/source", "to_operator": "/project1/glsl1", "input_index": 0 }
{ "from_operator": "/project1/glsl1", "to_operator": "/project1/out1", "input_index": 0 }
```

---

## Docked DATs vs Sibling DATs

`glslPOP` / `glslcopyPOP` **NO crean sus DATs dockeados al crearse el nodo**. Aparecen perezosamente al compilar.
**La mejor práctica comprobada** es crear un `textDAT` hermano (`shader_code`) y asignarlo a `computedat = "shader_code"`.
Esto evita problemas de sincronización y asegura que el código exista antes de que el nodo intente compilarlo.

## Verificación Visual y Cook Lag (Contratos C1 y C2)

1. **Cook Lag:** Toda modificación de shader o uniform en TD 2025+ requiere forzar cooks sucesivos para asentarse (`settle()` o forzar cook del nullPOP).
2. **Renderización:** Recuerda que para que los puntos POP se dibujen en un `renderTOP`, deben convertirse a point primitives vía `convertPOP(topointprims)` o renderizarse con `pointspriteMAT` y `render=True`.

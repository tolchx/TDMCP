---
name: td-glslpop-debug
description: "Use when diagnosing GLSL compile errors, shader bugs, missing inputs, GPU crashes or silent failures in TouchDesigner."
---

> **Adaptación Hermes.** Estas skills asumen el MCP oficial corriendo en TD (o `td-knowledge`).
> En Hermes las 26 tools del oficial se llaman **`mcp_tdmcp_<tool>`**; si usás Claude Code o el MCP directo, usá los nombres directos.
> Cargá **`td-general` primero** en cualquier tarea de TouchDesigner.

# TD GLSL POP Debug

Diagnostic flowchart and solutions for TouchDesigner GLSL compile errors, runtime anomalies, and GPU issues.

## Diagnostic Flowchart

```
GLSL Operator in Error
  │
  ├─ 1. Leer errores estructurados
  │     └─ Tool: get_operator_errors / inspect_values
  │
  ├─ 2. ¿Dice 'undeclared identifier'?
  │     ├─ Si es 'P' o 'Cd' → Falta 'outputattrs' en el glslPOP (solución: set_parameters outputattrs='P')
  │     └─ Si es un uniform → Verificar nombre en la página Vectors/Arrays del nodo
  │
  ├─ 3. ¿Dice 'attribute not found' o escribe atributos custom?
  │     └─ Crear atributo en Create Attributes: attr0name='custom', attr0customname='Vel'
  │
  ├─ 4. ¿Error de swizzling o tipos?
  │     ├─ TOP: 'vUV.uv' es inválido → usar 'vUV.st' o 'vUV.xy'
  │     └─ POP: P[id] es vec3 (o vec4 si 4 componentes). TDIndex() devuelve uint.
  │
  ├─ 5. ¿El render se ve negro?
  │     ├─ Verificar convertPOP(topointprims) antes del nullPOP / render
  │     ├─ Verificar pointspriteMAT (pointsize > 0, constantcolor, alpha > 0)
  │     └─ Verificar que cameraCOMP apunte al bounding box de los puntos
  │
  └─ 6. ¿Se cuelga el driver GPU (TDR / Vulkan Crash)?
        └─ Revisar loops: nunca usar loops con límite variable no constante (Contrato C7).
```

---

## Verified Solutions to Common Errors

### 1. `'P' : undeclared identifier` / `'Cd' : undeclared identifier`
- **Causa:** El parámetro `outputattrs` del `glslPOP` está vacío por defecto.
- **Fix:**
  ```python
  op('glsl1').par.outputattrs = 'P'       # para posición
  op('glsl1').par.outputattrs = 'P Cd'    # para posición y color
  ```

### 2. `outputattrs` vs `Create Attributes`
- **Regla R3:** `outputattrs` sólo sirve para atributos que **ya vienen de la entrada** y se desean reescribir.
- Si querés escribir un atributo nuevo que no existía (ej: `Mass`, `Life`, `Color`), tenés que crearlo en la página **Create Attributes**:
  ```python
  op('glsl1').par.attr0name = 'custom'      # lowercase en TD 2025+
  op('glsl1').par.attr0customname = 'Mass'
  op('glsl1').par.attr0numcomps = 1
  ```

### 3. Loop infinito o TDR de GPU (Crash de Vulkan)
- **Contrato C7:** En compute shaders POP y pixel shaders TOP, los bucles con cantidad de iteraciones dependiente de un uniform dinámico pueden atascar el watchdog de Windows (TDR de 2 segundos) y colgar TouchDesigner sin diálogo de error.
- **Fix:** Usar un bucle `#define MAX_STEPS 64` constante o limitar `break` temprano.

### 4. Herramienta de Consulta Rápida
Para consultar soluciones a cualquier error textual del compilador:
- Usar la tool offline **`glsl_solutions`** con el texto del error (ej. `error_query: "undeclared"`).
- Usar **`glsl_analyze`** para validar estáticamente el código antes de pegarlo a TouchDesigner.

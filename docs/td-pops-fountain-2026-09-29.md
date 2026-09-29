# Test POP + revisión de Jev — fuente de partículas (2026-09-29)

Sesión de testeo del MCP oficial de TouchDesigner (TDMCP 1.1.55) construyendo una
fuente de partículas POP y dejando que **Jev** (juez externo) revise su utilidad.

## Qué se construyó

```
/fountain_demo (baseCOMP)
├── geo (geometryCOMP)
│   ├── emit      spherePOP   (rad 0.3, cols/rows 8)
│   ├── particles particlePOP (birthrate 80, life 2.5, initvelocityy 3, timeintegration ON)
│   ├── gravity   forceradialPOP (globforcemult 1, globforcey -6)
│   ├── topoints  convertPOP  (topointprims → nube de puntos)
│   ├── null_render nullPOP   (display/render ON)
│   └── sprite_mat pointspriteMAT
├── cam (cameraCOMP) · light (lightCOMP)
├── ren (renderTOP) → null_view
└── check (poptoCHOP, ground truth GPU→CPU)
```

**Resultado: 8/8 checks PASS, 27 tool calls, 0 errores, 1 warning no fatal.**

## Veredicto de Jev

| Pregunta | Resultado | Lectura |
|---|---|---|
| ¿Es útil para un VJ? | **demo_parcial** (0.86) | Funciona y enseña, pero es un ejemplo genérico, no un asset terminado (13% util_real, 1% roto) |
| ¿Se usó bien el MCP? | **2.99/3** | Excelente: get_help dictó params reales + verificación GPU→CPU + captura |
| ¿Alcanza la evidencia para documentar? | **2.71/3** | Suficiente → completa |

**Conclusión de Jev:** la construcción es excelente (el MCP se usó bien), pero el
proyecto resultante es un *demo*, no una pieza reutilizable. Para que sea "util_real"
habría que: cablear la cámara (el warning), darle un rango de frames animado con
evidencia temporal, y empaquetarlo como componente reutilizable con parámetros custom.

## Hallazgos de parámetros REALES (vía get_help) — para contratos

1. `set_parameters` usa la clave **`values`** (no `params`).
2. **spherePOP**: `rad` (XYZW → radx/rady/radz), `cols`/`rows` (NO `columns`), `freq`.
3. **particlePOP**: `timeintegration` (Toggle, **debe estar ON** para que se muevan),
   `birthrate`, `life`, `initvelocity` (XYZW → initvelocityy/z), `maxparticles`,
   `createpointprim` (crea point primitives él solo, sin convertPOP), `emissionmode`.
4. **forceradialPOP**: `globforce` (XYZW → globforcey), `globforcemult` (Float),
   `radial`/`axial`/`spiral`/`planar` (Toggles). NO existe `globforceradial`.
5. `display`/`render` son **propiedades del OP** (`out.display = True`), NO params
   (`out.par.display` → AttributeError).
6. **poptoCHOP**: `.chans()` (método) y `.numSamples`, NO `.channels`.
   Conteo de puntos POP: `.numPoints()` / `.numPrims()`.
7. `view_operator` es **async**: devuelve `{status: capturing, job_id}` y se recupera
   con una segunda llamada `view_operator {path, job_id}` (con sleep ~0.4s).
8. renderTOP sin cámara cableada → warning "No Camera COMP found" (no fatal, pero el
   render queda indefinido): `ren.par.camera = './cam'`.

## Tools del MCP ejercitadas

`project_info` · `list_operators` · `get_help` · `create_operator` · `build_network` ·
`wiring` · `set_parameters` · `execute_code` · `get_errors` · `inspect_values` ·
`view_operator` (async) — 11 de las 26 tools, todas `[ok]`.

## Evidencia

- `tools/gauntlet/results/20260929-032904/build-fountain-report.json`
- `tools/gauntlet/results/20260929-032904/fountain.png` (captura del geometryCOMP)
- `tools/gauntlet/results/20260929-032904/build-fountain.jsonl` (27 tool calls con latencia)

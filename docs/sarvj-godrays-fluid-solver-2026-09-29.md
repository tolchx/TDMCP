# SARVJ — "God Rays & POP Fluid Solver" (investigación 2026-09-29)

Investigación del proyecto `D:\TD\POPs\POPs SARVJ\GOD RAYS & POP FLUID SOLVER`
(`God Rays & POP Fluid Solver - Low Performances.8.toe`, TD 2025.32460). El `.tox` del
MCP oficial está embebido en `/project1/TDMCP`. Todo el contenido visual vive en
`/project1`.

## 1. Arquitectura general

Tres contenedores hacen el trabajo pesado; el resto de `/project1` es el cableado de
render y post-proceso.

| Contenedor | Rol |
|---|---|
| `Voxel_Grid_Init` | Crea la grilla voxel R³ (P, BndN, Flag, ijk) desde la que corre el solver |
| `POP_Fluid_Solver` | El solver Navier-Stokes en GLSL POPs (12 shaders) + advección de partículas PIC |
| `God_Rays` | Post-proceso radial (glslTOP) sobre el render |

Cadena de datos: `pointgeneratorPOP → … → Voxel_Grid_Init → POP_Fluid_Solver → render1`
con `God_Rays` como pass de post sobre el render.

## 2. El solver de fluidos (POP_Fluid_Solver)

Solver de **partículas-in-cell (PIC)** + **Navier-Stokes en grilla** (estilo Stam). Los
12 DATs GLSL mapean a los pasos clásicos:

| DAT | Paso | Qué hace |
|---|---|---|
| `glsl_addForces` | Fuerzas | vorticidad confinement + flotabilidad + damping + soft cap + no-slip BC |
| `glsl_advection` | Advección de velocidad | semi-Lagrangian u·∇u |
| `glsl_diffusion` | Difusión de velocidad | laplaciano (Jacobi) |
| `glsl_Divergence` | Divergencia | ∇·u |
| `glsl_Pressure_Jacobi` | Presión | solve de Poisson (Jacobi) |
| `glsl_Gradient_Subtraction` | Proyección | u -= ∇p |
| `glsl_Advection_Temp` | Advección de temperatura | tinte |
| `glsl_Diffusion_Temp` | Difusión de temperatura | tinte |
| `glsl1_compute` | Splat PIC | velocidades partícula→grilla (atomicAdd, trilinear) |
| `glsl1_compute2` | Advect PIC | grilla→partícula (trilinear + Euler) |
| `glsl3_compute` | Normalización | AccV/AccW → U |

### Atributos de la grilla (definidos en Voxel_Grid_Init)

- `P` — centro del voxel · `BndN` — normal de borde (discreta, hacia afuera)
- `Flag` — 1 si es célula de borde · `ijk` — índices (i,j,k)
- `U` — velocidad · `Temp` — temperatura (tinte) · `AccV`/`AccW` — acumuladores de splat
- `v_input` — velocidad de grilla normalizada · `Speed` — magnitud de velocidad (advección)

### Uniforms clave (por `SimRes`, `SimSizex/y/z`, `dt`)

- **Vorticidad**: `vcStrength`, `curlMin`, `gradMin` — el confinement `f_conf = vcStrength·sCurl·sGrad·cross(N,ω)`.
- **Flotabilidad**: `sigma`, `T0`, `buoyDir` — `f_buoy = sigma·(T−T0)·jhat`.
- **Damping**: `linDamp`, `quadDamp`. **Soft cap**: `limitSpeed`, `vSoftCap`, `softCapKnee`.

## 3. God Rays (glslTOP)

Shader de muestreo radial desde un centro (`uCenter`, en UV normalizado). El truco:
muestrea la textura `uSamples` veces a lo largo de la dirección `(fragCoord−center)`,
acumulando con `-uStrength`. Es un **radial blur directional** barato (2 muestras por
iteración para performance).

```glsl
vec2 pos = uCenter * res;
vec2 dir = (gl_FragCoord.xy - pos) / res;
for (int i = 0; i < uSamples; i += 2) {
    color += texture(sTD2DInputs[0], vUV.st + float(i)/float(uSamples)*dir*-uStrength);
    color += texture(sTD2DInputs[0], vUV.st + float(i+1)/float(uSamples)*dir*-uStrength);
}
fragColor = color / float(uSamples);
```

## 4. Otras carpetas del repo SARVJ (contexto)

`D:\TD\POPs\POPs SARVJ\` es una colección de proyectos POP/VJ: `Dragon skin`, `Kinect -
Time slices`, `POP Fluid Solver V1.0 / Pre-Release`, `POPs filter`, `PTE - Path Tracing
Engine (POPs only)`, `Skin Your Trails`, `post-rendered Lens Flare`, `GOD RAYS FOR ALL`,
`God Rays v1.1`, `360 shadows`.

## 5. Shaders volcados a disco (para estudio)

`tools/gauntlet/results/shader_study/*.glsl` — copia local de los 12 shaders del solver +
`god_rays_pixel` + `voxel_glsl_grille` para variación fuera de TD.

# particle_swirl — red de POPs GLSL con efecto de partículas

> ⚠️ **CORREGIDO 2026-09-29 (pase 2).** Este documento describe la **primera** versión de la receta,
> que resultó **falsa en su punto central**: `convertPOP(convert='deleteprims')` deja **0 primitivas**
> y el render sale **negro**. El "35/35 verde" y las capturas de acá medían el **`torus1`** que el
> `geometryCOMP` auto-crea (apagar su flag `render` lleva el render de 81572 px a 0). Las partículas
> nunca se dibujaron. Receta correcta: `convert='topointprims'`. Ver `docs/td-curl-field-2026-09-29.md`.

Fecha: 2026-09-29 · TD 2025.32460 · TDMCP 1.1.55 · Windows 11

Build canónico: `tools/gauntlet/build_particle_fx.py` → run verde **20260929-010805 (35/35 checks, 0 fallos)**.
La red queda de pie en TouchDesigner como `/particle_swirl`.

## 1. Qué se construyó

```
/particle_swirl
  geo (geometryCOMP, material = pointsprite_mat)
    sphere_emit  (spherePOP, radio 2.5)
      → topoints (convertPOP, convert='deleteprims')      ← nube de puntos pura
        → glsl_swirl (glslPOP + shader_compute textDAT language=glsl)
          → null_render (nullPOP, display+render=true)    ← terminal dibujada
  cam (cameraCOMP, tz=5) · light (lightCOMP)
  ren (renderTOP, camera=geo... camera=/cam, geometry=/geo, lights=/light, 640x480)
    → null_view (nullTOP)
  check (poptoCHOP, par pop → /geo/null_render)           ← lectura GPU→CPU
```

Shader (`shader_compute`): espiral animada + glow por partícula.

```glsl
float ang = uTime * 0.7 + src.y * 2.5;
vec3  swirl = vec3(cos(ang)*r, src.y + 0.18*sin(uTime*1.5 + r*8.0), sin(ang)*r);
vec3  pos   = mix(src, swirl, uSwirl) + 0.04 * jitter(fid, uTime);
P[id] = pos;
Cd[id] = vec4(0.2+0.8*glow, 0.35+0.3*(1.0-glow), 0.9-0.4*glow, 1.0);   // glow = f(uTime, r)
```

Params relevantes: `outputattrs='P'`; Create Attributes `attr0name='custom'`,
`attr0customname='Cd'`, `attr0numcomps=4`; uniforms `vec0name='uTime'`
(expr `absTime.seconds`), `vec1name='uSwirl'` (=0.6); `computedat` → `shader_compute`.

Material `pointsprite_mat`: `sizingmodel='constatten'`, `attensizenear=8` (px),
`blending=true`, `srcblend='sa'`, `destblend='one'` (aditivo), color (0.25, 0.6, 1.0).

## 2. Verificación (todo reproducible con el build)

| Check | Evidencia |
|---|---|
| Shader válido antes de tocar TD | `glsl_analyze` R1-R4 OK (offline) |
| Compila en TD | `glsl_swirl.errors() == ''` |
| **Nube de puntos pura** | `null_render.numPoints()=252`, `numPrims()=0` |
| Atributos vivos | poptoCHOP: 10 canales (P_0..2, Cd_0..3, N_0..2) |
| **Anima con uTime** | P (poptoCHOP) cambia al escalonar uTime 0 → 3 |
| **Anima con uSwirl** | P (poptoCHOP) cambia al escalonar uSwirl 0 → 1 |
| Color por partícula | Cd vivo (min/max 0.2..1.0); el render sale ámbar (firma del Cd) |
| Render dibuja | px no negros tras asentar cooks; PNG > 1000 B |
| Red sin errores | `get_errors(/particle_swirl)` = 0 |

Métricas de los PNG del run (decodificados con PIL vía `tools/gauntlet/verify_visual.py`):

```
particle_fx.png      148x111  px_lit=4398   mean_rgb=[0.433, 0.851, 0.989]  bbox=[18,33,129,77]
                      pixel mas brillante: RGB(64, 153, 255)  (azul)
particle_fx_grid.png 640x360  por celda 2x2: px_lit=15430  mean_rgb=[0.430,0.846,0.986]
```

El color es **azul/cian** (B > G > R), coherente con el material (0.25, 0.6, 1.0)
modulado por el `Cd` del shader y acumulado con blending aditivo (el núcleo satura).
Preview con los PNG embebidos: `preview_particle_swirl.html`
(también en `tools/gauntlet/results/20260929-010805/preview_final.html`).

## 3. Contratos nuevos verificados en vivo

1. **`convertPOP` con `convert='deleteprims'` es lo que convierte la superficie en
   partículas.** Sin ese paso el render dibuja la esfera (252 pts / 500 prims, ~26.6 %
   del frame): es el "blob", no un enjambre. Con `deleteprims` → 252 pts / 0 prims.
2. **`pointspriteMAT` dibuja bien la nube de puntos.** `sizingmodel='constatten'` +
   `attensizenear` en píxeles es lo predecible: 20 px (default) = sprites gigantes que
   funden la nube en un blob; 8 px + `blending sa/one` = partículas con brillo aditivo.
3. **Los cambios de DAT de shader y de uniforms `vec*` se aplican con un cook de
   RETRASO.** Medir inmediatamente después de editar devuelve el estado anterior
   (firma detectada: editar `P = pos*2.0` no cambia P; al *restaurar*, el cook
   siguiente muestra exactamente el doble). Regla operativa: **asentar** (cocinar
   `geo → glsl → nr → ren` 4-5 veces) antes de leer.
4. **`numPoints`/`numPrims` son método en POPs pero propiedad (int) en SOPs**
   (`tor1.numPoints()` → `TypeError: 'int' object is not callable`).
5. **Clases de operador para `COMP.create()`**: los POP/SOP expuestos son
   `spherePOP`, `convertPOP`, `nullPOP`, `sphereSOP`, `convertSOP`, `constantMAT`…;
   `sphere`/`convert` a secas no existen como nombre global.
6. **`ParMode` es enum**: `int(par.mode)` falla; usar `str(par.mode)`.
7. **`build_particle_fx.py` no debe importarse**: era un script sin guard, y un
   `from build_particle_fx import SHADER` reconstruía la red entera y terminaba en
   `sys.exit()`. Añadido `if __name__ == "__main__": main()`.
8. **Las flags de dibujo van en el TERMINAL DEL CHAIN** (`null_render` con
   `display=true` y `render=true`), no en `null_view` (ese es el TOP del viewer).
   El script antiguo solo marcaba `null_view`, así que tras un rebuild el geo
   quedaba sin nodo dibujable.
9. **`set_parameters` no fijó `attensizenear`** del `pointspriteMAT` (quedaba en el
   default 20 px = sprites gigantes/​blob) aunque la tool devolviera ok; la escritura
   directa por `exec_code` sí, y el build ahora la verifica por read-back.
10. **Decodificar PNG a mano es una trampa**: un decoder casero con los filtros
    Sub/Paeth implementados a medias devolvía conteos y colores falsos (728 px
    "ámbar" en vez de 4398 px azules). Los PNG de `view_operator` son RGBA 8-bit
    (color type 6) y en orden RGB — verificado con sondas de color puro — así que
    **usar PIL**. `verify_visual.py` ya lo hace.

## 4. Límites del entorno remoto (importante para futuras verificaciones)

* **El reloj maestro está detenido.** `absTime.seconds` no avanza dentro de un
  `execute_code` (0.4-0.8 s de `time.sleep` → mismo valor); el `timeCOMP` del root
  es `/local/` (`play=True`, `frame`/`seconds` propios) y en 2025.32460 **no existe
  `root.par.play`** ni `absTime.play`. En consecuencia la GUI no produce frames
  mientras no se la enfoca/da play.
* **El `renderTOP` no re-sube geometría POP ante cambios de datos.** Sí refleja
  cambios de *material* (sonda de color: mean pasó a rojo) y de *estructura*
  (rewire/flags), pero escalonar `uTime`/`uSwirl` o editar `radx` no altera
  `numpyArray()`: la imagen queda cacheada (px constante). Un renderTOP recién creado
  tampoco lo refleja.
* Por eso el grid temporal (`view_operator frames=4`) repite el mismo fotograma y
  **la animación se verifica por `poptoCHOP`** (GPU→CPU), que sí sigue los cambios
  (y fue lo que permitió ver el retraso de cook del punto 3.3).
* En la GUI de TouchDesigner con el frame loop activo (play/foco) el efecto anima;
  lo que falta es captura fotograma-a-fotograma en este entorno headless.

## 5. Artefactos

| Archivo | Uso |
|---|---|
| `tools/gauntlet/build_particle_fx.py` | construye/verifica la red; re-ejecutable; deja `/particle_swirl` de pie |
| `tools/gauntlet/verify_visual.py <run_id>` | decodifica los PNG (frame + grid) y compara sub-frames |
| `tools/gauntlet/make_preview.py <run_id>` | genera el HTML de preview con los PNG embebidos |
| `preview_particle_swirl.html` | preview registrado en el panel |
| `tools/gauntlet/results/20260929-010805/` | PNGs y logs del run canónico |

## 6. Propuestas (upstream / siguientes pasos)

* Documentar en TD/TDMCP el **retraso de cook** de DAT+uniforms en POPs: hacerlo
  explícito ahorra horas de diagnóstico falso ("uniform desconectado").
* Añadir un check de **render con contenido** basado en píxeles (no en bytes del PNG):
  un PNG "con contenido" puede ser un blob de superficie en vez de partículas.
* Registrar en la KB (`knowledge/server.py`) que el look de partículas exige
  `deleteprims` + `pointspriteMAT` con `constatten` en píxeles.
* Si se quiere capturar movimiento en remoto: buscar la API de arranque de la
  timeline en 2025.32460 (o forzar frames por otro medio) y re-intentar el grid.

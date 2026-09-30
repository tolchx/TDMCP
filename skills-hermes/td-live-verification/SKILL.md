---
name: td-live-verification
description: "Use when measuring or verifying TD state from Python. Asentar cooks (cook lag), poptoCHOP como verdad, píxeles con numpyArray, capturas con PIL, read-back de writes."
---

> **Adaptación Hermes.** Estas skills son del repo oficial `TouchDesigner/TDMCPSkills`
> y asumen el MCP oficial corriendo en TD. En Hermes las 26 tools del oficial se
> llaman **`mcp_tdmcp_<tool>`** (ej. `get_help` → `mcp_tdmcp_get_help`,
> `list_operators` → `mcp_tdmcp_list_operators`); los nombres "pelados" que
> aparecen en el texto son de Claude Code/Codex: traducilos con ese prefijo.
> Cargá **`td-general` primero** en cualquier tarea de TouchDesigner.

---

# Verificación en vivo (medir sin engañarse)

Esta skill existe por una razón concreta: **casi todas las conclusiones falsas** de una sesión de
build salen de medir mal, no de que la red esté mal. Los cuatro contratos de abajo se verificaron
con evidencia numérica (2026-09-29, TD 2025.32460 + TDMCP 1.1.55).

## Regla 0 — asentar antes de leer (`cook_lag`)

Los cambios de **shader DAT**, **uniforms `vec*`** y parámetros de datos se aplican con **un cook
de retraso**. Medir inmediatamente devuelve el **estado anterior**. Evidencia: editar el shader a
`P[id] = pos * 2.0` no cambió nada; al restaurarlo, el cook siguiente mostró exactamente el doble.

```python
def settle(n=4):
    for _ in range(n):
        op('/X/geo').cook(force=True)
        op('/X/geo/glsl').cook(force=True)
        op('/X/geo/null_out').cook(force=True)
        op('/X/ren').cook(force=True)
        time.sleep(0.04)
```

⚠️ **El `settle()` tiene los paths de una red cableados**: si vas a leer píxeles de **otra** red, o
parámetrizalo o cociná **su** cadena. Medido: togglear `torus1.render` en `/particle_swirl` sin
cocinar la cadena de swirl no cambió nada (frame cacheado); al cocinarla, cayó a 0.

⚠️ **Y no copies este `settle()`: la medición tiene un solo dueño.** Ya hubo tres copias del wrapper
en el repo del gauntlet. El dueño es `tools/gauntlet/td_chain.py` — el programa que se **inyecta** en
TD con `td_probe.chain_source(root)`: `settle()`, `px()` y `render_is_ours()` atados a *esa* red (y
`selftest_render_ownership()` para probar que la guardia **puede fallar**). Los consumidores llaman a
esos helpers en vez de re-implementarlos: `python tools/gauntlet/check_single_home.py` convierte la
regla en algo ejecutable (exit 1 si alguien re-define `settle`/`px`/`render_is_ours`), y ese chequeo
más `python tools/gauntlet/td_probe.py` son pasos de `scripts/loop_gate.py`: si alguien re-implementa
la medición, el commit queda en **BLOCK**. El registro de qué quedó probado y con qué corrida vive en
`docs/BACKLOG.md` → *Estado verificado* (dueño único; no lo repitas acá).

Después de **cada** write relevante: `settle()` y recién ahí leer. Si dos lecturas seguidas no
coinciden, faltan cooks (no "es aleatorio").

## Regla 1 — números antes que píxeles

| Qué querés saber | Herramienta | Cómo |
|---|---|---|
| ¿Cuántos puntos / prims? | POP en Python | `null_out.numPoints()` (POP: **método**; SOP: **propiedad** int — `tor1.numPoints()` da `TypeError`) |
| ¿El shader corre y los uniforms llegan? | `poptoCHOP` | canales P/Cd/N; escalonar el uniform y comparar la firma de P antes/después |
| ¿Los valores son sanos? | `poptoCHOP` | `min`/`max` por canal (P ≈ ±radio, Cd en 0..1) |
| ¿El render dibuja? | `renderTOP.numpyArray()` | `(arr[:,:,:3].max(2) > 0.02).sum()` y `mean` de los encendidos |
| ¿Se ve como quiero? | `view_operator` + **PIL** | px encendidos, color medio, bbox, píxel más brillante |

`poptoCHOP` (GPU→CPU) es la **verdad** para datos y animación: sigue los cambios de datos aunque el
render esté cacheado. No existe input connector — se referencia por par: `chk.par.pop = op(...)`.

## Regla 1.5 — verificá de QUÉ son los píxeles (`autotorus_masks_render`)

El peor falso positivo no es "no dibuja": es **"dibuja y creo que es lo mío"**. El `geometryCOMP`
auto-crea un `torus1` (800 pts/800 prims) que el renderTOP dibuja. Una red de partículas con 0
primitivas puede dar `px>500` durante días: son los del torus. Medido: en `/particle_swirl`, apagar
el flag `render` del torus llevó el render de **81572 px a 0**.

**Regla:** un `px>500` sólo cuenta si (a) `geo.children` no tiene `torus*`, y (b) al apagar el flag
`render` del **terminal** el render cae a 0. Si no cae, estás midiendo otro nodo.

## Regla 2 — el render no es un termómetro de datos (`render_cache_vs_data`)

Verificado: el `renderTOP` responde a cambios de **material** (color/look) y a cambios
**estructurales** (rewire, flags, rebind `geometry`), pero **no re-sube geometría POP ante cambios
de datos** (uTime, uSwirl, o incluso el `radx` del emisor). Un renderTOP recién creado tampoco.

Consecuencia práctica:
- **Animación → poptoCHOP.** Píxeles solo para "¿hay algo dibujado?".
- Si necesitás capturar fotogramas distintos, cambiá de estrategia (GUI con play, o aceptar que la
  evidencia visual es un fotograma representativo + la prueba numérica).

## Regla 3 — el reloj puede estar parado (`clock_stopped`)

En sesiones remotas/headless, `absTime.seconds` **no avanza** dentro de un `execute_code`
(0.4–0.8 s de `time.sleep` → mismo valor). `absTime` solo expone `frame`, `seconds`, `step`,
`stepSeconds` (**sin `.play`**), y `op('/')` **no tiene** `play`/`frame`/`rate` en `par`. El reloj
del proyecto es el timeCOMP `/local/` (`root.time`).

Por eso: **verificá la animación escalonando el uniform a mano** (`par.val = 0 / 3`) y midiendo por
poptoCHOP; no dependas de que el tiempo corra. En la GUI con play, la expresion `absTime.seconds`
anima el efecto sin cambios.

## Regla 4 — escribí, releé, y decodificá imágenes con PIL

- **Read-back obligatorio**: `set_parameters` **puede no aplicar un par y responder ok** (visto con
  `pointspriteMAT.attensizenear` y con los `vecNvaluex` del `glslPOP`, que quedaron en 0.5). Tras
  cada write de valor: `assert par.eval() == lo_que_puse` o escribí por `execute_code`.
- **PNG con PIL**: los PNG de `view_operator` son RGBA 8-bit (color type 6), orden RGB. Un decoder
  casero (filtros Sub/Paeth a medio implementar) reportó 728 px "ámbar" donde PIL ve 4398 px
  azul/cian. Formatos: `resolution="small"` → 148×111; `frames=4` → grid **2×2** de 640×360.
- **`Inlineimages`**: `view_operator` devuelve imagen inline solo con `Inlineimages=true` en
  `/TDMCP`; volvelo a `false` al terminar.

## Anti-patrones que generan falsos diagnósticos

1. **"El uniform no está conectado"** → medido sin `settle`. Re-medí con cocción en cadena.
2. **"El render está roto / negro"** → puede ser (a) flags del terminal, (b) binding
   `geometry`/`camera`, (c) caché de geometría, (d) wedged por muchas iteraciones. Reconstruí la red
   y volvé a medir antes de tocar el shader.
3. **"Los puntos no dibujan nunca"** → en realidad: la cadena terminó con **0 primitivas**
   (`convert='deleteprims'` en vez de `'topointprims'`), o material sin `pointspriteMAT`, o medición
   prematura.
4. **"La animación no funciona"** → reloj parado y/o lectura sin asentar. Probá por poptoCHOP.
5. **"El grid temporal prueba movimiento"** → con el reloj parado el grid repite el mismo
   fotograma. Compará las celdas con PIL antes de afirmarlo (`verify_visual.py` lo reporta como INFO,
   no como PASS).
6. **"px>500 ⇒ mi efecto dibuja"** → puede ser el auto-torus. Ver Regla 1.5: apagá el terminal y
   confirmá que cae a 0.
7. **"deleteprims deja una nube que dibuja"** → falso: 0 primitivas = render negro. Lo que dibuja es
   `topointprims` (ver `td-pop-render-pipeline`).

# Cobertura POP en vivo — rayPOP, copyPOP y mathcombinePOP (2026-10-29)

Pase del **ítem 5d** (cobertura POP) ejecutado con el MCP oficial dentro de TouchDesigner.
Cierra la deuda #1 del ítem 10 (`rayPOP`: 0 mediciones), suma `copyPOP` y mide el
**gating de `rayPOP` con `mathcombinePOP`** (atributo 0/1 como selector del `mix`), que era
el pendiente que quedaba de esa deuda.

## Entorno

| qué | valor |
|---|---|
| TouchDesigner | **2025.32460** |
| TDMCP oficial | **1.1.55** (26 tools, `127.0.0.1:13316/mcp`) |
| Proyecto usado para las pruebas | `local/TDMCP.1.toe` (instancia aparte; la TD abierta del usuario tenía el componente sin `Active`) |
| Python host | 3.12 (el de TD es 3.11) |
| Suites offline previas | `server.py --selftest` 21/21 · `test_protocol.py` exit 0 · `td_probe.py` 6/6 · `check_single_home.py` 0 violaciones |

## Comandos

```bash
# los tres builds nuevos, sueltos
PYTHONIOENCODING=utf-8 python tools/gauntlet/build_pop_ray.py
PYTHONIOENCODING=utf-8 python tools/gauntlet/build_pop_copy.py
PYTHONIOENCODING=utf-8 python tools/gauntlet/build_pop_mathcombine.py

# batería completa (35 builds), con un run_id para agrupar la evidencia
GAUNTLET_RUN_ID=reg-20261029-2135 PYTHONIOENCODING=utf-8 python tools/gauntlet/regression_pop.py

# auditar/reacomodar todas las /pop_* (sale 1 si queda un par solapado)
PYTHONIOENCODING=utf-8 python tools/gauntlet/td_layout.py
```

La batería exige TD abierto y el componente **Active**; si el MCP no responde, sale 2
(entorno), no 1. Los `results/<run_id>/` están en `.gitignore`: la evidencia es local y se
regenera con el comando de arriba.

## Resultado global

| corrida | resultado | nota |
|---|---|---|
| `reg-20261029-2035` (primera) | **31/34** | `revolvePOP`, `tubePOP`, `topologyPOP` en rojo por **cascada del rate limiter** (`recovering from a slow operation`), no por regresión |
| builds sueltos de los 3 en rojo | **12/12 · 15/15 · 13/13 PASS** | confirman que era el cooldown |
| `reg-20261029-2040` (final) | **34/34 exit 0, 251.8 s** | con retry del cliente + 1 s entre builds |
| `reg-20261029-2135` (final, + mathcombine + layout) | **35/35 exit 0, 259.2 s** | layout PASS: 114 redes, 0 pares solapados |

Los 35 builds acumulan **473 chequeos** con número. Los tres nuevos:

| build | checks | PNG | contrato |
|---|---|---|---|
| `build_pop_ray.py` (`/pop_ray`) | **24/24** | 2.104 px | C19 |
| `build_pop_copy.py` (`/pop_copy`) | **20/20** | 9.833 px | C19 |
| `build_pop_mathcombine.py` (`/pop_mathcombine`) | **20/20** | 4.680 px | C20 |

## rayPOP — lo medido

Escena: `gridPOP` 3x3 en `z=-1` con `N=+Z` (input 0) contra `boxPOP` 1x1x1 centrado
(input 1) → 9 pts / 4 prims.

| caso | resultado |
|---|---|
| toggles de salida apagados | `P` **ya** está en el impacto (`z=-0.5`) y `N` en la normal (`-Z`); no hay atributos `Ray*` |
| `dist` | `RayDistance = 0.5` en los 9 rayos |
| `numhits` | `[3,2,3,2,4,2,3,2,3]` (caras trianguladas; el rayo central pasa por la diagonal) |
| `hitprimindex` | `RayPrimIndex = 0` (cara frontal) |
| `inside` | `RayInside = [1,0,1,0,0,0,1,0,1]` con los 9 orígenes **fuera** de la caja — quirk de bordes |
| `hitnormal` | **no crea `RayHitNormal`**; `N` se reescribe siempre (corrige C18) |
| `barycoords` | no agrega ningún atributo de punto visible |
| miss (grilla 3x3 de tamaño 3) | `P` queda en el origen; `RayDistance=1e8`; `RayPrimIndex=4294967296`; `RayNumHits=0` |
| `limitraylength` + `scale=0.6` | `P` a `0.6*0.5 = 0.3` del origen (`z=-0.7`), pero `RayDistance=0.5` y `RayNumHits=4` del impacto real |
| `lift=0.1` | `P` de `-0.5` a `-0.4`: se mueve **contra** la normal outward |
| `negateray` | sin impactos (`P=-1`, `N=+Z`, `RayNumHits=0`, centinelas) |
| `bypass` | passthrough exacto, sin `Ray*` |
| `hwraytracing=fastbuild` / `fasttrace` | mismo conteo; **sólo el primer hit** (`RayNumHits=1`), miss con centinelas; ambos modos idénticos acá |
| `numbounces=2` sin N | error explícito (`collision geometry doesn't have normals`) y salida intacta |
| `numbounces=2` con `spherePOP.normal='pointNormals'` | **27 pts / 9 prims** (3 puntos/rayo, 1 prim/rayo), sin error |
| `rayattrib` | menú **dinámico** `[P,N,Tex,Tex.i01]`, no un set fijo |

Gotcha transversal: `spherePOP.normal` y `normalPOP.nml` son **menús**, no toggles
(`none/pointNormals/vertNormals` y `noaction/alwayscompute/computeifnone/remove`). Pasar
`True` no genera `N` y el error recién aparece en `rayPOP`.

## copyPOP — lo medido

Input 0 = `boxPOP` 8 pts / 6 quads; input 1 = `gridPOP` 3x3 (9 pts).

| caso | resultado |
|---|---|
| sin template, `ncy=1/2/3` | 8/6 · 16/12 · 24/18 (copias superpuestas, mismo `P`) |
| con template, `ncy=1/2` | 72/54 · 144/108 (`fuente * template * ncy`) |
| `dotemplatetranslate` OFF (default) | copias apiladas, `P` en `[-0.5,0.5]` |
| `dotemplatetranslate` ON | `P = fuente + template`: x/y en `[-1,1]`, z en `[-0.5,0.5]`; primera copia `P_0=[-1,0,0,-1,...]` |
| `copyid='point'` (ncy=2) | `CopyId` en `pointAttributes` |
| `copyid='primitive'` / `'vertex'` | `CopyId` en `primAttributes` / `vertAttributes` |
| `ncy=1` | **no** emite `CopyId` en ningún scope, aunque el template genere 9 copias |
| `bypass` | fuente intacta (8/6) |
| `tx=1`, `sx=2`, `scale=2` | **no cambian `P`** en la configuración probada: usar los puntos template para ubicar copias |

## mathcombinePOP — lo medido

Escena: `gridPOP` 3x3 de tamaño 3 en `z=-1` (input 0 de `rayPOP`) contra `boxPOP` 1x1
(input 1), con `numhits=True`. La salida de `rayPOP` alimenta `mathcombinePOP`; una
segunda rama usa `mathmixPOP` como control y otra un `mathcombine` aparte para el lerp.

| caso | resultado |
|---|---|
| `RayNumHits` | `[0,0,0,0,4,0,0,0,0]`: sólo el rayo central impacta |
| `gt` con `thresh0=0` | `Hit = [0,0,0,0,1,0,0,0,0]` |
| `gt` ESTRICTO con umbral 4 | `HitAt4 = [0×9]`: `4 > 4` es falso |
| `gt` ESTRICTO con umbral 3 | `HitAt3 = [0,0,0,0,1,0,0,0,0]`: `4 > 3` es verdadero |
| `mix` A=0.2, B=0.9, C=`Hit` | `Gate = [0.2 ×4, 0.9, 0.2 ×4]` |
| `mix` con C=0.5 constante | `0.55` en los 9 puntos: `A*(1-C)+B*C`, no un clamp 0/1 |
| 4 bloques encadenados | `Hit` -> `Gate` -> `HitAt4` -> `HitAt3`; los bloques leen resultados previos |
| página `attr` default | **1 bloque vacío** (`attr0customname=''`); `comb*result` auto-crea `Hit`/`Gate`/`HitAt4`/`HitAt3` |
| `mathmixPOP` control (3 bloques) | `HitM` = `Hit`, `GateM` = `Gate`, `GateMPlusLo = GateM + 0.2` (`0.4` / `1.1`) |
| `mathmixPOP` estructura | soporta `comb1`/`comb2` y **no tiene página `attr`** |
| segunda entrada de `mathcombine` | `in1_Tex` da `Input attribute 'in1_Tex' not found`; con `input1attrs='*'` compila usando `Tex` sin prefijo (no se usó en el build; ver límites) |

El patrón de gating queda cerrado: `gt` sobre `RayNumHits` produce el 0/1 y ese atributo
entra como `C` del `mix`. `mathcombinePOP` es el que aporta la página `attr` y el encadenado
de 4 bloques; `mathmixPOP` sirve para el mismo cálculo con 3 bloques y sin página `attr`.

## Layout de las redes

El build deja todos los nodos separados. `td_layout.tidy` los ordena por **profundidad de
conexiones** (fuentes a la izquierda, consumidores a la derecha), cuenta también el
`par.pop` de los `poptoCHOP` y verifica que no quede ningún par solapado. La batería cierra
con `td_layout.py`, que recorre las `/pop_*` y sus COMP anidados; si queda un par encimado,
la batería sale 1.

- `build_pop_mathcombine.py` agrega el check **“red sin nodos solapados”** (base + geo).
- `reg-20261029-2135`: **114 redes, 0 pares solapados**.
- Antes del fix, todos los hijos de `geo` estaban en `(0,0)` (10 nodos encimados) y el
  `cam` tapaba al `geo` por 5 px; el layout se aplicó a las 114 redes existentes.
- Mover nodos no cambia parámetros ni conexiones: es sólo presentación del network.

## Hallazgo de harness

La primera batería dio 31/34: el rate limiter del componente responde
`TouchDesigner is recovering from a slow operation. Wait 0.9s, then retry this exact call`
y el build siguiente arranca con el cooldown encima (falla `create_operator`/`set_parameters`).
No era regresión: los tres builds pasan solos.

Fix, en dos piezas:

1. `tools/gauntlet/gauntlet_client.py::Gauntlet.call()` reintenta hasta 3 veces cuando el
   texto trae `recovering from a slow operation` (espera 1.5 s). Es el reintento que pide
   C14/`td_slow_operation`.
2. `tools/gauntlet/regression_pop.py` deja **1 s** entre builds.

Con eso: **34/34, 251.8 s** en la corrida base de 34 builds y **35/35, 259.2 s** con
`build_pop_mathcombine.py` y el audit de layout sumados (`reg-20261029-2135`). Un rojo de
batería con ese mensaje se reintenta antes de declarar regresión.

## Límites

- La medición es de **un** build de TD (2025.32460) y un `.tox` (1.1.55). `RayInside`,
  `barycoords` y los pars de transform de `copyPOP` pueden cambiar entre builds; los tests
  numéricos existen justamente para detectarlo.
- `barycoords=True` se reporta como quirk (no hay atributo visible), no como contrato de
  nombre: no se pudo determinar si el dato va a otro scope o no se implementa.
- El MCP se levantó en una **instancia aparte** de TD (`local/TDMCP.1.toe`) porque la
  instancia abierta del usuario no tenía el servidor escuchando; los sandboxes `/pop_*` de
  las pruebas viven en esa instancia y no se guardaron.
- La segunda entrada de `mathcombinePOP` **no** expone `in1_<attr>` en esta configuración:
  `input1attrs` debe seleccionar los atributos y el nombre visible es `Tex` (sin prefijo),
  no `in1_Tex`. El probe no distinguió input0 de input1 porque ambas grillas tenían el
  mismo `Tex`; no se usa en el build. Queda como gotcha de nombre, no como semántica
  verificada.
- `mathmixPOP` se usa como control del gating, no como cobertura completa del operador.
- `build_monitor_pop.py` tiene un check de calibración estocástico: en `reg-20261029-2125`
  falló por `|0.1222 - 0.0908| = 0.0314` contra un umbral de `0.03`; solo pasa 7/7. No es
  regresión de layout: reintentar antes de declarar rojo.

## Archivos

- `tools/gauntlet/build_pop_ray.py`, `tools/gauntlet/build_pop_copy.py`,
  `tools/gauntlet/build_pop_mathcombine.py`, `tools/gauntlet/td_layout.py` (nuevos).
- `tools/gauntlet/regression_pop.py` (35 builds + pausa de 1 s + audit de layout).
- `tools/gauntlet/gauntlet_client.py` (retry C14).
- `knowledge/contracts/VERIFIED_CONTRACTS.md` (C19, C20 + corrección de C18).
- `docs/BACKLOG.md` (filas en *Estado verificado* + 5d + ítem 10).
- `README.md` (sección de pruebas POP).

---
name: td-pop-neighbors-and-rays
description: "Use when un sistema POP tiene que interactuar con geometría o con sus propios vecinos: flocking (neighborPOP), colisiones/superficies (rayPOP), plexus (proximity), campos (forceradialPOP/fieldPOP)."
---

# POPs que interactúan: vecinos, campos y rayos

Complementa `td-pop-particle-systems` (el lazo y las fuerzas) con los operadores que **consultan
geometría**: `neighborPOP` (vecindad entre puntos), `proximityPOP`/`skinPOP` (líneas),
`forceradialPOP`/`fieldPOP` (campos de fuerza/atracción) y **`rayPOP`** (raycast contra geometría).

> **Provenance.** **[T]** = 4 tutoriales de la comunidad transcritos el 2026-10-07 en
> `knowledge/kb/tutorials/pop_2026/` (**local, no versionado**); **sin verificar en vivo por
> nosotros**. **[V]** = contrato con corrida propia (`contracts/VERIFIED_CONTRACTS.md`).
> `rayPOP` y la receta de flocking **no han sido medidos nunca** en este repo: son candidatos
> naturales del ítem 5d (cobertura POP) — hasta entonces, tratalos como hipótesis de trabajo.

---

## 1. `forceradialPOP` — campos radiales, axiales y espirales

Es el reemplazo POP del viejo `forceSOP` **[T]**. No es un operador de partículas: **escribe una
fuerza** y por eso su lugar natural es **dentro del lazo `targetpop`** de un `particlePOP`.

Parámetros (nombres reales, `pops/pop_matrix.json`): `radial` (ON por default), `radialstrength`,
`planar`/`planarexponent`/`planarstrength`, `axial`/`axialrx/ry/rz`/`axialstrength`,
**`spiral`**/`spiralrx/ry/rz`/`spiralstrength`, `falloff` (menú), `falloffradius` (default **2**),
`falloffplateau`, `falloffsteepness`, `falloffbias`, `falloffexponent`, `fallofflimitrange`,
`posx/y/z`, `directionx/y/z`, `globforcex/y/z` + `globforcemult`,
`windspeedx/y/z` + `windspeedmult`, `specpop`, `map*`.

Pitfalls:

- **[T] `direction=000` ⇒ la espiral no hace nada.** Seteá p.ej. `directionz=1`. Es el error que más
  gente reporta con el modo spiral.
- **[T]** `radialstrength` **positiva empuja hacia afuera**, **negativa atrae**. `falloffradius`
  demasiado grande (default 2) concentra todo en el centro: bajalo.
- **[V] `globforcemult` (y `windspeedmult`) default a 0**: `globforce*`/`windspeed*` no hacen nada
  hasta setear el multiplicador (p.ej. gravedad: `globforcey=-6`, `globforcemult=1`).
- **[T]** `falloff` default es **S-curve**; `inverse distance` pega más fuerte cerca del centro
  (bajá el valor central si usás esa). `falloffradius` **no puede quedar ≤ 0**: si lo manejás con un
  ruido, dejá `offset > amplitud`.
- **[T]** `plateau` y `steepness` se ven mucho más claros **sin** `particlePOP` (puntos estáticos).

### 1.1 `force`, `specpop` y control por punto
- **[T `specpop`]** Conectá un POP con **N puntos**: cada punto **instancia** una fuerza propia.
  Sirve para tener varias fuerzas simultáneas (o multi-centro) sin duplicar operadores.
- **[T]** Los **atributos del spec pop pisan los parámetros**: `falloffradius` y `spiralstrength`
  (esos nombres exactos) y `P` (pisa `posx/y/z`). Los nombres autoritativos de cada atributo están
  en la **help page** del operador — copialos de ahí, no los adivines.
- **[T]** Un atributo de un solo float se alimenta con un `noisePOP` **con `noisesize=1`** +
  `output combined attribute scope = none`; si mandás los tres componentes, el operador tira error
  pidiendo un único valor.

### 1.2 Usar `forceradialPOP` **sin** `particlePOP` (integración a mano)
El operador asume el ecosistema de `particlePOP`; **[T]** fuera de él hay que integrar a mano, porque
`mathmixPOP` **no** va a aplicar sola la fuerza al punto (no existe un atributo `Force` que ya esté
afectando `P`):

```text
points ─────────────────────────────────> mathmixPOP 'integrate' ──> nullPOP 'P_end' ──┐
                                            │                                          │
forceradialPOP ──(atributo Force)───────────┘   (feedback)                              │
  1) bloque A*B : Force * 0.01      → resultado `PF`          (escalar la fuerza)
  2) bloque A+B : PF + P            → resultado `P`           (mover el punto)
```

**[V]** recordá que las secuencias `comb`/`vec` de `mathmixPOP` **arrancan vacías**:
`n.par.comb.sequence.numBlocks = 2` y después `comb0oper`, y los scopes en una segunda pasada.
**[T]** Para **localizar** el campo, multiplicá `PF` por el `weight` de un `fieldPOP` aguas arriba.
**[T]** Para un efecto de *deslizamiento* en vez de empuje directo: `feedbackPOP` + `blendPOP`
(`blend type = differencing`, point attribute scope `P`) — sólo un poco de la señal del frame
anterior, con un slider que va de "todo feedback" a "todo nuevo".

---

## 2. `neighborPOP` — vecindad y flocking

Entrega, por punto, información de sus vecinos por distancia. Params reales: `nebrtype`,
`maxdistance`, `maxneighbors`, `distribution`, `numhashbuckets`, `outputhash`, `nebroutput`,
`nebrs`, `nebrattrname`, `numnebrs`, `numnbrsattrname`, `dodist`, `distattrname`, `maxnebrsavg`,
`incquerypt`, **`addprefix`**, `castintstofloats`, `nebrptattrs`.

Pitfalls:
- **[V] `nebroutput='avg'` no promedia nada sin `nebrptattrs='P'`** (default `''` → P crudo); en modo
  `avg` también promedia `NumNebrs`. Los arrays por vecino llegan como `Nebr_0_`, `NebrP_0_`,
  `Dist_0_` (doble underscore final). Ver `neighborpop_arrays_y_avg` en los contratos.
- **[T]** Como el promedio de posición de los vecinos escribe sobre un atributo, **puede pisar `P`**
  del propio punto. Usá **`addprefix`** (o renombrá) para que la salida no colisione con `P` — el
  síntoma es "el promedio de vecinos me movió todos los puntos a otro lado".
- **[T]** `maxneighbors` es un **tope de muestreo**: si la densidad lo supera, el promedio es sesgado
  y aparecen ráfagas/inestabilidad. Ver el presupuesto en `td-pop-particle-systems` §3.

### 2.1 Receta de flocking (boids, nodos — sin GLSL) **[T]**
```text
pointgeneratorPOP → randomPOP (randomiza N) → neighborPOP → mathPOP (rename) → mathcombinePOP → feedback
```
- **Dos o tres radios**, no uno: atracción ≈ **0.5** (cohesión), alineación ≈ **0.3**, repulsión ≈
  **0.25** (separación). Los rangos en conflicto en un solo operador no dan boids.
- Fuerzas de steering del ejemplo: atracción **0.01** por ciclo, paso **0.02** a lo largo de la
  normal, fuerza de centrado **0.03**.
- **Alineación = el DELTA** entre tu normal actual y la normal objetivo; el error típico es usar la
  normal objetivo directa y obtener un snap en vez de un viraje.
- `randomPOP` puede randomizar **N** (no sólo `P`): necesario para que no todos los boids tengan la
  misma dirección inicial.
- Para el caso "muchas partículas" (50k–200k), reemplazá `neighborPOP` por la **rejilla de sondas**
  descrita en `td-pop-particle-systems` §3.

---

## 3. `proximityPOP` / `skinPOP` — líneas entre puntos

- **[T]** Plexus: `particlePOP → proximityPOP → geometryCOMP(wireframe/lineMAT)`. El ejemplo usó
  **`maxneighbors=3`** y "una línea por punto".
- **[T]** Las líneas **no se ven** por sí solas: necesitan una geometría separada con material de
  líneas (el tutorial prefiere **wireframe** a `lineMAT` por control del grosor) — y en `proximityPOP`
  hay un mínimo/máximo de distancia por debajo/arriba del cual no dibuja.
- **[T]** Sobre decenas de miles de puntos, **primero `deletePOP` en modo *thin* aleatorio** sobre una
  red de referencia chica y conectá la proximidad a esa muestra (§3 de particle-systems).
- **[T]** `skinPOP` hace algo parecido (necesita un **grupo de primitivas**); el autor no domina su
  semántica — **no lo uses como sustituto confiable** de `proximityPOP` sin medirlo.

---

## 4. `rayPOP` — colisiones y muestreo de superficie (*no medido todavía*)

Es el operador de raycast de la familia: emite rayos **desde los puntos** contra geometría y devuelve
dónde/contra qué pegaron. **[T]** es la pieza que convierte POPs en algo interactivo con la escena.

**Contrato de inputs (crítico):** **[T]** `rayPOP` tiene **2 inputs**: input0 = los puntos (tus
partículas), input1 = **la geometría de colisión**. Sin el segundo: error `not enough inputs`.
Activá **`fastbuild`** o es lento.

**Salidas (se declaran y se nombran en el operador):** `hitnormal` (+`hitnormalname`),
`doreflectedray` (+`reflectedrayname`), `dist` (+`distname`), `numhits` (+`numhitsname`), `inside`
(+`insidename`), `hitprimindex` (+`hitprimindexname`), `barycoords` (+`barycoordsname`), además de
`limitraylength`/`raydistancemaxattr`, `trimray`/`trimdistanceattr`, `numbounces`, `connectpoints`,
`hwraytracing`, `opaque`, `anyhit`, `farhit`, `negateray`, `scale`, `lift`,
`hitpointattrscope`/`hitprimattrscope`/`hitvertattrscope`, `delinputattrs`.

El nombre de cada atributo de salida **es lo que vas a escribir en los scopes aguas abajo** —
nombrarlos prolijo (p.ej. `rayhitnormal`, `distance`) ahorra depurar.

### 4.1 Dos idiomas de colisión

**A) Mapear la normal de impacto a un parámetro.** El `map` del `noisePOP` (o de otro POP) acepta un
atributo de entrada como modulador: **`map0op` → `map0element` = tu atributo `rayhitnormal` →
`map0parm` = el parámetro a afectar (p.ej. `amp`)** **[T]**. Las partículas se deforman al tocar y
"explotan" en la superficie. *(El tutorial no explica por qué con este enfoque las partículas parecen
nacer en el punto de impacto al resetear: **sin resolver**.)*

**B) Rebote por velocidad reflejada (gating con `mathcombinePOP`).** **[T]**
```text
reflected = reflectedray * length(PartVel)      # misma rapidez, nueva dirección
damped    = reflected * 0.8                      # amortiguar
close     = (distance < umbral)                  # bloque 'smaller than' → atributo 0/1
PartVel   = mix(PartVel, damped, close)          # mathcombinePOP, scope C = close
```
Este es el patrón reusable: **`mathcombinePOP` + un atributo 0/1 como selector del `mix`** permite
gatear cualquier fuerza por una condición geométrica sin escribir GLSL.

### 4.2 Extras del ejemplo
- **[T] `negateray=ON`** invierte el sentido del rayo → las partículas son "aspiradas" hacia el objeto.
- **[T]** Piso rápido sin geometría: `limitPOP` con clamp en Y.
- **[T]** Estelas de choque: `trailPOP` con `attrmatch=True` + `attrname='PartId'` y las líneas
  activadas, para que no se conecten partículas distintas (mismo contrato **C10**/`PartId` que ya
  documentamos).

---

## 5. `lookupattributePOP` como función de transferencia (fase por punto)

**`lookupattributePOP` es el `lookupCHOP` de los POPs**: input0 = puntos, input1 = la **curva**
(`curvePOP`) que define la transferencia (X = coordenada de entrada, Y = salida). **[T]**

- Por defecto muestrea la **posición X** del punto. Con **`lookupattr`** muestreás **cualquier
  atributo** — es lo que permite usar una **fase por punto** en vez de la posición.
- **Curva S** = movimiento tipo "ascensor": acelera, se mantiene, desacelera. La **alpha de la
  `curvePOP`** controla cuánto se aplana (`[T]`: sube la meseta y suaviza la aceleración).
- **Fase única por punto** (para que no caigan/entren todos a la vez) **[T]**:
  ```text
  rampTOP (ancho en píxeles = cantidad de puntos, animado con absTime.seconds)
      └─ toptoPOP (canal R → atributo custom `val`)
            └─ attributecombinePOP (val del input0 + P del input1 — ojo el ORDEN)
                  └─ lookupattributePOP (lookupattr = 'val')
  ```
- **`mergePOP` de dos curvas** (la segunda corrida +1 en valor) da el ciclo
  "entra, se queda, se va". **[T]**
- **`randomPOP`**: un atributo escalar necesita **size 1** (si no, un `scale` float3 randomiza X/Y/Z
  por separado y las copias salen ovaladas); también puede **agregar N puntos por punto** de entrada.
- Recordá la regla de casing (**[V]**): `lookupattributePOP` **en minúsculas exactas**; camelCase
  (`lookupAttributePOP`) lo rechaza `create_operator`.

---

## 6. Verificación pendiente
`rayPOP`, la receta de flocking y el camino standalone de `forceradialPOP` son las tres piezas con
más valor sin medir. Patrón del repo: build versionado en `tools/gauntlet/` + checks con número +
fila en *Estado verificado* + contrato si hay sorpresa (ver ítem 5d del `docs/BACKLOG.md`).

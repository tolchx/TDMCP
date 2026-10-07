---
name: td-pop-particle-systems
description: "Use when diseñás un sistema de partículas POP o elegís entre feedback, particlePOP y GLSL. Ciclo de vida, bucle targetpop, fuerzas, atractores y presupuesto GPU."
---

# Sistemas de partículas POP — arquitectura y fuerzas

Cierra el hueco entre `td-pop-family` (mapa general) y `td-pop-trails-fields` (estelas/campos 4D)
para la **decisión de arquitectura** y la **integración de fuerzas** dentro de una simulación POP.

> **Provenance.** Lo marcado **[T]** sale de 4 tutoriales de la comunidad transcritos el 2026-10-07
> en `knowledge/kb/tutorials/pop_2026/` (carpeta **local, no versionada**): particle POP, instalaciones
> con POPs, elección de arquitectura y atractores. **No está verificado en vivo por nosotros.** Lo
> marcado **[V]** ya tiene corrida propia (`docs/BACKLOG.md` → *Estado verificado*,
> `contracts/VERIFIED_CONTRACTS.md`). Si un **[T]** choca con un **[V]**, gana el **[V]** y el choque
> queda anotado abajo (§6) para medirlo.

---

## 1. La decisión primero: ¿qué mecanismo de simulación?

El error caro es elegir `particlePOP` "porque suena a partículas" cuando el efecto pedido no necesita
ciclo de vida. Matriz (fuente **[T]**, video de arquitectura):

| Necesitás | Mecanismo | Qué ganás | Qué perdés |
|---|---|---|---|
| Un lazo de actualización, sin nacimiento/muerte | **`feedbackPOP`** puro | Los puntos nacen una vez y viven para siempre; los operadores del lazo hacen todo el trabajo. Es el patrón más simple y el más barato | No hay edad, ni muerte, ni nacimiento selectivo |
| Nacimiento/muerte **y** control directo de P/V | **`particlePOP` con `timeintegration=OFF`** | Controlás posición y velocidad a mano; nacés partículas por audio/espectro y las matás por textura o mouse | Sin integración física: la gravedad/arrastre/drag no existen para vos |
| Física (masa, drag, fuerza acumulada) | **`particlePOP` con `timeintegration=ON`** | `PartForce` se resetea a 0 por frame, vos escribís fuerza, TD integra v+dt y P+v·dt | **No podés setear velocidad directo** (corrompe la integración); hay que reformular el algoritmo en términos de fuerza; la masa pasa a importar |
| El mismo algoritmo, más corto y legible | nodos (`mathcombinePOP`) o **`glslPOP`** | **[T]** mismo resultado; el GLSL es más corto y con comentarios | El GLSL necesita compilar y depurar |

**Truco reverse** que menciona el tutorial: con `timeintegration=ON` podés recuperar una velocidad
objetivo calculando `force = (targetVel − vel)/dt`. **[T] No lo recomiendan**: rompe el modelo y la
masa deja de tener sentido. Si necesitás eso, probablemente querés `timeintegration=OFF`.

---

## 2. `particlePOP`: el bucle `targetpop` es la arquitectura

A diferencia de `particleSOP` (donde se agregaban fuerzas a la **entrada**), `particlePOP` crea un
**bucle de feedback propio**: el parámetro `targetpop` ("Target Particles Update POP") marca el
**punto final** del lazo, y todo lo que pongas **entre** `particlePOP` y ese target altera el
comportamiento frame a frame. **[T]** El parámetro es **obligatorio de cerrar**: sin target, no hay
integración. **[V]** (`particle_integration_needs_feedback`) — las dos fuentes coinciden.

```text
pointgeneratorPOP ──> particlePOP ──┬─> mathmixPOP (fuerza constante) ──┐
                                    ├─> noisePOP    (perturba PartVel) ─┤
                                    └─> transformPOP (atrae al centro) ─┼─> nullPOP 'target' ──┐
                                                                        │                      │
                                                                        └── targetpop ─────────┘
                        (post-proceso, FUERA del lazo: color, trail, render)
```

Reglas del lazo:
- Poné **fuerzas y transformaciones adentro**; poné **color/estelas/render afuera** (fuera del lazo
  se recalcula una vez por frame sobre el buffer ya integrado). **[T]**
- Los cambios de parámetro **dentro** del lazo se componen en el tiempo (igual que el feedback de
  TOPs): un `scale=0.96` por frame atrae al centro de forma acumulativa. **[T]** Efectos dramáticos
  sin querer = revisar qué quedó adentro.
- **Error clásico:** `target has to have the same number of particles as the particle pop`. Aparece
  al bypassear un op del lazo (el conteo deja de coincidir). **[T]** El tutorial lo limpia
  reseteando el sistema; en build por código, evitá bypasses a mitad de lazo.

### Atributos que `particlePOP` crea solo **[T]** (confirmables con `poptoDAT`/`poptoCHOP`)

| Atributo | Para qué |
|---|---|
| `P` | posición |
| `Age` | tiempo de vida transcurrido (sube hasta `Life`) |
| `Life` / `Lifespan` | máximo de vida **por partícula** (con `lifevariance` no es constante) |
| `Force` | fuerza del frame — **se resetea a 0 cada frame**; acá escribís |
| `ID` | id único; por defecto se **reusa en loop** (`pointidreuse`) |
| `Velocity` | velocidad (`PartVel`) |

`Age`/`Life` juntos dan la **edad normalizada** `Age/Life` ∈ [0,1] — la llave para colorear por vida
(§4.3) y para matar partículas a voluntad.

Parámetros que importan: `maxparticles` (tope limpio del buffer, **[T]** "mucho más cómodo que en
`particleSOP`"), `birthrate`, `life`, `lifevariance`, `initvelocityx/y/z`, `randomseed`,
`pointidreuse`, `attrs` (pasa atributos de la entrada a las partículas), `timeintegration`.

---

## 3. Presupuesto y costos (decidir antes de escalar)

- **[T]** `neighborPOP` para sensar por partícula es **preciso pero caro**: el costo crece con
  `n × maxneighbors`, y `maxneighbors` **topa el muestreo** → promedios sesgados → saltos, ráfagas y
  patrones inestables cuando la densidad sube. Regla práctica del tutorial: cómodo hasta ~5k
  partículas; y **la densidad máxima tiene que quedar por debajo de `maxneighbors`**.
- **[T]** Para 50k–200k partículas el camino no es más vecinos sino **rejilla de sondas**: una grilla
  fija de puntos (que también son POPs) pasa como segundo input de `neighborPOP`, y cada sonda
  acumula *densidad*, *velocidad media* y una *madurez* (memoria persistente que crece con flujo
  consistente y se desvanece si no). Se convierte a 3D con `toptoPOP` y se muestrea desde cualquier
  lado. Ahí el cuello de botella pasa a ser el **render**, no la simulación.
- **[T]** `trailPOP` sobre *todas* las partículas es carísimo ("tu computadora se va a morir"):
  usalo corto (0.3–0.5 s, o 12–16 frames) o solo sobre un subconjunto.
- **[T]** Para `proximityPOP`/`skinPOP` sobre decenas de miles de puntos, pasá **primero** por un
  `deletePOP` en modo *thin* aleatorio (una red de referencia con pocos puntos) y conectá la
  proximidad a esa muestra — si no, generás líneas entre todos los puntos.
- **[T]** Geometría interna barata: primitivas de **punto** y pocas filas/columnas; subí densidad con
  `freq`, no con polígonos. Sombras: demandantes, apagalas si no suman.

---

## 4. Recetas

### 4.1 Fuerza constante (con `timeintegration=ON`)
`mathmixPOP` con `comb0oper='a+b'`, scope A = `Force`, scope B = literal vector
**`"0 0.01 0"`** (tres números separados por espacio = vector, atajo del build **[T]**), resultado →
`Force`. **[V]** antes de tocar `comb*`, creá el bloque: `n.par.comb.sequence.numBlocks = 2`
(las secuencias arrancan vacías) y seteá primero `comb0oper`, después los scopes.

### 4.2 Ruido sobre velocidad
`noisePOP` dentro del lazo: **lookup = `P`**, y `comb` = suma con output scope `PartVel` **[T]**.
Animar con `absTime.seconds` en la página Transform para que el ruido no quede estático.
Alternativa: `transformPOP` con `scale≈0.96` para no perder las partículas fuera de cámara.

### 4.3 Color por edad
`mathmixPOP` → `normage = Age/Life` (0..1) → **`lookuptexturePOP`** con un `rampTOP` y
`lookupattr='normage'` como U → `outputattrscope='Color'`. Rampa transparente en ambos extremos =
fade in/out limpio al nacer y morir. **[T]** **[V]** `lookuptexturePOP` **no escribe el atributo sin
`overrideautoattr`** y muestrea el texel exacto con `interpolate=off`.

### 4.4 Morir por contacto ("bounded box")
**[T]** `groupPOP` con un **bounding box** (p.ej. `scale=2`, `invert=ON` ⇒ el grupo es "adentro") →
`mathmixPOP` operando **solo sobre ese grupo** con `Age = Life` ⇒ la partícula muere y renace donde
nace. Es el mismo idioma que el "borrado radial" (restar el centro, `length`, `delete` por umbral).

### 4.5 Atractores
Tres arquitecturas vistas **[T]**: (a) lazo a mano con `mathmixPOP` (atractor tipo "four-wing");
(b) **componente `.tox` con GLSL** que encapsula las ecuaciones — se enchufa y listo, pero **es
código de terceros**: nuestro criterio es reimplementar con `mathmixPOP`/`glslPOP` propio y
documentar; (c) esfera-dentro-de-esfera por `copyPOP` con dos ramas (proximidad/skin + estelas).
Con `fieldPOP`/`forceradialPOP` el atractor es un **campo**, no una ecuación: ver
`td-pop-neighbors-and-rays`.

### 4.6 `copyPOP` con plantillas de atributos (para instanciar geometría sobre partículas)
**[T]** El `copyPOP` **procesa** los atributos: para que un atributo llegue a la geometría copiada hay
que **declararlo en la página de templates**, con el **nombre exacto** que tiene en la cadena.
- `rotation`: hay que declararlo `float3` (**random size 3**) y con rango **0..360**; con un rango
  0..1 no rota.
- `scale`: declaralo **de 1 componente** o las copias salen ovaladas (un float3 randomiza X/Y/Z por
  separado).
- Los nombres built-in (`color`, `size`, `rotation`) los entiende solo; los custom necesitan la
  declaración con el mismo nombre.
- Si el atributo nace aguas arriba de un lazo de feedback, **actualizá el lazo** para que atraviese
  (el tutorial lo ve como "Rotate attribute not found" hasta refrescar).

---

## 5. Trucos de cámara y render que ahorran tiempo

- **[T]** `camera.lookat` → un `nullSOP`: el `nullSOP` es el punto (0,0,0) del espacio, así que la
  cámara siempre mira al centro de la geometría.
- **[T]** Cámara por camino: `lineSOP`/`circleSOP` como *path* de la cámara + `lookat` al null; se
  automatiza con un `lfoCHOP` sobre la posición a lo largo del camino. Evitá los extremos del rango
  (las últimas posiciones dan saltos).
- **[T]** Cámara **dentro** de la simulación: dejá una red duplicada con **un solo punto**, extraé su
  posición con `poptoCHOP` y manejá `tx/ty/tz` de la cámara con esos canales.
- **[T]** Para líneas, el tutorial prefiere material **wireframe** a `lineMAT` (más control del
  grosor). Nuestro `td-pop-render-pipeline` cubre el camino verificado con `pointspriteMAT`.

---

## 6. Choques abiertos entre tutorial y contrato (medir en vivo)

| Tema | Tutorial **[T]** | Nuestro contrato **[V]** | Estado |
|---|---|---|---|
| Reset de la simulación | Resetear/`initialize` el timer (tecla 1 en la UI) para limpiar el error de conteo | `particle_initialize_enferma`: **NO** usar `initializepulse`/`preroll` en builds MCP — el buffer se infla; el reciclado lo hace `life` | **Abierto.** Probable reconciliación: la tecla 1 es un reset de **UI/tiempo**; `initializepulse`+`preroll` por API es lo que enferma el buffer. Verificar con una sonda antes de adoptar el reset del tutorial en código |
| `timeintegration` | Se usa ON para física | `particlePOP` no se mueve sin `timeintegration=ON` | Coinciden ✔ |
| Cerrar el lazo | Obligatorio (`targetpop`) | `particle_integration_needs_feedback` | Coinciden ✔ |

## 7. Verificación
Todo **[T]** de este skill se midió solo contra transcripts (citas en
`knowledge/kb/tutorials/pop_2026/_extract_*.json`, verificadas con `tools/verify_tutorial_extracts.py`).
Antes de convertirlo en contrato: armá el build en el sandbox y corré los checks numéricos de
`td-live-verification`; recién entonces la fila va a *Estado verificado*.

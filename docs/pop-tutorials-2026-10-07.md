# POPs — tutoriales de YouTube 2026: transcripción, destilado y skills nuevas

**Fecha:** 2026-10-07 · **Autor:** sesión interactiva (Hermes) · **Estado:** commiteado, sin
verificación en vivo (ver §5).

Cierra el pedido "aumentar el conocimiento del repo usando transcripciones de tutoriales de POPs".
El material previo del repo sobre tutoriales eran dos fuentes: la playlist *GLSL for POPs*
(`knowledge/kb/tutorials/pop_tutorial/`, 6 videos GLSL) y una síntesis de la serie de una escuela
(`pop-interactive-hq.md`). Ninguna cubría **operadores de interacción** ni **arquitectura de
simulación**. Este pase agrega 10 tutoriales de sistemas POP y destila lo que faltaba en skills
versionadas.

---

## 1. Qué se hizo

1. **Relevamiento.** Se barrió YouTube (playlists oficialmente recomendadas por Derivative, canales
   de POPs activos en 2025-2026) con `yt-dlp`, y se eligieron 10 videos por **cobertura de operador
   y de arquitectura**, no por popularidad. Criterio explícito: evitar lo ya documentado (GLSL copy/
   advanced, estelas, snippets oficiales) y priorizar lo que **nunca se midió**.
2. **Transcripción.** 10/10 videos, 46.033 palabras, 5h01m de material. Metadata con
   `yt-dlp --skip-download --print`; captions con `youtube-transcript-api` (el camino
   `yt-dlp --write-auto-subs` devuelve **HTTP 429** en esta red). Formato del repo: bloques con
   timestamp cada ~30 s.
3. **Extracción.** 5 subagentes en paralelo, cada uno con la consigna de emitir **JSON estructurado
   con cita textual + timestamp por afirmación** (operadores, parámetros, atributos, GLSL, patrones,
   gotchas, correcciones). Sin cita, la afirmación se descarta.
4. **Verificación de las citas.** `tools/verify_tutorial_extracts.py` comprueba que cada cita exista
   literalmente en su transcript: **81/85 citas verificadas (95%)**. Las 4 que no matchean fueron
   parafraseos de los subagentes y **se descartaron del destilado**.
5. **Destilado a skills.** El conocimiento accionable quedó en **2 skills nuevas**
   (ver §3), con la provenance separada explícitamente: **[T]** = tutorial (no verificado en vivo),
   **[V]** = contrato propio con corrida.

Los transcripts crudos y los JSON de extracción viven en `knowledge/kb/tutorials/pop_2026/`
(**carpeta local**: `knowledge/kb/` está gitignoreado a propósito — es data derivada / de terceros).

## 2. Material: los 10 videos

`knowledge/kb/tutorials/pop_2026/INDEX.md` (local) tiene la tabla completa con duración y palabras.
Cobertura temática:

| Tema | Videos |
|---|---|
| Fundamentos y modelo de datos POP | Intro to POPs (familia, atributos, primitivas, instancing) |
| Instalaciones interactivas con POPs | canal oficial de TouchDesigner (Parse/Error) |
| **Arquitectura de simulación** | *Particle Systems: Choices, Trade-offs and Architecture* |
| `particlePOP` a fondo | ciclo de vida, `targetpop`, fuerza, muerte por contacto, color por edad |
| **Colisiones** | *Particle Collisions with Ray POP* (**`rayPOP`**, nunca medido en este repo) |
| Campos de fuerza | `forceradialPOP` (espiral/axial/planar), `specpop`, camino standalone |
| **Flocking** | *Flocking with POPs* (`neighborPOP`, 3 bandas, steering) |
| Lookup | `lookupattributePOP` + `curvePOP` como función de transferencia / fase por punto |
| Atractores | 3 arquitecturas: lazo+`mathmixPOP`, componente GLSL, esfera-en-esfera |
| Gaussian Splatting con POPs | componente + shader de vértices sobre POPs (build experimental) |

## 3. Entregables versionados

| Artefacto | Qué aporta |
|---|---|
| `skills-hermes/td-pop-particle-systems/SKILL.md` **(nueva)** | Matriz de decisión (`feedbackPOP` vs `particlePOP` con/sin `timeintegration` vs GLSL), bucle `targetpop`, atributos del particlePOP, recetas (fuerza constante, ruido en velocidad, color por edad, muerte por contacto, atractores), `copyPOP` con plantillas de atributos, presupuesto GPU y trucos de cámara |
| `skills-hermes/td-pop-neighbors-and-rays/SKILL.md` **(nueva)** | `forceradialPOP` (incl. **integración manual sin `particlePOP`** y control por `specpop`), `neighborPOP` + **receta de flocking**, `proximityPOP`/`skinPOP`, **`rayPOP`** (2 inputs, salidas, los dos idiomas de colisión, gating con `mathcombinePOP`), `lookupattributePOP` como fase por punto |
| `skills-hermes/td-pop-family/SKILL.md` (patch) | Índice: apunta a las 2 skills nuevas |
| `skills-hermes/td-pop-trails-fields/SKILL.md` (patch) | Cross-ref + aviso del choque con C10 (reset) |
| `tools/fetch_youtube_transcripts.py` **(nueva)** | Pipeline reutilizable de transcripts (metadata `yt-dlp` + captions API + chunks de 30 s) |
| `tools/verify_tutorial_extracts.py` **(nueva)** | Verificador de citas: convierte "el subagente dice" en "está en el transcript" |
| `docs/BACKLOG.md` (patch) | Ítem 10: deuda de verificación en vivo + huecos de KB detectados |
| `FORK-NOTES.md` (patch) | Conteo de skills actualizado |

## 4. Hallazgos

### 4.1 Corroboraciones (fuente independiente para contratos propios)
- **`particle_integration_needs_feedback` [V] ↔ [T]**: el tutorial describe exactamente el mismo
  mecanismo (el `targetpop` cierra el lazo y sin él no hay integración). Refuerza C10.
- **`particlePOP` sin `timeintegration=ON` no se mueve [V] ↔ [T]**: el tutorial usa ON para física y
  OFF para control directo, con la misma consecuencia que medimos.
- **`mathmixPOP`/`mathcombinePOP` con secuencias vacías [V] ↔ [T]**: el tutorial crea los bloques
  antes de setear `comb0oper`; es exactamente el pitfall que ya teníamos.
- **`neighborPOP` `nebroutput='avg'` + atributo de prefijo [V] ↔ [T]**: el tutorial choca con que el
  promedio de vecinos pisa `P` y lo resuelve prefijando; nosotros ya lo documentamos como
  `nebrptattrs='P'` + arrays `Nebr_0_`/`Dist_0_`.

### 4.2 Nuevo (sin medir todavía)
- **`rayPOP`**: completamente ausente de nuestra KB. Contrato de inputs (puntos + geometría ≠ opcional,
  `fastbuild`), set de salidas y **dos idiomas de colisión** (mapear `hitnormal` al `map` de otro POP;
  o rebote por velocidad reflejada con `mathcombinePOP` + atributo 0/1 como selector del `mix`).
- **Receta de flocking** con bandas separadas (atracción/alineación/repulsión) y el error típico de
  alineación (usar la normal objetivo en vez del **delta**).
- **`forceradialPOP` standalone**: cómo integrar la fuerza a mano cuando no hay `particlePOP`
  (`mathmix A*B` → escalar, `A+B` → sumar a `P`) y el gotcha de `direction=000` que anula la espiral.
- **Arquitectura**: matriz de decisión + el truco del **probe grid** para 50k-200k partículas cuando
  `neighborPOP` ya no alcanza (`maxneighbors` topa el muestreo).
- **Gaussian Splatting sobre POPs**: es un **componente + shader de vértices**, no un POP nativo, y
  depende de un build **experimental**. Hueco real de KB (no hay tipo `gaussiansplatPOP` en la matriz
  de 97/101 tipos medidos). Documentado acá como hallazgo; **no** se promovió a skill porque es
  inestable entre builds.

### 4.3 Choque abierto (decisión pendiente)
| Tema | Tutorial **[T]** | Nuestro contrato **[V]** |
|---|---|---|
| Reset de la simulación | resetear/`initialize` el timer (atajo de teclado en la UI) | `particle_initialize_enferma`: **no** usar `initializepulse`/`preroll` por API en builds MCP |

No se resolvió a favor de nadie: es plausible que sean dos cosas distintas (reset de **UI/tiempo** vs
`initializepulse`+`preroll` **por API**). Queda como ítem 10 para medir con una sonda.

## 5. Verificación de ESTE pase

**Offline (todo verde, corrido en esta sesión):**

| Suite | Resultado |
|---|---|
| `python knowledge/server.py --selftest` | `21/21 offline ok` |
| `python knowledge/test_protocol.py` | PASS (18 casos; evidencia en `selftest_protocol.json`) |
| `python tools/gauntlet/check_single_home.py` | `0 violaciones (dueños: td_chain.py, td_probe.py)` |
| `python tools/gauntlet/td_probe.py` | `6/6 chequeos locales OK` |
| `tools/verify_tutorial_extracts.py` | 81/85 citas (95%) |

**Suite TD: NO corrida, a propósito.** Hay un **escritor concurrente vivo** sobre el mismo
TouchDesigner (otra sesión de agente con consignas propias). Precedente del propio repo: el ciclo
diario del 2026-10-06/07 no corrió la suite TD con un escritor vivo, por las **sandboxes de nombre
fijo** (`/gauntlet_smoke`, `/gauntlet_core`) que colisionan entre sesiones. Por eso el commit se
verifica con el gate en `--no-tests` **y** las 4 suites offline de arriba; **nada de lo que afirma
este pase se apoya en una medición en vivo**, y así está marcado en las skills.

**Evidencia del escritor concurrente (observada durante este pase, 11:13–11:18):** aparecieron en el
árbol `knowledge/build_tutorial_*.py` (4 builds: `particle_pop`, `force_radial`, `lookup_pop`,
`particle_attractors`) y 4 docs nuevos en `knowledge/kb/tutorials/tutorial-*.md`, correspondientes a
**4 de los mismos 10 videos** de este set (particle POP, force radial, lookup POP, atractores), con
`build: "2025.32460"` en el frontmatter. Son de **otra sesión**: este pase **no los commitó ni los
modificó** (el commit va por pathspec, exactamente los 9 paths propios). La cobertura es
**complementaria**: el otro escritor hizo *breakdown por tutorial*; este pase hizo las **skills de
operador** — y no tocó `rayPOP`, flocking, arquitectura, el set de introducción ni Gaussian
Splatting, que es donde está el hueco de KB.

## 6. Cómo se repite

```bash
# 1) transcripts de un set nuevo (manifest = [{index,id,title}])
python tools/fetch_youtube_transcripts.py --manifest <manifest.json> \
       --out knowledge/kb/tutorials/<set> --prefix pop

# 2) extracción estructurada (por subagentes): un JSON por video con cita + timestamp

# 3) verificar que cada cita exista en su transcript (falla = afirmación sin fuente)
python tools/verify_tutorial_extracts.py --dir knowledge/kb/tutorials/<set> --strict

# 4) destilar a skill versionada; transcripts y extracts quedan locales
```

`verify_tutorial_extracts.py` quita las marcas `[HH:MM:SS]` de ambos lados antes de comparar: una
cita que cruza el borde de un bloque de 30 s trae el marcador en el medio y, sin eso, da **falso
negativo** (fue el primer bug de la herramienta).

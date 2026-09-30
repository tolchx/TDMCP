# BACKLOG — items del TDMCP (fork tolchx)

(El triage del loop los agrega automáticamente.)

## Estado verificado — dueño único

Acá vive **el estado real**: qué suites existen, quién las corre, qué quedó probado y con qué
corrida. Los demás docs y skills **señalan acá** en vez de repetirlo — ya derivó una vez (el
2026-09-29 cuatro sitios afirmaban "0 violaciones" mientras el árbol tenía dos).

**Quién corre qué** — no hay otro runner:

`python scripts/loop_gate.py --action commit` → `scripts/loop_gate.py::run_tests`, en orden:
`knowledge/server.py --selftest` · `knowledge/test_protocol.py` · `run_regression.py --quick` (exige
TD: exit 2 = entorno caído → se saltea, no es rojo) · `tools/gauntlet/check_single_home.py` ·
`tools/gauntlet/td_probe.py`. Con `requireGreenTests: true`, cualquiera que se ponga rojo deja el
commit en **BLOCK**.

Probado el 2026-09-29 sobre el árbol de la sesión:

| qué | corrida / salida real |
|---|---|
| gate, `--paths` con los paths del cambio (≤ `maxFiles`) | `ALLOW · ✔ dentro de gate.yaml (…) suites verdes` · exit 0 |
| gate, invariante sembrada (`_seed_single_home.py`) | `BLOCK · ✖ las suites no están verdes` · exit 2 · `--json`: `single_home exit=1` |
| gate, entrada sin `--paths` (paths derivados de git) | `BLOCK · ✖ 15 archivos > maxFiles=12` · exit 2 — **sólo por tamaño**: es el diff acumulado de la sesión, no un rojo de suites |
| `build_pop_fountain.py` (asienta por `chain_source`) | `results/20260929-150850` — 8/8 cheks, 0 fallos |
| `build_godrays_particles.py` (asienta por `chain_source`) | `results/20260929-150924` — 0 fallos |
| `build_pop_curlfield.py` (incluye `selftest_render_ownership`) | `results/20260929-150538` — 45 calls, 0 fallos |
| `build_particle_fx.py` (`px` + `render_is_ours`) | `results/20260929-150904` — 42 calls, 0 fallos |
| **`build_pop_streams.py`** (proyecto C: estelas circle→trail→noise→topointprims) | `results/20260929-161923` — 11/11 cheks, 0 fallos, PNG 177 px |
| **`build_pop_field.py`** (proyecto D: campo 4D toro→sprinkle→noise) | `results/20260929-162735` — 9/9 cheks, 0 fallos, PNG 1443 px |
| **`build_pop_sim_trails.py`** (proyecto E: sim con feedback + estelas) | `results/20260929-221732` — 13/13 cheks, 0 fallos, PNG 304 px |
| auditoría `trailPOP` de la receta oficial (`probe_auditrail*`, sonda desechable) | `velocityscale`/`color1*`/`color2*` NO existen; `length` es tiempo (`lengthunit`) → contrato `trailPOP_pars` en C8 |
| **`build_pop_color_trails.py`** (proyecto F: estelas con color por velocidad) | `results/20260929-225109` — 14/14 cheks, 0 fallos, PNG 338 px → contratos C11 |
| **`build_pop_color_trails_attr.py`** (proyecto F-var: attributePOP sin glsl) | `results/20260929-232452` — 13/13 cheks, 0 fallos, PNG 638 px verde — `attributePOP_no_mapea` (C11): attr constante sí, dup/ren no mapean |
| **`build_pop_trails_floor.py`** (proyecto G: dardos apuntando según PartVel, coloreados por velocidad, iluminando el piso) | `results/20260930-030437` — 16/16 cheks, 0 fallos, PNG 13851 px — Euler del glslPOP verificados vs numpy (maxdiff 0.0) + `instancer_euler_xz`, `glslpop_custom_attr`, `curl_no_partvel`, `px_ciego_a_rotacion` (addendum C12) |
| **`build_pop_field_trails.py`** (proyecto 8: campo de estelas DIRECTO coloreado por NoiseGradient con attributePOP+rerangePOP — cero glsl, cero convertPOP) | `results/20260930-033443` — 16/16 cheks, 0 fallos, PNG 2413 px — corr(NoiseGradient_i, Color_i)=1.0 cierra C11; `noise_gradient_attr` + `td_slow_operation` (C14); `rerangePOP_mapea` cerrado a [V] |
| **`build_pop_transform.py`** (cobertura: transformPOP + groupPOP como apoyo) | `results/reg-20260930-094856` — 12/12 cheks, 0 fallos, PNG con contenido — group scoping exacto (moved 213==dentro, 0 fuera), grupo sin población NO filtra (400/400), mapeo T/R/S punto a punto err 0.0, swap pstdev N 1.0851↔1.0992 → C15 |
| **`build_pop_quantize.py`** (cobertura: quantizePOP) | `results/reg-20260930-094856` — 12/12 cheks, 0 fallos — round 0.25 → 5 niveles exactos err<1e-6, floor 0.3 err 0.0 (baja negativos 32/64), scope vacío = in-place → C15 |
| **`build_pop_limit.py`** (cobertura: limitPOP) | `results/reg-20260930-094856` — 10/10 cheks, 0 fallos — clamp saturación exacta 16+16 err 0.0, sólo-min vuela el techo, loop = shift por ventana w=0.6 (0.5→−0.1) → C15 |
| **`build_pop_sort.py`** (cobertura: sortPOP) | `results/reg-20260930-094856` — 13/13 cheks, 0 fallos — vector ordena el buffer (148→0 descensos, multiset intacto), rev/seed/shift reversibles → C15 |
| **`build_pop_neighbor.py`** (cobertura: neighborPOP) | `results/reg-20260930-094856` — 12/12 cheks, 0 fallos — NumNebrs 3..8 (4 esquinas, 16 interiores), Dist max 0.2828, avg opt-in esquina 0.5→0.4 → C15 |
| **`build_pop_connectivity.py`** (cobertura: connectivityPOP) | `results/reg-20260930-094856` — 10/10 cheks, 0 fallos — tabla de prims exacta (lines 12, strips 4, tris 18, quads 9, none 0; pts 16 siempre), closed +1/fila → C15 |
| **`build_pop_facet.py`** (cobertura: facetPOP) | `results/reg-20260930-131003` — 11/11 cheks, 0 fallos — unique 16→36 (grilla) y 800→3200 (toro) con prims intactas, cusp angle=20 no corta / angle=1 sí, conspoints 0.3→16 pts / 0.5→1 → C16 |
| **`build_pop_subdivide.py`** (cobertura: subdividePOP) | `results/reg-20260930-131003` — 12/12 cheks, 0 fallos — escalado exacto 16/9→49/72→169/288, bb y planaridad preservados, creaseweight desplaza sin cambiar conteos → C16 |
| **`build_pop_triangulate.py`** (cobertura: triangulatePOP) | `results/reg-20260930-131003` — 10/10 cheks, 0 fallos — toggle triangulatequads necesario (off pasa intacta), on 9→18 (grilla) y 800→1600 (toro) con pts intactos → C16 |
| **`build_pop_extrude.py`** (cobertura: extrudePOP) | `results/reg-20260930-131003` — 12/12 cheks, 0 fallos — jaula 25/20 incluso con distance=0 (grid 4x4: 52/45), P_2=[0,distance], axis=y mueve el rango, taper no cambia conteos → C16 |
| **`build_pop_pattern.py`** (cobertura: patternPOP) | `results/reg-20260930-131003` — 13/13 cheks, 0 fallos — ramp exacto err<2e-8, tabla prims linestrip 1 / lines 5 / points 6 / none 0, sin 2 ciclos err 3.4e-7, random determinístico por índice → C16 |
| **`build_pop_random.py`** (cobertura: randomPOP) | `results/reg-20260930-131003` — 14/14 cheks, 0 fallos — add in-place deltas uniformes [0,1], set+scope vacío NO-OP, amp NO escala el uniforme, gaussian ≈N(0,1), extrapts multiplica (9→18→27) → C16 |
| batería completa 20 builds (8 proyectos + 12 cobertura) | `results/reg-20260930-131003` — 20/20 exit 0, 121.6 s |
| `knowledge/server.py --selftest` (contratos C8/C9 en el archivo servido) | exit 0 |
| `td_probe.py` · `check_single_home.py` | 6/6 · 0 violaciones, exit 0 |

La guardia de propiedad del render, enfrentada a terminales que **no** son el par `geo`/`ren` (redes
scratch, construidas y destruidas en el mismo pase):

| caso | resultado |
|---|---|
| control `geo`+`ren` · geometry llamada `geoB` · renderTOP llamado `render_out` | `[True, 615, 0]` |
| terminal vacío (decoy) con `render=true` · terminal de **otra** red | `[False, 615, 615]` — niega, no afirma |
| red inexistente | `RuntimeError: no existe la red /X` — falla cerrado y con mensaje |

**Sigue sin probarse:** F3–F4 del gauntlet sobre este árbol (ninguna fase F3 usa `td_chain`; F1+F2 sí
corren dentro del gate) · el gate con el juez externo encendido (`--no-judge` en las corridas de
arriba) · `render_is_ours` contra el camino de excepción de `px()`.

## Proyectos POP (2026-09-29, tarde)

Dos redes nuevas construidas y verificadas contra TD vivo, con el camino de medición del dueño único
(`chain_source` → `settle`/`px`/`render_is_ours`):

- **`/pop_streams`** ([build_pop_streams.py](../tools/gauntlet/build_pop_streams.py)): anillo
  `circlePOP` → estelas `trailPOP` → `noisePOP` curl → `topointprims` → pointsprite. 256 pts/256
  prims, guardia `[True, 4315, 0]`. Aprendizaje: el trail ACUMULA el campo y el enjambre migra del
  anillo — la cámara se centra en el centroide de P (`cam_follows_data`), no en el origen.
- **`/pop_field`** ([build_pop_field.py](../tools/gauntlet/build_pop_field.py)): superficie de
  `torusPOP` → `sprinklePOP` 3000 pts → `noisePOP` **4D** animado por `t4d` (el tiempo escalonado
  es lo que mueve el campo sin simulación) → `topointprims`. 3000 pts, PNG 1443 px.
- **`/pop_sim_trails`** ([build_pop_sim_trails.py](../tools/gauntlet/build_pop_sim_trails.py),
  noche): **simulación + estelas** — `spherePOP` → `particlePOP` (life=1.2, sin initialize/preroll)
  → `forceradialPOP` → `trailPOP` → curl → `topointprims`, con rama `grav` → `fb` (nullPOP) y
  `targetpop=fb`: **sin el loop de feedback la integración se descarta** (P clavado en el emisor).
  Animación verificada escalando `globforcey` -6 → -14 entre llamadas: `P_1.min` de sim
  -1.89 → -5.03, terminal -3.45 → -10.11; población viva por `PartId` (≤ 701), buffer con slots
  muertos (30k) documentado. Contratos nuevos: **C10** en
  `knowledge/contracts/VERIFIED_CONTRACTS.md`.
- Contratos nuevos en `knowledge/contracts/VERIFIED_CONTRACTS.md`: **C8** (trails/cámara/
  renderTOP-lista/noisesize-writeonly/wiring-inputs), **C9** (ruido 4D + torusPOP) y **C10**
  (loop de feedback, initialize-enferma, canales Part*, spherePOP radz/cols).
- **`/pop_color_trails`** ([build_pop_color_trails.py](../tools/gauntlet/build_pop_color_trails.py),
  noche): **estelas con color por velocidad** — sim (C10) → curl → `glslPOP` 'shade' escribe
  `Color` desde `PartVel` (uniform `uSpeedScale`, rampa frío→caliente) ANTES del trail: la estela
  arrastra historial de color. Material blanco (multiplica), trail 16 FRAMES. Palanca por
  números: media Color_0 0.547 → 0.300 al comprimir el rampa; colores históricos (max terminal
  0.943 > max shade 0.626). Contratos nuevos: **C11** (main canónico con `TDIndex()` guardia,
  inputs por `TDIn_*` no buffers, `Color` float4 por `attr0name='color'`, gradables de color).
- **`/pop_color_trails_attr`** ([build_pop_color_trails_attr.py](../tools/gauntlet/build_pop_color_trails_attr.py),
  noche): variante del proyecto F **sin glsl** — attributePOP aguas arriba del trail crea
  `Color` float4 **constante** (sobrevive toda la cadena hasta el render, material blanco).
  Veredicto medido: attributePOP **NO mapea atributo→atributo** (dup/ren ineffective read-back-ok,
  cero efecto) — el color por velocidad con rampa sigue necesitando glslPOP (proyecto F).
  Contrato `attributePOP_no_mapea` en C11.
- **`/pop_trails_floor`** ([build_pop_trails_floor.py](../tools/gauntlet/build_pop_trails_floor.py),
  2026-09-30): **estelas de DARDOS coloreados por velocidad y apuntando según PartVel**
  (elevación del proyecto G, 16/16) — cadena del proyecto F (sim+feedback, glsl rampa, trail)
  como DATOS en `geo_data`, `geo_cubes` con `boxPOP`+phong+**instancing** (fuente = poptoCHOP
  `src` sobre `tr_out`: la fuente POP directa NO cruza COMPs, C12), color por instancia vía
  `Color_0/1/2` **y orientación por instancia**: el glslPOP calcula los Euler de la skill en GPU
  (rx=degrees(atan2(dz,√(dx²+dy²))), rz=degrees(atan2(-dx,dy)) — maxdiff 0.0 vs numpy) en el
  attr custom `Rot` que el trail arrastra; `instancerop=src` + `instancerx/y/z='Rot_0/1/2'`.
  `geo_floor` phong oscuro en XZ, `ren.par.geometry` como LISTA de 2 COMPs. Gradables: toggles
  estructurales por chain, color por datos (max `Color_0`) y orientación por **A/B congelado**
  (diff 0.0054, 6% de px — el px total es ciego a la rotación, plantilla simétrica). Contratos
  **C12** (`instancing_pop_crosscomp`, `instancecolormode_menu`, guardias multi-geometry) +
  addendum de flechas (`instancer_euler_xz`, `glslpop_custom_attr`, `curl_no_partvel`,
  `px_ciego_a_rotacion`).
- **`/pop_field_trails`** ([build_pop_field_trails.py](../tools/gauntlet/build_pop_field_trails.py),
  2026-09-30): **campo de estelas directo sin glsl ni convertPOP** (proyecto 8, 16/16) —
  toro→sprinkle→noisePOP(simplex4d + `gradient=True`: escribe NoiseGradient_0..3, el vector
  del campo por punto)→attributePOP (crea Color)→**rerangePOP** (NoiseGradient→Color,
  corr = 1.0 por componente, cierre de C11)→trailPOP **directo** (`surftype='points'` + flags
  en el propio trail, sin convertPOP — C8). Animación por t4d escalonado (C9); las estelas
  acumulan el historial del campo (uniq de P_0 crece). Contratos **C14**
  (`noise_gradient_attr`, `td_slow_operation`) + `rerangePOP_mapea` cerrado a [V].
- Recetas reutilizables (estelas y campo 4D, con sus pitfalls) documentadas como skill
  **`td-pop-trails-fields`** en `skills-hermes/` (referenciada por `td-pop-family` y
  `td-pop-render-pipeline`).

## Items

- [x] 1. Hallado por el loop (triage automático, id `arbol-sucio`, huella `63cc9331b8a0d0a5`):
  9 archivos modificados sin commitear. **CERRADO 2026-09-29** (ciclo diario, intento 1): eran **un
  solo trabajo coherente**, no residuo — el refactor "un solo dueño de la medición" (`td_chain.py`
  inyectado por `td_probe.chain_source`, `Gauntlet.offline()` como único wrapper de td-knowledge,
  `check_single_home.py` como regla ejecutable). Verificado con gauntlet completo **PASS**
  (`results/20260929-032041`), las dos suites de host verdes (hoy las corre el gate); gate **ALLOW**;
  commit `bdee341` (árbol limpio al cerrar). Evidencia: `docs/loop-run-2026-09-29.md`.
  Razón del cierre: un árbol sucio contamina al juez externo y re-dispara el candidato cada día.

- [x] 2. **El gate ya corre `check_single_home.py`. CERRADO 2026-09-29 (auditoría).** Evidencia
  original (ciclo diario): un archivo que re-implementaba la medición pasaba igual —
  `VIOLACION build_pop_fountain.py:128: def settle(n=8):` · exit 1, con ese archivo ya publicado en
  `6cab054` y el gate habiendo dado ALLOW (sus suites eran las de arriba, sin el guard). Fix:
  `check_single_home.py` y la autoprueba `td_probe.py` son pasos de `loop_gate.run_tests`, y los dos
  builds que violaban la regla (`build_pop_fountain.py`, `build_godrays_particles.py`) asientan con
  `td_probe.chain_source` (probado con la invariante sembrada: ver *Estado verificado*). Detectado
  por: el ciclo diario, verificando el árbol publicado.

- [ ] 3. **El cierre del ciclo commitea con `git add -A` y publica WIP de un escritor concurrente.**
  Evidencia real (2026-09-29): el commit de cierre `6cab054` barrió `tools/gauntlet/build_pop_fountain.py`
  (nuevo, 179 líneas, mtime 03:24:01) y `tools/gauntlet/td_probe.py` (+30) que **no** escribió la
  corrida: los escribió otro agente/sesión en el **mismo working tree** (sus corridas quedaron en
  `results/20260929-032233/032405/032429`). El gate no lo vio porque sólo juzga los paths que se le
  pasan. Qué hacer: cerrar con `git add <paths explícitos>` (nunca `-A`) y abortar el cierre si
  aparecen archivos nuevos/modificados que la corrida no tocó. Detectado por: el ciclo diario
  (comparando `git status` antes/después del add).

- [ ] 4. **Hallado por el loop (triage automático)** — 4 archivo(s) modificados sin commitear. Evidencia: knowledge/contracts/VERIFIED_CONTRACTS.md; knowledge/selftest_protocol.json; skills-hermes/td-pop-trails-fields/SKILL.md; tools/gauntlet/build_pop_trails_floor.py. Cómo lo detectó: `loop_triage.py` (id `arbol-sucio`, huella `b6e661339e23a028`). Qué hacer: Decidir por archivo: es trabajo en curso (commitear) o residuo (revertir). Un árbol sucio contamina al juez externo..
  **DECISIÓN 2026-09-30 (ciclo diario, intento 1): NO commitear y NO revertir — ítem ABIERTO.**
  Los 4 archivos los está escribiendo **una sesión viva en el mismo working tree** (mtimes
  23:59:08–00:08:36; `build_pop_trails_floor.py` reescrito a las 00:08:36 y re-corrido a las 00:08:56;
  ventanas de 45 s con escrituras hasta 00:12). Publicar WIP ajeno es el modo de falla del ítem 3 y
  revertir sería destructivo sobre trabajo vivo. Por archivo: los 2 de documentación
  (`contracts/VERIFIED_CONTRACTS.md` +19, `skills-hermes/td-pop-trails-fields/SKILL.md` +10) tienen
  **evidencia real** (`results/20260929-235821/probe-surftype2.jsonl`: mismo frame, 380 prims/380 pts,
  `surftype=rows` → 0 px vs `points` → **5495 px**) y los commitea su propia sesión;
  `knowledge/selftest_protocol.json` es **artefacto generado** por `knowledge/test_protocol.py`;
  `tools/gauntlet/build_pop_trails_floor.py` (nuevo, 418 líneas) está **en rojo** en sus dos corridas
  (`results/20260930-000700` ok=false 6/13 checks False; `results/20260930-000856` ok=false 5/13).
  Sin verificación en vivo de nada (suite TD no corrida: escritor vivo en el mismo TouchDesigner +
  sandboxes de nombre fijo `/gauntlet_smoke`, `/gauntlet_core`). Evidencia completa:
  `docs/loop-run-2026-09-30.md`.

- [x] 5. **Cobertura POP en vivo: CERRADO el 2026-09-30 con 6 tipos nuevos medidos y commiteados.**
  Eran 15 de 101 tipos ejercitados; se sumaron transformPOP, quantizePOP, limitPOP, sortPOP,
  neighborPOP y connectivityPOP con red viva + script versionado + checks con número (21 → 27 tipos
  ejercitados). Batería 14/14 exit 0 (`results/reg-20260930-094856`, 83.3 s); contratos C15 en
  `VERIFIED_CONTRACTS.md` (incluye los 2 tipos de la lista que NO existen: mathMixPOP,
  lookupAttributePOP — `unknown_operator_type`, guardado verbatim). Filas por build en
  *Estado verificado*. Quedan 74 tipos sin medir para futuros ítems.
- [x] 5b. **Cobertura POP (tramo 2) CERRADO el 2026-09-30: 6 tipos nuevos — facetPOP, subdividePOP,
  triangulatePOP, extrudePOP, patternPOP y randomPOP — medidos con el patrón del ítem 5.**
  27 → 33 de 101 tipos ejercitados. Batería 20/20 exit 0 (`results/reg-20260930-131003`, 121.6 s);
  contratos C16 en `VERIFIED_CONTRACTS.md` (sorpresas: triangulatequads default OFF,
  jaula de extrude existe con distance=0, el 'set' de randomPOP es NO-OP con scope vacío y amp
  no escala el uniforme, el random de pattern genera por índice). 6 filas nuevas arriba. Helps y
  live-params en `results/20260930-124833/help/`. Quedan 68 tipos sin medir → ítem 5c.
- [ ] 5c. **Cobertura POP (continúa): 68 de 101 tipos siguen sin una sola medición.**
  Prioridad restante de la lista del ítem 5: groupPOP (medido como apoyo en C15: falta red propia),
  proximityPOP, revolvePOP, tubePOP, topologyPOP, lookupTexturePOP. (mathMixPOP y
  lookupAttributePOP NO existen en el build — removidos, ver C15.) Mismo patrón: build versionado
  + checks con número + fila en *Estado verificado* + contrato si hay sorpresa.

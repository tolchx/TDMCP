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
| gate, cierre por pathspec (`--do-commit`) + BLOCK por stage ajeno (ítem 3, 2026-10-05) | clon temporal + árbol real: commit con EXACTAMENTE los paths pedidos (untracked incluido, `README.md` stageado ajeno NO entra); `--paths README.md` limpio → `✖ git commit falló` exit 2; BLOCK con stage ajeno fuera de `--paths` |
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
| **`build_pop_group.py`** (cobertura: groupPOP con red propia) | `results/reg-20261002-022418` — 13/13 cheks, 0 fallos — población inmutable (thin = metadato: step 2 exacto 10/20), debugcolor 2 valores con pairing estable, ghost mueve TODO, secuencias bound con PISO de 1 bloque (`numBlocks=0` → `tdError: Minimum size is 1 block`) y bound sin efecto en 4 configs [abierto] → C17 |
| **`build_pop_proximity.py`** (cobertura: proximityPOP) | `results/reg-20261002-022418` — 12/12 cheks, 0 fallos — grid 3x3 @0.21 avoid = 12 ortogonales exactas (0 diagonales), donothing DOBLA 24, @0.29→20 / @0.10→0, `maxlinesperpoint=1`→8 determinístico, output='points' 9/12, cpureadback irrelevante para contar → C17 |
| **`build_pop_revolve.py`** (cobertura: revolvePOP) | `results/reg-20261002-022418` — 12/12 cheks, 0 fallos — perfil 2 pts ramp 0.2..0.5 × divs 20 = 40/20, radios XZ EXACTOS {0.2,0.5}, tabla surftype 2x20, divs escala 4→8/4 y 8→16/8, autopivot ON/OFF colineal idénticos, PNG 648 px → C17 |
| **`build_pop_tube.py`** (cobertura: tubePOP) | `results/reg-20261002-022418` — 15/15 cheks, 0 fallos — `radx`/`rady` son los radios de los EXTREMOS (cono, interpolación lineal exacta 0.2→1.0), cols8 rows4 = EXACTO 32/24, `endcaps` Toggle agrega cols−2 prims sin puntos nuevos, `closedu=False` duplica seam (+rows pts), normal/texture opt-in al poptoCHOP → C17 |
| **`build_pop_topology.py`** (cobertura: topologyPOP) | `results/reg-20261002-022418` — 13/13 cheks, 0 fallos — `primsourcemode='specpop'`+`primspop=B`: 9 pts de A / 4 quads de B, P del INPUT, `topology='ref'` vivo (0/8/4 con cook explícito del origen), 'copy' NO congela, maxpoints=5 → 5/4 determinístico → C17 |
| **`build_pop_lookuptexture.py`** (cobertura: lookuptexturePOP) | `results/reg-20261002-022418` — 14/14 cheks, 0 fallos — sin `overrideautoattr` NO aparece attr; con override+scope Color+attrtype color crea Color 4c, `interpolate=False` muestrea texel EXACTO (pertenencia a los 59 texels), swap constantTOP 0.9→0.898 (±1 LSB), offset 0.125 desplaza y 0 restaura → C17 |
| batería completa 26 builds | `results/reg-20261002-022418` — 26/26 exit 0, 167.2 s |
| sonda desechable `probe_bound2.py` (6 fases, borrada tras medir) | `results/probe_bound2` — cierra `grouppop_bound_sin_efecto_api`: con `bound0enabled=ON` excluye de verdad (radio = 0.5·scale ABSOLUTO, frontera inclusiva, invert = complemento exacto 8/12↔12/8, bound∩attr = AND fijo entre páginas, combine solo entre bloques de la misma secuencia: or 10 / xor 6 / and 4 / nor 10); el build 5c no encendía el Toggle → "sin efecto"; membresía STALE tras el primer enable → C17 |
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

- [x] 3. **El cierre del ciclo commitea con `git add -A` y publica WIP de un escritor concurrente. CERRADO 2026-10-05 con hardening mecánico en el gate.**
  Evidencia real (2026-09-29): el commit de cierre `6cab054` barrió `tools/gauntlet/build_pop_fountain.py`
  (nuevo, 179 líneas, mtime 03:24:01) y `tools/gauntlet/td_probe.py` (+30) que **no** escribió la
  corrida: los escribió otro agente/sesión en el **mismo working tree** (sus corridas quedaron en
  `results/20260929-032233/032405/032429`). El gate no lo vio porque sólo juzga los paths que se le
  pasan. **REPETIDO el 2026-10-02 07:34:54:** `ec27eb7` ("feat(knowledge): integrate 79 shaders…")
  barrió los 13 archivos del tramo 5c de una sesión cortada media hora antes (2,072 líneas de
  builds, +93 de C17, regression_pop, td_probe y el borrado de 2 sondas) mezclados con los knowledge
  propios — el bullet final del mensaje ("include gauntlet test builds") confiesa que el committer
  VIO los archivos ajenos y los publicó igual. Fix mecánico en `scripts/loop_gate.py`:
  (1) BLOCK si hay archivos STAGEADOS fuera de `--paths` (`git diff --cached` vs paths: la huella
  del `git add -A`, propio o ajeno); (2) reporte no-bloqueante `conc=N`/`concurrentes` de lo dirty
  fuera de los paths (escritor concurrente VISIBLE; revertir sería destructivo, ver ítem 4);
  (3) `--do-commit "MSG"`: tras ALLOW corre `git add -- <paths>` + `git commit -m MSG -- <paths>` —
  commit por PATHSPEC que no puede barrer nada fuera de lo pedido (nunca `-A`); (4) `added_lines`
  cuenta con pathspec: los archivos ajenos ya no inflan `maxLines`. Probado en clon temporal y
  árbol real (ver *Estado verificado*). Detectado por: el ciclo diario (comparando `git status`
  antes/después del add) — ahora también lo frena el gate en el momento del cierre.

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
- [x] 5c. **Cobertura POP (tramo 3) CERRADO el 2026-10-02: 6 tipos nuevos — groupPOP (red propia),
  proximityPOP, revolvePOP, tubePOP, topologyPOP y lookuptexturePOP — medidos con el patrón del ítem 5.**
  33 → 39 de 101 tipos ejercitados. Batería 26/26 exit 0 (`results/reg-20261002-022418`, 167.2 s);
  contratos C17 en `VERIFIED_CONTRACTS.md` (sorpresas: la cámara canónica del gauntlet es
  `cam.par.lookat`+traslación iso — apuntar con rx/ry manual da render NEGRO en todas las configs;
  tubePOP `radx`/`rady` son los extremos del CONO y `endcaps` agrega cols−2 prims sin puntos;
  lookuptexturePOP no escribe attr sin `overrideautoattr` y muestrea texel exacto con
  interpolate off; topologyPOP 'copy' NO congela; las secuencias bound tienen piso de 1 bloque).
  6 filas nuevas arriba. Quedan 62 tipos sin medir → ítem 5d.
- [ ] 5d. **Cobertura POP (continúa): 62 de 101 tipos siguen sin una sola medición.**
  Mismo patrón: build versionado + checks con número + fila en *Estado verificado* + contrato si
  hay sorpresa. Priorizar los tipos que aparecen en recetas y errores reales del loop.
  **CERRADO además (2026-10-05):** el contrato abierto de C17 `grouppop_bound_sin_efecto_api` —
  `probe_bound2.py` (sonda desechable, 6 fases) halló el Toggle `bound0enabled` (default OFF) y
  midió el modelo completo de exclusión; ver C17.

- [ ] 6. **Hallado por el ciclo diario (2026-10-02, verificación de entorno)** — el check de F3.2
  (`f3-n2-audio-clock`) es **FLAKY**. En la suite #1 de hoy (`results/20261002-000742`) falló
  `f3_n2_audio_clock.py:102` "par animado por expresion cambia en el tiempo" con
  `delta=2.5970552997023333e-07` (umbral `1e-4`); la misma fase sola (`results/20261002-000913`) y la
  suite #2 (`results/20261002-000922`) dieron **PASS** (todas las fases). **No es regresión**: el
  archivo no se modificó desde `793ad71` y ya había fallado 7 veces el 2026-09-28 (`delta=0.0`).
  Causa probable (NO verificada): el término `0.15*abs(absTime.seconds % 2 - 1)` (`f3_n2_audio_clock.py:45-46`)
  muestreado 1.2 s después es sensible a la fase absoluta del reloj → rojo falso probabilístico.
  Qué hacer: **robustecer** el check (señal con movimiento garantizado en toda fase, o muestreo con
  ventana) **sin deshabilitarlo** (`loop-constraints.md`: un test en rojo es un hallazgo, no un obstáculo).
  Extra del mismo hallazgo: `sig_live_evidence_fail()` (`scripts/loop_triage.py:104-122`) glob-ea
  `tools/gauntlet/results/*.json` **sin recursión** → los `*-summary.json` dentro de
  `results/<run_id>/` nunca se vuelven candidato `vivo-rojo-*`; mismo agujero en `sig_gauntlet_rojo`
  (sólo corre `--quick`, F1+F2). Evidencia completa: `docs/loop-run-2026-10-02.md`.

- [x] 7. **Hallado por el loop (triage automático)** — 1 archivo(s) modificados sin commitear. Evidencia: knowledge/server.py. Cómo lo detectó: `loop_triage.py` (id `arbol-sucio`, huella `cebefde95bf63597`).
  **CERRADO 2026-10-05:** consolidado con ítem 8.

- [x] 8. **Hallado por el loop (triage automático)** — 3 archivo(s) modificados sin commitear (`server.py`, `healthcheck.py`, `selftest_protocol.json`).
  **CERRADO 2026-10-05:** Se completó el refactor y robustecimiento de la capa offline/live (`server.py`, `live.py`, `healthcheck.py`, `test_live.py`).
  - Eliminado el bloque duplicado al final de `server.py` que causaba `SyntaxError`.
  - Coerción tolerante de tipos para clientes MCP (números, strings, booleanos).
  - Búsqueda y coincidencia exacta > prefijo > substring evitando matches vacíos o falsos.
  - Normalización e insensibilidad a mayúsculas/minúsculas en filtros y categorías (`kb_search`, `kb_taxonomy`, `pop_matrix`).
  - Glosario bidireccional ES/EN y remoción de acentos en `resolve_operator`.
  - Manejo seguro de comentarios, variables locales y asignaciones compuestas en `glsl_analyze`.
  - Prevención de crashes de codificación en Windows reconfigurando stdio a UTF-8.
  - `EXPECTED_TOOLS = 27` en `healthcheck.py` y `LIVE_READONLY` exportado en `live.py`.
  - Todas las suites verificadas en verde: `server.py --selftest` (21/21 ok), `test_protocol.py` PASS, `healthcheck.py` PASS (cero problemas), `test_live.py` (12/12 etapas exitosas contra TouchDesigner vivo). Gate commit ALLOW.

- [ ] 9. **Hallado por el loop (triage automático)** — 2 archivo(s) modificados sin commitear. Evidencia: tools/gauntlet/build_pop_line.py; tools/gauntlet/probe_5d_scout.py. Cómo lo detectó: `loop_triage.py` (id `arbol-sucio`, huella `ab380a16c7831674`). Qué hacer: Decidir por archivo: es trabajo en curso (commitear) o residuo (revertir). Un árbol sucio contamina al juez externo..
  **Auditoría del ciclo diario 2026-10-06 (evidencia real, no cierre):** ambos archivos son
  trabajo TERMINADO del escritor concurrente sobre el **item 5d** (cobertura POP) y compilan.
  - `tools/gauntlet/build_pop_line.py` (232 l.) = build 1/6 (**linePOP**); última corrida
    `results/20261005-123124/build-pop-line-report.json`: `ok=true`, **14/14 checks PASS**
    (geometría exacta, divs+1, closed 2×, ctrlpoints, 2·divs+1, guardia de píxeles).
  - `tools/gauntlet/probe_5d_scout.py` (124 l.) = sonda de esquema de los 6 tipos
    (`results/probe_5d/scout-*.jsonl`).
  Decisión del ciclo: **NO commitear** (WIP ajeno sin verificación en el brief del ciclo) y
  **NO revertir** (destruye trabajo vivo). **Item ABIERTO** — lo decide Tolch (mismo criterio
  que el item 4). Ver `docs/loop-run-2026-10-06.md`.
  **Revisión del ciclo diario 2026-10-07:** mismo par de archivos (232 l. + 124 l.), ambos
  `py_compile` OK; sin cambios respecto del 06/10, no se commiteó ni revirtió. Entorno verde
  (gauntlet completo PASS, `results/20261007-001339`). Ver `docs/loop-run-2026-10-07.md`.

- [ ] 10. **Tutoriales de YouTube 2026 → skills POP (pase interactivo del 2026-10-07).** Se
  transcribieron y destilaron 10 tutoriales de sistemas POP (46.033 palabras) a 2 skills nuevas:
  `td-pop-particle-systems` (arquitectura de simulación, `targetpop`, fuerzas, `copyPOP` con
  plantillas) y `td-pop-neighbors-and-rays` (`neighborPOP`/flocking, `forceradialPOP` standalone +
  `specpop`, `proximity`/`skin`, **`rayPOP`**). Detalle y provenance: `docs/pop-tutorials-2026-10-07.md`.
  **Todo el conocimiento [T] está SIN verificar en vivo** (había un escritor concurrente sobre el
  mismo TD; la suite TD no se corrió, ver §5 del reporte). Deuda accionable, por orden de valor:
  - **`rayPOP`**: 0 mediciones. Inputs (puntos + geometría), `fastbuild`, salidas
    (`hitnormal`/`dist`/`numhits`/`inside`/`barycoords`/`hitprimindex`) y el **gating por
    `mathcombinePOP` con atributo 0/1** como selector del `mix`. Candidato #1 del ítem 5d.
  - **Flocking con `neighborPOP`** (3 bandas + steering) y el error de alineación (delta vs normal
    objetivo): receta sin un solo número medido.
  - **`forceradialPOP` standalone** (`mathmix A*B` → escalar, `A+B` → sumar a `P`) y su gotcha
    `direction=000` anula la espiral.
  - **Reset de simulación**: choque abierto entre el atajo de teclado del tutorial
    (`initialize`/timer) y `particle_initialize_enferma` (C10: `initializepulse`+`preroll` hinchan el
    buffer por API). Medir con una sonda antes de adoptar el reset del tutorial en código.
  - **Hueco de KB declarado**: Gaussian Splatting sobre POPs es un **componente + shader de vértices**
    sobre build experimental (no hay tipo POP de GS en la matriz de 97/101). No promovido a skill por
    volatilidad entre builds.
  Herramientas que deja el pase: `tools/fetch_youtube_transcripts.py` (transcripts reutilizables) y
  `tools/verify_tutorial_extracts.py` (verifica que cada cita exista en el transcript: 81/85 = 95%).

- [ ] 11. **Hallazgo del pase del 2026-10-07 — el juez externo (jev) juzga el ÁRBOL ENTERO, no el
  diff del commit.** `scripts/loop_gate.py::run_judge` arma
  `python jev_audit_diff.py --repo ROOT --json` **sin pasarle los `--paths`** del commit; el juez hace
  `git status --porcelain` y difea *todo* lo sucio (su `construir_diff` usa `git status`, no el
  pathspec). Evidencia de esta sesión (había un escritor concurrente vivo):
  `python jev_audit_diff.py --repo <repo> --brief .freebuff_tasks/brief-pop-tutorials-2026-10-07.txt`
  → `ROJO no_corresponde_al_brief=0.21 · diff_truncado`, y en "archivos juzgados" entran
  `knowledge/build_tutorial_*.py`, `knowledge/selftest_protocol.json`, `tools/gauntlet/build_pop_line.py`
  y `loop-run-log.md` — **nada** de eso estaba en el brief ni en los 9 paths del commit.
  Consecuencia: con cualquier WIP ajeno en el árbol (situación **recurrente** en este repo: items 3, 4,
  9 y este mismo pase) el veredicto queda sesgado y además **trunca el diff** → el juez deja de mirar
  justo el cambio que se va a publicar. Es el pitfall 8 de la skill `juez-externo-jev` ("si lo corrés
  después de escribir los docs → ROJO espurio") y el pitfall 3 ("bucket de ruido conocido") en versión
  estructural. **Fix propuesto:** que `run_judge` reciba los `--paths` del gate y los pase al juez
  (un `--paths` nuevo en el script, o un `--max-chars` acorde); mientras tanto, el veredicto del juez
  sobre un árbol con escritor concurrente **no es evidencia** y hay que reportarlo como tal.
  **Estado de este pase:** el gate igual dio **ALLOW** (naturaleza `trabajo_real`, `debilita=0.12 < 0.6`);
  el ROJO se reportó sin bloquear, que es lo que manda la regla advisory de Tolch.
  **Prueba (reproducible):** con un `git clone --no-hardlinks` + copiar **sólo** los archivos del pase,
  el juez sobre el árbol AISLADO da **`VERDE trabajo_real (0.99) · debilita=0.06 · corresponde=0.69`**
  (2ª corrida, delta final: `VERDE (0.97) · debilita=0.05 · corresponde=0.63`). En el árbol real, con el
  mismo contenido, da `ROJO corresponde=0.09..0.21 · diff_truncado`. La diferencia es **sólo** el WIP
  ajeno: el juez no está midiendo el commit, está midiendo la convivencia de dos sesiones.

- [ ] 12. **El commit `6075955` mezcló DOS sesiones (pasó el 2026-10-07, ~11:22:59).** Lo hizo la otra
  sesión viva (autor `tolchx`) y **ya está en `origin/main`**. Entraron en el mismo commit los 4
  `knowledge/build_tutorial_*.py` de esa sesión **y 9 archivos de este pase** (`td-pop-particle-systems`,
  `td-pop-neighbors-and-rays`, `td-pop-family`, `td-pop-trails-fields`, `docs/pop-tutorials-2026-10-07.md`,
  `docs/BACKLOG.md` ítem 10, `FORK-NOTES.md`, `tools/verify_tutorial_extracts.py`) — un **snapshot a
  mitad de camino** de este trabajo, más `knowledge/selftest_protocol.json` (artefacto generado).
  Mecanismo probable: el gate **sin `--paths` deriva los paths de `git`** (todo lo sucio), así que el
  hardening del ítem 3 ("BLOCK por stage ajeno fuera de --paths") **no cubre el caso sin paths** —
  commitea el árbol entero, incluido el WIP ajeno. Es el mismo modo de falla que el ítem 3 quiso cerrar,
  por la puerta de atrás.
  **Qué queda de este pase después de esa mezcla:** `docs/BACKLOG.md` (ítems 11 y 12) +
  `tools/fetch_youtube_transcripts.py` (quedó afuera del barrido) → se commitean aparte, por pathspec.
  **Para revisar a mano:** `git show --stat 6075955` (¿la otra sesión quería publicar los 9 archivos de
  este pase?, ¿el snapshot de las 2 skills es el bueno?) y **regla operativa nueva**: cuando hay dos
  sesiones vivas sobre el mismo working tree, **siempre** `--action commit --paths ...` explícito, y
  chequear `git log -1 --stat` antes de pushear.

#!/usr/bin/env python3
"""regression_pop.py — batería de regresión de los 32 builds POP (runs verdes en TD vivo).

Corre los builds en orden; cada uno DESTRUYE y reconstruye su red ROOT (verificación en
frío), así que el orden sólo importa para no pisar la misma red dos veces: el monitor
(/pop_sim_trails) va después de su build padre. Exit 0 sólo si TODOS los exit codes son 0.

Uso:  PYTHONIOENCODING=utf-8 python tools/gauntlet/regression_pop.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))

BATERIA = [
    ("build_pop_streams.py", "proyecto C: estelas circle→trail→noise (/pop_streams)"),
    ("build_pop_field.py", "proyecto D: campo 4D toro→sprinkle (/pop_field)"),
    ("build_pop_sim_trails.py", "proyecto E: sim con loop de feedback (/pop_sim_trails)"),
    ("build_pop_color_trails.py", "proyecto F: color por velocidad (/pop_color_trails)"),
    ("build_pop_color_trails_attr.py", "proyecto F-var: attributePOP sin glsl (/pop_color_trails_attr)"),
    ("build_pop_trails_floor.py", "proyecto G: dardos orientados por PartVel iluminando el piso (/pop_trails_floor)"),
    ("build_pop_field_trails.py", "proyecto 8: campo de estelas directo sin glsl ni convertPOP (/pop_field_trails)"),
    ("build_pop_transform.py", "cobertura: transformPOP + groupPOP scoping (/pop_transform)"),
    ("build_pop_quantize.py", "cobertura: quantizePOP round/floor (/pop_quantize)"),
    ("build_pop_limit.py", "cobertura: limitPOP clamp/loop (/pop_limit)"),
    ("build_pop_sort.py", "cobertura: sortPOP vector/rev/seed/shift (/pop_sort)"),
    ("build_pop_neighbor.py", "cobertura: neighborPOP distancia + avg (/pop_neighbor)"),
    ("build_pop_connectivity.py", "cobertura: connectivityPOP tabla de prims (/pop_connectivity)"),
    ("build_pop_facet.py", "cobertura: facetPOP unique/cusp/conspoints (/pop_facet)"),
    ("build_pop_subdivide.py", "cobertura: subdividePOP escalado exacto (/pop_subdivide)"),
    ("build_pop_triangulate.py", "cobertura: triangulatePOP quads->tris (/pop_triangulate)"),
    ("build_pop_extrude.py", "cobertura: extrudePOP jaula + distance/axis (/pop_extrude)"),
    ("build_pop_pattern.py", "cobertura: patternPOP ramp/sin/random (/pop_pattern)"),
    ("build_pop_random.py", "cobertura: randomPOP add/set/gaussian/extrapts (/pop_random)"),
    ("build_pop_group.py", "cobertura 5c: groupPOP (población inmutable, thin, debugcolor, secuencias) (/pop_group)"),
    ("build_pop_proximity.py", "cobertura 5c: proximityPOP (grafo exacto por distancia) (/pop_proximity)"),
    ("build_pop_revolve.py", "cobertura 5c: revolvePOP (perfil→vaso, radios exactos, surftype) (/pop_revolve)"),
    ("build_pop_tube.py", "cobertura 5c: tubePOP (malla exacta, cono radx→rady, endcaps) (/pop_tube)"),
    ("build_pop_topology.py", "cobertura 5c: topologyPOP (topología de B sobre puntos de A) (/pop_topology)"),
    ("build_pop_lookuptexture.py", "cobertura 5c: lookuptexturePOP (muestreo de TOP sobre puntos) (/pop_lookup)"),
    ("build_pop_line.py", "cobertura: linePOP subdivisión exacta, closed y ctrlpoints (/pop_line)"),
    ("build_pop_curve.py", "cobertura: curvePOP + lineresamplePOP + linemetricsPOP (/pop_curve)"),
    ("build_pop_field_vectors.py", "cobertura: fieldPOP + curl3d + SDF analítico + confinamiento (/pop_field_vectors)"),
    ("build_pop_twist.py", "cobertura: twistPOP + bend/shear/squash + conservación radial y confinamiento (/pop_twist)"),
    ("build_pop_analytics_cull.py", "cobertura: analyzePOP + accumulatePOP + deletePOP (/pop_analytics_cull)"),
    ("build_pop_blend.py", "cobertura: blendPOP + cacheblendPOP + morphing baricéntrico (/pop_blend)"),
    ("build_monitor_pop.py", "monitor GPU: heatmap de P.y sobre la nube (/pop_sim_trails)"),
]


def main() -> int:
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("GAUNTLET_RUN_ID", time.strftime("reg-%Y%m%d-%H%M%S"))

    resultados = []
    t0 = time.monotonic()
    for i, (script, label) in enumerate(BATERIA, 1):
        print("\n" + "=" * 72)
        print("[%d/%d] %s — %s" % (i, len(BATERIA), script, label))
        print("=" * 72, flush=True)
        t1 = time.monotonic()
        proc = subprocess.run([sys.executable, os.path.join(HERE, script)],
                              cwd=HERE, env=env)
        dt = time.monotonic() - t1
        resultados.append((script, proc.returncode, dt))
        print("--> %s: exit %d (%.1f s)" % (script, proc.returncode, dt), flush=True)
        if proc.returncode != 0:
            print("\n*** FALLÓ %s — la batería continúa con el resto para informe completo "
                  "(el exit final será 1) ***" % script, flush=True)

    total = time.monotonic() - t0
    print("\n" + "=" * 72)
    print("RESUMEN de la batería (%.1f s total)" % total)
    print("=" * 72)
    fallados = 0
    for script, rc, dt in resultados:
        marca = "PASS" if rc == 0 else "FAIL"
        if rc != 0:
            fallados += 1
        print("  %-4s %-34s %6.1f s" % (marca, script, dt))
    print("\n%d/%d builds verdes" % (len(resultados) - fallados, len(resultados)))
    return 1 if fallados else 0


if __name__ == "__main__":
    sys.exit(main())

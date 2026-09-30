#!/usr/bin/env python3
"""build_monitor_pop.py (v4) — monitor GPU: heatmap de P.y (cuantil REAL del buffer).

La textura del poptoTOP trae valores CRUDOS (r=P.x, g=P.y, b=P.z) y alpha=flag de vivo:
los slots muertos del trail llegan como (0,0,0,0) y diluyen cualquier estadística del buffer
COMPLETO — la fracción se mide ENTRE VIVOS (máscara en el shader y en la medición). El rango
lo fija el cuantil del buffer vivo (del poptoCHOP src, gratis); uFrac es un umbral sobre el
valor NORMALIZADO (no un percentil), así que los extremos saturan (0.0 → ~0, 1.0 → ~1) y la
fracción a uFrac medio es LIBRE DE ESCALA (cambiar la gravedad no la mueve) pero SÍ ve los
cambios de demografía del buffer (post-reset sale de la banda): el monitor es sensor de estado.
"""
from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gauntlet_client import Gauntlet  # noqa: E402
from td_probe import chain_source  # noqa: E402

ROOT = "/pop_sim_trails"
CHAIN = chain_source(ROOT)
g = Gauntlet(phase="build-monitor-pop",
             run_id=os.environ.get("GAUNTLET_RUN_ID") or time.strftime("%Y%m%d-%H%M%S"))
g.init()

SHADER = """uniform float uLo;
uniform float uHi;
uniform float uFrac;

out vec4 fragColor;

void main()
{
    vec4 c = texture(sTD2DInputs[0], vUV.st);
    float alive = step(0.5, c.a);          // alpha = flag de vivo; slots muertos = todo cero
    float t = clamp((c.g - uLo) / max(uHi - uLo, 1e-5), 0.0, 1.0);
    float fallen = step(t, uFrac) * alive;
    fragColor = TDOutputSwizzle(vec4(fallen, 0.2 * (1.0 - fallen) * alive,
                                     0.8 * (1.0 - fallen) * alive, 1.0));
}
"""

report = {"run_id": os.environ.get("GAUNTLET_RUN_ID") or time.strftime("%Y%m%d-%H%M%S"),
          "objetivo": "monitor GPU: fraccion caida (poptoTOP→glslTOP, cuantil real del buffer)",
          "ok": False, "cheks": []}


def chek(name, ok, detail=""):
    report["cheks"].append((name, bool(ok)))
    g.check(name, ok, str(detail)[:240])


# ── 1. montar (shader con máscara PartId; attribscope 'P PartId') ──
ok, d = g.exec_code(CHAIN + """
import json
import time
data = op(ROOT + '/data')
if data is None:
    data = op(ROOT).create(poptoTOP, 'data')
data.par.pop = ROOT + '/geo/null_render'
data.par.attribscope = 'P PartId'
data.par.layout = 'onerow'
heat = op(ROOT + '/heat')
if heat is None:
    heat = op(ROOT).create(glslTOP, 'heat')
pix = op(ROOT + '/heat_pixel')
if pix is None:
    pix = op(ROOT).create(textDAT, 'heat_pixel')
pix.par.language = 'glsl'
pix.text = %s
heat.par.pixeldat = pix
if len(heat.inputs) == 0:
    data.outputConnectors[0].connect(heat)
heat.par.vec.sequence.numBlocks = 3
heat.par.vec0name = 'uLo'
heat.par.vec1name = 'uHi'
heat.par.vec2name = 'uFrac'
heat.par.vec2valuex = 0.2
src = op(ROOT + '/src')
if src is None:
    src = op(ROOT).create(poptoCHOP, 'src')
src.par.pop = ROOT + '/geo/null_render'
time.sleep(0.5)
for o in (op(ROOT + '/geo'), data, heat, src):
    o.cook(force=True)
print('<<JSON>>' + json.dumps(dict(err=str(heat.errors() or '')[:160],
                                   scope=str(data.par.attribscope.eval()),
                                   nsamples=src.numSamples)))
""" % (repr(SHADER),))
montaje = d if ok else {}
chek("monitor montado (máscara alpha-vivo, onerow, src CHOP)", montaje.get("err") == ""
     and "PartId" in str(montaje.get("scope", "")) and (montaje.get("nsamples") or 0) > 0, montaje)


def medir(label, ufrac=0.2):
    """Rango por cuantil REAL del buffer y fracción 'caída' clasificada en GPU."""
    ok, d = g.exec_code(CHAIN + """
import json
import time
src = op(ROOT + '/src')
src.cook(force=True)
vals = None
for c in src.chans():
    if c.name == 'P_1':
        vals = sorted(c.vals)
if not vals:
    print('<<JSON>>' + json.dumps(dict(err='sin P_1')))
else:
    n = len(vals)
    lo = vals[int(0.02 * (n - 1))] - 0.02
    hi = vals[int(0.98 * (n - 1))] + 0.02    # cuantiles del buffer vivo (el CHOP no trae muertos)
    heat = op(ROOT + '/heat')
    heat.par.vec0valuex = lo - 0.02
    heat.par.vec1valuex = hi + 0.02
    heat.par.vec2valuex = %r
    time.sleep(0.1)
    for o in (op(ROOT + '/data'), heat):
        o.cook(force=True)
    time.sleep(0.1)
    heat.cook(force=True)
    arr = heat.numpyArray()
    sel = arr[:, :, :3].reshape(-1, 3)
    # en el OUTPUT: rojo=caído (implícitamente vivo), azul=vivo, negro=slot muerto
    alive = (sel[:, 2] > 0.1) | (sel[:, 0] > 0.5)
    n_alive = int(alive.sum())
    warm = int((sel[:, 0] > 0.5).sum())
    total = int(len(sel))
    frac = round(warm / float(n_alive), 4) if n_alive else None
    print('<<JSON>>' + json.dumps(dict(wh=[int(arr.shape[1]), int(arr.shape[0])], total=total,
                                       n_alive=n_alive, lo=round(lo, 2), hi=round(hi, 2),
                                       warm_frac=frac)))
""" % (ufrac,))
    print("   [%s] %s" % (label, json.dumps(d)))
    return d if ok else {}


# ── 2. correlación con uFrac + estabilidad entre estados ──
time.sleep(1.5)
c00 = medir("uFrac=0.0", ufrac=0.0)
c09 = medir("uFrac=1.0", ufrac=1.0)
w1 = medir("estado 1 (g=-6, uFrac=0.2)")
w1b = medir("estado 1 a uFrac=0.8", ufrac=0.8)
ok, d = g.exec_code("""
import json
import time
gv = op('%s/geo/grav')
gv.par.globforcey = -12
time.sleep(2.0)
print('<<JSON>>' + json.dumps(dict(fy=gv.par.globforcey.eval())))
""" % ROOT)
w2 = medir("estado 2 (g=-12, uFrac=0.2)")
ok, d = g.exec_code("""
import json
import time
gv = op('%s/geo/grav')
gv.par.globforcey = -6
op('%s/geo/tr').par.reset.pulse()
time.sleep(1.5)
print('<<JSON>>' + json.dumps(dict(fy=gv.par.globforcey.eval())))
""" % (ROOT, ROOT))
w3 = medir("estado 3 (reset, g=-6, uFrac=0.2)")

v00, v09 = c00.get("warm_frac"), c09.get("warm_frac")
v02, v08 = w1.get("warm_frac"), w1b.get("warm_frac")
vals = [w.get("warm_frac") for w in (w1, w2, w3)]
n_alive = [w.get("n_alive") for w in (w1, w2, w3)]
whs = [tuple(w.get("wh") or ()) for w in (w1, w2, w3)]
report["mediciones"] = {"u00": v00, "u09": v09, "u02": v02, "u08": v08,
                        "estados_u02": vals, "n_alive": n_alive, "wh": whs}
# uFrac es umbral sobre el valor NORMALIZADO (no percentil): los extremos saturan y la respuesta
# intermedia se mide DENTRO de un mismo estado (inmune a la deriva demográfica del buffer).
# La fracción es ENTRE VIVOS (máscara alpha) — los slots muertos del trail diluyen el buffer
# completo, y el piso de uFrac=0.0 no llega a 0 porque el trail repite posiciones viejas.
chek("extremos saturan (uFrac=0.0 → <0.15, uFrac=1.0 → >0.85 entre vivos)",
     v00 is not None and v09 is not None and v00 < 0.15 and v09 > 0.85,
     {"u00": v00, "u09": v09})
chek("respuesta intermedia en un mismo estado (warm(0.8) > 2.5× warm(0.2))",
     v02 is not None and v08 is not None and v08 > max(2.5 * v02, 0.25),
     {"u02": v02, "u08": v08})
chek("calibración libre de escala (g=-6 vs g=-12: |Δ| < 0.03 a uFrac=0.2)",
     vals[0] is not None and vals[1] is not None and abs(vals[0] - vals[1]) < 0.03,
     {"g-6": vals[0], "g-12": vals[1]})
# La firma del reset es conjunta: cae la población viva (ratio < 0.6) Y la fracción sale de
# la banda madura por arriba — dos canales independientes del mismo monitor.
reset_visto = (n_alive[2] is not None and all(n_alive[:2])
               and n_alive[2] < 0.6 * (n_alive[0] + n_alive[1]) / 2.0
               and vals[2] is not None and vals[0] is not None and vals[1] is not None
               and vals[2] > max(vals[0], vals[1]) + 0.02)
chek("el monitor detecta el reset (cae n_alive < 0.6× Y sale de la banda)", reset_visto,
     {"reset": vals[2], "madura": max(vals[0], vals[1]), "n_alive": n_alive})
chek("el buffer vive (la textura cambia de tamaño entre estados)", len(set(whs)) >= 2, {"wh": whs})

# ── 3. la red canónica intacta ──
ok, d = g.exec_code(CHAIN + """
import json
term = op(ROOT + '/geo/null_render')
gv = op(ROOT + '/geo/grav')
settle(3)
print('<<JSON>>' + json.dumps(dict(fy=gv.par.globforcey.eval(), px=px(),
                                   term_rend=bool(term.render))))
""")
chek("red canonica intacta (terminal dibuja, g=-6)", ok and d.get("fy") == -6
     and (d.get("px") or 0) > 500 and d.get("term_rend") is True, d)

report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-monitor-pop-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print("\n=== RESUMEN monitor ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| fallos:", g.failures)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

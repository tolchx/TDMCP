#!/usr/bin/env python3
"""build_pop_sort.py — cobertura POP 4/6: sortPOP.

contratos que este build mide (evidencia: results/<run>/build-pop-sort-report.json):
  * sprinkle crudo viene desordenado (P_0 con >50 descensos consecutivos).
  * ptmethod='vector' con dir=(1,0,0) REORDENA EL BUFFER: 0 descensos y el
    multiset de valores preservado (misma nube, otro orden). OJO: conviene
    escribir pointdirx/y/z explícitos y releerlos (C4).
  * pointrev invierte: el orden ascendente pasa a descendente.
  * ptmethod='seed' es determinístico (dos lecturas iguales), cambia con la
    semilla (3 vs 9) y preserva el multiset (permutación, no otra nube).
  * pointshift+offset permuta reversiblemente: distinto del orden sin shift,
    mismo multiset, y al desactivar vuelve exactamente el orden anterior.
  * NO verificado acá: 'prox' (no produjo orden por distancia en nuestra
    medición exploratoria) y 'object'; quedan fuera de los checks.
"""
from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gauntlet_client import Gauntlet  # noqa: E402
from td_probe import chain_source, png_stats, set_and_verify  # noqa: E402

RUN = os.environ.get("GAUNTLET_RUN_ID") or time.strftime("%Y%m%d-%H%M%S")
g = Gauntlet(phase="build-pop-sort", run_id=RUN)
g.init()

ROOT = "/pop_sort"
CHAIN = chain_source(ROOT)

report = {"run_id": RUN,
          "objetivo": "sortPOP: vector ordena el buffer (0 descensos), reverse, seed "
                      "determinístico, shift reversible",
          "ok": False, "cheks": []}


def chek(name, ok, detail=""):
    report["cheks"].append((name, bool(ok)))
    g.check(name, ok, str(detail)[:240])


LECTURA = """
def chans(pop):
    chk.par.pop = pop
    settle(2)
    chk.cook(force=True)
    time.sleep(0.2)
    chk.cook(force=True)
    time.sleep(0.1)
    chk.cook(force=True)
    return {c.name: list(c.vals) for c in chk.chans()}


def p0(pop):
    return chans(pop).get('P_0', [])


def descs(v):
    return sum(1 for a, b in zip(v, v[1:]) if b < a - 1e-5)


def ascs(v):
    return sum(1 for a, b in zip(v, v[1:]) if b > a + 1e-5)
"""

# ── 0. entorno limpio + estructura ──
g.call("project_info", {}, note="TD vivo")
ok, d = g.exec_code("import json\ntry:\n op('%s').destroy()\nexcept Exception:\n pass\n"
                    "print('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
chek("limpieza previa", ok)

g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_sort",
                              "nodeX": -2000, "nodeY": 2600, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"}, {"type": "cameraCOMP", "name": "cam"},
    {"type": "renderTOP", "name": "ren"}, {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True}, note="estructura")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 1. cadena toro→sprinkle(300)→sort + base desordenada ──
ok, d = g.exec_code(CHAIN + """
import json
import time
geo = op(ROOT + '/geo')
for c in list(geo.children):
    if c.name.lower().startswith('torus'):
        c.destroy()
toro = geo.create(torusPOP, 'toro')
spr = geo.create(sprinklePOP, 'spr')
srt = geo.create(sortPOP, 'srt')
spr.inputConnectors[0].connect(toro.outputConnectors[0])
srt.inputConnectors[0].connect(spr.outputConnectors[0])
toro.par.radx = 2.2
toro.par.rady = 2.2
toro.par.scale = 0.55
spr.par.numpoints = 300
srt.display = True
srt.render = True
chk = op(ROOT + '/check')
""" + LECTURA + """
base = p0(spr)
print('<<JSON>>' + json.dumps(dict(n=len(base), descs=descs(base),
                                   re_numpoints=spr.par.numpoints.eval())))
""")
chek("sprinkle crudo desordenado (n=300, descensos > 50)",
     ok and (d.get("n") or 0) == 300 and (d.get("descs") or 0) > 50, d)
report["base"] = d

# ── 2. vector (1,0,0): buffer PERFECTAMENTE ascendente, multiset preservado ──
ok, d = g.exec_code(CHAIN + """
import json
import time
srt = op(ROOT + '/geo/srt')
chk = op(ROOT + '/check')
""" + LECTURA + """
spr = op(ROOT + '/geo/spr')
base = p0(spr)
srt.par.ptmethod = 'vector'
srt.par.pointdirx = 1.0
srt.par.pointdiry = 0.0
srt.par.pointdirz = 0.0
vec = p0(srt)
print('<<JSON>>' + json.dumps(dict(n=len(vec), descs=descs(vec), ascs=ascs(vec),
                                   multiset=(sorted(vec) == sorted(base)),
                                   re_dir=[srt.par.pointdirx.eval(), srt.par.pointdiry.eval(),
                                           srt.par.pointdirz.eval()],
                                   re_method=str(srt.par.ptmethod.eval()))))
""")
chek("vector dir=(1,0,0) releejo (C4) y ordena el buffer: 0 descensos",
     ok and d.get("re_dir") == [1.0, 0.0, 0.0] and d.get("descs") == 0
     and (d.get("ascs") or 0) > 250, d)
chek("el multiset se preserva (misma nube, otro orden)",
     ok and d.get("multiset") is True, d)
report["vector"] = d

# ── 3. reverse: ascendente → descendente y reversible ──
ok, d = g.exec_code(CHAIN + """
import json
import time
srt = op(ROOT + '/geo/srt')
chk = op(ROOT + '/check')
""" + LECTURA + """
srt.par.ptmethod = 'vector'
srt.par.pointdirx = 1.0
srt.par.pointdiry = 0.0
srt.par.pointdirz = 0.0
srt.par.pointrev = False
orden = p0(srt)
srt.par.pointrev = True
rev = p0(srt)
srt.par.pointrev = False
vuelta = p0(srt)
print('<<JSON>>' + json.dumps(dict(descs_rev=descs(rev), ascs_rev=ascs(rev),
                                   reversible=(vuelta == orden))))
""")
chek("pointrev invierte el orden (0 ascensos, >250 descensos) y es reversible",
     ok and d.get("ascs_rev") == 0 and (d.get("descs_rev") or 0) > 250
     and d.get("reversible") is True, d)
report["rev"] = d

# ── 4. seed: determinístico, cambia con semilla, permuta el multiset ──
ok, d = g.exec_code(CHAIN + """
import json
import time
srt = op(ROOT + '/geo/srt')
chk = op(ROOT + '/check')
""" + LECTURA + """
srt.par.ptmethod = 'seed'
srt.par.pointseed = 3.0
s1 = p0(srt)
s2 = p0(srt)
srt.par.pointseed = 9.0
s3 = p0(srt)
srt.par.ptmethod = 'vector'
srt.par.pointdirx = 1.0
orden = p0(srt)
srt.par.pointshift = True
srt.par.pointoffset = 5
sh = p0(srt)
srt.par.pointshift = False
vuelta = p0(srt)
print('<<JSON>>' + json.dumps(dict(
    n=len(s1), deterministico=(s1 == s2), cambia_seed=(s1 != s3),
    multiset_seed=(sorted(s1) == sorted(s3)),
    descs_seed=descs(s1),
    shift_distinto=(sh != orden), shift_multiset=(sorted(sh) == sorted(orden)),
    shift_reversible=(vuelta == orden))))
""")
chek("seed determinístico (2 lecturas iguales) y cambia con la semilla (3≠9)",
     ok and d.get("deterministico") is True and d.get("cambia_seed") is True, d)
chek("seed preserva el multiset (permutación) y NO ordena por x (sigue desordenado)",
     ok and d.get("multiset_seed") is True and (d.get("descs_seed") or 0) > 50, d)
chek("pointshift permuta reversiblemente (distinto, mismo multiset, vuelve exacto)",
     ok and d.get("shift_distinto") is True and d.get("shift_multiset") is True
     and d.get("shift_reversible") is True, d)
report["seed_shift"] = d

# ── 5. material + cámara + PNG + guardia ──
g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "pointspriteMAT", "name": "mat"},
          note="material")
bad, got = set_and_verify(g, ROOT + "/geo/mat", {"pointsize": 4.0, "colorr": 1.0, "colorg": 0.85, "colorb": 0.2},
                          "material dorado")
chek("pars del material aplicados (C4)", not bad, got)
ok, d = g.exec_code(CHAIN + """
import json
import time
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
geo.par.material = geo.op('mat')
chk = op(ROOT + '/check')
chk.par.pop = op(ROOT + '/geo/srt')
settle(3)
chk.cook(force=True)
medios = {}
for c in chk.chans():
    if c.name in ('P_0', 'P_1', 'P_2'):
        medios[c.name] = (min(c.vals) + max(c.vals)) / 2
cam.par.tx = round(medios.get('P_0', 0.0), 2)
cam.par.ty = round(medios.get('P_1', 0.0), 2)
cam.par.tz = round(medios.get('P_2', 0.0) + 8.0, 2)
ren.par.geometry = geo
ren.par.camera = cam
settle(3)
print('<<JSON>>' + json.dumps(dict(mat=str(geo.par.material.eval()),
                                   centro={k: round(v, 2) for k, v in medios.items()})))
""")
chek("material + cámara al dato", ok and "mat" in str(d.get("mat", ""))
     and len((d.get("centro") or {})) == 3, d)
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_sort.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

ok, d = g.exec_code(CHAIN + """
import json
import time
srt = op(ROOT + '/geo/srt')
settle(3)
time.sleep(1.5)
antes = px()
print('<<JSON>>' + json.dumps(dict(px_antes=antes, guardia=list(render_is_ours(srt)))))
""")
d = d or {}
guardia = d.get("guardia") or []
chek("el render subió la geometría (px > 0 antes de la guardia)", (d.get("px_antes") or 0) > 0,
     {"px": d.get("px_antes")})
chek("los px son del sort (guardia: apagar el terminal → 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-sort-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_sort ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| fallos:", g.failures)
print("vector:", json.dumps((report.get("vector") or {}), ensure_ascii=False)[:220])
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

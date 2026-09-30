#!/usr/bin/env python3
"""build_pop_field_trails.py — octavo proyecto POP: campo de estelas DIRECTO
(surftype='points', sin convertPOP) coloreado por la velocidad del campo con
attributePOP + rerangePOP — CERO glsl.

Receta (C9 campo 4D + C8 trail directo + C11 attributePOP/rerangePOP):
  toro (r=2.2, tubo scale 0.55) → spr (sprinkle 3000)
    → ruido (noisePOP simplex4d amp 0.4 + gradient=True: escribe NoiseGradient_0..3,
             el vector del campo POR PUNTO — la "velocidad" de un campo sin sim)
    → tint (attributePOP: CREA Color float4 — C11: attributePOP_no_mapea crea constantes)
    → rr (rerangePOP: mapea NoiseGradient → Color, inputattrscope/outputattrscope +
          fromlow0/fromhigh0 → tolow0/tohigh0 — cierra el [V*] de rerangePOP_mapea)
    → tr (trailPOP DIRECTO: surftype='points' + flags en el propio trail, sin convertPOP
          — C8: 1 sprite por sample, numPrims()==numPoints() 1:1)
  La animación del campo va por t4d ESCALONADO A MANO (C9: el reloj no corre en
  execute_code); las estelas acumulan el historial de las posiciones del campo.

Gradables: t4d mueve la nube (P cambia), NoiseGradient spanea, Color aparece y
CORRELACIONA por componente con NoiseGradient (numpy), el trail acumula historial al
escalonar t4d, el campo pinta (amp ↑ → Color_0 media ↑), render propio por guardia.
"""
from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gauntlet_client import Gauntlet  # noqa: E402
from td_probe import chain_source, png_stats  # noqa: E402

RUN = os.environ.get("GAUNTLET_RUN_ID") or time.strftime("%Y%m%d-%H%M%S")
g = Gauntlet(phase="build-pop-field-trails", run_id=RUN)
g.init()

ROOT = "/pop_field_trails"
CHAIN = chain_source(ROOT)

report = {"run_id": RUN,
          "objetivo": "campo de estelas directo (surftype=points) coloreado por la velocidad "
                      "del campo con attributePOP+rerangePOP — cero glsl, cero convertPOP",
          "ok": False, "cheks": []}


def chek(name, ok, detail=""):
    report["cheks"].append((name, bool(ok)))
    g.check(name, ok, str(detail)[:240])


# ── 0. entorno limpio ──
g.call("project_info", {}, note="TD vivo")
ok, d = g.exec_code("import json\ntry:\n op('%s').destroy()\nexcept Exception:\n pass\n"
                    "print('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
chek("limpieza previa", ok)

# ── 1. estructura + cadena del campo ──
g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_field_trails",
                              "nodeX": -2400, "nodeY": 2100, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"},
    {"type": "cameraCOMP", "name": "cam"},
    {"type": "renderTOP", "name": "ren"},
    {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True},
    note="estructura geo+render+check")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")
g.call_ok("build_network", {"parent_path": ROOT + "/geo", "operators": [
    {"type": "torusPOP", "name": "toro"},
    {"type": "sprinklePOP", "name": "spr"},
    {"type": "noisePOP", "name": "ruido"},
    {"type": "attributePOP", "name": "tint"},
    {"type": "rerangePOP", "name": "rr"},
    {"type": "trailPOP", "name": "tr"}],
    "connections": [{"from": "toro", "to": "spr"}, {"from": "spr", "to": "ruido"},
                    {"from": "ruido", "to": "tint"}, {"from": "tint", "to": "rr"},
                    {"from": "rr", "to": "tr"}],
    "auto_layout": True}, note="cadena del campo sin glsl ni convertPOP")

# ── 2. auto-torus fuera ──
ok, d = g.exec_code(CHAIN + """
import json
geo = op(ROOT + '/geo')
borrados = list()
for c in list(geo.children):
    if c.name.lower().startswith('torus'):
        c.destroy()
        borrados.append(c.name)
print('<<JSON>>' + json.dumps(dict(borrados=borrados)))
""")
chek("auto-torus borrado", ok and len(d.get("borrados") or []) == 1, d)

# ── 3. parámetros del campo (C9: radx/rady + scale; simplex4d; gradient ON) ──
ok, d = g.exec_code(CHAIN + """
import json
import time
geo = op(ROOT + '/geo')
toro, spr, ruido = geo.op('toro'), geo.op('spr'), geo.op('ruido')
tint, rr, tr = geo.op('tint'), geo.op('rr'), geo.op('tr')
toro.par.radx = 2.2
toro.par.rady = 2.2
toro.par.scale = 0.55
spr.par.numpoints = 3000
ruido.par.type = 'simplex4d'
ruido.par.amp = 0.4
ruido.par.t4d = 0.0
ruido.par.gradient = True    # escribe NoiseGradient_0..3 (el vector del campo por punto)
ruido.par.curl3d = False
ruido.par.curl2d = False
tr.par.lengthunit = 'frames'
tr.par.length = 16
tr.par.surftype = 'points'   # TRAIL DIRECTO: 1 sprite por sample, sin convertPOP (C8)
tr.display = True
tr.render = True
time.sleep(0.3)
settle(3)
print('<<JSON>>' + json.dumps(dict(tubo=toro.par.scale.eval(), n=spr.par.numpoints.eval(),
                                   tipo=ruido.par.type.eval(), amp=ruido.par.amp.eval(),
                                   grad=bool(ruido.par.gradient.eval()),
                                   st=str(tr.par.surftype.eval()),
                                   ln=tr.par.length.eval(), rend=bool(tr.render))))
""")
chek("campo aplicado (toro, 3000 pts, simplex4d+gradient, trail directo points)",
     ok and d.get("tubo") == 0.55 and d.get("n") == 3000 and d.get("tipo") == "simplex4d"
     and d.get("grad") is True and d.get("st") == "points" and d.get("rend") is True, d)

# ── 4. CERO glsl y CERO convertPOP (estructural, todo el árbol) ──
ok, d = g.exec_code(CHAIN + """
import json
tipos = {}
for o in op(ROOT).children:
    tipos[o.OPType] = tipos.get(o.OPType, 0) + 1
    for c in o.children:
        tipos[c.OPType] = tipos.get(c.OPType, 0) + 1
prohibidos = [t for t in tipos if t in ('glslPOP', 'convertPOP', 'glslTOP')]
print('<<JSON>>' + json.dumps(dict(tipos=tipos, prohibidos=prohibidos)))
""")
chek("cero glsl y cero convertPOP en toda la red (estructural)",
     ok and not d.get("prohibidos") and d.get("tipos", {}).get("trailPOP") == 1, d)

# ── 5. el campo mueve los puntos (C9: t4d escalonado a mano) ──
chk = op_chk = None
ok, d = g.exec_code(CHAIN + """
import json
import time
ruido = op(ROOT + '/geo/ruido')
chk = op(ROOT + '/check')
chk.par.pop = op(ROOT + '/geo/tr')
chk.cook(force=True)
time.sleep(0.2)
chk.cook(force=True)


def nube():
    for c in chk.chans():
        if c.name == 'P_0':
            return sorted(round(v, 4) for v in c.vals)[:200]
    return []


ruido.par.t4d = 0.0
chk.cook(force=True)
time.sleep(0.15)
chk.cook(force=True)
a = nube()
ruido.par.t4d = 3.5
chk.cook(force=True)
time.sleep(0.15)
chk.cook(force=True)
b = nube()
print('<<JSON>>' + json.dumps(dict(iguales=(a == b), n=len(a), cambian=sum(1 for x, y in zip(a, b) if abs(x - y) > 1e-4))))
""")
chek("el campo mueve los puntos (t4d 0 → 3.5 cambia la nube, C9)",
     ok and d.get("iguales") is False and (d.get("cambian") or 0) > 20, d)
ruido_t4d_reset = g.exec_code("import json\nop('%s/geo/ruido').par.t4d = 0.0\n"
                              "print('<<JSON>>' + json.dumps({'t4d': 0}))" % ROOT)

# ── 6. NoiseGradient existe y spanea (la velocidad del campo, sin sim) ──
ok, d = g.exec_code(CHAIN + """
import json
import time
rr = op(ROOT + '/geo/rr')
chk = op(ROOT + '/check')
chk.par.pop = rr          # ANTES del rerange: los spans crudos del gradiente
chk.cook(force=True)
time.sleep(0.25)
chk.cook(force=True)
ch = {}
for c in chk.chans():
    if c.name.startswith('NoiseGradient'):
        ch[c.name] = [round(min(c.vals), 3), round(max(c.vals), 3)]
print('<<JSON>>' + json.dumps(ch))
""")
grad_spans = d if ok else {}
report["gradient_spans"] = grad_spans
chek("NoiseGradient existe y spanea (vector del campo por punto)",
     all(k in grad_spans for k in ("NoiseGradient_0", "NoiseGradient_1", "NoiseGradient_2"))
     and max(abs(grad_spans[k][1] - grad_spans[k][0]) for k in grad_spans if k.startswith("NoiseGradient_")) > 0.1,
     grad_spans)

# ── 7. attributePOP CREA Color + rerangePOP mapea NoiseGradient → Color ──
ok, d = g.exec_code(CHAIN + """
import json
import time
geo = op(ROOT + '/geo')
tint, rr = geo.op('tint'), geo.op('rr')
# attributePOP: crea Color float4 (C11: crea constantes; acá sólo la PLANTILLA del attr)
tint.par.attr.sequence.numBlocks = 1
tint.par.attr0name = 'color'
tint.par.attr0numcomps = '4'
tint.par.attr0value0 = 0.5
tint.par.attr0value1 = 0.5
tint.par.attr0value2 = 0.5
tint.par.attr0value3 = 1.0
# rerangePOP: mapea NoiseGradient → Color (pars REALES: scopes + rangos escalares)
rr.par.inputattrscope = 'NoiseGradient'
rr.par.outputattrscope = 'Color'
rr.par.fromlow0 = -0.5
rr.par.fromhigh0 = 0.5
rr.par.tolow0 = 0.0
rr.par.tohigh0 = 1.0
rr.par.attrnumcomps = '4'
time.sleep(0.3)
settle(3)
chk = op(ROOT + '/check')
chk.par.pop = rr
chk.cook(force=True)
time.sleep(0.25)
chk.cook(force=True)
rb = dict(tint_name=str(tint.par.attr0name.eval()), rr_in=str(rr.par.inputattrscope.eval()),
          rr_out=str(rr.par.outputattrscope.eval()),
          fl=rr.par.fromlow0.eval(), fh=rr.par.fromhigh0.eval(), tl=rr.par.tolow0.eval(),
          th=rr.par.tohigh0.eval())
print('<<JSON>>' + json.dumps(rb))
""")
chek("attributePOP crea Color + rerangePOP configurado (scopes y rangos reales)",
     ok and d.get("rr_in") == "NoiseGradient" and d.get("rr_out") == "Color"
     and d.get("fl") == -0.5 and d.get("th") == 1.0, d)

# ── 8. EL CHECK CLAVE: Color correlaciona por componente con NoiseGradient (cierra C11 [V*]) ──
ok, d = g.exec_code(CHAIN + """
import json
import time
chk = op(ROOT + '/check')
chk.par.pop = op(ROOT + '/geo/rr')
chk.cook(force=True)
time.sleep(0.3)
chk.cook(force=True)
ch = {}
for c in chk.chans():
    ch[c.name] = list(c.vals)
out = {}
if all(k in ch for k in ('NoiseGradient_0', 'NoiseGradient_1', 'NoiseGradient_2',
                         'Color_0', 'Color_1', 'Color_2')):
    import math
    n = min(len(ch[k]) for k in ('NoiseGradient_0', 'Color_0'))
    corrs = {}
    for i in range(3):
        x = ch['NoiseGradient_%d' % i][:n]
        y = ch['Color_%d' % i][:n]
        mx, my = sum(x) / n, sum(y) / n
        sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
        sxx = math.sqrt(sum((a - mx) ** 2 for a in x))
        syy = math.sqrt(sum((b - my) ** 2 for b in y))
        corrs[i] = round(sxy / (sxx * syy), 4) if sxx > 1e-6 and syy > 1e-6 else None
    out['corr'] = corrs
    out['color_spans'] = {k: [round(min(ch[k]), 3), round(max(ch[k]), 3)]
                          for k in ('Color_0', 'Color_1', 'Color_2') if k in ch}
    out['alpha'] = [round(min(ch['Color_3']), 3), round(max(ch['Color_3']), 3)] if 'Color_3' in ch else None
    out['n'] = n
print('<<JSON>>' + json.dumps(out))
""")
corr = (d or {}).get("corr") or {}
report["rerange_corr"] = d
# las claves del JSON viajan como strings
buenos = [corr.get(str(i), corr.get(i)) for i in range(3)]
chek("rerangePOP mapea por componente (corr(NoiseGradient_i, Color_i) > 0.8, cierra C11 [V*])",
     all(c is not None and abs(c) > 0.8 for c in buenos),
     {"corr": corr, "color_spans": (d or {}).get("color_spans")})

# ── 9. material + cámara al dato + guardia: el trail directo dibuja y es NUESTRO ──
g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "pointspriteMAT", "name": "mat"},
          note="material de sprites")
ok, d = g.exec_code(CHAIN + """
import json
import time
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
m = op(ROOT + '/geo/mat')
m.par.pointsize = 3.0
m.par.colorr = 1.0
m.par.colorg = 1.0
m.par.colorb = 1.0    # BLANCO: multiplica el Color por punto del rerange (C11)
geo.par.material = m
tr = geo.op('tr')
chk = op(ROOT + '/check')
chk.par.pop = tr
settle(3)
chk.cook(force=True)
medios = []
for c in chk.chans():
    if c.name == 'P_0':
        medios.append((min(c.vals) + max(c.vals)) / 2)
    elif c.name == 'P_1':
        medios.append((min(c.vals) + max(c.vals)) / 2)
    elif c.name == 'P_2':
        medios.append((min(c.vals) + max(c.vals)) / 2)
cam.par.tx = round(medios[0], 2)
cam.par.ty = round(medios[1], 2)
cam.par.tz = round(medios[2] + 9.0, 2)
ren.par.geometry = geo
ren.par.camera = cam
settle(3)
print('<<JSON>>' + json.dumps(dict(mat=str(geo.par.material.eval()),
                                   centro_P=[round(v, 2) for v in medios])))
""")
chek("material blanco + camara al dato + bindings", ok and "mat" in str(d.get("mat", ""))
     and len(d.get("centro_P") or []) == 3, d)

# la GUARDIA va al FINAL (bloque 14): la red lleva más wall-time viva y el render ya subió la
# geometría; el calentamiento agresivo dentro de una sola llamada agota a TD ('recovering from
# a slow operation').

# ── 10. trail directo 1:1 ──
ok, d = g.exec_code(CHAIN + """
import json
import time
tr = op(ROOT + '/geo/tr')
settle(4)
tr.cook(force=True)
time.sleep(0.2)
tr.cook(force=True)
print('<<JSON>>' + json.dumps(dict(prims=tr.numPrims(), pts=tr.numPoints(),
                                   err=str(op(ROOT + '/geo').errors() or '')[:120])))
""")
chek("trail directo 1:1 (numPrims == numPoints > 0, sin convertPOP)",
     ok and d.get("prims", 0) == d.get("pts", 1) and d.get("prims", 0) > 0 and d.get("err") == "", d)

# ── 10. las estelas acumulan el historial del campo (t4d escalonado) ──
ok, d = g.exec_code(CHAIN + """
import json
import time
ruido = op(ROOT + '/geo/ruido')
chk = op(ROOT + '/check')
chk.par.pop = op(ROOT + '/geo/tr')
ruido.par.t4d = 0.0
chk.cook(force=True)
time.sleep(0.2)
chk.cook(force=True)


def uniq_p0():
    for c in chk.chans():
        if c.name == 'P_0':
            return len(set(round(v, 3) for v in c.vals))
    return 0


u1 = uniq_p0()
ruido.par.t4d = 2.5
chk.cook(force=True)
time.sleep(0.2)
chk.cook(force=True)
u2 = uniq_p0()
ruido.par.t4d = 5.0
chk.cook(force=True)
time.sleep(0.2)
chk.cook(force=True)
u3 = uniq_p0()
print('<<JSON>>' + json.dumps(dict(uniq=[u1, u2, u3])))
""")
uniq = (d or {}).get("uniq") or [0, 0, 0]
chek("las estelas acumulan historial del campo (uniq de P_0 crece al escalonar t4d)",
     ok and uniq[0] > 0 and uniq[2] > uniq[0] * 1.3, {"uniq_P0": uniq})

# ── 11. el campo pinta (amp ↑ → gradiente más violento → Color_0 media cambia) ──
ok, d = g.exec_code(CHAIN + """
import json
import time
ruido = op(ROOT + '/geo/ruido')
chk = op(ROOT + '/check')
chk.par.pop = op(ROOT + '/geo/rr')
ruido.par.t4d = 0.0


def color0_mean():
    chk.cook(force=True)
    time.sleep(0.15)
    chk.cook(force=True)
    for c in chk.chans():
        if c.name == 'Color_0':
            return round(sum(c.vals) / len(c.vals), 4)
    return None


ruido.par.amp = 0.4
m_a = color0_mean()
ruido.par.amp = 0.9
m_b = color0_mean()
ruido.par.amp = 0.4
m_c = color0_mean()
print('<<JSON>>' + json.dumps(dict(amp_04=m_a, amp_09=m_b, vuelta=m_c)))
""")
ma, mb = (d or {}).get("amp_04"), (d or {}).get("amp_09")
chek("el campo pinta (media de Color_0 responde al amp del ruido)",
     ok and ma is not None and mb is not None and abs(mb - ma) > 0.02, d)

# ── 12. estado canónico + errores + evidencia visual ──
ok, d = g.exec_code(CHAIN + """
import json
ruido = op(ROOT + '/geo/ruido')
ruido.par.amp = 0.4
ruido.par.t4d = 0.0
print('<<JSON>>' + json.dumps(dict(amp=ruido.par.amp.eval(), t4d=ruido.par.t4d.eval())))
""")
chek("estado canónico restaurado (amp 0.4, t4d 0)", ok and d.get("amp") == 0.4 and d.get("t4d") == 0.0, d)
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_field_trails.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

# ── 14. guardia de propiedad del render (al final, red caliente) ──
ok, d = g.exec_code(CHAIN + """
import json
import time
tr = op(ROOT + '/geo/tr')
settle(3)
time.sleep(1.5)
antes = px()
print('<<JSON>>' + json.dumps(dict(px_antes=antes, guardia=list(render_is_ours(tr)))))
""")
d = d or {}
guardia = d.get("guardia") or []
chek("el render subio la geometria (px > 0 antes de la guardia)",
     (d.get("px_antes") or 0) > 0, {"px": d.get("px_antes")})
chek("los px son del trail directo (guardia: apagar el terminal → 0)",
     len(guardia) == 3 and guardia[0] is True and guardia[2] == 0, guardia)

# ── 13. cierre ──
report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-field-trails-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_field_trails ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| fallos:", g.failures)
print("gradient spans:", json.dumps(report.get("gradient_spans", {}), ensure_ascii=False)[:300])
print("rerange corr:", json.dumps((report.get("rerange_corr") or {}).get("corr", {}), ensure_ascii=False))
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

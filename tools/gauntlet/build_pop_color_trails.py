#!/usr/bin/env python3
"""build_pop_color_trails.py — sexto proyecto POP: ESTELAS con COLOR POR VELOCIDAD.

Basado en la skill `td-pop-trails-fields` (receta A de estelas, de /pop_streams) + C10
(loop de feedback de /pop_sim_trails) + C3 (glslPOP con textDAT hermano).

Pipeline (dentro del geometryCOMP):
  emit(spherePOP r=0.3) → sim(particlePOP) → grav(forceradialPOP) ─┬→ fb (nullPOP, targetpop)
                                      └→ curl(noisePOP) → shade(glslPOP) → tr(trailPOP)
                                          → topoints → null_render  + pointspriteMAT blanco

El color: el trailPOP NO tiene pars de color (contrato trailPOP_pars en C8) y el atributo de
render en POPs es `Color` float4 (no `Cd`, td-pop-family). `shade` (glslPOP) lo calcula desde
`PartVel`: t = clamp(|PartVel| * uSpeedScale) → mix(frío azul, caliente ámbar). Va ANTES del
trail: la estela re-hornea samples con el color que el punto tenía en cada frame → el historial
de velocidad queda pintado a lo largo del trail (gravedad acelera → gradiente frío→caliente).

Verificación (números antes que píxeles, C5):
  * Color presente y variando en el terminal (canales Color_* del poptoCHOP, rango > umbral).
  * Palanca `uSpeedScale` (0.4 → 0.15 en llamadas separadas + settle): la MEDIA de Color cambia.
  * El trail acumula el historial: n(terminal) >> n(shade) y MÁS valores de Color distintos.
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
g = Gauntlet(phase="build-pop-color-trails", run_id=RUN)
g.init()

ROOT = "/pop_color_trails"
GEO = ROOT + "/geo"
CHAIN = chain_source(ROOT)   # settle()/px()/render_is_ours() no se copian: se importan

# Patrón canónico del compute (C3): el main lo escribe NOSOTROS y `id` se declara con
# TDIndex() + guardia TDNumElements() — los buffers de atributos (PartVel/Color) y el uniform
# (vec auto-declarado) los expone el framework.
SHADER = """void main()
{
    const uint id = TDIndex();
    if (id >= TDNumElements())
        return;
    float v = length(TDIn_PartVel());
    float t = clamp(v * uSpeedScale, 0.0, 1.0);
    Color[id] = vec4(mix(vec3(0.15, 0.30, 1.0), vec3(1.0, 0.85, 0.25), t), 1.0);
}
"""

report = {"run_id": RUN,
          "objetivo": "estelas con color por velocidad (glsl Color desde PartVel, trail arrastra historial)",
          "ok": False, "cheks": []}


def chek(name, ok, detail=""):
    report["cheks"].append((name, bool(ok)))
    g.check(name, ok, str(detail)[:240])


COLOR_CHANS = ("Color_0", "Color_1", "Color_2")


def measure_color(label):
    """n + Color (min/max/media/únicos) del nodo shade Y del terminal, en UNA llamada."""
    ok, d = g.exec_code(CHAIN + """
import json
settle(4)
chk = op('%s/check')
out = dict()
for n in ('shade', 'term'):
    chk.par.pop = ('%s/geo/shade' if n == 'shade' else '%s/geo/null_render')
    chk.cook(force=True)
    m = dict()
    for c in chk.chans():
        if c.name in ('P_1',) + %r:
            vals = c.vals
            m[c.name] = dict(mn=round(min(vals), 3), mx=round(max(vals), 3),
                             mean=round(sum(vals) / max(len(vals), 1), 3),
                             uniq=len(set(round(v, 2) for v in vals)))
    m['n'] = chk.numSamples
    out[n] = m
chk.par.pop = '%s/geo/null_render'
print('<<JSON>>' + json.dumps(dict(out=out, t=round(absTime.seconds, 2))))
""" % (ROOT, ROOT, ROOT, COLOR_CHANS, ROOT))
    if not ok:
        print("    (medición falló: %s)" % json.dumps(d)[:200])
        return {}
    m = d.get("out") or {}
    print("    [%s] shade n=%s | term n=%s | Color_0 term=%s"
          % (label, (m.get("shade") or {}).get("n"), (m.get("term") or {}).get("n"),
             (m.get("term") or {}).get("Color_0")))
    return m


# ── 0. entorno limpio ──
g.call("project_info", {}, note="TD vivo")
ok, d = g.exec_code("import json\ntry:\n op('%s').destroy()\nexcept Exception:\n pass\n"
                    "print('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
chek("limpieza previa", ok)

# ── 1. estructura de render ──
g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_color_trails",
                              "nodeX": -1600, "nodeY": 900, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"},
    {"type": "cameraCOMP", "name": "cam"},
    {"type": "lightCOMP", "name": "light"},
    {"type": "renderTOP", "name": "ren"},
    {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True},
    note="estructura geo+render+check")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 2. auto-torus fuera ──
ok, d = g.exec_code("""
import json
geo = op('%s')
torus = [c.name for c in geo.children if c.name.lower().startswith('torus')]
for n in torus:
    geo.op(n).destroy()
print('<<JSON>>' + json.dumps({'had_torus': torus}))
""" % GEO)
chek("auto-torus borrado", ok and bool(d.get("had_torus")), d)

# ── 3. cadena POP: sim → fuerzas → curl → COLOR (glsl) → trail → prims; fb desde grav ──
g.call_ok("build_network", {"parent_path": GEO, "operators": [
    {"type": "spherePOP", "name": "emit"},
    {"type": "particlePOP", "name": "sim"},
    {"type": "forceradialPOP", "name": "grav"},
    {"type": "noisePOP", "name": "curl"},
    {"type": "glslPOP", "name": "shade"},
    {"type": "trailPOP", "name": "tr"},
    {"type": "convertPOP", "name": "topoints"},
    {"type": "nullPOP", "name": "null_render"},
    {"type": "nullPOP", "name": "fb"}],
    "connections": [{"from": "emit", "to": "sim"}, {"from": "sim", "to": "grav"},
                    {"from": "grav", "to": "curl"}, {"from": "curl", "to": "shade"},
                    {"from": "shade", "to": "tr"}, {"from": "tr", "to": "topoints"},
                    {"from": "topoints", "to": "null_render"}, {"from": "grav", "to": "fb"}],
    "auto_layout": True}, note="cadena sim+color+estelas con rama de feedback")

# ── 4. textDAT del shader (hermano, C3) + bind ANTES de uniforms ──
ok, d = g.exec_code("""
import json
geo = op('%s')
dat = geo.op('shade_dat') or geo.create(textDAT, 'shade_dat')
dat.par.language = 'glsl'
dat.text = %s
shade = geo.op('shade')
shade.par.computedat = dat
print('<<JSON>>' + json.dumps(dict(dat=str(dat.path), lang=str(dat.par.language.eval()),
                                   bound=str(shade.par.computedat.eval()))))
""" % (GEO, repr(SHADER)))
chek("textDAT hermano + computedat enlazado", ok and str(d.get("bound", "")).endswith("/shade_dat"), d)

# ── 5. parámetros de la cadena (después del bind: attr/vec/outputattrs, C3) ──
ok, d = g.exec_code("""
import json
emit, sim, gv = op('%s/emit'), op('%s/sim'), op('%s/grav')
curl, shade, tr = op('%s/curl'), op('%s/shade'), op('%s/tr')
sim.par.targetpop = op('%s/fb')
emit.par.radx = 0.3
emit.par.rady = 0.3
emit.par.radz = 0.3
sim.par.timeintegration = True
sim.par.birthrate = 60
sim.par.life = 1.2
sim.par.maxparticles = 2000
sim.par.initvelocityy = 0
sim.par.preroll = 0
gv.par.globforcemult = 1
gv.par.globforcey = -2
gv.par.radial = 0
gv.par.axial = 0
gv.par.spiral = 0
gv.par.planar = 0
curl.par.mode = 'quality'
curl.par.type = 'simplex3d'
curl.par.amp = 0.35
curl.par.offset = 0.0
curl.par.curl3d = True
# glsl: outputattrs declara la ESCRITURA; attr0 crea el atributo 'Color' (4 comps)
shade.par.outputattrs = 'Color'
shade.par.attr.sequence.numBlocks = 1
shade.par.attr0name = 'color'
shade.par.attr0numcomps = '4'
# uniform palanca (C3: nombre/valor por execute_code, DESPUES de enlazar el DAT)
shade.par.vec0name = 'uSpeedScale'
shade.par.vec0valuex = 0.4
# trail en FRAMES (contrato trailPOP_pars: length es tiempo, lengthunit ∈ {seconds, frames})
tr.par.lengthunit = 'frames'
tr.par.length = 16
tr.par.reset.pulse()
v = dict(target=str(sim.par.targetpop), fy=gv.par.globforcey.eval(), amp=curl.par.amp.eval(),
         oa=str(shade.par.outputattrs.eval()), attr=str(shade.par.attr0name.eval()),
         comps=str(shade.par.attr0numcomps.eval()), u=str(shade.par.vec0name.eval()),
         uval=round(shade.par.vec0valuex.eval(), 3),
         lu=str(tr.par.lengthunit.eval()), ln=tr.par.length.eval())
print('<<JSON>>' + json.dumps(v))
""" % (GEO, GEO, GEO, GEO, GEO, GEO, GEO))
chek("cadena aplicada (fb, g=-2, curl 3D, attr Color 4c, uSpeedScale=0.4, trail 16 FRAMES)",
     ok and str(d.get("target", "")).endswith("/fb") and d.get("fy") == -2
     and d.get("amp") == 0.35 and d.get("oa") == "Color" and d.get("attr") == "color"
     and d.get("comps") == "4" and d.get("u") == "uSpeedScale" and d.get("uval") == 0.4
     and d.get("lu") == "frames" and d.get("ln") == 16, d)

# errores del shader (compiló o no)
ok, d = g.exec_code("""
import json
shade = op('%s/shade')
shade.cook(force=True)
print('<<JSON>>' + json.dumps(dict(err=str(shade.errors() or ''))))
""" % GEO)
chek("shader compila sin errores", ok and d.get("err") == "", d.get("err", "?"))

bad, got = set_and_verify(g, GEO + "/topoints", {"convert": "topointprims"}, "prims de punto")
chek("topointprims aplicado", not bad, got)

# ── 6. material BLANCO (multiplica el Color del punto: si no, distorsiona la paleta) ──
g.call_ok("create_operator", {"parent_path": GEO, "type": "pointspriteMAT", "name": "mat"},
          note="material de puntos")
ok, d = g.exec_code(
    CHAIN
    + """
import json
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
m = op(ROOT + '/geo/mat')
m.par.pointsize = 4.0
m.par.colorr = 1.0
m.par.colorg = 1.0
m.par.colorb = 1.0
geo.par.material = m
term = geo.op('null_render')
term.display = True
term.render = True
chk = op(ROOT + '/check')
chk.par.pop = ROOT + '/geo/null_render'
settle()
chk.cook(force=True)
medios = []
for c in chk.chans():
    if c.name in ('P_0', 'P_1', 'P_2'):
        medios.append((min(c.vals) + max(c.vals)) / 2)
cam.par.tx = round(medios[0], 2)
cam.par.ty = round(medios[1], 2)
cam.par.tz = round(medios[2] + 10.0, 2)
ren.par.geometry = geo
ren.par.camera = cam
ren.par.lights = op(ROOT + '/light')
settle()
print('<<JSON>>' + json.dumps({'mat': str(geo.par.material.eval()),
                               'centro_P': [round(v, 2) for v in medios]}))
""")
chek("material blanco + flags + camara-al-dato + bindings",
     ok and "mat" in str(d.get("mat", "")) and d.get("centro_P"), d)

# ── 7. verificación: números antes que píxeles (C5) ──
ok, d = g.exec_code("""
import json
%s
term = op('%s/null_render')
chk = op('%s/check')
settle()
chk.cook(force=True)
out = {'pts': term.numPoints(), 'prims': term.numPrims(), 'samples': chk.numSamples, 'px': px()}
print('<<JSON>>' + json.dumps(out))
""" % (CHAIN, GEO, ROOT))
chek("1 prim/punto + poptoCHOP ve el terminal", ok and d.get("prims") == d.get("pts")
     and (d.get("samples") or 0) > 0 and (d.get("px") or 0) > 500, d)

ok, d = g.exec_code("""
import json
%s
own = render_is_ours(op('%s/geo/null_render'))
print('<<JSON>>' + json.dumps({'ok': own[0], 'on': own[1], 'off': own[2]}))
""" % (CHAIN, ROOT))
chek("los px son nuestros (guardia: apagar el terminal -> 0)", ok and d.get("ok") is True, d)

# ── 8. LO NUEVO: el color por velocidad, medido ──
time.sleep(1.5)
m04 = measure_color("uSpeedScale=0.4")

term = m04.get("term") or {}
c0 = term.get("Color_0") or {}
c2 = term.get("Color_2") or {}
spread = ((c2.get("mx") or 0) - (c2.get("mx") and c2.get("mn") or 0))
chek("Color presente en el terminal y variando (rango Color_2 > 0.1)",
     bool(c0 and c2) and (c2.get("mx", 0) - c2.get("mn", 1)) > 0.1,
     {"Color_2": c2, "Color_0": c0})

# palanca: comprimir el rampa (0.4 -> 0.15) debe corer la media de Color hacia el frío
ok, d = g.exec_code("""
import json
shade = op('%s/shade')
shade.par.vec0valuex = 0.15
print('<<JSON>>' + json.dumps(dict(uval=round(shade.par.vec0valuex.eval(), 3))))
""" % GEO)
time.sleep(1.5)
m015 = measure_color("uSpeedScale=0.15")
report["color_evidencia"] = {"scale_0.4": m04, "scale_0.15": m015}


def _mean(m, chan):
    return ((m.get("term") or {}).get(chan) or {}).get("mean") or 0


d0 = _mean(m04, "Color_0") - _mean(m015, "Color_0")
chek("la velocidad pinta (la media de Color_0 cambia al comprimir el rampa)",
     abs(d0) > 0.02, {"mean_0.4": _mean(m04, "Color_0"), "mean_0.15": _mean(m015, "Color_0")})

# El trail arrastra el HISTORIAL de color: más valores distintos que shade, y el max del
# terminal supera al del shade (muestra colores de frames pasados cuando la partícula iba más
# rápido). `n` NO es la señal: el buffer de shade arrastra slots muertos del loop (C10).
sh, tm = m04.get("shade") or {}, m04.get("term") or {}
uniq_sh = sum((sh.get(c) or {}).get("uniq", 0) for c in COLOR_CHANS)
uniq_tm = sum((tm.get(c) or {}).get("uniq", 0) for c in COLOR_CHANS)
mx_sh = max(((sh.get(c) or {}).get("mx") or 0) for c in COLOR_CHANS[:2])
mx_tm = max(((tm.get(c) or {}).get("mx") or 0) for c in COLOR_CHANS[:2])
chek("el trail acumula historial de color (más valores distintos y max > shade)",
     uniq_tm > uniq_sh and mx_tm > mx_sh + 0.02,
     {"uniq_shade": uniq_sh, "uniq_term": uniq_tm, "max_shade": mx_sh, "max_term": mx_tm})

# restaurar palanca y trail
ok, d = g.exec_code("""
import json
shade, tr = op('%s/shade'), op('%s/tr')
shade.par.vec0valuex = 0.4
tr.par.reset.pulse()
print('<<JSON>>' + json.dumps(dict(uval=round(shade.par.vec0valuex.eval(), 3))))
""" % (GEO, GEO))
chek("estado canónico restaurado (uSpeedScale=0.4)", ok and d.get("uval") == 0.4, d)

# ── 9. errores + evidencia visual ──
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_color_trails.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

# ── 10. cierre ──
report["final_px"] = d
report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-color-trails-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_color_trails ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| failures:", g.failures)
print("color:", json.dumps(report.get("color_evidencia", {}), ensure_ascii=False)[:900])
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

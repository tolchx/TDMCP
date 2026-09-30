#!/usr/bin/env python3
"""build_pop_sim_trails.py — quinto proyecto POP del hilo: SIMULACIÓN + ESTELAS.

Combina los dos mundos ya medidos contra TD vivo:
  * simulación (C6, /fountain_demo): spherePOP → particlePOP (birthrate/life, timeintegration
    ON) → forceradialPOP (globforcey con globforcemult=1)
  * estelas (C8, /pop_streams): trailPOP (length=16) → noisePOP curl 3D → topointprims →
    nullPOP + pointspriteMAT

Pipeline (lo que la sesión midió hoy — contratos C10):
  geo: emit(spherePOP r=0.3) → sim(particlePOP) → grav(forceradialPOP) ─┬→ tr(trailPOP)
       → curl(noisePOP) → topoints(convertPOP) → null_render            └→ fb(nullPOP)
       y `sim.par.targetpop = fb`: SIN el loop cerrado la integración se descarta
       (PartForce/PartVel se escriben pero P queda clavado en el emisor).

Lo que NO se hace (medido, sonda 4/5): `initializepulse` + `preroll` — el buffer del loop se
infla (62k-103k "partículas" con maxparticles=800/2000) y la red queda enferma. El reciclado
poblacional lo hace `life` (1.2s) contra el timeline, que SÍ corre ENTRE llamadas MCP
(dentro de una llamada no corre nada, C1/clock_stopped): por eso la palanca (globforcey)
y cada medición van en llamadas separadas con sleep en el host.

Verificación: números antes que píxeles (C5) por el dueño único (chain_source), guardia
render_is_ours, y la animación medida como caída de P_1.min (sim y terminal) al escalar
la gravedad -6 → -14, con la población acotada como guardia de red sana.
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
g = Gauntlet(phase="build-pop-sim-trails", run_id=RUN)
g.init()

ROOT = "/pop_sim_trails"
GEO = ROOT + "/geo"
CHAIN = chain_source(ROOT)   # settle()/px()/render_is_ours() no se copian: se importan

report = {"run_id": RUN, "objetivo": "simulacion con feedback + estelas (emit→sim→grav→tr→curl→topoints, targetpop=fb)",
          "ok": False, "cheks": []}


def chek(name, ok, detail=""):
    report["cheks"].append((name, bool(ok)))
    g.check(name, ok, str(detail)[:240])


def measure(label):
    """Población y P/vel del nodo sim Y del terminal, en UNA llamada (mismo frame).

    El poptoCHOP re-apuntado al nodo `sim` da la verdad de la simulación; el terminal
    (via chk.par.pop canónico) da lo que dibuja el render. Canales EXACTOS: el poptoCHOP
    expone P_0/1/2, PartVel_0/1/2, PartId, PartAge... — un filtro startswith('P') tomaría
    también PartVel/PartId (contrato canales del poptoCHOP).
    """
    ok, d = g.exec_code(CHAIN + """
import json
settle(4)
chk = op('%s/check')
out = dict()
for n in ('sim', 'term'):
    chk.par.pop = ('%s/sim' if n == 'sim' else '%s/geo/null_render')
    chk.cook(force=True)
    m = dict()
    for c in chk.chans():
        if c.name in ('P_1', 'PartVel_1', 'PartId'):
            m[c.name] = [round(min(c.vals), 3), round(max(c.vals), 3)]
    m['n'] = chk.numSamples
    out[n] = m
chk.par.pop = '%s/geo/null_render'
print('<<JSON>>' + json.dumps(dict(out=out, t=round(absTime.seconds, 2))))
""" % (ROOT, GEO, ROOT, ROOT))
    if not ok:
        print("    (medición falló: %s)" % json.dumps(d)[:200])
        return {}
    m = d.get("out") or {}
    print("    [%s] sim n=%s P_1=%s ids=%s | term n=%s P_1=%s"
          % (label, (m.get("sim") or {}).get("n"), (m.get("sim") or {}).get("P_1"),
             (m.get("sim") or {}).get("PartId"),
             (m.get("term") or {}).get("n"), (m.get("term") or {}).get("P_1")))
    return m


# ── 0. entorno limpio ──
g.call("project_info", {}, note="TD vivo")
ok, d = g.exec_code("import json\ntry:\n op('%s').destroy()\nexcept Exception:\n pass\n"
                    "print('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
chek("limpieza previa", ok)

# ── 1. estructura de render ──
g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_sim_trails",
                              "nodeX": -1200, "nodeY": 900, "display": True}, note="contenedor")
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

# ── 2. auto-torus fuera (contrato autotorus_masks_render) ──
ok, d = g.exec_code("""
import json
geo = op('%s')
torus = [c.name for c in geo.children if c.name.lower().startswith('torus')]
for n in torus:
    geo.op(n).destroy()
print('<<JSON>>' + json.dumps({'had_torus': torus}))
""" % GEO)
chek("auto-torus borrado", ok and bool(d.get("had_torus")), d)

# ── 3. cadena POP: emisor → sim → gravedad → estelas → curl → prims + fb (feedback) ──
g.call_ok("build_network", {"parent_path": GEO, "operators": [
    {"type": "spherePOP", "name": "emit"},
    {"type": "particlePOP", "name": "sim"},
    {"type": "forceradialPOP", "name": "grav"},
    {"type": "trailPOP", "name": "tr"},
    {"type": "noisePOP", "name": "curl"},
    {"type": "convertPOP", "name": "topoints"},
    {"type": "nullPOP", "name": "null_render"},
    {"type": "nullPOP", "name": "fb"}],
    "connections": [{"from": "emit", "to": "sim"}, {"from": "sim", "to": "grav"},
                    {"from": "grav", "to": "tr"}, {"from": "tr", "to": "curl"},
                    {"from": "curl", "to": "topoints"}, {"from": "topoints", "to": "null_render"},
                    {"from": "grav", "to": "fb"}],
    "auto_layout": True}, note="cadena sim+estelas con rama de feedback")

# ── 4. parámetros (execute_code + releer: C4; SIN initializepulse/preroll — enferman el loop) ──
ok, d = g.exec_code("""
import json
emit, sim, gv, tr, curl = op('%s/emit'), op('%s/sim'), op('%s/grav'), op('%s/tr'), op('%s/curl')
sim.par.targetpop = op('%s/fb')
# emisor: esfera chica (radz existe; cols/rows NO aplican por set_parameters, C4)
emit.par.radx = 0.3
emit.par.rady = 0.3
emit.par.radz = 0.3
# simulacion: nace/recicla por life contra el timeline (SIN initialize, SIN preroll)
sim.par.timeintegration = True
sim.par.birthrate = 60
sim.par.life = 1.2
sim.par.maxparticles = 2000
sim.par.initvelocityy = 0
sim.par.preroll = 0
# gravedad global: sin globforcemult la fuerza no hace nada (C6)
gv.par.globforcemult = 1
gv.par.globforcey = -6
gv.par.radial = 0
gv.par.axial = 0
gv.par.spiral = 0
gv.par.planar = 0
# estelas + curl
tr.par.length = 16
tr.par.reset.pulse()
curl.par.mode = 'quality'
curl.par.type = 'simplex3d'
curl.par.amp = 0.25
curl.par.offset = 0.0
curl.par.curl3d = True
v = dict(target=str(sim.par.targetpop), radz=emit.par.radz.eval(), birth=sim.par.birthrate.eval(),
         life=sim.par.life.eval(), maxp=sim.par.maxparticles.eval(), ti=bool(sim.par.timeintegration.eval()),
         fy=gv.par.globforcey.eval(), mult=gv.par.globforcemult.eval(),
         length=tr.par.length.eval(), amp=curl.par.amp.eval(), ns=curl.par.noisesize.eval(),
         curl3d=bool(curl.par.curl3d.eval()))
print('<<JSON>>' + json.dumps(v))
""" % (GEO, GEO, GEO, GEO, GEO, GEO))
chek("cadena aplicada (targetpop=fb, life=1.2, g=-6, trail=16, curl 3D)",
     ok and str(d.get("target", "")).endswith("/fb") and d.get("radz") == 0.3
     and d.get("life") == 1.2 and d.get("maxp") == 2000 and d.get("ti") is True
     and d.get("fy") == -6 and d.get("mult") == 1 and d.get("length") == 16
     and d.get("amp") == 0.25 and d.get("curl3d") is True, d)
# noisesize WRITEONLY (C8/noisesize_writeonly): NO aplica lo escrito (pedimos 1.2). El valor
# de atasco depende del contexto: '2' en /pop_streams, '3' acá — el contrato es que no cambia.
chek("noisesize writeonly (pide 1.2, queda clavado — defecto conocido C8)",
     d.get("ns") != 1.2, d.get("ns"))

bad, got = set_and_verify(g, GEO + "/topoints", {"convert": "topointprims"}, "prims de punto")
chek("topointprims aplicado", not bad, got)

# ── 5. material + flags + cámara centrada en el DATO (no en el origen, C8/cam_follows_data) ──
g.call_ok("create_operator", {"parent_path": GEO, "type": "pointspriteMAT", "name": "mat"},
          note="material de puntos")
ok, d = g.exec_code(
    CHAIN
    + """
import json
geo, cam, ren = op(ROOT + '/geo'), op(ROOT + '/cam'), op(ROOT + '/ren')
m = op(ROOT + '/geo/mat')
m.par.pointsize = 4.0
m.par.colorr = 0.35
m.par.colorg = 1.0
m.par.colorb = 0.7
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
    if c.name in ('P_0', 'P_1', 'P_2'):     # EXACTO: 'P*' también matchea PartVel/PartId
        medios.append((min(c.vals) + max(c.vals)) / 2)
cam.par.tx = round(medios[0], 2)
cam.par.ty = round(medios[1], 2)
cam.par.tz = round(medios[2] + 10.0, 2)
ren.par.geometry = geo
ren.par.camera = cam
ren.par.lights = op(ROOT + '/light')
settle()
print('<<JSON>>' + json.dumps({'mat': str(geo.par.material.eval()),
                               'centro_P': [round(v, 2) for v in medios],
                               'cam': [cam.par.tx.eval(), cam.par.ty.eval(), cam.par.tz.eval()]}))
""")
chek("material+flags+camara-al-dato+bindings", ok and "mat" in str(d.get("mat", "")) and d.get("centro_P"), d)

# ── 6. verificación: números antes que píxeles (C5) ──
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

# ── 7. LO NUEVO: la simulación INTEGRA (feedback) y las estelas la siguen ──
# Palanca: globforcey -6 → -14 en una llamada; la integración ocurre ENTRE llamadas (el
# timeline corre ahí, C1/clock_stopped). Se mide P_1.min del nodo sim (verdad de la sim,
# via chk re-apuntado) y del terminal (lo que dibuja el render). life=1.2 < sleep 2.5s:
# la población se recicló completa con la fuerza nueva.
time.sleep(1.0)
antes = measure("antes (g=-6)")
ok, d = g.exec_code("""
import json
gv = op('%s/grav')
gv.par.globforcey = -14
print('<<JSON>>' + json.dumps({'globforcey': gv.par.globforcey.eval()}))
""" % GEO)
time.sleep(2.5)
despues = measure("despues (g=-14)")

s_a = (antes.get("sim") or {}).get("P_1") or [None, None]
s_d = (despues.get("sim") or {}).get("P_1") or [None, None]
t_a = (antes.get("term") or {}).get("P_1") or [None, None]
t_d = (despues.get("term") or {}).get("P_1") or [None, None]
n_sim = (despues.get("sim") or {}).get("n") or 0
n_term = (despues.get("term") or {}).get("n") or 0
id_max = ((despues.get("sim") or {}).get("PartId") or [0, 0])[1]
report["sim_evidencia"] = {"antes_g6": antes, "despues_g14": despues}

chek("la simulacion integra (P_1.min de sim cae al escalar globforcey)",
     bool(ok) and s_a[0] is not None and s_d[0] is not None and s_d[0] < s_a[0] - 1.0,
     {"antes": s_a, "despues": s_d})
chek("las estelas siguen a la simulacion (P_1.min del terminal cae)",
     t_a[0] is not None and t_d[0] is not None and t_d[0] < t_a[0] - 1.0,
     {"antes": t_a, "despues": t_d})
# La población VIVA (ids) respeta maxparticles aunque el buffer del loop arrastre slots
# muertos (medido: 28k slots con maxparticles=2000 — defecto documentado en C10).
chek("poblacion viva acotada (PartId.max <= maxparticles) y terminal renderizable (n <= 4000)",
     0 < id_max <= 2000 and 0 < n_term <= 4000,
     {"id_max": id_max, "maxparticles": 2000, "n_term": n_term, "buffer_sim": n_sim})

# restaurar el estado canónico de la red (queda de pie con la gravedad original)
ok, d = g.exec_code("""
import json
gv = op('%s/grav')
gv.par.globforcey = -6
op('%s/tr').par.reset.pulse()
print('<<JSON>>' + json.dumps({'globforcey': gv.par.globforcey.eval()}))
""" % (GEO, GEO))
chek("estado canónico restaurado (globforcey=-6)", ok and d.get("globforcey") == -6, d)

# ── 8. errores + evidencia visual ──
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_sim_trails.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

# ── 9. cierre ──
report["final_px"] = d
report["png"] = st
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-sim-trails-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_sim_trails ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| failures:", g.failures)
print("sim:", json.dumps(report.get("sim_evidencia", {}), ensure_ascii=False)[:800])
print("PNG:", st)
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

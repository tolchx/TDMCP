"""build_particle_fx.py — red de POPs GLSL con efecto visual de particulas.

Flujo completo (el mismo validado en el gauntlet N6):
  A. offline: glsl_analyze valida el shader de movimiento contra las reglas
     R1-R4 y emite los params de Create Attributes (Cd).
  B. en vivo: spherePOP -> convertPOP(topointprims) -> glslPOP (swirl animado)
     -> nullPOP dentro de un geometryCOMP. El topointprims es lo que da a cada
     punto su PRIMITIVA DE PUNTO: sin eso el render no dibuja NADA (deleteprims
     deja 0 primitivas y el render sale negro — ver docs/td-curl-field-2026-09-29.md).
     pointspriteMAT da el look de sprites; renderTOP -> null_view; poptoCHOP para
     verificacion numerica GPU->CPU.
  * el geometryCOMP auto-crea un torus1 (POP 800 pts/800 prims, display+render) que el
    renderTOP DIBUJA: hay que BORRARLO o la verificacion "px>500" mide el torus, no las
    particulas (paso en este build: apagar el flag render del torus llevaba el render a 0).

Contratos aprendidos a golpes (sesion 2026-09-28/29):
  * los cambios en el DAT del shader o en los uniforms vec* se aplican con
    UN COOK DE RETRASO: hay que "asentar" (cocinar geo->glsl->nr->ren varias
    veces) ANTES de medir, o las lecturas son del estado anterior.
  * en este entorno (TDMCP sin frame loop activo: absTime.seconds no avanza
    entre cooks, root.time = el timeCOMP /local/ y no hay root.par.play) el
    renderTOP refleja cambios de MATERIAL y ESTRUCTURA, pero no re-sube la
    geometria ante cambios de datos POP. La animacion se verifica por
    poptoCHOP (P se mueve con uTime/uSwirl), no por fotogramas.
  * este script NO debe importarse: al ser script ejecuta el build. El guard
    de __main__ lo impide (antes un import reconstruia la red entera).

La red QUEDA DE PIE al terminar (es un build, no un test): /particle_swirl.
Re-ejecutable: borra /particle_swirl al empezar.
"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gauntlet_client import Gauntlet
from td_probe import chain_source, png_stats, set_and_verify

ROOT = "/particle_swirl"

SHADER = """// particle_swirl.glsl — enjambre en espiral con color pulsante.
// uniforms float auto-declarados por la secuencia vec del glslPOP (no redeclarar).
void main()
{
    const uint id = TDIndex();
    if (id >= TDNumElements()) return;
    float fid = float(id);
    vec3 src = TDIn_P(0, id);

    float r = length(src.xz);
    float ang = uTime * 0.7 + src.y * 2.5;
    vec3 swirl = vec3(cos(ang) * r,
                      src.y + 0.18 * sin(uTime * 1.5 + r * 8.0),
                      sin(ang) * r);
    vec3 pos = mix(src, swirl, uSwirl);
    pos += 0.04 * vec3(sin(uTime * 2.1 + fid),
                       cos(uTime * 1.7 + fid * 1.3),
                       sin(uTime * 2.7 + fid * 0.7));
    P[id] = pos;

    float glow = 0.5 + 0.5 * sin(uTime * 2.0 + r * 6.0);
    Cd[id] = vec4(0.2 + 0.8 * glow, 0.35 + 0.3 * (1.0 - glow), 0.9 - 0.4 * glow, 1.0);
}
"""

# asentar, medir px y probar propiedad del render: UNA implementacion, en td_probe
CHAIN = chain_source(ROOT)

g = Gauntlet("build-particle-fx")


def main():
    # ══ 1. conocimiento offline: validar el shader ANTES de tocar TD ═════
    print("== 1. glsl_analyze (offline) ==")
    an = g.offline("glsl_analyze", {"code": SHADER, "family": "pop"})
    g.check("shader pasa R1-R4 sin errores", an.get("ok") is True, json.dumps(an.get("errores"))[:300])
    r3 = next((n for n in an.get("notas", []) if isinstance(n, dict) and n.get("attr") == "Cd"), None)
    params_r3 = dict((r3 or {}).get("parametros", {}))
    oa = next((n for n in an.get("notas", []) if isinstance(n, dict)
               and n.get("regla") == "POP R3 (outputattrs)"), None)
    outputattrs_val = (oa or {}).get("outputattrs", "P")
    g.check("analyzer emite params de Cd", params_r3.get("attr0customname") == "Cd", str(params_r3))
    g.check("analyzer emite outputattrs (" + outputattrs_val + ")", bool(outputattrs_val), str(oa)[:200])

    # ══ 2. build en vivo ════════════════════════════════════════════════
    print("== 2. build en vivo ==")
    g.call("delete_operator", {"path": ROOT}, note="limpieza previa (tolerada)")
    g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "particle_swirl",
                                  "nodeX": -300, "nodeY": 900, "display": True}, note="COMP principal")

    # estructura: geo (particulas) + render + verificacion
    g.call_ok("build_network", {"parent_path": ROOT, "operators": [
        {"type": "geometryCOMP", "name": "geo"},
        {"type": "cameraCOMP", "name": "cam"},
        {"type": "lightCOMP", "name": "light"},
        {"type": "renderTOP", "name": "ren"},
        {"type": "nullTOP", "name": "null_view"},
        {"type": "poptoCHOP", "name": "check"}],
        "connections": [{"from": "ren", "to": "null_view"}],
        "auto_layout": True}, note="estructura del efecto")
    # el geometryCOMP auto-crea un torus1 que DIBUJA: borrarlo o la verificacion
    # del render mide el torus (contrato autotorus_masks_render)
    ok, d = g.exec_code("""
import json
geo = op('%s/geo')
torus = [c.name for c in geo.children if c.name.lower().startswith('torus')]
for n in torus:
    geo.op(n).destroy()
print('<<JSON>>' + json.dumps({'had_torus': torus, 'kids': [c.name for c in geo.children]}))
""" % ROOT)
    g.check("auto-torus borrado (si no, el render mide el torus)", ok and bool(d.get("had_torus")),
            json.dumps(d, ensure_ascii=False)[:200])

    # cadena de particulas DENTRO del geometryCOMP: emit -> topoints -> endpoint
    g.call_ok("build_network", {"parent_path": ROOT + "/geo", "operators": [
        {"type": "spherePOP", "name": "sphere_emit"},
        {"type": "convertPOP", "name": "topoints"},
        {"type": "nullPOP", "name": "null_render"}],
        "connections": [], "auto_layout": True}, note="emit + topoints + endpoint")
    # radio 1.5: con el default (r=1) los 252 puntos quedan amontonados en una pelotita
    # casi invisible; con r=2.5 parte de la nube sale del frame (px baja). 1.5 entra justo.
    bad_r, got_r = set_and_verify(g, ROOT + "/geo/sphere_emit",
                                  {"radx": 1.5, "rady": 1.5, "radz": 1.5}, "radio esfera 1.5")
    g.check("radio de la esfera aplicado (1.5)",
            abs(float(got_r.get("radx", 0)) - 1.5) < 1e-6, json.dumps(got_r)[:150])

    # topointprims: cada punto de la esfera recibe su PRIMITIVA DE PUNTO (lo que
    # hace que el render dibuje como nube). deleteprims dejaria 0 primitivas =
    # render negro.
    g.call_ok("set_parameters", {"path": ROOT + "/geo/topoints", "values": {"convert": "topointprims"}},
              note="topointprims -> nube con point primitives")
    g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "glslPOP", "name": "glsl_swirl"})
    g.call_ok("wiring", {"from_path": ROOT + "/geo/sphere_emit", "to_path": ROOT + "/geo/topoints", "to_index": 0},
              note="emit->topoints")
    g.call_ok("wiring", {"from_path": ROOT + "/geo/topoints", "to_path": ROOT + "/geo/glsl_swirl", "to_index": 0},
              note="topoints->shader")
    g.call_ok("wiring", {"from_path": ROOT + "/geo/glsl_swirl", "to_path": ROOT + "/geo/null_render", "to_index": 0},
              note="shader->endpoint")

    # material pointsprite (particulas = puntos camara-facing, sin luz)
    g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "pointspriteMAT", "name": "pointsprite_mat"})

    # shader DAT (bind ANTES de params: enlazar resetea la secuencia vec, leccion N6)
    g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "textDAT", "name": "shader_compute"})
    g.call_ok("set_dat_content", {"path": ROOT + "/geo/shader_compute", "text": SHADER},
              note="shader validado offline al DAT")
    g.call_ok("set_parameters", {"path": ROOT + "/geo/shader_compute", "values": {"language": "glsl"}})
    ok, d = g.exec_code(f"""
import json
op('{ROOT}/geo/glsl_swirl').par.computedat = op('{ROOT}/geo/shader_compute')
print('<<JSON>>' + json.dumps({{'dat': str(op('{ROOT}/geo/glsl_swirl').par.computedat.eval())}}))""")
    g.check("computedat enlazado", ok and "shader_compute" in str(d.get("dat", "")), str(d)[:200])

    # params del glslPOP: lo que dicto el analyzer (R3 + outputattrs) + uniforms
    # la secuencia vec arranca en numBlocks=1: para 2 uniforms hay que subirla (exec_code)
    ok, d = g.exec_code("""
import json
s = op('%s/geo/glsl_swirl')
before = s.par.vec.sequence.numBlocks
s.par.vec.sequence.numBlocks = 2
print('<<JSON>>' + json.dumps({'blocks_before': before, 'blocks_after': s.par.vec.sequence.numBlocks}))
""" % ROOT)
    g.check("secuencia vec con 2 bloques", (d.get("blocks_after") or 0) == 2, json.dumps(d)[:200])

    vals = dict(params_r3)
    vals.update({"outputattrs": outputattrs_val,
                 "vec0name": "uTime", "vec1name": "uSwirl"})
    g.call_ok("set_parameters", {"path": ROOT + "/geo/glsl_swirl", "values": vals},
              note="R3 + outputattrs + uniforms")
    # los VALORES vecNvaluex no los aplica set_parameters: por exec_code + read-back
    ok, d = g.exec_code("""
import json
s = op('%s/geo/glsl_swirl')
s.par.vec1valuex.val = 0.6
print('<<JSON>>' + json.dumps({'uSwirl': s.par.vec1valuex.eval(),
      'v1name': str(s.par.vec1name.eval())}))
""" % ROOT)
    g.check("uSwirl=0.6 aplicado por exec_code", ok and abs((d.get("uSwirl") or 0) - 0.6) < 1e-6,
            json.dumps(d)[:200])
    # uTime animado por expresion (set_parameters solo constantes)
    ok, d = g.exec_code(f"""
import json
s = op('{ROOT}/geo/glsl_swirl')
if str(s.par.vec0name.eval()) != 'uTime':
    s.par.vec0name = 'uTime'
s.par.vec0valuex.expr = 'absTime.seconds'
print('<<JSON>>' + json.dumps({{'uTime_expr': str(s.par.vec0valuex.expr), 'vec1': str(s.par.vec1name.eval())}}))""")
    g.check("uTime en modo EXPRESSION (animado)", ok and "absTime" in str(d.get("uTime_expr", "")), str(d)[:200])

    # material + bindings del render (OP-pars por exec_code)
    ok, d = g.exec_code(f"""
import json
geo = op('{ROOT}/geo')
geo.par.material = op('{ROOT}/geo/pointsprite_mat')
ren = op('{ROOT}/ren')
ren.par.camera = op('{ROOT}/cam')
ren.par.geometry = op('{ROOT}/geo')
# el par de la luz no se llama 'light' en este build: resolverlo por nombre
light_par = None
for p in ren.pars():
    if p.name == 'light':
        light_par = 'light'; break
    if p.name.lower().startswith('light'):
        light_par = light_par or p.name
if light_par:
    setattr(ren.par, light_par, op('{ROOT}/light'))
print('<<JSON>>' + json.dumps({{'mat': str(geo.par.material.eval()),
      'cam': str(ren.par.camera.eval()), 'geo': str(ren.par.geometry.eval()),
      'light_par': light_par}}))""")
    g.check("material + bindings del renderTOP", ok and "pointsprite" in str(d.get("mat", ""))
            and "cam" in str(d.get("cam", "")), str(d)[:250])
    # look de particulas: sprites chicos con blending aditivo.
    # NOTA: set_parameters NO fija attensizenear (se queda en el default 20px =
    # sprites gigantes); la escritura directa por exec_code si. Se verifica.
    # El tamano REAL del sprite es `pointsize` (default 1.0 = ~2 px). `attensizenear`
    # NO cambia el tamano (medido: 1/8/60 -> mismo px). `sizingmodel='perspective'`
    # infla los sprites a pantalla completa. Ver contrato pointsprite_pars.
    ok, d = g.exec_code(f"""
import json
mat = op('{ROOT}/geo/pointsprite_mat')
mat.par.sizingmodel = 'constatten'
mat.par.pointsize = 3.0
mat.par.blending = True
mat.par.srcblend = 'sa'
mat.par.destblend = 'one'
mat.par.colorr = 0.25
mat.par.colorg = 0.6
mat.par.colorb = 1.0
print('<<JSON>>' + json.dumps({{'sizing': str(mat.par.sizingmodel.eval()),
      'pointsize': mat.par.pointsize.eval(), 'blend': bool(mat.par.blending),
      'src': str(mat.par.srcblend.eval()), 'dst': str(mat.par.destblend.eval())}}))""")
    g.check("look de particulas aplicado (constatten, pointsize 3, aditivo)",
            ok and d.get("sizing") == "constatten" and abs((d.get("pointsize") or 0) - 3.0) < 1e-6
            and d.get("blend") is True, json.dumps(d, ensure_ascii=False)[:200])
    g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 640, "resolutionh": 480}})
    # flags: null_view (viewer) y el TERMINAL DEL CHAIN (es el que dibuja el
    # draw-stream del geometryCOMP: con render=false el render sale negro)
    g.call_ok("edit_operator", {"path": ROOT + "/null_view", "display": True, "render": True}, note="flags null_view")
    ok, d = g.exec_code(f"""
import json
nr = op('{ROOT}/geo/null_render')
nr.display = True
nr.render = True
print('<<JSON>>' + json.dumps({{'flags': [bool(nr.display), bool(nr.render)]}}))""")
    g.check("terminal del chain dibujable (null_render display+render)",
            ok and d.get("flags") == [True, True], str(d)[:150])

    # verificacion numerica: poptoCHOP apunta al endpoint de particulas
    ok, d = g.exec_code(f"""
import json
chk = op('{ROOT}/check')
chk.par.pop = op('{ROOT}/geo/null_render')
print('<<JSON>>' + json.dumps({{'pop': str(chk.par.pop.eval())}}))""")
    g.check("poptoCHOP -> null_render", ok and "null_render" in str(d.get("pop", "")), str(d)[:150])

    # ══ 3. verificacion: compila, es nube de puntos, anima, se ve ═══════
    print("== 3. verificacion ==")
    ok, d = g.exec_code(f"""
import json
{CHAIN}
settle()
nr = op('{ROOT}/geo/null_render')
r = {{'err': str(op('{ROOT}/geo/glsl_swirl').errors() or ''),
      'npts': nr.numPoints(), 'nprims': nr.numPrims(),
      'chk_chans': len(op('{ROOT}/check').chans())}}
print('<<JSON>>' + json.dumps(r))""")
    g.check("glsl_swirl compila sin errores", ok and not d.get("err"), str(d)[:250])
    g.check("nube de puntos (numPoints>0)", (d.get("npts") or 0) > 0, str(d)[:200])
    g.check("cada punto con su primitiva (numPrims==numPoints): lo que DIBUJA",
            d.get("nprims") == d.get("npts") and (d.get("npts") or 0) > 0, str(d)[:200])
    ok, d2 = g.exec_code("""
import json
geo = op('%s/geo')
print('<<JSON>>' + json.dumps({'torus': [c.name for c in geo.children if c.name.lower().startswith('torus')]}))
""" % ROOT)
    g.check("sin auto-torus (el render es de la cadena, no del torus)", ok and d2.get("torus") == [],
            json.dumps(d2)[:150])

    # estado final persistido: flags del terminal y look del material
    ok, d = g.exec_code(f"""
import json
{CHAIN}
settle()
nr = op('{ROOT}/geo/null_render')
mat = op('{ROOT}/geo/pointsprite_mat')
print('<<JSON>>' + json.dumps({{'flags': [bool(nr.display), bool(nr.render)],
      'nP': nr.numPoints(), 'nPri': nr.numPrims(),
      'sizing': str(mat.par.sizingmodel.eval()), 'near': mat.par.pointsize.eval(),
      'blend': bool(mat.par.blending)}}))""")
    g.check("estado persistido (flags + look + point prims)", ok and d.get("flags") == [True, True]
            and d.get("nPri") == d.get("nP") and (d.get("nP") or 0) > 0
            and d.get("sizing") == "constatten"
            and abs((d.get("near") or 0) - 3.0) < 1e-6, json.dumps(d, ensure_ascii=False)[:250])

    # animacion: escalonar uTime con ASENTAMIENTO y leer P por poptoCHOP
    ok, d = g.exec_code(f"""
import json
{CHAIN}
chk = op('{ROOT}/check')
glsl = op('{ROOT}/geo/glsl_swirl')
def sigP():
    settle()
    chk.cook(force=True); chk.cook(force=True)
    return [round(c[0], 4) for c in chk.chans() if c.name.startswith('P_')] + \\
           [round(c[chk.numSamples-1], 4) for c in chk.chans() if c.name.startswith('P_')]
def cd():
    chk.cook(force=True)
    out = {{}}
    for c in chk.chans():
        if c.name.startswith('Cd_'):
            vals = [c[i] for i in range(chk.numSamples)]
            out[c.name] = [round(min(vals), 4), round(max(vals), 4)]
    return out
v0 = glsl.par.vec0valuex
v0.expr = ''
v0.val = 0.0
a = sigP()
v0.val = 3.0
b = sigP()
v1 = glsl.par.vec1valuex
v1.val = 0.0; c0 = sigP()
v1.val = 1.0; c1 = sigP()
v1.val = 0.6
v0.expr = 'absTime.seconds'; v0.val = 0.0
settle()
r = {{'animada_uTime': a != b, 'animada_uSwirl': c0 != c1,
      'n_chans': len(chk.chans()), 'cd': cd()}}
print('<<JSON>>' + json.dumps(r))""")
    g.check("poptoCHOP extrae atributos (>=3 canales)", (d.get("n_chans") or 0) >= 3, str(d)[:200])
    g.check("efecto animado: uTime mueve P (poptoCHOP)", d.get("animada_uTime") is True, str(d)[:250])
    g.check("efecto animado: uSwirl mueve P (poptoCHOP)", d.get("animada_uSwirl") is True, str(d)[:250])
    cd = d.get("cd") or {}
    g.check("Cd vivo (particulas coloreadas)", bool(cd) and any(v[1] > 0.2 for v in cd.values()),
            json.dumps(cd)[:200])

    # render con pixeles (la cuenta de px es la compartida)
    ok, d = g.exec_code(f"""
import json
{CHAIN}
settle()
print('<<JSON>>' + json.dumps({{'px': px()}}))""")
    g.check("el render dibuja las particulas (px no negros)", ok and (d.get("px") or 0) > 500,
            json.dumps(d)[:200])

    # los píxeles SON nuestros: la guardia compartida apaga el terminal y exige 0 px
    ok, d = g.exec_code(f"""
import json
{CHAIN}
own = render_is_ours(op('{ROOT}/geo/null_render'))
print('<<JSON>>' + json.dumps({{'ok': own[0], 'on': own[1], 'off': own[2]}}))""")
    g.check("los px son nuestros (render_is_ours: apagar el terminal los lleva a 0)",
            ok and d.get("ok") is True, json.dumps(d)[:200])

    # visual: PNG del frame + grid temporal
    g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}})
    r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
    png = g.save_image(r, os.path.join(HERE, "results", g.run_id, "particle_fx.png"))
    # contenido por PIXELES (PIL), no por bytes: una nube de 252 puntos es densa en data
    # pero muy liviana en archivo (816 B con 83 px) — el tamano de archivo no es gradable.
    st = png_stats(png) if png else {"px_lit": 0}
    g.check("render capturado con contenido real (PIL)",
            bool(png) and st.get("px_lit", 0) > 20, json.dumps(st, ensure_ascii=False)[:220])
    r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "frames": 4, "step": 6, "resolution": "small"},
                  note="grid temporal")
    job = g.json_of(r).get("job_id", "")
    time.sleep(4.5)
    r = g.call("view_operator", {"path": ROOT + "/null_view", "job_id": job}, note=f"retrieve {job}")
    png2 = g.save_image(r, os.path.join(HERE, "results", g.run_id, "particle_fx_grid.png"))
    g.check("grid temporal capturado", bool(png2))
    g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}})

    # pulir: anotacion + shortcut del COMP
    g.call_ok("annotation", {"parent_path": ROOT,
                             "comment": "Particulas GLSL POP: sphere_emit -> topoints(topointprims) -> glsl_swirl (swirl+glow) -> null_render. uTime anima; datos en poptoCHOP 'check'.",
                             "width": 460}, note="anotacion")
    g.call_ok("set_parameters", {"path": ROOT, "values": {"parentshortcut": "ParticleSwirl"}})

    errs = g.call_ok("get_errors", {"path": ROOT})
    et = g.text_of(errs)
    g.check("red sin errores", '"count": 0' in et or '"items": []' in et, et[:250])

    s = g.summary()
    print("\nBUILD:", json.dumps(s, ensure_ascii=False))
    print(f"\nRed lista en {ROOT} (abri el viewer de {ROOT}/null_view). PNGs: results/{g.run_id}/")
    return 0 if s["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

"""build_pop_curlfield.py — SEGUNDA red POP, construida EN FRÍO siguiendo la receta.

No es "otro efecto": es el **playtest de la receta**
(`skills-hermes/td-pop-render-pipeline/SKILL.md` + `knowledge/contracts/VERIFIED_CONTRACTS.md`).
La construye al pie de la letra en una red NUEVA (`/curl_field`, sin tocar `/particle_swirl`) y
registra en un ledger cada punto donde la receta NO alcanza, MIENTE o se queda corta, corrigiéndolo
en vivo.

Hallazgo principal de este pase (ver `findings.json`):
  * `points_need_pointprims` — la receta dice que hay que `convertPOP(convert='deleteprims')` para
    hacer "nube de puntos pura" y que ESO dibuja. Es al revés: `deleteprims` deja **0 primitivas** y
    el render sale **negro** (0 px). Lo que dibuja es `convert='topointprims'` (cada punto con su
    primitiva de punto) — o `surftype='points'` en el generador. Gradable correcto:
    `numPrims() == numPoints()` (NO `numPrims()==0`).
  * `autotorus_masks_render` — el geometryCOMP auto-crea `torus1` (POP, 800 pts/800 prims); la receta
    dice "borralo" pero su script de referencia nunca lo hace. La verificación "el render dibuja"
    de `/particle_swirl` medía **el torus**, no las partículas: apagando su flag `render`, ese render
    cae de 81572 px a **0**. Verificación falsa.

Red: `/curl_field` — grilla 3D 16^3 desplazada por **curl-noise** a mano en GLSL (TDPerlinNoise no
existe en compute shaders), color por magnitud. Distinta al enjambre esférico.

Re-ejecutable: borra /curl_field al empezar. Deja la red DE PIE.
"""
import json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gauntlet_client import Gauntlet
from td_probe import chain_source, png_stats, selftest_render_ownership, set_and_verify

ROOT = "/curl_field"

# ── shader: curl noise escrito a mano ────────────────────────────────────────
SHADER = """// curl_field.glsl — campo de puntos desplazado por curl-noise (TDPerlinNoise NO existe en
// compute shaders: noise a mano). Uniforms uTime/uAmount/uScale auto-declarados por la
// secuencia vec del glslPOP como float (no redeclarar).
float hash31(vec3 x)
{
    x = fract(x * 0.3183099 + vec3(0.1, 0.2, 0.3));
    x *= 17.0;
    return fract(x.x * x.y * x.z * (x.x + x.y + x.z));
}

float vnoise(vec3 x)
{
    vec3 i = floor(x);
    vec3 f = fract(x);
    f = f * f * (3.0 - 2.0 * f);
    float n000 = hash31(i + vec3(0.0, 0.0, 0.0));
    float n100 = hash31(i + vec3(1.0, 0.0, 0.0));
    float n010 = hash31(i + vec3(0.0, 1.0, 0.0));
    float n110 = hash31(i + vec3(1.0, 1.0, 0.0));
    float n001 = hash31(i + vec3(0.0, 0.0, 1.0));
    float n101 = hash31(i + vec3(1.0, 0.0, 1.0));
    float n011 = hash31(i + vec3(0.0, 1.0, 1.0));
    float n111 = hash31(i + vec3(1.0, 1.0, 1.0));
    float a = mix(n000, n100, f.x);
    float b = mix(n010, n110, f.x);
    float c = mix(n001, n101, f.x);
    float d = mix(n011, n111, f.x);
    return mix(mix(a, b, f.y), mix(c, d, f.y), f.z);
}

vec3 potential(vec3 q)
{
    return vec3(vnoise(q),
                vnoise(q + vec3(31.4, 7.7, 12.3)),
                vnoise(q + vec3(11.1, 23.9, 3.3)));
}

vec3 curlfield(vec3 q)
{
    const float e = 0.12;
    vec3 dxp = potential(q + vec3(e, 0.0, 0.0));
    vec3 dxm = potential(q - vec3(e, 0.0, 0.0));
    vec3 dyp = potential(q + vec3(0.0, e, 0.0));
    vec3 dym = potential(q - vec3(0.0, e, 0.0));
    vec3 dzp = potential(q + vec3(0.0, 0.0, e));
    vec3 dzm = potential(q - vec3(0.0, 0.0, e));
    float inv = 0.5 / e;
    return vec3(((dyp.z - dym.z) - (dzp.y - dzm.y)) * inv,
                ((dzp.x - dzm.x) - (dxp.z - dxm.z)) * inv,
                ((dxp.y - dxm.y) - (dyp.x - dym.x)) * inv);
}

void main()
{
    const uint id = TDIndex();
    if (id >= TDNumElements()) return;
    vec3 src = TDIn_P(0, id);

    vec3 flow = curlfield(src * uScale + vec3(0.0, uTime * 0.35, uTime * 0.2));
    P[id] = src + flow * uAmount;

    float m = clamp(length(flow) * 0.5, 0.0, 1.0);
    Cd[id] = vec4(0.35 + 0.65 * m, 0.25 + 0.35 * (1.0 - m), 0.55 + 0.45 * m, 1.0);
}
"""

# asentar, medir px y probar propiedad del render: UNA implementacion, en td_probe
CHAIN = chain_source(ROOT)

g = Gauntlet("build-curlfield")
FINDINGS = []


def find(kind, area, symptom, recipe_says, reality, fixed=""):
    f = {"kind": kind, "area": area, "symptom": symptom, "recipe_says": recipe_says,
         "reality": reality, "fixed": fixed}
    FINDINGS.append(f)
    print(f"  >>> RECIPE {kind}: [{area}] {symptom}")
    return f


def main():
    # ══ 0. conocimiento offline: validar el shader ANTES de tocar TD ═══
    print("== 0. glsl_analyze (offline, la receta lo exige primero) ==")
    an = g.offline("glsl_analyze", {"code": SHADER, "family": "pop"})
    g.check("shader pasa R1-R4 sin errores", an.get("ok") is True, json.dumps(an.get("errores"))[:400])
    r3 = next((n for n in an.get("notas", []) if isinstance(n, dict) and n.get("attr") == "Cd"), None)
    params_r3 = dict((r3 or {}).get("parametros", {}))
    oa = next((n for n in an.get("notas", []) if isinstance(n, dict)
               and n.get("regla") == "POP R3 (outputattrs)"), None)
    outputattrs_val = (oa or {}).get("outputattrs", "P")
    g.check("analyzer emite params de Cd", params_r3.get("attr0customname") == "Cd", str(params_r3))
    g.check("analyzer emite outputattrs", bool(outputattrs_val), str(oa)[:200])

    # ══ 1. build en vivo (la receta, con la conversión CORREGIDA) ════════
    print("== 1. build en vivo ==")
    g.call("delete_operator", {"path": ROOT}, note="limpieza previa (tolerada)")
    g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "curl_field",
                                  "nodeX": 300, "nodeY": 900, "display": True}, note="COMP principal")

    g.call_ok("build_network", {"parent_path": ROOT, "operators": [
        {"type": "geometryCOMP", "name": "geo"},
        {"type": "cameraCOMP", "name": "cam"},
        {"type": "lightCOMP", "name": "light"},
        {"type": "renderTOP", "name": "ren"},
        {"type": "nullTOP", "name": "null_view"},
        {"type": "poptoCHOP", "name": "check"}],
        "connections": [{"from": "ren", "to": "null_view"}],
        "auto_layout": True}, note="estructura del efecto")

    ok, d = g.exec_code("""
import json
geo = op('%s/geo')
kids = [c.name for c in geo.children]
torus = [n for n in kids if n.lower().startswith('torus')]
for n in torus:
    geo.op(n).destroy()
print('<<JSON>>' + json.dumps({'had_torus': torus, 'removed': True}))
""" % ROOT)
    g.check("geometryCOMP auto-crea torus1 (y lo borramos)", ok and bool(d.get("had_torus")),
            json.dumps(d, ensure_ascii=False)[:200])
    if d.get("had_torus"):
        find("trap", "geometryCOMP auto-torus",
             "el geometryCOMP crea un torus POP (800 pts/800 prims) que DIBUJA. Si no lo borrás, "
             "tus 'partículas' no son lo que ves: la verificación del render mide el torus",
             "la receta dice 'borrá el torus1' — su script de referencia NUNCA lo hace",
             "torus presente y renderizando (verificado: apagarlo lleva /particle_swirl de 81572 a 0 px)",
             "lo borré al crear el geo")

    g.call_ok("build_network", {"parent_path": ROOT + "/geo", "operators": [
        {"type": "gridPOP", "name": "grid_emit"},
        {"type": "convertPOP", "name": "topoints"},
        {"type": "nullPOP", "name": "null_render"}],
        "connections": [], "auto_layout": True}, note="emisor + convert + endpoint")
    # CONVERSIÓN CORREGIDA: topointprims (cada punto con su primitiva de punto).
    # la receta dice deleteprims; medimos los dos y elegimos el que dibuja.
    bad, got = set_and_verify(g, ROOT + "/geo/topoints", {"convert": "topointprims"}, "convert=topointprims")
    if bad:
        find("lie", "convertPOP.convert", "set_parameters no aplicó 'convert'", "constantes", str(bad))

    g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "glslPOP", "name": "glsl_curl"})
    g.call_ok("wiring", {"from_path": ROOT + "/geo/grid_emit", "to_path": ROOT + "/geo/topoints", "to_index": 0})
    g.call_ok("wiring", {"from_path": ROOT + "/geo/topoints", "to_path": ROOT + "/geo/glsl_curl", "to_index": 0})
    g.call_ok("wiring", {"from_path": ROOT + "/geo/glsl_curl", "to_path": ROOT + "/geo/null_render", "to_index": 0})

    bad, got = set_and_verify(g, ROOT + "/geo/grid_emit",
                              {"cols": 16, "rows": 16, "slices": 16, "dimension": "rowscolsslicesalways",
                               "sizex": 4.0, "sizey": 4.0, "sizez": 4.0}, "grilla 3D")
    if bad:
        find("lie", "gridPOP pars", "set_parameters no aplicó pars de la grilla", "cols/rows/slices", str(bad))
    ok, d = g.exec_code("""
import json
gp = op('%s/geo/grid_emit')
print('<<JSON>>' + json.dumps({'pts': gp.numPoints(), 'expect': 16*16*16}))
""" % ROOT)
    g.check("gridPOP 3D da cols*rows*slices puntos", (d.get("pts") or 0) == 16 * 16 * 16,
            json.dumps(d, ensure_ascii=False)[:200])

    g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "pointspriteMAT", "name": "pointsprite_mat"})

    # DAT del shader: medimos si el glslPOP auto-dockea DATs (la skill td-glsl-shaders
    # manda escribir en <name>_compute) antes de enlazar nada.
    ok, d = g.exec_code("""
import json
gl = op('%s/geo/glsl_curl')
print('<<JSON>>' + json.dumps({'auto_children_before_bind': [c.name for c in gl.children]}))
""" % ROOT)
    before = d.get("auto_children_before_bind") or []
    g.call_ok("create_operator", {"parent_path": ROOT + "/geo", "type": "textDAT", "name": "shader_compute"})
    g.call_ok("set_dat_content", {"path": ROOT + "/geo/shader_compute", "text": SHADER},
              note="shader validado offline al DAT")
    g.call_ok("set_parameters", {"path": ROOT + "/geo/shader_compute", "values": {"language": "glsl"}})
    ok, d = g.exec_code("""
import json
op('%s/geo/glsl_curl').par.computedat = op('%s/geo/shader_compute')
gl = op('%s/geo/glsl_curl')
print('<<JSON>>' + json.dumps({'dat': str(gl.par.computedat.eval()),
      'auto_children_after_bind': [c.name for c in gl.children]}))
""" % (ROOT, ROOT, ROOT))
    g.check("computedat enlazado al textDAT hermano", ok and "shader_compute" in str(d.get("dat", "")),
            str(d)[:200])
    find("nuance", "glslPOP docked DATs",
         "el glslPOP NO crea DATs dockeados al crearse (children=[]), pero SÍ aparecen "
         "(<name>_info, <name>_compute) al cocinar/enlazar. La skill td-glsl-shaders dice 'escribí el "
         "shader en <name>_compute'; el contrato C3 (textDAT hermano + computedat) es el que funciona "
         "siempre y no depende de cuándo aparecen los docks",
         "skill td-glsl-shaders: shaders en DATs auto-dockeados",
         "children antes del bind: %s · después: %s" % (before, d.get("auto_children_after_bind")),
         "usé textDAT hermano (contrato C3)")

    # uniforms: la receta solo muestra 2 (vec0/vec1); necesito 3 -> numBlocks
    ok, d = g.exec_code("""
import json
gl = op('%s/geo/glsl_curl')
r = {'blocks_before': gl.par.vec.sequence.numBlocks}
gl.par.vec.sequence.numBlocks = 3
r['blocks_after'] = gl.par.vec.sequence.numBlocks
print('<<JSON>>' + json.dumps(r))
""" % ROOT)
    if (d.get("blocks_before") or 0) < 3:
        find("gap", "glslPOP vec sequence",
             "la secuencia vec arranca con numBlocks=1: para N>1 uniforms hay que subirla. La receta "
             "muestra 2 uniforms por set_parameters y no menciona numBlocks",
             "receta: vec0name/vec1name vía set_parameters", "numBlocks default = %s" % d.get("blocks_before"),
             "seteé gl.par.vec.sequence.numBlocks = 3 por exec_code")
    g.check("la secuencia vec acepta 3 bloques", (d.get("blocks_after") or 0) == 3, json.dumps(d)[:200])

    vals = dict(params_r3)
    vals.update({"outputattrs": outputattrs_val,
                 "vec0name": "uTime", "vec1name": "uAmount", "vec2name": "uScale",
                 "vec1valuex": 0.9, "vec2valuex": 1.6})
    bad, got = set_and_verify(g, ROOT + "/geo/glsl_curl", vals, "R3 + outputattrs + 3 uniforms")
    if bad:
        find("lie", "set_parameters en glslPOP",
             "set_parameters responde ok pero NO aplica los pars vecNvaluex del glslPOP "
             "(quedan en el default 0.5)",
             "set_parameters = constantes, aplica", str(bad),
             "escribí por exec_code y releí")
        # corrección en vivo
        g.exec_code("""
import json
gl = op('%s/geo/glsl_curl')
gl.par.vec1valuex.val = 0.9
gl.par.vec2valuex.val = 1.6
print('<<JSON>>' + json.dumps({'v1': gl.par.vec1valuex.eval(), 'v2': gl.par.vec2valuex.eval()}))
""" % ROOT)

    ok, d = g.exec_code("""
import json
s = op('%s/geo/glsl_curl')
s.par.vec0valuex.expr = 'absTime.seconds'
print('<<JSON>>' + json.dumps({'uTime_expr': str(s.par.vec0valuex.expr),
      'vec1': str(s.par.vec1name.eval()), 'vec2': str(s.par.vec2name.eval())}))
""" % ROOT)
    g.check("uTime en modo EXPRESSION", ok and "absTime" in str(d.get("uTime_expr", "")), str(d)[:200])
    ok, d = g.exec_code("""
import json
s = op('%s/geo/glsl_curl')
print('<<JSON>>' + json.dumps({'v1': s.par.vec1valuex.eval(), 'v2': s.par.vec2valuex.eval()}))
""" % ROOT)
    g.check("tras la corrección por exec_code, vec1valuex=0.9",
            ok and abs((d.get("v1") or 0) - 0.9) < 1e-6, json.dumps(d)[:200])

    ok, d = g.exec_code("""
import json
geo = op('%s/geo')
geo.par.material = op('%s/geo/pointsprite_mat')
ren = op('%s/ren')
ren.par.camera = op('%s/cam')
ren.par.geometry = op('%s/geo')
light_par = None
for p in ren.pars():
    if p.name == 'light':
        light_par = 'light'; break
    if p.name.lower().startswith('light'):
        light_par = light_par or p.name
if light_par:
    setattr(ren.par, light_par, op('%s/light'))
print('<<JSON>>' + json.dumps({'mat': str(geo.par.material.eval()),
      'cam': str(ren.par.camera.eval()), 'geo': str(ren.par.geometry.eval()),
      'light_par': light_par}))
""" % (ROOT, ROOT, ROOT, ROOT, ROOT, ROOT))
    g.check("material + bindings del renderTOP", ok and "pointsprite" in str(d.get("mat", ""))
            and "cam" in str(d.get("cam", "")), str(d)[:250])

    # el tamano REAL del sprite es `pointsize` (default 1.0); `attensizenear` no cambia
    # el tamano (medido: 1/8/60 -> mismo px). Ver contrato pointsprite_pars.
    ok, d = g.exec_code("""
import json
mat = op('%s/geo/pointsprite_mat')
mat.par.sizingmodel = 'constatten'
mat.par.pointsize = 1.6
mat.par.blending = True
mat.par.srcblend = 'sa'
mat.par.destblend = 'one'
mat.par.colorr = 1.0
mat.par.colorg = 0.45
mat.par.colorb = 0.85
print('<<JSON>>' + json.dumps({'sizing': str(mat.par.sizingmodel.eval()),
      'pointsize': mat.par.pointsize.eval(), 'blend': bool(mat.par.blending)}))
""" % ROOT)
    g.check("look aplicado (constatten, pointsize 1.6, aditivo rosa)",
            ok and d.get("sizing") == "constatten" and abs((d.get("pointsize") or 0) - 1.6) < 1e-6,
            json.dumps(d)[:200])

    g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 640, "resolutionh": 480}})
    g.call_ok("edit_operator", {"path": ROOT + "/null_view", "display": True, "render": True}, note="flags null_view")
    ok, d = g.exec_code("""
import json
nr = op('%s/geo/null_render')
nr.display = True
nr.render = True
print('<<JSON>>' + json.dumps({'flags': [bool(nr.display), bool(nr.render)]}))
""" % ROOT)
    g.check("terminal del chain dibujable", ok and d.get("flags") == [True, True], str(d)[:150])

    ok, d = g.exec_code("""
import json
chk = op('%s/check')
chk.par.pop = op('%s/geo/null_render')
print('<<JSON>>' + json.dumps({'pop': str(chk.par.pop.eval())}))
""" % (ROOT, ROOT))
    g.check("poptoCHOP -> null_render", ok and "null_render" in str(d.get("pop", "")), str(d)[:150])

    # ══ 2. EXPERIMENTO DECISIVO: deleteprims vs topointprims ════════════
    print("== 2. experimento: deleteprims (receta) vs topointprims (realidad) ==")
    ok, d = g.exec_code("""
import json
%s
tp = op('%s/geo/topoints')
nr = op('%s/geo/null_render')
out = {}
for mode in ('deleteprims', 'topointprims'):
    tp.par.convert = mode
    settle()
    out[mode] = {'px': px(), 'prims': nr.numPrims(), 'pts': nr.numPoints()}
print('<<JSON>>' + json.dumps(out))
""" % (CHAIN, ROOT, ROOT))
    # El hallazgo se descubrió midiendo /particle_swirl ANTES de arreglarla: apagar el flag
    # `render` de su torus1 auto-creado la llevaba de 81572 px a 0 (dibujaba el torus, no las
    # partículas). Se registra el hallazgo con esa evidencia y se deja un guard de regresión:
    # ahora /particle_swirl está arreglada (sin torus, con point prims, render propio).
    find("false-verification", "render_flag_on_terminal + auto-torus",
         "'/particle_swirl' se dio por verificado (35/35 PASS, px>500) MIDIENDO EL TORUS: las "
         "partículas con deleteprims (0 prims) nunca se dibujaron. Apagando el flag render del "
         "torus, su render caía a 0 px",
         "receta: 'borrá el torus1' + 'deleteprims deja una nube que dibuja'",
         "medido 2026-09-29: torus ON 81572 px → torus OFF 0 px (el build de referencia nunca "
         "borraba el torus y su gradable numPrims()==0 lo daba por bueno)",
         "arreglado: auto-torus borrado + convert='topointprims' (build_particle_fx.py)")
    # la guardia compartida tambien se prueba a si misma: monta el auto-torus dibujando y
    # EXIGE que falle (si siempre dijera "si", el bug del torus volveria a pasar).
    ok_t, dt = selftest_render_ownership(g)
    g.check("la guardia puede FALLAR: detecta que dibuja el auto-torus (y pasa sin el)",
            ok_t, json.dumps(dt)[:280])

    g.check("deleteprims -> 0 prims -> render NEGRO (0 px)", (d.get("deleteprims", {}).get("px") or 0) == 0,
            json.dumps(d)[:250])
    g.check("topointprims -> 1 prim/punto -> render dibuja", (d.get("topointprims", {}).get("px") or 0) > 500,
            json.dumps(d)[:250])
    find("lie", "points_need_deleteprims",
         "la receta manda convertPOP(deleteprims) para 'nube de puntos' y afirma que ESO dibuja. "
         "deleteprims deja 0 primitivas y el render sale negro; lo que dibuja es topointprims "
         "(o surftype='points' en el generador)",
         "deleteprims -> nube pura -> render dibuja; gradable numPrims()==0",
         "deleteprims: %s px, %s prims · topointprims: %s px, %s prims" % (
             d.get("deleteprims", {}).get("px"), d.get("deleteprims", {}).get("prims"),
             d.get("topointprims", {}).get("px"), d.get("topointprims", {}).get("prims")),
         "usé convert='topointprims' y cambié el gradable a numPrims()==numPoints()")
    # dejar la conversión buena puesta
    ok2, _ = g.exec_code("import json\nop('%s/geo/topoints').par.convert='topointprims'\nprint('<<JSON>>'+json.dumps({'ok':True}))" % ROOT)

    # ══ 3. verificacion (gradables de la receta, CORREGIDOS) ════════════
    print("== 3. verificacion ==")
    ok, d = g.exec_code("""
import json
%s
settle()
nr = op('%s/geo/null_render')
print('<<JSON>>' + json.dumps({'err': str(op('%s/geo/glsl_curl').errors() or ''),
      'npts': nr.numPoints(), 'nprims': nr.numPrims(),
      'chk_chans': len(op('%s/check').chans())}))
""" % (CHAIN, ROOT, ROOT, ROOT))
    g.check("glsl_curl compila sin errores", ok and not d.get("err"), str(d)[:300])
    g.check("nube de puntos (numPoints>0)", (d.get("npts") or 0) > 0, str(d)[:200])
    g.check("cada punto con su primitiva (numPrims==numPoints): lo que DIBUJA",
            d.get("nprims") == d.get("npts") and (d.get("npts") or 0) > 0, str(d)[:200])

    ok, d = g.exec_code("""
import json
%s
chk = op('%s/check')
gl = op('%s/geo/glsl_curl')
def sigP():
    settle()
    chk.cook(force=True); chk.cook(force=True)
    return [round(c[0], 4) for c in chk.chans() if c.name.startswith('P_')] + \\
           [round(c[chk.numSamples-1], 4) for c in chk.chans() if c.name.startswith('P_')]
def cdrange():
    chk.cook(force=True)
    out = {}
    for c in chk.chans():
        if c.name.startswith('Cd_'):
            vals = [c[i] for i in range(chk.numSamples)]
            out[c.name] = [round(min(vals), 4), round(max(vals), 4)]
    return out
v0 = gl.par.vec0valuex
v0.expr = ''
v0.val = 0.0
a = sigP()
v0.val = 3.0
b = sigP()
v1 = gl.par.vec1valuex
v1.val = 0.0; c0 = sigP()
v1.val = 1.2; c1 = sigP()
v1.val = 0.9
v2 = gl.par.vec2valuex
v2.val = 1.6
v0.expr = 'absTime.seconds'; v0.val = 0.0
settle()
print('<<JSON>>' + json.dumps({'animada_uTime': a != b, 'animada_uAmount': c0 != c1,
      'n_chans': len(chk.chans()), 'cd': cdrange()}))
""" % (CHAIN, ROOT, ROOT))
    g.check("poptoCHOP extrae atributos (>=3 canales)", (d.get("n_chans") or 0) >= 3, str(d)[:200])
    g.check("animado: uTime mueve P (poptoCHOP)", d.get("animada_uTime") is True, str(d)[:250])
    g.check("animado: uAmount mueve P (poptoCHOP)", d.get("animada_uAmount") is True, str(d)[:250])
    cd = d.get("cd") or {}
    g.check("Cd vivo (puntos coloreados)", bool(cd) and any(v[1] > 0.2 for v in cd.values()),
            json.dumps(cd)[:200])

    ok, d = g.exec_code("""
import json
%s
settle()
print('<<JSON>>' + json.dumps({'px': px()}))
""" % CHAIN)
    g.check("el render dibuja (px no negros)", ok and (d.get("px") or 0) > 500,
            json.dumps(d, ensure_ascii=False)[:200])

    g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}})
    r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
    png = g.save_image(r, os.path.join(HERE, "results", g.run_id, "curl_field.png"))
    st = png_stats(png) if png else {"px_lit": 0}
    g.check("render capturado con contenido real (PIL)",
            bool(png) and st.get("px_lit", 0) > 20, json.dumps(st, ensure_ascii=False)[:220])
    g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}})

    g.call_ok("annotation", {"parent_path": ROOT,
                             "comment": "Campo curl-noise: grid_emit (16^3) -> topoints(topointprims: 1 prim/punto, SIN esto el render es negro) -> glsl_curl (curl noise a mano) -> null_render. uTime anima; datos en poptoCHOP 'check'.",
                             "width": 520}, note="anotacion")
    g.call_ok("set_parameters", {"path": ROOT, "values": {"parentshortcut": "CurlField"}})

    errs = g.call_ok("get_errors", {"path": ROOT})
    et = g.text_of(errs)
    g.check("red sin errores", '"count": 0' in et or '"items": []' in et, et[:250])

    out = os.path.join(HERE, "results", g.run_id, "findings.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(FINDINGS, f, ensure_ascii=False, indent=2)
    print(f"\nHALLAZGOS SOBRE LA RECETA ({len(FINDINGS)}): {out}")
    for f_ in FINDINGS:
        print("  -", f_["kind"], "|", f_["area"], "|", f_["symptom"][:100])

    s = g.summary()
    print("\nBUILD:", json.dumps(s, ensure_ascii=False))
    print(f"\nRed lista en {ROOT} (abrí el viewer de {ROOT}/null_view). PNGs: results/{g.run_id}/")
    return 0 if s["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

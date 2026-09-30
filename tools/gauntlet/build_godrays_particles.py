#!/usr/bin/env python3
"""build_godrays_particles.py — variación completa del SARVJ: partículas 3D POP
(instancias vía pointspriteMAT) + God Rays de post-proceso, en un contenedor.

Pipeline (igual al original, pero con loop constante en el shader = sin TDR):
  geo: spherePOP(emit) -> particlePOP -> forceradialPOP(gravedad) -> convertPOP(topointprims) -> nullPOP
  render: geometryCOMP + camera + light -> renderTOP -> god rays glslTOP -> nullTOP
Exporta D:/TD/POPs/POPs SARVJ/GodRays_Particles.tox
"""
from __future__ import annotations
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gauntlet_client import Gauntlet  # noqa: E402
from td_probe import chain_source  # noqa: E402

g = Gauntlet(phase="build-godrays-particles", run_id=time.strftime("%Y%m%d-%H%M%S"))
g.init()
ROOT = "/project1/GodRays_Particles"
GEO = ROOT + "/geo"
CHAIN = chain_source(ROOT)   # settle()/px()/render_is_ours() no se copian: se importan

GODRAYS_SHADER = """layout(location = 0) out vec4 fragColor;
uniform vec2 uCenter;
uniform float uStrength;
uniform vec3 uTint;
const int SAMPLES = 32;  // loop CONSTANTE: sin TDR

void main(void)
{
    vec2 res = uTD2DInfos[0].res.zw;
    vec2 pos = uCenter * res;
    vec2 dir = (gl_FragCoord.xy-pos)/res;
    float dist = length(dir);

    vec4 color = vec4(0.0,0.0,0.0,0.0);
    for (int i = 0; i < SAMPLES; i += 2)
    {
        color += texture(sTD2DInputs[0],vUV.st+float(i)/float(SAMPLES)*dir*-uStrength);
        color += texture(sTD2DInputs[0],vUV.st+float(i+1)/float(SAMPLES)*dir*-uStrength);
    }
    color /= float(SAMPLES);

    float falloff = 1.0 - smoothstep(0.0, 1.0, dist) * 0.55;
    vec3 tinted = color.rgb * mix(vec3(1.0), uTint, falloff);
    fragColor = vec4(tinted, color.a);
}
"""

# ── 1. limpiar + baseCOMP ──
g.exec_code(f"import json\ntry:\n op('{ROOT}').destroy()\n print('<<JSON>>' + json.dumps({{'clean':1}}))\nexcept Exception as e:\n print('<<JSON>>' + json.dumps({{'clean':0,'e':str(e)}}))")
g.call_ok("create_operator", {"parent_path": "/project1", "type": "baseCOMP", "name": "GodRays_Particles",
                              "nodeX": 400, "nodeY": 400, "display": True}, note="baseCOMP principal")

# ── 2. estructura de render ──
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo"},
    {"type": "cameraCOMP", "name": "cam"},
    {"type": "lightCOMP", "name": "light"},
    {"type": "renderTOP", "name": "ren"},
    {"type": "glslTOP", "name": "godrays"},
    {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "godrays"}, {"from": "godrays", "to": "null_view"}],
    "auto_layout": True}, note="estructura render + god rays")

# ── 3. borrar auto-torus del geometryCOMP ──
ok, d = g.exec_code(f"""
import json
geo = op('{GEO}')
torus = [c.name for c in geo.children if c.name.lower().startswith('torus')]
for n in torus:
    geo.op(n).destroy()
print('<<JSON>>' + json.dumps({{'had_torus': torus, 'kids': [c.name for c in geo.children]}}))
""")
g.check("auto-torus borrado", ok and bool(d.get("had_torus")), json.dumps(d, ensure_ascii=False)[:150])

# ── 4. cadena de partículas dentro del geometryCOMP ──
g.call_ok("build_network", {"parent_path": GEO, "operators": [
    {"type": "spherePOP", "name": "emit"},
    {"type": "particlePOP", "name": "particles"},
    {"type": "forceradialPOP", "name": "gravity"},
    {"type": "convertPOP", "name": "topoints"},
    {"type": "nullPOP", "name": "null_render"}],
    "connections": [{"from": "emit", "to": "particles"}, {"from": "particles", "to": "gravity"},
                    {"from": "gravity", "to": "topoints"}, {"from": "topoints", "to": "null_render"}],
    "auto_layout": True}, note="cadena POP partículas")

# ── 5. parámetros de partículas (nombres reales verificados) ──
g.call_ok("set_parameters", {"path": GEO + "/emit", "values": {"radx": 0.4, "rady": 0.4, "radz": 0.4, "cols": 6, "rows": 6}},
          note="esfera emisora")
g.call_ok("set_parameters", {"path": GEO + "/particles", "values": {"birthrate": 60, "life": 3.0, "initvelocityy": 2.5, "maxparticles": 600, "timeintegration": True}},
          note="partículas: nacen, suben y se mueven")
g.call_ok("set_parameters", {"path": GEO + "/topoints", "values": {"convert": "topointprims"}}, note="topointprims → instancias de puntos")
# gravedad + flags del terminal (propiedades, no params)
ok, d = g.exec_code(f"""
import json
gv = op('{GEO}/gravity')
gv.par.globforcemult = 1
gv.par.globforcey = -5
nr = op('{GEO}/null_render')
nr.display = True
nr.render = True
# cámara en el renderTOP
op('{ROOT}/ren').par.camera = './cam'
print('<<JSON>>' + json.dumps({{'gf': gv.par.globforcemult.eval(), 'display': bool(nr.display)}}))
""")
g.check("gravedad + flags + cámara", ok and d.get("gf") == 1, json.dumps(d, ensure_ascii=False)[:150])

# ── 6. material pointsprite (instancias) ──
g.call_ok("create_operator", {"parent_path": GEO, "type": "pointspriteMAT", "name": "pointsprite_mat"}, note="material instancias")
ok, d = g.exec_code(f"""
import json
geo = op('{GEO}')
mat = op('{GEO}/pointsprite_mat')
# asignar material al geometryCOMP
geo.par.material = mat
print('<<JSON>>' + json.dumps({{'mat': str(geo.par.material.eval())}}))
""")
g.check("material asignado", ok and "pointsprite" in str(d.get("mat", "")), str(d)[:120])

# ── 7. shader god rays (DAT + bind + uniforms) ──
g.call_ok("create_operator", {"parent_path": ROOT, "type": "textDAT", "name": "godrays_pixel"}, note="DAT shader god rays")
g.call_ok("set_dat_content", {"path": ROOT + "/godrays_pixel", "text": GODRAYS_SHADER}, note="escribir shader")
g.call_ok("set_parameters", {"path": ROOT + "/godrays_pixel", "values": {"language": "glsl"}}, note="language glsl")
ok, d = g.exec_code(f"""
import json
gl = op('{ROOT}/godrays')
gl.par.pixeldat = '{ROOT}/godrays_pixel'
gl.par.vec0name.val = 'uCenter'
gl.par.vec0valuex = 0.5
gl.par.vec0valuey = 0.5
gl.par.vec1name.val = 'uStrength'
gl.par.vec1valuex = 0.4
gl.par.vec2name.val = 'uTint'
gl.par.vec2valuex = 1.0
gl.par.vec2valuey = 0.7
gl.par.vec2valuez = 0.3
print('<<JSON>>' + json.dumps({{'pd': str(gl.par.pixeldat.eval())}}))
""")
g.check("shader god rays enlazado", ok and "godrays_pixel" in str(d.get("pd", "")), str(d)[:120])

# ── 8. verificación: asentar (helper compartido) + poptoCHOP + get_errors ──
ok, d = g.exec_code(f"""
import json
{CHAIN}
chk = op('{ROOT}/check')
chk.par.pop = '{GEO}/null_render'
settle()
chk.cook(force=True)
chans = [c.name for c in chk.chans()]
npts = chk.numSamples
print('<<JSON>>' + json.dumps({{'chans': chans[:5], 'npts': npts}}))
""")
g.check("poptoCHOP cuenta partículas", ok and d.get("npts", 0) > 0, json.dumps(d, ensure_ascii=False)[:150])
g.call("get_errors", {"path": ROOT}, note="errores finales")

# ── 9. exportar .tox ──
TOX_OUT = r"D:/TD/POPs/POPs SARVJ/GodRays_Particles.tox"
ok_tox, d_tox = g.exec_code(f"""
import json, os
op('{ROOT}').save('{TOX_OUT}')
print('<<JSON>>' + json.dumps({{'saved': os.path.isfile('{TOX_OUT}'), 'path': '{TOX_OUT}'}}))
""")
g.check("exportado a .tox", ok_tox and d_tox.get("saved"), json.dumps(d_tox, ensure_ascii=False)[:150])

report = {"ok": len(g.failures) == 0, "failures": g.failures, "npts": d.get("npts", 0),
          "tox": TOX_OUT if (ok_tox and d_tox.get("saved")) else None,
          "tools": [l["tool"] for l in g.log]}
with open(os.path.join(g.out_dir, "build-godrays-particles-report.json"), "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print("\n=== PARTICLES + GOD RAYS ===")
print("ok:", report["ok"], "| npts:", report["npts"], "| .tox:", report["tox"], "| failures:", g.failures)

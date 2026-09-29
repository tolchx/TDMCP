#!/usr/bin/env python3
"""build_godrays_variation.py — variación PRECISA del God Rays de SARVJ en un
contenedor nuevo (/project1/GodRays_Variation).

Cambios precisos sobre el shader original (god_rays_pixel):
  1. + uniform vec3 uTint   (tinte cromático)
  2. + uniform float uFalloff (atenuación radial)
  3. dist = length(dir); falloff = 1 - smoothstep(0,1,dist)*uFalloff
  4. fragColor.rgb *= mix(vec3(1), uTint, falloff)  → cálido al centro, frío afuera

Entrada: in1 (inTOP) → glsl_variation (glslTOP) → out1 (nullTOP).
Se cablea a /project1/render1 para ser una variación REAL del mismo render.
"""
from __future__ import annotations
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gauntlet_client import Gauntlet  # noqa: E402

g = Gauntlet(phase="build-godrays-variation", run_id=os.environ.get("GAUNTLET_RUN_ID") or time.strftime("%Y%m%d-%H%M%S"))
g.init()
ROOT = "/project1/GodRays_Variation"

VARIATION_SHADER = """layout(location = 0) out vec4 fragColor;
uniform vec2 uCenter;
uniform int uSamples;
uniform float uStrength;
uniform vec3 uTint;      // VARIACIÓN 1: tinte cromático
uniform float uFalloff;  // VARIACIÓN 2: atenuación radial

void main(void)
{
    vec2 res = uTD2DInfos[0].res.zw;
    vec2 pos = uCenter * res;
    vec2 dir = (gl_FragCoord.xy-pos)/res;
    float dist = length(dir);   // VARIACIÓN 2: distancia radial

    vec4 color = vec4(0.0,0.0,0.0,0.0);
    for (int i = 0; i < uSamples; i += 2)
    {
        color += texture(sTD2DInputs[0],vUV.st+float(i)/float(uSamples)*dir*-uStrength);
        color += texture(sTD2DInputs[0],vUV.st+float(i+1)/float(uSamples)*dir*-uStrength);
    }
    color /= float(uSamples);

    // VARIACIÓN: tinte cálido al centro, atenuación con la distancia
    float falloff = 1.0 - smoothstep(0.0, 1.0, dist) * uFalloff;
    vec3 tinted = color.rgb * mix(vec3(1.0), uTint, falloff);
    fragColor = vec4(tinted, color.a);
}
"""

# ── 1. limpiar si existía ──
g.exec_code(f"import json\ntry:\n op('{ROOT}').destroy()\n print('<<JSON>>' + json.dumps({{'clean':1}}))\nexcept Exception as e:\n print('<<JSON>>' + json.dumps({{'clean':0,'e':str(e)}}))")

# ── 2. baseCOMP + cadena ──
g.call_ok("create_operator", {"parent_path": "/project1", "type": "baseCOMP", "name": "GodRays_Variation",
                              "nodeX": 200, "nodeY": 200, "display": True}, note="baseCOMP variación")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "inTOP", "name": "in1"},
    {"type": "glslTOP", "name": "glsl_variation"},
    {"type": "nullTOP", "name": "out1"}],
    "connections": [{"from": "in1", "to": "glsl_variation"}, {"from": "glsl_variation", "to": "out1"}],
    "auto_layout": True}, note="inTOP → glslTOP → nullTOP")

# ── 3. shader al DAT (set_dat_content) ──
g.call_ok("create_operator", {"parent_path": ROOT, "type": "textDAT", "name": "shader_pixel"}, note="DAT del shader")
g.call_ok("set_dat_content", {"path": ROOT + "/shader_pixel", "text": VARIATION_SHADER}, note="escribir shader variación")
g.call_ok("set_parameters", {"path": ROOT + "/shader_pixel", "values": {"language": "glsl"}}, note="language glsl")

# ── 4. enlazar computedat + uniforms ──
ok, d = g.exec_code(f"""
import json
gl = op('{ROOT}/glsl_variation')
gl.par.pixeldat = '{ROOT}/shader_pixel'
gl.par.resolutionw = 640
gl.par.resolutionh = 640
# uniforms: uCenter (vec2), uSamples (int), uStrength (float), uTint (vec3), uFalloff (float)
gl.par.vec0name.val = 'uCenter'
gl.par.vec0valuex = 0.5
gl.par.vec0valuey = 0.5
gl.par.vec1name.val = 'uSamples'
gl.par.vec1valuex = 32
gl.par.vec1valuey = 0.35
gl.par.vec1name.val = 'uStrength'
gl.par.vec2name.val = 'uTint'
gl.par.vec2valuex = 1.0
gl.par.vec2valuey = 0.7
gl.par.vec2valuez = 0.3
gl.par.vec2valuew = 0.6
print('<<JSON>>' + json.dumps({{'pixeldat': str(gl.par.pixeldat.eval()), 'vec0': gl.par.vec0name.val, 'vec1': gl.par.vec1name.val, 'vec2': gl.par.vec2name.val}}))
""")
print("enlace shader:", ok, d if not ok else "")

# ── 5. cablear al render del fluid solver ──
g.call_ok("wiring", {"from_path": "/project1/render1", "to_path": ROOT + "/in1", "to_index": 0}, note="render1 → variación")

# ── 6. verificar ──
g.call("get_errors", {"path": ROOT}, note="errores de la variación")
time.sleep(0.5)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call("view_operator", {"path": ROOT + "/out1", "resolution": "small"}, note="captura variación")
job = g.json_of(r).get("job_id", "")
time.sleep(0.4)
r2 = g.call("view_operator", {"path": ROOT + "/out1", "job_id": job}, note=f"retrieve {job}") if job else r
img = g.save_image(r2, os.path.join(g.out_dir, "godrays_variation.png"))
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

report = {"ok": len(g.failures) == 0, "failures": g.failures, "png": bool(img),
          "shader": VARIATION_SHADER, "tools": [l["tool"] for l in g.log]}
with open(os.path.join(g.out_dir, "build-godrays-variation-report.json"), "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print("\n=== VARIACIÓN ===")
print("ok:", report["ok"], "| PNG:", report["png"], "| failures:", g.failures)

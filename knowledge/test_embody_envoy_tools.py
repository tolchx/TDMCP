"""Prueba de las nuevas herramientas integradas inspiradas en Embody, Envoy y TDXN:
1. t_tdxn_export (TDXN v2.1 YAML)
2. t_eval_render_frame (Evaluación de calidad de render y veredicto PASS/FAIL)
3. t_get_op_errors_deep (Inspección profunda de errores, warnings y shaders)
"""
import sys
import os
import json
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import live

print("=== 1. Probando t_tdxn_export (TDXN v2.1 YAML) ===")
TMP = os.path.join(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()), "Temp")
tdxn_file = os.path.join(TMP, "test_network.tdxn")

# Creamos un pequeño sandbox en TD para probar
live.exec_code(r'''
import json
root = op('/')
for c in list(root.children):
    if c.name == 'test_embody_box' and c.valid: c.destroy()
box = root.create('baseCOMP', 'test_embody_box')
n = box.create('noiseTOP', 'noise_tex')
n.par.resolutionw = 512
n.par.resolutionh = 512
n.par.amp = 0.8
n.par.seed.expr = 'absTime.frame % 100'
l = box.create('levelTOP', 'level_adj')
l.inputConnectors[0].connect(n)
l.par.opacity.expr = 'parent().par.w / 1000.0'
o = box.create('outTOP', 'out1')
o.inputConnectors[0].connect(l)
o.display = True
print('<<JSON>>' + json.dumps({'ok': True}))
''')

# Exportar como TDXN
res_tdxn = live.t_tdxn_export({"root_path": "/test_embody_box", "out_path": tdxn_file})
print("Resultado TDXN Export:")
print(json.dumps(res_tdxn, indent=2))
assert res_tdxn["ok"] is True
assert res_tdxn["format"] == "tdxn"
assert os.path.exists(tdxn_file)

with open(tdxn_file, "r", encoding="utf-8") as f:
    yaml_content = f.read()
print("\nPrimeras 25 líneas del YAML exportado:")
print("\n".join(yaml_content.splitlines()[:25]))
assert "format: tdxn" in yaml_content
assert "version: '2.0'" in yaml_content

print("\n=== 2. Probando t_eval_render_frame ===")
# Evaluar el operador out1 activo
res_eval = live.t_eval_render_frame({"op_path": "/test_embody_box/out1"})
print("Resultado de evaluación visual:")
print(json.dumps(res_eval, indent=2))
assert res_eval["ok"] is True
assert res_eval["quality"] in ("PASS", "FAIL")

# Ahora creamos un TOP negro puro para verificar que detecte FAIL correctamente
live.exec_code(r'''
import json
box = op('/test_embody_box')
black = box.create('constantTOP', 'black_test')
black.par.colorr = 0
black.par.colorg = 0
black.par.colorb = 0
black.par.alpha = 1
print('<<JSON>>' + json.dumps({'ok': True}))
''')
res_black = live.t_eval_render_frame({"op_path": "/test_embody_box/black_test"})
print("\nResultado de evaluación sobre constantTOP negro (debe dar FAIL):")
print(json.dumps(res_black, indent=2))
assert res_black["quality"] == "FAIL"
assert "NEGRO" in res_black["verdict"]

print("\n=== 3. Probando t_get_op_errors_deep ===")
res_errors = live.t_get_op_errors_deep({"root_path": "/test_embody_box"})
print("Resultado de errores profundos:")
print(json.dumps(res_errors, indent=2))
assert "error_count" in res_errors

# Cleanup sandbox y archivo
print("\n=== 4. Limpieza ===")
live.call("delete_operator", {"path": "/test_embody_box"})
if os.path.exists(tdxn_file):
    os.remove(tdxn_file)
print("Limpieza completada con éxito.")
print("\n¡TODAS LAS PRUEBAS DE LAS NUEVAS HERRAMIENTAS PASARON 100% OK!")

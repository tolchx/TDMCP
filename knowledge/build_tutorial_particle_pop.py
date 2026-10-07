"""
build_tutorial_particle_pop.py — Construcción y verificación ejecutable en TouchDesigner
del tutorial "A Look at the Particle POP in TouchDesigner" (Interactive & Immersive HQ / Jack Delora).

Arquitectura:
/project1/tut_particle_pop (baseCOMP):
  - ramp_tex (rampTOP): Rampa de color con fundido alpha
  - geo (geometryCOMP):
      - emit (spherePOP): Emisor esférico con normales
      - sim (particlePOP): Motor de partículas con loop targetpop
      - force_up (mathmixPOP): Fuerza ascendente constante
      - curl (noisePOP): Turbulencia 3D
      - damp (transformPOP): Escala 0.96 para amortiguación centrípeta
      - sim_target (nullPOP): Terminal del bucle de feedback (targetpop)
      - color_map (lookuptexturePOP): Mapea ramp_tex al atributo Color
      - trail (trailPOP): Estelas temporales basadas en PartId
      - topoints (convertPOP): Conversión a point primitives
      - null_out (nullPOP): Terminal de render (display/render flags)
  - mat (pointspriteMAT): Point size = 3.0
  - cam (cameraCOMP)
  - light (lightCOMP)
  - ren (renderTOP)
  - out (nullTOP)
"""

import time
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live

COMP_PATH = "/project1/tut_particle_pop"


def build():
    print(f"=== [1/4] Construyendo Particle POP Tutorial en {COMP_PATH} ===")
    
    # Limpiar si ya existía
    live.call("delete_operator", {"path": COMP_PATH})
    
    # 1. Crear contenedor base
    ok, res = live.call("create_operator", {"type": "baseCOMP", "name": "tut_particle_pop", "parent_path": "/project1"})
    assert ok, f"Error creando baseCOMP: {res}"
    
    # 2. Rampa de color (rampTOP)
    ok, res = live.call("create_operator", {"type": "rampTOP", "name": "ramp_tex", "parent_path": COMP_PATH})
    assert ok, f"Error creando ramp_tex: {res}"
    
    setup_ramp = f"""
r = op('{COMP_PATH}/ramp_tex')
r.par.resolutionw = 256
r.par.resolutionh = 1
r.par.format = 'rgba32float'
"""
    live.call("execute_code", {"code": setup_ramp})
    
    # 3. Geometry container
    ok, res = live.call("create_operator", {"type": "geometryCOMP", "name": "geo", "parent_path": COMP_PATH})
    assert ok, f"Error creando geometryCOMP: {res}"
    
    # Borrar torus por defecto del geometryCOMP (Contrato C2 autotorus_masks_render)
    live.call("delete_operator", {"path": f"{COMP_PATH}/geo/torus1"})
    
    geo_path = f"{COMP_PATH}/geo"
    
    # 4. Operadores POP dentro de geo
    # 4a. Emisor spherePOP
    ok, res = live.call("create_operator", {"type": "spherePOP", "name": "emit", "parent_path": geo_path})
    assert ok, f"Error creando emit: {res}"
    
    # 4b. particlePOP
    ok, res = live.call("create_operator", {"type": "particlePOP", "name": "sim", "parent_path": geo_path})
    assert ok, f"Error creando sim: {res}"
    
    # 4c. mathmixPOP (fuerza ascendente)
    ok, res = live.call("create_operator", {"type": "mathmixPOP", "name": "force_up", "parent_path": geo_path})
    assert ok, f"Error creando force_up: {res}"
    
    # 4d. noisePOP (turbulencia de velocidad)
    ok, res = live.call("create_operator", {"type": "noisePOP", "name": "curl", "parent_path": geo_path})
    assert ok, f"Error creando curl: {res}"
    
    # 4e. transformPOP (damp centrípeto)
    ok, res = live.call("create_operator", {"type": "transformPOP", "name": "damp", "parent_path": geo_path})
    assert ok, f"Error creando damp: {res}"
    
    # 4f. nullPOP para cerrar el loop de feedback (Contrato C10 particle_feedback_loop)
    ok, res = live.call("create_operator", {"type": "nullPOP", "name": "sim_target", "parent_path": geo_path})
    assert ok, f"Error creando sim_target: {res}"
    
    # 4g. lookuptexturePOP (color por edad)
    ok, res = live.call("create_operator", {"type": "lookuptexturePOP", "name": "color_map", "parent_path": geo_path})
    assert ok, f"Error creando color_map: {res}"
    
    # 4h. trailPOP (estelas temporales)
    ok, res = live.call("create_operator", {"type": "trailPOP", "name": "trail", "parent_path": geo_path})
    assert ok, f"Error creando trail: {res}"
    
    # 4i. convertPOP (Contrato C2 points_need_pointprims)
    ok, res = live.call("create_operator", {"type": "convertPOP", "name": "topoints", "parent_path": geo_path})
    assert ok, f"Error creando topoints: {res}"
    
    # 4j. nullPOP de salida
    ok, res = live.call("create_operator", {"type": "nullPOP", "name": "null_out", "parent_path": geo_path})
    assert ok, f"Error creando null_out: {res}"
    
    # 5. Cableado del loop y de la cadena post-processing
    chain = [
        ("emit", "sim"),
        ("sim", "force_up"),
        ("force_up", "curl"),
        ("curl", "damp"),
        ("damp", "sim_target"),
        ("sim_target", "color_map"),
        ("color_map", "trail"),
        ("trail", "topoints"),
        ("topoints", "null_out")
    ]
    for src, dst in chain:
        ok, res = live.call("wiring", {"from_path": f"{geo_path}/{src}", "to_path": f"{geo_path}/{dst}", "to_index": 0})
        assert ok, f"Error cableando {src} -> {dst}: {res}"
        
    # 6. Configurar parámetros vía Python (execute_code)
    setup_pops = f"""
# Configurar emisor
e = op('{geo_path}/emit')
e.par.radx = 0.3
e.par.rady = 0.3
e.par.radz = 0.3
e.par.rows = 16
e.par.cols = 16

# Configurar simulador particlePOP con feedback loop (Contrato C10)
s = op('{geo_path}/sim')
s.par.birthrate = 1500
s.par.life = 2.5
s.par.lifevariance = 0.5
s.par.timeintegration = True
s.par.targetpop = op('{geo_path}/sim_target')
s.par.pointidreuse = 'none'

# Configurar force_up (mathmixPOP)
f = op('{geo_path}/force_up')
f.par.comb0oper = 'add'
f.par.comb0scopea = 'PartForce'
f.par.comb0scopeb = '0 0.05 0'
f.par.comb0result = 'PartForce'

# Configurar curl noise
c = op('{geo_path}/curl')
c.par.type = 'simplex3d'
c.par.curl3d = True
c.par.amp = 0.4
c.par.period = 1.2
c.par.tz.expr = 'absTime.seconds * 0.15'

# Configurar damp transform
d = op('{geo_path}/damp')
d.par.sx = 0.98
d.par.sy = 0.98
d.par.sz = 0.98

# Configurar color_map
cm = op('{geo_path}/color_map')
cm.par.top = op('{COMP_PATH}/ramp_tex')
cm.par.overrideautoattr = True
cm.par.outputattrscope = 'Color'
cm.par.attrtype = 'color'

# Configurar trailPOP
tr = op('{geo_path}/trail')
tr.par.length = 6
tr.par.attrmatch = True
tr.par.attrname = 'PartId'

# Configurar convertPOP
cp = op('{geo_path}/topoints')
cp.par.convert = 'topointprims'

# Flags terminales (Contrato C2)
nout = op('{geo_path}/null_out')
nout.display = True
nout.render = True
"""
    ok, res = live.call("execute_code", {"code": setup_pops})
    assert ok, f"Error configurando parámetros POP: {res}"
    
    # 7. Render setup
    ok, res = live.call("create_operator", {"type": "cameraCOMP", "name": "cam", "parent_path": COMP_PATH})
    assert ok, f"Error creando cam: {res}"
    
    ok, res = live.call("create_operator", {"type": "lightCOMP", "name": "light", "parent_path": COMP_PATH})
    assert ok, f"Error creando light: {res}"
    
    ok, res = live.call("create_operator", {"type": "pointspriteMAT", "name": "mat", "parent_path": COMP_PATH})
    assert ok, f"Error creando mat: {res}"
    
    ok, res = live.call("create_operator", {"type": "renderTOP", "name": "ren", "parent_path": COMP_PATH})
    assert ok, f"Error creando ren: {res}"
    
    ok, res = live.call("create_operator", {"type": "nullTOP", "name": "out", "parent_path": COMP_PATH})
    assert ok, f"Error creando out: {res}"
    
    ok, res = live.call("wiring", {"from_path": f"{COMP_PATH}/ren", "to_path": f"{COMP_PATH}/out", "to_index": 0})
    assert ok, f"Error cableando ren -> out: {res}"
    
    setup_render = f"""
m = op('{COMP_PATH}/mat')
m.par.pointsize = 3.0

g = op('{COMP_PATH}/geo')
g.par.material = op('{COMP_PATH}/mat')

cam = op('{COMP_PATH}/cam')
cam.par.tz = 4.0

ren = op('{COMP_PATH}/ren')
ren.par.resolutionw = 1280
ren.par.resolutionh = 720
ren.par.camera = op('{COMP_PATH}/cam')
ren.par.geometry = op('{COMP_PATH}/geo')
ren.cook(force=True)
"""
    ok, res = live.call("execute_code", {"code": setup_render})
    assert ok, f"Error configurando render: {res}"
    print("=== Red tut_particle_pop construida con éxito ===")


def verify():
    print("=== Verificando estado numérico y render de tut_particle_pop ===")
    check_code = f"""
import json
import time

sim = op('{COMP_PATH}/geo/sim')
nout = op('{COMP_PATH}/geo/null_out')
ren = op('{COMP_PATH}/ren')

# Bucle settle (Contrato C1 cook_lag)
for _ in range(6):
    sim.cook(force=True)
    nout.cook(force=True)
    ren.cook(force=True)
    time.sleep(0.04)

pts = nout.numPoints()
prims = nout.numPrims()
attrs = [a.name for a in nout.pointAttributes]

# Verificación de renderTOP en píxeles (Contrato C5)
arr = ren.numpyArray()
lit_pixels = int((arr[:, :, :3].max(axis=2) > 0.01).sum())

print("{live.MARK}" + json.dumps({{
    "points": pts,
    "prims": prims,
    "has_color": 'Color' in attrs,
    "has_partid": 'PartId' in attrs,
    "has_partvel": 'PartVel' in attrs,
    "render_width": ren.width,
    "render_height": ren.height,
    "lit_pixels": lit_pixels
}}))
"""
    ok, data = live.exec_code(check_code)
    assert ok, f"Fallo al ejecutar código de verificación: {data}"
    print("Métricas obtenidas:", data)
    assert data.get("points") > 0, f"Puntos esperados > 0, obtenido {data.get('points')}"
    assert data.get("prims") > 0, f"Primitivas esperadas > 0, obtenido {data.get('prims')}"
    assert data.get("has_color"), "Atributo Color no detectado"
    assert data.get("has_partid"), "Atributo PartId no detectado"
    assert data.get("lit_pixels") > 0, f"Render vacío: lit_pixels={data.get('lit_pixels')}"
    print(">>> VERIFICACIÓN [PASS]: 100% verde en simulación, atributos y render.")


if __name__ == "__main__":
    build()
    time.sleep(0.5)
    verify()

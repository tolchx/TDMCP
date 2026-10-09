"""
build_tutorial_paketa12_advection.py — Construcción y verificación ejecutable en TouchDesigner
del tutorial "3D Particle Flowfield Advection & Trails with POPs" (Paketa12 & The NODE Institute).

Arquitectura:
/project1/tut_paketa12_advection (baseCOMP):
  - ramp_tex (rampTOP): Rampa de color con fundido alpha
  - geo (geometryCOMP):
      - emit (spherePOP): Emisor de partículas esférico
      - sim (particlePOP): Simulador con targetpop feedback loop
      - curl (noisePOP): Campo de advección vectorial curl 3D
      - field (fieldPOP): Campo delimitador esférico de influencia/peso
      - damp (transformPOP): Amortiguación centrípeta
      - tgt (nullPOP): Terminal del bucle de feedback (targetpop)
      - color_map (lookuptexturePOP): Mapea rampa a atributo Color
      - trail (trailPOP): Generación de estelas temporales por PartId
      - topoints (convertPOP): Conversión a point primitives
      - null_out (nullPOP): Terminal de render (display/render flags)
  - mat (pointspriteMAT): Point size = 3.0, aditivo
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

COMP_PATH = "/project1/tut_paketa12_advection"


def build():
    print(f"=== Construyendo tutorial Paketa12 Advection & Trails en {COMP_PATH} ===")
    
    # Limpiar si ya existía
    live.call("delete_operator", {"path": COMP_PATH})
    
    # 1. Crear contenedor base
    ok, res = live.call("create_operator", {"type": "baseCOMP", "name": "tut_paketa12_advection", "parent_path": "/project1"})
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
    
    # Borrar torus por defecto (Contrato C2 autotorus_masks_render)
    live.call("delete_operator", {"path": f"{COMP_PATH}/geo/torus1"})
    
    geo_path = f"{COMP_PATH}/geo"
    
    # 4. Operadores POP dentro de geo
    # 4a. Emisor spherePOP
    ok, res = live.call("create_operator", {"type": "spherePOP", "name": "emit", "parent_path": geo_path})
    assert ok, f"Error creando emit: {res}"
    
    # 4b. particlePOP
    ok, res = live.call("create_operator", {"type": "particlePOP", "name": "sim", "parent_path": geo_path})
    assert ok, f"Error creando sim: {res}"
    
    # 4c. noisePOP (campo curl 3D)
    ok, res = live.call("create_operator", {"type": "noisePOP", "name": "curl", "parent_path": geo_path})
    assert ok, f"Error creando curl: {res}"
    
    # 4d. fieldPOP (campo esférico)
    ok, res = live.call("create_operator", {"type": "fieldPOP", "name": "field", "parent_path": geo_path})
    assert ok, f"Error creando field: {res}"
    
    # 4e. transformPOP (damp)
    ok, res = live.call("create_operator", {"type": "transformPOP", "name": "damp", "parent_path": geo_path})
    assert ok, f"Error creando damp: {res}"
    
    # 4f. nullPOP para cerrar el loop de feedback (Contrato C10 particle_feedback_loop)
    ok, res = live.call("create_operator", {"type": "nullPOP", "name": "tgt", "parent_path": geo_path})
    assert ok, f"Error creando tgt: {res}"
    
    # 4g. lookuptexturePOP (color)
    ok, res = live.call("create_operator", {"type": "lookuptexturePOP", "name": "color_map", "parent_path": geo_path})
    assert ok, f"Error creando color_map: {res}"
    
    # 4h. trailPOP (estelas)
    ok, res = live.call("create_operator", {"type": "trailPOP", "name": "trail", "parent_path": geo_path})
    assert ok, f"Error creando trail: {res}"
    
    # 4i. convertPOP (Contrato C2 points_need_pointprims)
    ok, res = live.call("create_operator", {"type": "convertPOP", "name": "topoints", "parent_path": geo_path})
    assert ok, f"Error creando topoints: {res}"
    
    # 4j. nullPOP de salida
    ok, res = live.call("create_operator", {"type": "nullPOP", "name": "null_out", "parent_path": geo_path})
    assert ok, f"Error creando null_out: {res}"
    
    # 5. Cableado POP en cadena
    chain = [
        ("emit", "sim"),
        ("sim", "curl"),
        ("curl", "field"),
        ("field", "damp"),
        ("damp", "tgt"),
        ("tgt", "color_map"),
        ("color_map", "trail"),
        ("trail", "topoints"),
        ("topoints", "null_out")
    ]
    for src, dst in chain:
        ok, res = live.call("wiring", {"from_path": f"{geo_path}/{src}", "to_path": f"{geo_path}/{dst}", "to_index": 0})
        assert ok, f"Error cableando {src} -> {dst}: {res}"
        
    # 6. Configurar parámetros POP vía Python
    setup_pops = f"""
# Configurar emisor spherePOP
e = op('{geo_path}/emit')
e.par.radx = 0.5
e.par.rady = 0.5
e.par.radz = 0.5
e.par.rows = 16
e.par.cols = 16

# Configurar simulador particlePOP con feedback loop (Contrato C10)
s = op('{geo_path}/sim')
s.par.birthrate = 1600
s.par.life = 2.4
s.par.lifevariance = 0.5
s.par.timeintegration = True
s.par.targetpop = op('{geo_path}/tgt')
s.par.pointidreuse = 'none'

# Configurar curl 3D advection field
c = op('{geo_path}/curl')
c.par.type = 'simplex3d'
c.par.curl3d = True
c.par.amp0 = 0.55
c.par.period = 1.3
c.par.tz.expr = 'absTime.seconds * 0.12'

# Configurar fieldPOP (influencia esférica)
fp = op('{geo_path}/field')
fp.par.mode = 'sphere'
fp.par.radx = 1.2
fp.par.rady = 1.2
fp.par.radz = 1.2
fp.par.weight = True

# Configurar amortiguación
d = op('{geo_path}/damp')
d.par.sx = 0.985
d.par.sy = 0.985
d.par.sz = 0.985

# Configurar color_map
cm = op('{geo_path}/color_map')
cm.par.top = op('{COMP_PATH}/ramp_tex')
cm.par.overrideautoattr = True
cm.par.outputattrscope = 'Color'
cm.par.attrtype = 'color'

# Configurar trailPOP
tr = op('{geo_path}/trail')
tr.par.length = 8
tr.par.attrmatch = True
tr.par.attrname = 'PartId'

# Configurar convertPOP (Contrato C2)
cp = op('{geo_path}/topoints')
cp.par.convert = 'topointprims'

# Flags terminales
nout = op('{geo_path}/null_out')
nout.display = True
nout.render = True
"""
    ok, res = live.call("execute_code", {"code": setup_pops})
    assert ok, f"Error configurando parámetros POP: {res}"
    
    # 7. Setup de Render
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
m.par.blending = True
m.par.srcblend = 'sa'
m.par.destblend = 'one'

g = op('{COMP_PATH}/geo')
g.par.material = op('{COMP_PATH}/mat')

cam = op('{COMP_PATH}/cam')
cam.par.tz = 3.8

ren = op('{COMP_PATH}/ren')
ren.par.resolutionw = 1280
ren.par.resolutionh = 720
ren.par.camera = op('{COMP_PATH}/cam')
ren.par.geometry = op('{COMP_PATH}/geo')
ren.cook(force=True)
"""
    ok, res = live.call("execute_code", {"code": setup_render})
    assert ok, f"Error configurando render: {res}"
    print("=== Red tut_paketa12_advection construida con éxito ===")


def verify():
    print("=== Verificando estado numérico y render de tut_paketa12_advection ===")
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
    assert data.get("points") > 1000, f"Puntos esperados > 1000, obtenido {data.get('points')}"
    assert data.get("prims") > 0, f"Primitivas esperadas > 0, obtenido {data.get('prims')}"
    assert data.get("has_color"), "Atributo Color no detectado"
    assert data.get("has_partid"), "Atributo PartId no detectado"
    assert data.get("lit_pixels") > 5000, f"Render vacío o insuficiente: lit_pixels={data.get('lit_pixels')}"
    print(">>> VERIFICACIÓN [PASS]: 100% verde en advección, estelas y render.")


if __name__ == "__main__":
    build()
    time.sleep(0.5)
    verify()

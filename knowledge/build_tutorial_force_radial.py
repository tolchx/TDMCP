"""
build_tutorial_force_radial.py — Construcción y verificación ejecutable en TouchDesigner
del tutorial "Spiralling particle fields with Force Radial POP" (Torin Blankensmith).

Arquitectura:
/project1/tut_force_radial (baseCOMP):
  - geo (geometryCOMP):
      - emit (gridPOP): Emisor rectangular de partículas 2D
      - sim (particlePOP): Simulador con targetpop loop
      - vortex (forceradialPOP): Vórtice espiral en GPU (spiral=True, dirz=1.0, globforcemult=1.0)
      - damp (transformPOP): Amortiguación centrípeta
      - sim_target (nullPOP): Cierre de feedback loop
      - trail (trailPOP): Estelas continuas basadas en PartId
      - topoints (convertPOP): Conversión a point primitives (topointprims)
      - null_out (nullPOP): Salida con flags display/render
  - mat (pointspriteMAT): pointsize = 2.5
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

COMP_PATH = "/project1/tut_force_radial"


def build():
    print(f"=== [2/4] Construyendo Force Radial Tutorial en {COMP_PATH} ===")
    
    # Limpiar si ya existía
    live.call("delete_operator", {"path": COMP_PATH})
    
    # 1. Crear contenedor base
    ok, res = live.call("create_operator", {"type": "baseCOMP", "name": "tut_force_radial", "parent_path": "/project1"})
    assert ok, f"Error creando baseCOMP: {res}"
    
    # 2. Geometry container
    ok, res = live.call("create_operator", {"type": "geometryCOMP", "name": "geo", "parent_path": COMP_PATH})
    assert ok, f"Error creando geometryCOMP: {res}"
    
    # Borrar torus por defecto (Contrato C2 autotorus_masks_render)
    live.call("delete_operator", {"path": f"{COMP_PATH}/geo/torus1"})
    
    geo_path = f"{COMP_PATH}/geo"
    
    # 3. Operadores POP dentro de geo
    # 3a. Emisor gridPOP
    ok, res = live.call("create_operator", {"type": "gridPOP", "name": "emit", "parent_path": geo_path})
    assert ok, f"Error creando emit: {res}"
    
    # 3b. particlePOP
    ok, res = live.call("create_operator", {"type": "particlePOP", "name": "sim", "parent_path": geo_path})
    assert ok, f"Error creando sim: {res}"
    
    # 3c. forceradialPOP
    ok, res = live.call("create_operator", {"type": "forceradialPOP", "name": "vortex", "parent_path": geo_path})
    assert ok, f"Error creando vortex: {res}"
    
    # 3d. transformPOP (damp)
    ok, res = live.call("create_operator", {"type": "transformPOP", "name": "damp", "parent_path": geo_path})
    assert ok, f"Error creando damp: {res}"
    
    # 3e. nullPOP target (cierre del loop de targetpop, Contrato C10)
    ok, res = live.call("create_operator", {"type": "nullPOP", "name": "sim_target", "parent_path": geo_path})
    assert ok, f"Error creando sim_target: {res}"
    
    # 3f. trailPOP
    ok, res = live.call("create_operator", {"type": "trailPOP", "name": "trail", "parent_path": geo_path})
    assert ok, f"Error creando trail: {res}"
    
    # 3g. convertPOP
    ok, res = live.call("create_operator", {"type": "convertPOP", "name": "topoints", "parent_path": geo_path})
    assert ok, f"Error creando topoints: {res}"
    
    # 3h. nullPOP out
    ok, res = live.call("create_operator", {"type": "nullPOP", "name": "null_out", "parent_path": geo_path})
    assert ok, f"Error creando null_out: {res}"
    
    # 4. Cableado
    chain = [
        ("emit", "sim"),
        ("sim", "vortex"),
        ("vortex", "damp"),
        ("damp", "sim_target"),
        ("sim_target", "trail"),
        ("trail", "topoints"),
        ("topoints", "null_out")
    ]
    for src, dst in chain:
        ok, res = live.call("wiring", {"from_path": f"{geo_path}/{src}", "to_path": f"{geo_path}/{dst}", "to_index": 0})
        assert ok, f"Error cableando {src} -> {dst}: {res}"
        
    # 5. Configurar parámetros vía Python (execute_code)
    setup_pops = f"""
# Configurar emisor gridPOP
e = op('{geo_path}/emit')
e.par.rows = 24
e.par.cols = 24
e.par.sizex = 2.5
e.par.sizey = 1.5

# Configurar simulador particlePOP con feedback loop (Contrato C10)
s = op('{geo_path}/sim')
s.par.birthrate = 1800
s.par.life = 2.5
s.par.lifevariance = 0.4
s.par.timeintegration = True
s.par.targetpop = op('{geo_path}/sim_target')
s.par.pointidreuse = 'none'

# Configurar forceradialPOP con vórtice espiral (Contrato C6)
v = op('{geo_path}/vortex')
v.par.globforcemult = 1.0
v.par.directionx = 0.0
v.par.directiony = 0.0
v.par.directionz = 1.0
v.par.spiral = True
v.par.spiralstrength = 0.85
v.par.falloffradius = 2.0
v.par.radial = False

# Configurar amortiguación
d = op('{geo_path}/damp')
d.par.sx = 0.985
d.par.sy = 0.985
d.par.sz = 0.985

# Configurar trailPOP
tr = op('{geo_path}/trail')
tr.par.length = 8
tr.par.attrmatch = True
tr.par.attrname = 'PartId'

# Configurar convertPOP a point primitives (Contrato C2)
cp = op('{geo_path}/topoints')
cp.par.convert = 'topointprims'

# Flags terminales (Contrato C2)
nout = op('{geo_path}/null_out')
nout.display = True
nout.render = True
"""
    ok, res = live.call("execute_code", {"code": setup_pops})
    assert ok, f"Error configurando parámetros POP: {res}"
    
    # 6. Render setup
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
m.par.pointsize = 2.5

g = op('{COMP_PATH}/geo')
g.par.material = op('{COMP_PATH}/mat')

cam = op('{COMP_PATH}/cam')
cam.par.tz = 3.5

ren = op('{COMP_PATH}/ren')
ren.par.resolutionw = 1280
ren.par.resolutionh = 720
ren.par.camera = op('{COMP_PATH}/cam')
ren.par.geometry = op('{COMP_PATH}/geo')
ren.cook(force=True)
"""
    ok, res = live.call("execute_code", {"code": setup_render})
    assert ok, f"Error configurando render: {res}"
    print("=== Red tut_force_radial construida con éxito ===")


def verify():
    print("=== Verificando estado numérico y render de tut_force_radial ===")
    check_code = f"""
import json
import time

sim = op('{COMP_PATH}/geo/sim')
vortex = op('{COMP_PATH}/geo/vortex')
nout = op('{COMP_PATH}/geo/null_out')
ren = op('{COMP_PATH}/ren')

# Bucle settle (Contrato C1 cook_lag)
for _ in range(6):
    sim.cook(force=True)
    vortex.cook(force=True)
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
    "has_partid": 'PartId' in attrs,
    "has_partvel": 'PartVel' in attrs,
    "has_partforce": 'PartForce' in attrs,
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
    assert data.get("has_partid"), "Atributo PartId no detectado"
    assert data.get("has_partforce"), "Atributo PartForce no detectado"
    assert data.get("lit_pixels") > 0, f"Render vacío: lit_pixels={data.get('lit_pixels')}"
    print(">>> VERIFICACIÓN [PASS]: 100% verde en simulación espiral y render.")


if __name__ == "__main__":
    build()
    time.sleep(0.5)
    verify()

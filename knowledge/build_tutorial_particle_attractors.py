"""
build_tutorial_particle_attractors.py — Construcción y verificación ejecutable en TouchDesigner
del tutorial "3 Ways to Make POPs Particle Attractors" (Torin Blankensmith).

Arquitectura:
/project1/tut_particle_attractors (baseCOMP):
  - geo (geometryCOMP):
      - seed_pts (spherePOP): Distribución esférica densa de puntos (1000 pts)
      - attractor_field (noisePOP): Campo vectorial 4D con curl 3D simulando atractor
      - rand_rot (randomPOP): Atributo 'Rot' (3 componentes, 0..360)
      - rand_scale (randomPOP): Atributo 'PointScale' (1 componente, 0.05..0.15)
      - rand_color (randomPOP): Atributo 'Color' (RGBA)
      - thin_pts (deletePOP): Thinning aleatorio para aislar nodos clave
      - prox_lines (proximityPOP): Red de proximidad en GPU conectando nodos vecinos
      - topoints (convertPOP): Conversión a point primitives
      - merge (mergePOP): Fusión de puntos y líneas de proximidad
      - null_out (nullPOP): Terminal de render (display/render)
  - mat (pointspriteMAT): pointsize = 3.5
  - cam (cameraCOMP): tz = 4.0
  - light (lightCOMP)
  - ren (renderTOP): 1280x720
  - out (nullTOP)
"""

import time
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live

COMP_PATH = "/project1/tut_particle_attractors"


def build():
    print(f"=== [4/4] Construyendo Particle Attractors Tutorial en {COMP_PATH} ===")
    
    # Limpiar si ya existía
    live.call("delete_operator", {"path": COMP_PATH})
    
    # 1. Crear contenedor base
    ok, res = live.call("create_operator", {"type": "baseCOMP", "name": "tut_particle_attractors", "parent_path": "/project1"})
    assert ok, f"Error creando baseCOMP: {res}"
    
    # 2. Geometry container
    ok, res = live.call("create_operator", {"type": "geometryCOMP", "name": "geo", "parent_path": COMP_PATH})
    assert ok, f"Error creando geometryCOMP: {res}"
    
    # Borrar torus por defecto (Contrato C2 autotorus_masks_render)
    live.call("delete_operator", {"path": f"{COMP_PATH}/geo/torus1"})
    
    geo_path = f"{COMP_PATH}/geo"
    
    # 3. Operadores POP dentro de geo
    # 3a. spherePOP seed
    ok, res = live.call("create_operator", {"type": "spherePOP", "name": "seed_pts", "parent_path": geo_path})
    assert ok, f"Error creando seed_pts: {res}"
    
    # 3b. noisePOP atractor curl 4D
    ok, res = live.call("create_operator", {"type": "noisePOP", "name": "attractor_field", "parent_path": geo_path})
    assert ok, f"Error creando attractor_field: {res}"
    
    # 3c. randomPOP Rot
    ok, res = live.call("create_operator", {"type": "randomPOP", "name": "rand_rot", "parent_path": geo_path})
    assert ok, f"Error creando rand_rot: {res}"
    
    # 3d. randomPOP PointScale
    ok, res = live.call("create_operator", {"type": "randomPOP", "name": "rand_scale", "parent_path": geo_path})
    assert ok, f"Error creando rand_scale: {res}"
    
    # 3e. randomPOP Color
    ok, res = live.call("create_operator", {"type": "randomPOP", "name": "rand_color", "parent_path": geo_path})
    assert ok, f"Error creando rand_color: {res}"
    
    # 3f. deletePOP (thinning para proximidad)
    ok, res = live.call("create_operator", {"type": "deletePOP", "name": "thin_pts", "parent_path": geo_path})
    assert ok, f"Error creando thin_pts: {res}"
    
    # 3g. proximityPOP
    ok, res = live.call("create_operator", {"type": "proximityPOP", "name": "prox_lines", "parent_path": geo_path})
    assert ok, f"Error creando prox_lines: {res}"
    
    # 3h. convertPOP
    ok, res = live.call("create_operator", {"type": "convertPOP", "name": "topoints", "parent_path": geo_path})
    assert ok, f"Error creando topoints: {res}"
    
    # 3i. mergePOP
    ok, res = live.call("create_operator", {"type": "mergePOP", "name": "merge", "parent_path": geo_path})
    assert ok, f"Error creando merge: {res}"
    
    # 3j. nullPOP out
    ok, res = live.call("create_operator", {"type": "nullPOP", "name": "null_out", "parent_path": geo_path})
    assert ok, f"Error creando null_out: {res}"
    
    # 4. Cableado:
    # seed_pts -> attractor_field -> rand_rot -> rand_scale -> rand_color
    main_chain = [
        ("seed_pts", "attractor_field"),
        ("attractor_field", "rand_rot"),
        ("rand_rot", "rand_scale"),
        ("rand_scale", "rand_color")
    ]
    for src, dst in main_chain:
        ok, res = live.call("wiring", {"from_path": f"{geo_path}/{src}", "to_path": f"{geo_path}/{dst}", "to_index": 0})
        assert ok, f"Error cableando {src} -> {dst}: {res}"
        
    # rand_color -> topoints -> merge (in 0)
    live.call("wiring", {"from_path": f"{geo_path}/rand_color", "to_path": f"{geo_path}/topoints", "to_index": 0})
    live.call("wiring", {"from_path": f"{geo_path}/topoints", "to_path": f"{geo_path}/merge", "to_index": 0})
    
    # rand_color -> thin_pts -> prox_lines -> merge (in 1)
    live.call("wiring", {"from_path": f"{geo_path}/rand_color", "to_path": f"{geo_path}/thin_pts", "to_index": 0})
    live.call("wiring", {"from_path": f"{geo_path}/thin_pts", "to_path": f"{geo_path}/prox_lines", "to_index": 0})
    live.call("wiring", {"from_path": f"{geo_path}/prox_lines", "to_path": f"{geo_path}/merge", "to_index": 1})
    
    # merge -> null_out
    live.call("wiring", {"from_path": f"{geo_path}/merge", "to_path": f"{geo_path}/null_out", "to_index": 0})
    
    # 5. Configurar parámetros vía Python (execute_code)
    setup_pops = f"""
# Configurar emisor esférico
s = op('{geo_path}/seed_pts')
s.par.radx = 1.0
s.par.rady = 1.0
s.par.radz = 1.0
s.par.rows = 24
s.par.cols = 24

# Configurar atractor noisePOP 4D con curl 3D
n = op('{geo_path}/attractor_field')
n.par.type = 'simplex4d'
n.par.curl3d = True
n.par.amp0 = 0.8
n.par.period = 1.5
n.par.t4d.expr = 'absTime.seconds * 0.15'

# Atributo Rot (3 componentes para rotación 3D)
rr = op('{geo_path}/rand_rot')
rr.par.outputattrscope = 'Rot'
rr.par.overrideautoattr = True
rr.par.attrtype = 'float'
rr.par.attrnumcomps = 3
rr.par.valuea0 = 0.0
rr.par.valueb0 = 360.0

# Atributo PointScale (1 componente)
rs = op('{geo_path}/rand_scale')
rs.par.outputattrscope = 'PointScale'
rs.par.overrideautoattr = True
rs.par.attrtype = 'float'
rs.par.attrnumcomps = 1
rs.par.valuea0 = 0.05
rs.par.valueb0 = 0.25

# Atributo Color (4 componentes RGBA)
rc = op('{geo_path}/rand_color')
rc.par.outputattrscope = 'Color'
rc.par.overrideautoattr = True
rc.par.attrtype = 'color'
rc.par.attrnumcomps = 4

# Thinning para proximidad (deletePOP)
th = op('{geo_path}/thin_pts')
th.par.thinenabled = True
th.par.thinrandom = 0.8
th.par.thinrandomseed = 2.0

# ProximityPOP (conectar vecinos cercanos)
pr = op('{geo_path}/prox_lines')
pr.par.maxdist = 0.55
pr.par.maxlinesperpoint = 4
pr.par.output = 'lines'
pr.par.duplines = 'avoid'

# ConvertPOP
cp = op('{geo_path}/topoints')
cp.par.convert = 'topointprims'

# Flags terminales
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
    
    live.call("wiring", {"from_path": f"{COMP_PATH}/ren", "to_path": f"{COMP_PATH}/out", "to_index": 0})
    
    setup_render = f"""
m = op('{COMP_PATH}/mat')
m.par.pointsize = 3.5

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
    print("=== Red tut_particle_attractors construida con éxito ===")


def verify():
    print("=== Verificando estado numérico y render de tut_particle_attractors ===")
    check_code = f"""
import json
import time

nout = op('{COMP_PATH}/geo/null_out')
prox = op('{COMP_PATH}/geo/prox_lines')
ren = op('{COMP_PATH}/ren')

# Bucle settle (Contrato C1 cook_lag)
for _ in range(6):
    prox.cook(force=True)
    nout.cook(force=True)
    ren.cook(force=True)
    time.sleep(0.04)

pts = nout.numPoints()
prims = nout.numPrims()
prox_prims = prox.numPrims()
attrs = [a.name for a in nout.pointAttributes]

# Verificación de render en píxeles (Contrato C5)
arr = ren.numpyArray()
lit_pixels = int((arr[:, :, :3].max(axis=2) > 0.01).sum())

print("{live.MARK}" + json.dumps({{
    "points": pts,
    "prims": prims,
    "prox_lines_prims": prox_prims,
    "has_rot": 'Rot' in attrs,
    "has_pointscale": 'PointScale' in attrs,
    "has_color": 'Color' in attrs,
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
    assert data.get("prox_lines_prims") > 0, f"Líneas de proximidad esperadas > 0, obtenido {data.get('prox_lines_prims')}"
    assert data.get("has_rot"), "Atributo Rot no detectado"
    assert data.get("has_pointscale"), "Atributo PointScale no detectado"
    assert data.get("has_color"), "Atributo Color no detectado"
    assert data.get("lit_pixels") > 0, f"Render vacío: lit_pixels={data.get('lit_pixels')}"
    print(">>> VERIFICACIÓN [PASS]: 100% verde en atractores, red de proximidad y render.")


if __name__ == "__main__":
    build()
    time.sleep(0.5)
    verify()

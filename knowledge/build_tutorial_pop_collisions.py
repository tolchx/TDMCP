"""
build_tutorial_pop_collisions.py — Construcción y verificación ejecutable en TouchDesigner
del tutorial "Particle Collisions & Deflector Surfaces with 2025/2026 POPs" (Jack DiLaura / Interactive & Immersive HQ).

Arquitectura:
/project1/tut_pop_collisions (baseCOMP):
  - ramp_tex (rampTOP): Rampa de color reactiva
  - geo (geometryCOMP):
      - emit (spherePOP): Emisor elevado a Y = 2.5
      - sim (particlePOP): Simulador con targetpop feedback loop
      - gravity (mathmixPOP): Fuerza de gravedad hacia -Y
      - floor_clamp (limitPOP): Deflector de suelo (parsize=3, mintype1='clamp', min1=0.0)
      - damp (transformPOP): Fricción y amortiguación superficial
      - tgt (nullPOP): Terminal del bucle de feedback (targetpop)
      - deflector_plane (gridPOP): Plano de colisión físico (rx=90, Y=0)
      - ray_deflect (rayPOP): Trazador de rayos de colisión y vector reflejado (RayReflect)
      - color_map (lookuptexturePOP): Mapea ramp_tex a atributo Color
      - trail (trailPOP): Estelas continuas basadas en PartId
      - topoints (convertPOP): Conversión a point primitives
      - null_out (nullPOP): Salida con flags display/render
  - mat (pointspriteMAT): Point size = 3.2, blending aditivo
  - cam (cameraCOMP): ty = 1.2, tz = 4.5
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

COMP_PATH = "/project1/tut_pop_collisions"


def build():
    print(f"=== Construyendo tutorial Pop Collisions en {COMP_PATH} ===")
    
    # Limpiar si ya existía
    live.call("delete_operator", {"path": COMP_PATH})
    
    # 1. Crear contenedor base
    ok, res = live.call("create_operator", {"type": "baseCOMP", "name": "tut_pop_collisions", "parent_path": "/project1"})
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
    # 4a. Emisor elevado spherePOP
    ok, res = live.call("create_operator", {"type": "spherePOP", "name": "emit", "parent_path": geo_path})
    assert ok, f"Error creando emit: {res}"
    
    # 4b. particlePOP
    ok, res = live.call("create_operator", {"type": "particlePOP", "name": "sim", "parent_path": geo_path})
    assert ok, f"Error creando sim: {res}"
    
    # 4c. mathmixPOP gravedad
    ok, res = live.call("create_operator", {"type": "mathmixPOP", "name": "gravity", "parent_path": geo_path})
    assert ok, f"Error creando gravity: {res}"
    
    # 4d. limitPOP cota inferior de suelo
    ok, res = live.call("create_operator", {"type": "limitPOP", "name": "floor_clamp", "parent_path": geo_path})
    assert ok, f"Error creando floor_clamp: {res}"
    
    # 4e. transformPOP fricción / amortiguación
    ok, res = live.call("create_operator", {"type": "transformPOP", "name": "damp", "parent_path": geo_path})
    assert ok, f"Error creando damp: {res}"
    
    # 4f. nullPOP para cerrar el loop de feedback
    ok, res = live.call("create_operator", {"type": "nullPOP", "name": "tgt", "parent_path": geo_path})
    assert ok, f"Error creando tgt: {res}"
    
    # 4g. gridPOP plano deflector de colisión
    ok, res = live.call("create_operator", {"type": "gridPOP", "name": "deflector_plane", "parent_path": geo_path})
    assert ok, f"Error creando deflector_plane: {res}"
    
    # 4h. rayPOP trazador de rayos de colisión y vector reflejado
    ok, res = live.call("create_operator", {"type": "rayPOP", "name": "ray_deflect", "parent_path": geo_path})
    assert ok, f"Error creando ray_deflect: {res}"
    
    # 4i. lookuptexturePOP (color)
    ok, res = live.call("create_operator", {"type": "lookuptexturePOP", "name": "color_map", "parent_path": geo_path})
    assert ok, f"Error creando color_map: {res}"
    
    # 4j. trailPOP (estelas)
    ok, res = live.call("create_operator", {"type": "trailPOP", "name": "trail", "parent_path": geo_path})
    assert ok, f"Error creando trail: {res}"
    
    # 4k. convertPOP (Contrato C2 points_need_pointprims)
    ok, res = live.call("create_operator", {"type": "convertPOP", "name": "topoints", "parent_path": geo_path})
    assert ok, f"Error creando topoints: {res}"
    
    # 4l. nullPOP de salida
    ok, res = live.call("create_operator", {"type": "nullPOP", "name": "null_out", "parent_path": geo_path})
    assert ok, f"Error creando null_out: {res}"
    
    # 5. Cableado POP:
    # Loop de simulación: emit -> sim -> gravity -> floor_clamp -> damp -> tgt
    sim_chain = [
        ("emit", "sim"),
        ("sim", "gravity"),
        ("gravity", "floor_clamp"),
        ("floor_clamp", "damp"),
        ("damp", "tgt")
    ]
    for src, dst in sim_chain:
        ok, res = live.call("wiring", {"from_path": f"{geo_path}/{src}", "to_path": f"{geo_path}/{dst}", "to_index": 0})
        assert ok, f"Error cableando {src} -> {dst}: {res}"
        
    # Post-proceso con rayPOP: tgt (in 0) y deflector_plane (in 1) -> ray_deflect
    live.call("wiring", {"from_path": f"{geo_path}/tgt", "to_path": f"{geo_path}/ray_deflect", "to_index": 0})
    live.call("wiring", {"from_path": f"{geo_path}/deflector_plane", "to_path": f"{geo_path}/ray_deflect", "to_index": 1})
    
    post_chain = [
        ("ray_deflect", "color_map"),
        ("color_map", "trail"),
        ("trail", "topoints"),
        ("topoints", "null_out")
    ]
    for src, dst in post_chain:
        ok, res = live.call("wiring", {"from_path": f"{geo_path}/{src}", "to_path": f"{geo_path}/{dst}", "to_index": 0})
        assert ok, f"Error cableando {src} -> {dst}: {res}"
        
    # 6. Configurar parámetros POP vía Python
    setup_pops = f"""
# Configurar emisor spherePOP elevado
e = op('{geo_path}/emit')
e.par.radx = 0.3
e.par.rady = 0.3
e.par.radz = 0.3
e.par.ty = 2.4
e.par.rows = 16
e.par.cols = 16

# Configurar simulador particlePOP con feedback loop (Contrato C10)
s = op('{geo_path}/sim')
s.par.birthrate = 1500
s.par.life = 2.8
s.par.lifevariance = 0.4
s.par.timeintegration = True
s.par.targetpop = op('{geo_path}/tgt')
s.par.pointidreuse = 'none'

# Configurar gravedad hacia -Y (mathmixPOP)
g = op('{geo_path}/gravity')
g.par.comb0oper = 'add'
g.par.comb0scopea = 'PartForce'
g.par.comb0scopeb = '0 -4.5 0'
g.par.comb0result = 'PartForce'

# Configurar limitPOP como deflector de suelo (P.y >= 0.0)
fc = op('{geo_path}/floor_clamp')
fc.par.inputattrscope = 'P'
fc.par.parsize = 3
fc.par.mintype1 = 'clamp'
fc.par.min1 = 0.0

# Amortiguación y fricción superficial (transformPOP)
d = op('{geo_path}/damp')
d.par.sx = 0.99
d.par.sy = 0.99
d.par.sz = 0.99

# Plano deflector geométrico (gridPOP horizontal a Y = 0)
dp = op('{geo_path}/deflector_plane')
dp.par.sizex = 5.0
dp.par.sizey = 5.0
dp.par.rx = 90.0
dp.par.ty = 0.0

# Configurar rayPOP (cálculo de colisión, distancia y rayo reflejado)
rp = op('{geo_path}/ray_deflect')
rp.par.rayattrib = 'PartVel'
rp.par.dist = True
rp.par.hitnormal = True
rp.par.doreflectedray = True

# Mapear color según altura Y
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
m.par.pointsize = 6.0
m.par.blending = True
m.par.srcblend = 'sa'
m.par.destblend = 'one'

g = op('{COMP_PATH}/geo')
g.par.material = op('{COMP_PATH}/mat')

cam = op('{COMP_PATH}/cam')
cam.par.tx = 0.0
cam.par.ty = 1.8
cam.par.tz = 4.0
cam.par.rx = -15.0

ren = op('{COMP_PATH}/ren')
ren.par.resolutionw = 1280
ren.par.resolutionh = 720
ren.par.camera = op('{COMP_PATH}/cam')
ren.par.geometry = op('{COMP_PATH}/geo')
ren.cook(force=True)
"""
    ok, res = live.call("execute_code", {"code": setup_render})
    assert ok, f"Error configurando render: {res}"
    print("=== Red tut_pop_collisions construida con éxito ===")


def verify():
    print("=== Verificando estado numérico, colisiones y render ===")
    
    # Muestreo con varias llamadas separadas para que el timeline avance
    for _ in range(5):
        live.call("execute_code", {"code": f"""
op('{COMP_PATH}/geo/sim').cook(force=True)
op('{COMP_PATH}/geo/ray_deflect').cook(force=True)
op('{COMP_PATH}/geo/null_out').cook(force=True)
op('{COMP_PATH}/ren').cook(force=True)
"""})
        time.sleep(0.08)

    check_code = f"""
import json
nout = op('{COMP_PATH}/geo/null_out')
ren = op('{COMP_PATH}/ren')

pts = nout.numPoints()
prims = nout.numPrims()
attrs = [a.name for a in nout.pointAttributes]

# Verificar confinamiento de suelo (P.y >= 0.0)
p_pts = nout.points('P')
n_sample = min(200, pts)
y_vals = [p_pts[i][1] for i in range(n_sample)]
min_y = min(y_vals) if y_vals else -999.0

# Verificación de render en píxeles (Contrato C5)
arr = ren.numpyArray()
lit_pixels = int((arr[:, :, :3].max(axis=2) > 0.01).sum())

print("{live.MARK}" + json.dumps({{
    "points": pts,
    "prims": prims,
    "min_y": min_y,
    "has_rayreflect": 'RayReflect' in attrs,
    "has_rayhitnormal": 'RayHitNormal' in attrs,
    "has_raydistance": 'RayDistance' in attrs,
    "has_color": 'Color' in attrs,
    "has_partid": 'PartId' in attrs,
    "render_width": ren.width,
    "render_height": ren.height,
    "lit_pixels": lit_pixels
}}))
"""
    ok, data = live.exec_code(check_code)
    assert ok, f"Fallo al ejecutar código de verificación: {data}"
    print("Métricas obtenidas:", data)
    assert data.get("points") > 500, f"Puntos esperados > 500, obtenido {data.get('points')}"
    assert data.get("prims") > 500, f"Primitivas esperadas > 500, obtenido {data.get('prims')}"
    assert data.get("min_y") >= -0.01, f"Fallo en cota de colisión: min_y={data.get('min_y')} < 0.0"
    assert data.get("has_rayreflect"), "Atributo RayReflect no detectado"
    assert data.get("has_raydistance"), "Atributo RayDistance no detectado"
    assert data.get("has_color"), "Atributo Color no detectado"
    assert data.get("lit_pixels") > 5000, f"Render vacío o insuficiente: lit_pixels={data.get('lit_pixels')}"
    print(">>> VERIFICACIÓN [PASS]: 100% verde en colisiones, deflector y render.")


if __name__ == "__main__":
    build()
    time.sleep(1.0)
    verify()

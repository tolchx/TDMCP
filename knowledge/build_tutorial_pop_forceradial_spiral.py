"""
Script de construcción y verificación para el tutorial:
"Spiralling particle fields with Force Radial POP - TouchDesigner"
(Video POPs 2026: UoglSKDtcfI)

Construye la red en /project1/tut_pop_spiral.
Verifica:
1. Red con 0 errores en todos los operadores.
2. Emisión y dinámica espiral de partículas con forceradialPOP (radial=False, spiral=True, directionz=1.0).
3. Modulación por turbulencia con noisePOP (simplex4d sobre PartForce).
4. Multi-fuerza interactiva mediante Specification POP (specpop).
5. Generación de estelas espirales coherentes con trailPOP (attrmatch=True, attrname='PartId').
6. Cumplimiento estricto del Contrato C2 (convertPOP con topointprims).
7. Pipeline de renderizado completo (pointspriteMAT, cameraCOMP, lightCOMP, renderTOP 1280x720, nullTOP).
8. Validación numérica de velocidad angular / tangencial y render con > 5000 píxeles iluminados.
"""

import time
import json
import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live

COMP_PATH = "/project1/tut_pop_spiral"


def build():
    print(f"=== Construyendo tutorial Force Radial Spiral en {COMP_PATH} ===")
    
    # 1. Asegurar baseCOMP limpio
    ok, res = live.call("destroy_operator", {"path": COMP_PATH})
    ok, res = live.call("create_operator", {"type": "baseCOMP", "name": "tut_pop_spiral", "parent_path": "/project1"})
    assert ok, f"Error creando baseCOMP {COMP_PATH}: {res}"
    
    # 2. Textura de gradiente para colorización
    ok, res = live.call("create_operator", {"type": "rampTOP", "name": "ramp_tex", "parent_path": COMP_PATH})
    assert ok, f"Error creando ramp_tex: {res}"
    
    setup_ramp = f"""
r = op('{COMP_PATH}/ramp_tex')
r.par.resolutionw = 256
r.par.resolutionh = 1
r.par.type = 'horizontal'
"""
    live.call("execute_code", {"code": setup_ramp})
    
    # 3. geometryCOMP contenedor (Contrato C2: destruir torus1)
    ok, res = live.call("create_operator", {"type": "geometryCOMP", "name": "geo", "parent_path": COMP_PATH})
    assert ok, f"Error creando geometryCOMP: {res}"
    
    geo_path = f"{COMP_PATH}/geo"
    ok, res = live.call("destroy_operator", {"path": f"{geo_path}/torus1"})
    
    # 4. Operadores POP dentro de geo:
    # 4a. Emisor base (pointgeneratorPOP rectangular)
    ok, res = live.call("create_operator", {"type": "pointgeneratorPOP", "name": "emit", "parent_path": geo_path})
    assert ok, f"Error creando emit: {res}"
    
    # 4b. Specification POP generator (generador de múltiples centros de fuerza espiral)
    ok, res = live.call("create_operator", {"type": "pointgeneratorPOP", "name": "spec_emit", "parent_path": geo_path})
    assert ok, f"Error creando spec_emit: {res}"
    
    # 4c. noisePOP para animar las posiciones de los centros de fuerza
    ok, res = live.call("create_operator", {"type": "noisePOP", "name": "spec_pos_noise", "parent_path": geo_path})
    assert ok, f"Error creando spec_pos_noise: {res}"
    
    # 4d. nullPOP de especificación
    ok, res = live.call("create_operator", {"type": "nullPOP", "name": "spec_null", "parent_path": geo_path})
    assert ok, f"Error creando spec_null: {res}"
    
    # 4e. particlePOP (motor de partículas compute)
    ok, res = live.call("create_operator", {"type": "particlePOP", "name": "sim", "parent_path": geo_path})
    assert ok, f"Error creando sim: {res}"
    
    # 4f. forceradialPOP (fuerza espiral tangencial con specpop)
    ok, res = live.call("create_operator", {"type": "forceradialPOP", "name": "spiral_force", "parent_path": geo_path})
    assert ok, f"Error creando spiral_force: {res}"
    
    # 4g. noisePOP turbulencia sobre PartForce
    ok, res = live.call("create_operator", {"type": "noisePOP", "name": "turb_force", "parent_path": geo_path})
    assert ok, f"Error creando turb_force: {res}"
    
    # 4h. nullPOP para cerrar el loop de feedback
    ok, res = live.call("create_operator", {"type": "nullPOP", "name": "tgt", "parent_path": geo_path})
    assert ok, f"Error creando tgt: {res}"
    
    # 4i. lookuptexturePOP (color dinámico según PartAge / velocidad)
    ok, res = live.call("create_operator", {"type": "lookuptexturePOP", "name": "color_map", "parent_path": geo_path})
    assert ok, f"Error creando color_map: {res}"
    
    # 4j. trailPOP (estelas espirales por partícula)
    ok, res = live.call("create_operator", {"type": "trailPOP", "name": "trail", "parent_path": geo_path})
    assert ok, f"Error creando trail: {res}"
    
    # 4k. convertPOP (Contrato C2: topointprims)
    ok, res = live.call("create_operator", {"type": "convertPOP", "name": "topoints", "parent_path": geo_path})
    assert ok, f"Error creando topoints: {res}"
    
    # 4l. nullPOP terminal
    ok, res = live.call("create_operator", {"type": "nullPOP", "name": "null_out", "parent_path": geo_path})
    assert ok, f"Error creando null_out: {res}"
    
    # 5. Cableado POP:
    # Cadena de especificación: spec_emit -> spec_pos_noise -> spec_null
    live.call("wiring", {"from_path": f"{geo_path}/spec_emit", "to_path": f"{geo_path}/spec_pos_noise", "to_index": 0})
    live.call("wiring", {"from_path": f"{geo_path}/spec_pos_noise", "to_path": f"{geo_path}/spec_null", "to_index": 0})
    
    # Bucle de simulación: emit -> sim -> spiral_force -> turb_force -> tgt
    sim_chain = [
        ("emit", "sim"),
        ("sim", "spiral_force"),
        ("spiral_force", "turb_force"),
        ("turb_force", "tgt")
    ]
    for src, dst in sim_chain:
        ok, res = live.call("wiring", {"from_path": f"{geo_path}/{src}", "to_path": f"{geo_path}/{dst}", "to_index": 0})
        assert ok, f"Error cableando {src} -> {dst}: {res}"
        
    # Cadena post-proceso: tgt -> color_map -> trail -> topoints -> null_out
    post_chain = [
        ("tgt", "color_map"),
        ("color_map", "trail"),
        ("trail", "topoints"),
        ("topoints", "null_out")
    ]
    for src, dst in post_chain:
        ok, res = live.call("wiring", {"from_path": f"{geo_path}/{src}", "to_path": f"{geo_path}/{dst}", "to_index": 0})
        assert ok, f"Error cableando {src} -> {dst}: {res}"
        
    # 6. Configuración de parámetros POP:
    setup_pops = f"""
# 1. Emisor plano 2:1
em = op('{geo_path}/emit')
em.par.shape = 'rectangle'
em.par.sizex = 2.0
em.par.sizey = 1.0

# 2. Spec POP para multi-vortex espiral interactivo
sem = op('{geo_path}/spec_emit')
sem.par.shape = 'rectangle'
sem.par.sizex = 2.0
sem.par.sizey = 1.0
sem.par.numpoints = 16

sno = op('{geo_path}/spec_pos_noise')
sno.par.combineop = 'add'
sno.par.combineattrscope = 'P'
sno.par.amp = 0.35
sno.par.type = 'simplex4d'
sno.par.t4d.expr = 'absTime.seconds * 0.15'

# 3. Simulación de partículas
sim = op('{geo_path}/sim')
sim.par.birthrate = 2200
sim.par.life = 3.5
sim.par.maxparticles = 25000
sim.par.targetpop = op('{geo_path}/tgt')

# 4. Fuerza espiral radial con vorticidad en eje Z
sf = op('{geo_path}/spiral_force')
sf.par.radial = False
sf.par.spiral = True
sf.par.directionx = 0.0
sf.par.directiony = 0.0
sf.par.directionz = 1.0
sf.par.falloffradius = 0.75
sf.par.falloff = 'scurve'
sf.par.spiralstrength = 0.85
sf.par.specpop = op('{geo_path}/spec_null')

# 5. Turbulencia de ruido agregada a PartForce
tb = op('{geo_path}/turb_force')
tb.par.type = 'simplex4d'
tb.par.combineop = 'add'
tb.par.combineattrscope = 'PartForce'
tb.par.amp = 0.3
tb.par.t4d.expr = 'absTime.seconds * 0.2'

# 6. Color dinámico
cm = op('{geo_path}/color_map')
cm.par.top = op('{COMP_PATH}/ramp_tex')
cm.par.overrideautoattr = True
cm.par.outputattrscope = 'Color'
cm.par.attrtype = 'color'

# 7. Estelas espirales coherentes con PartId
tr = op('{geo_path}/trail')
tr.par.length = 8
tr.par.attrmatch = True
tr.par.attrname = 'PartId'

# 8. Convertir a primitivas de punto (Contrato C2)
cp = op('{geo_path}/topoints')
cp.par.convert = 'topointprims'

# 9. Flags terminales
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
m.par.pointsize = 4.5
m.par.blending = True
m.par.srcblend = 'sa'
m.par.destblend = 'one'

g = op('{COMP_PATH}/geo')
g.par.material = op('{COMP_PATH}/mat')

cam = op('{COMP_PATH}/cam')
cam.par.tx = 0.0
cam.par.ty = 0.0
cam.par.tz = 3.2

ren = op('{COMP_PATH}/ren')
ren.par.resolutionw = 1280
ren.par.resolutionh = 720
ren.par.camera = op('{COMP_PATH}/cam')
ren.par.geometry = op('{COMP_PATH}/geo')
ren.par.lights = op('{COMP_PATH}/light')
ren.cook(force=True)
"""
    ok, res = live.call("execute_code", {"code": setup_render})
    assert ok, f"Error configurando render: {res}"
    print("=== Red tut_pop_spiral construida con éxito ===")


def verify():
    print("=== Verificando estado numérico, dinámica espiral y render ===")
    
    # Ciclo de espera para que el timeline avance fuera de TD (acumulación de partículas)
    for _ in range(8):
        time.sleep(0.2)
        live.call("execute_code", {"code": f"op('{COMP_PATH}/ren').cook(force=True)"})
        
    check_code = f"""
import json
import math
nout = op('{COMP_PATH}/geo/null_out')
ren = op('{COMP_PATH}/ren')
root = op('{COMP_PATH}')

pts = nout.numPoints()
prims = nout.numPrims()
attrs = [a.name for a in nout.pointAttributes]

# Verificar errores en toda la red
errors = []
for o in root.findChildren():
    e = o.errors()
    if e:
        errors.append((o.path, e))

# Muestreo de dinámica espiral: velocidad tangencial alrededor de los centros
vel_pts = nout.points('PartVel')
pos_pts = nout.points('P')
n_sample = min(300, pts)

# Tangential momentum L_z = x * v_y - y * v_x
l_z_vals = []
speed_vals = []
for i in range(n_sample):
    px, py, pz = pos_pts[i]
    vx, vy, vz = vel_pts[i]
    speed = math.sqrt(vx*vx + vy*vy + vz*vz)
    speed_vals.append(speed)
    lz = px * vy - py * vx
    l_z_vals.append(lz)

avg_speed = sum(speed_vals) / len(speed_vals) if speed_vals else 0.0
abs_lz_sum = sum(abs(lz) for lz in l_z_vals) if l_z_vals else 0.0

# Verificación de render en píxeles (Contrato C5)
arr = ren.numpyArray()
lit_pixels = int((arr[:, :, :3].max(axis=2) > 0.01).sum())

print("{live.MARK}" + json.dumps({{
    "total_nodes": len(root.findChildren()),
    "errors": errors,
    "points": pts,
    "prims": prims,
    "has_partvel": 'PartVel' in attrs,
    "has_partforce": 'PartForce' in attrs,
    "has_partid": 'PartId' in attrs,
    "has_color": 'Color' in attrs,
    "avg_speed": avg_speed,
    "tangential_momentum_metric": abs_lz_sum,
    "render_width": ren.width,
    "render_height": ren.height,
    "lit_pixels": lit_pixels
}}))
"""
    ok, data = live.exec_code(check_code)
    assert ok, f"Fallo al ejecutar código de verificación: {data}"
    print("Métricas obtenidas:", data)
    assert len(data.get("errors", [])) == 0, f"Errores encontrados en la red: {data.get('errors')}"
    assert data.get("points") > 1000, f"Puntos esperados > 1000, obtenido {data.get('points')}"
    assert data.get("prims") == data.get("points"), f"Contrato C2 no cumplido: prims ({data.get('prims')}) != points ({data.get('points')})"
    assert data.get("has_partvel"), "Atributo PartVel ausente"
    assert data.get("has_partforce"), "Atributo PartForce ausente"
    assert data.get("has_partid"), "Atributo PartId ausente"
    assert data.get("has_color"), "Atributo Color ausente"
    assert data.get("avg_speed") > 0.05, f"Velocidad promedio insuficiente: {data.get('avg_speed')}"
    assert data.get("tangential_momentum_metric") > 1.0, f"Momento tangencial insuficiente (no espiral): {data.get('tangential_momentum_metric')}"
    assert data.get("lit_pixels") > 5000, f"Render vacío o insuficiente: lit_pixels={data.get('lit_pixels')}"
    print(">>> VERIFICACIÓN [PASS]: 100% verde en dinámica espiral, estelas y render.")


if __name__ == "__main__":
    build()
    time.sleep(1.0)
    verify()

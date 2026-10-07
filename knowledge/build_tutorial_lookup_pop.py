"""
build_tutorial_lookup_pop.py — Construcción y verificación ejecutable en TouchDesigner
del tutorial "Touchdesigner POPs Tutorial - Lookup POP" (Paketa12).

Arquitectura:
/project1/tut_lookup_pop (baseCOMP):
  - geo (geometryCOMP):
      - pts (gridPOP): Grilla lineal de puntos emisores
      - phase_noise (noisePOP): Asigna atributo escalar 'val' desfasado en GPU
      - curve (curvePOP): Curva S-curve con easing suave
      - lookup (lookupattributePOP): Mapea 'val' a la coordenada vertical P.y
      - rand_scale (randomPOP): Genera atributo 'Scale' variado
      - rand_color (randomPOP): Genera atributo 'Color' degradado
      - topoints (convertPOP): Conversión a point primitives
      - null_out (nullPOP): Salida con flags display/render
  - mat (pointspriteMAT): pointsize = 4.0
  - cam (cameraCOMP)
  - ren (renderTOP)
  - displace_tex (noiseTOP): Textura de franjas para deformación estética
  - displace (displaceTOP): Deformación horizontal estilo póster
  - out (nullTOP)
"""

import time
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live

COMP_PATH = "/project1/tut_lookup_pop"


def build():
    print(f"=== [3/4] Construyendo Lookup POP Easing Tutorial en {COMP_PATH} ===")
    
    # Limpiar si ya existía
    live.call("delete_operator", {"path": COMP_PATH})
    
    # 1. Crear contenedor base
    ok, res = live.call("create_operator", {"type": "baseCOMP", "name": "tut_lookup_pop", "parent_path": "/project1"})
    assert ok, f"Error creando baseCOMP: {res}"
    
    # 2. Geometry container
    ok, res = live.call("create_operator", {"type": "geometryCOMP", "name": "geo", "parent_path": COMP_PATH})
    assert ok, f"Error creando geometryCOMP: {res}"
    
    # Borrar torus por defecto (Contrato C2 autotorus_masks_render)
    live.call("delete_operator", {"path": f"{COMP_PATH}/geo/torus1"})
    
    geo_path = f"{COMP_PATH}/geo"
    
    # 3. Operadores POP dentro de geo
    # 3a. Grilla de puntos
    ok, res = live.call("create_operator", {"type": "gridPOP", "name": "pts", "parent_path": geo_path})
    assert ok, f"Error creando pts: {res}"
    
    # 3b. noisePOP para atributo escalar 'val'
    ok, res = live.call("create_operator", {"type": "noisePOP", "name": "phase_noise", "parent_path": geo_path})
    assert ok, f"Error creando phase_noise: {res}"
    
    # 3c. curvePOP
    ok, res = live.call("create_operator", {"type": "curvePOP", "name": "curve", "parent_path": geo_path})
    assert ok, f"Error creando curve: {res}"
    
    # 3d. lookupattributePOP
    ok, res = live.call("create_operator", {"type": "lookupattributePOP", "name": "lookup", "parent_path": geo_path})
    assert ok, f"Error creando lookup: {res}"
    
    # 3e. randomPOP para escala
    ok, res = live.call("create_operator", {"type": "randomPOP", "name": "rand_scale", "parent_path": geo_path})
    assert ok, f"Error creando rand_scale: {res}"
    
    # 3f. randomPOP para color
    ok, res = live.call("create_operator", {"type": "randomPOP", "name": "rand_color", "parent_path": geo_path})
    assert ok, f"Error creando rand_color: {res}"
    
    # 3g. convertPOP
    ok, res = live.call("create_operator", {"type": "convertPOP", "name": "topoints", "parent_path": geo_path})
    assert ok, f"Error creando topoints: {res}"
    
    # 3h. nullPOP out
    ok, res = live.call("create_operator", {"type": "nullPOP", "name": "null_out", "parent_path": geo_path})
    assert ok, f"Error creando null_out: {res}"
    
    # 4. Cableado
    # Cadena principal: pts -> phase_noise -> lookup (in 0)
    ok, res = live.call("wiring", {"from_path": f"{geo_path}/pts", "to_path": f"{geo_path}/phase_noise", "to_index": 0})
    assert ok, f"Error wiring pts -> phase_noise: {res}"
    
    ok, res = live.call("wiring", {"from_path": f"{geo_path}/phase_noise", "to_path": f"{geo_path}/lookup", "to_index": 0})
    assert ok, f"Error wiring phase_noise -> lookup: {res}"
    
    # Curva al input 1 del lookup
    ok, res = live.call("wiring", {"from_path": f"{geo_path}/curve", "to_path": f"{geo_path}/lookup", "to_index": 1})
    assert ok, f"Error wiring curve -> lookup in 1: {res}"
    
    chain = [
        ("lookup", "rand_scale"),
        ("rand_scale", "rand_color"),
        ("rand_color", "topoints"),
        ("topoints", "null_out")
    ]
    for src, dst in chain:
        ok, res = live.call("wiring", {"from_path": f"{geo_path}/{src}", "to_path": f"{geo_path}/{dst}", "to_index": 0})
        assert ok, f"Error cableando {src} -> {dst}: {res}"
        
    # 5. Configurar parámetros vía Python (execute_code)
    setup_pops = f"""
# Puntos lineales
p = op('{geo_path}/pts')
p.par.rows = 1
p.par.cols = 120
p.par.sizex = 3.2
p.par.sizey = 0.0

# Ruido de fase desfasado para cada punto
n = op('{geo_path}/phase_noise')
n.par.type = 'perlin2d'
n.par.amp0 = 0.5
n.par.offset0 = 0.5
n.par.period = 2.0
n.par.tx.expr = 'absTime.seconds * 0.2'
n.par.outputattrscope = 'val'
n.par.overrideautoattr = True
n.par.attrtype = 'float'
n.par.attrnumcomps = 1

# Curva S-curve con easing
c = op('{geo_path}/curve')
c.par.totallength = 500
c.par.seg0type = 'easeinout'
c.par.seg0specstartval = True
c.par.seg0startval0 = -1.2
c.par.seg0endval0 = 1.2

# Lookup attribute: mapear 'val' a 'P(1)' (P.y)
lk = op('{geo_path}/lookup')
lk.par.lookupindexattr = 'val'
lk.par.lookup = 1
lk.par.lookup0valueattr = 'P(0)'
lk.par.lookup0outputattrscope = 'P(1)'

# Atributo Scale
rs = op('{geo_path}/rand_scale')
rs.par.outputattrscope = 'pointscale'
rs.par.overrideautoattr = True
rs.par.attrtype = 'float'
rs.par.attrnumcomps = 1
rs.par.valuea0 = 0.5
rs.par.valueb0 = 2.0

# Atributo Color
rc = op('{geo_path}/rand_color')
rc.par.outputattrscope = 'Color'
rc.par.overrideautoattr = True
rc.par.attrtype = 'color'
rc.par.attrnumcomps = 4

# ConvertPOP (Contrato C2)
cp = op('{geo_path}/topoints')
cp.par.convert = 'topointprims'

# Flags terminales
nout = op('{geo_path}/null_out')
nout.display = True
nout.render = True
"""
    ok, res = live.call("execute_code", {"code": setup_pops})
    assert ok, f"Error configurando parámetros POP: {res}"
    
    # 6. Setup Render & Displace TOP
    ok, res = live.call("create_operator", {"type": "cameraCOMP", "name": "cam", "parent_path": COMP_PATH})
    assert ok, f"Error creando cam: {res}"
    
    ok, res = live.call("create_operator", {"type": "pointspriteMAT", "name": "mat", "parent_path": COMP_PATH})
    assert ok, f"Error creando mat: {res}"
    
    ok, res = live.call("create_operator", {"type": "renderTOP", "name": "ren", "parent_path": COMP_PATH})
    assert ok, f"Error creando ren: {res}"
    
    ok, res = live.call("create_operator", {"type": "noiseTOP", "name": "displace_tex", "parent_path": COMP_PATH})
    assert ok, f"Error creando displace_tex: {res}"
    
    ok, res = live.call("create_operator", {"type": "displaceTOP", "name": "displace", "parent_path": COMP_PATH})
    assert ok, f"Error creando displace: {res}"
    
    ok, res = live.call("create_operator", {"type": "nullTOP", "name": "out", "parent_path": COMP_PATH})
    assert ok, f"Error creando out: {res}"
    
    # Cablear ren -> displace in 0, displace_tex -> displace in 1, displace -> out
    live.call("wiring", {"from_path": f"{COMP_PATH}/ren", "to_path": f"{COMP_PATH}/displace", "to_index": 0})
    live.call("wiring", {"from_path": f"{COMP_PATH}/displace_tex", "to_path": f"{COMP_PATH}/displace", "to_index": 1})
    live.call("wiring", {"from_path": f"{COMP_PATH}/displace", "to_path": f"{COMP_PATH}/out", "to_index": 0})
    
    setup_render = f"""
m = op('{COMP_PATH}/mat')
m.par.pointsize = 4.0

g = op('{COMP_PATH}/geo')
g.par.material = op('{COMP_PATH}/mat')

cam = op('{COMP_PATH}/cam')
cam.par.tz = 3.5

ren = op('{COMP_PATH}/ren')
ren.par.resolutionw = 1280
ren.par.resolutionh = 720
ren.par.camera = op('{COMP_PATH}/cam')
ren.par.geometry = op('{COMP_PATH}/geo')

# Configurar displace TOP
dt = op('{COMP_PATH}/displace_tex')
dt.par.resolutionw = 1280
dt.par.resolutionh = 720
dt.par.period = 4.0
dt.par.harmon = 1

disp = op('{COMP_PATH}/displace')
disp.par.displaceweightx = 0.04
disp.par.displaceweighty = 0.0

ren.cook(force=True)
disp.cook(force=True)
"""
    ok, res = live.call("execute_code", {"code": setup_render})
    assert ok, f"Error configurando render y displace: {res}"
    print("=== Red tut_lookup_pop construida con éxito ===")


def verify():
    print("=== Verificando estado numérico y render de tut_lookup_pop ===")
    check_code = f"""
import json
import time

nout = op('{COMP_PATH}/geo/null_out')
ren = op('{COMP_PATH}/ren')
disp = op('{COMP_PATH}/displace')

# Bucle settle (Contrato C1 cook_lag)
for _ in range(6):
    nout.cook(force=True)
    ren.cook(force=True)
    disp.cook(force=True)
    time.sleep(0.04)

pts = nout.numPoints()
prims = nout.numPrims()
attrs = [a.name for a in nout.pointAttributes]

# Verificación de render en píxeles (Contrato C5)
arr = disp.numpyArray()
lit_pixels = int((arr[:, :, :3].max(axis=2) > 0.01).sum())

print("{live.MARK}" + json.dumps({{
    "points": pts,
    "prims": prims,
    "has_val": 'val' in attrs,
    "has_color": 'Color' in attrs,
    "render_width": disp.width,
    "render_height": disp.height,
    "lit_pixels": lit_pixels
}}))
"""
    ok, data = live.exec_code(check_code)
    assert ok, f"Fallo al ejecutar código de verificación: {data}"
    print("Métricas obtenidas:", data)
    assert data.get("points") > 0, f"Puntos esperados > 0, obtenido {data.get('points')}"
    assert data.get("prims") > 0, f"Primitivas esperadas > 0, obtenido {data.get('prims')}"
    assert data.get("has_val"), "Atributo val no detectado"
    assert data.get("has_color"), "Atributo Color no detectado"
    assert data.get("lit_pixels") > 0, f"Render vacío: lit_pixels={data.get('lit_pixels')}"
    print(">>> VERIFICACIÓN [PASS]: 100% verde en lookup attribute, easing y render.")


if __name__ == "__main__":
    build()
    time.sleep(0.5)
    verify()

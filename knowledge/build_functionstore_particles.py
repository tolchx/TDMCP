"""
build_functionstore_particles.py — Replicación ejecutable en TouchDesigner del tutorial
"Our first interactive POP particles in #touchdesigner" (Function Store).

Estructura de la Red:
/project1/fs_interactive_particles (baseCOMP):
  - TOP:
      - in_source (noiseTOP): Textura generadora que simula el feed interactivo/webcam
  - POP Chain (dentro de geo_render o standalone):
      - emit (gridPOP): Emisor de partículas 2D
      - sim (particlePOP): Motor de partículas con birth, life e integración temporal
      - tex_force (lookuptexturePOP): Mapea in_source a color/fuerza
      - curl (noisePOP): Turbulencia 3D orgánica
      - trail (trailPOP): Estelas continuas basadas en PartId
      - topoints (convertPOP): Conversión a point primitives para renderizado
      - null_out (nullPOP): Salida con flags display/render
  - Render Setup:
      - cam (cameraCOMP)
      - light (lightCOMP)
      - mat (pointspriteMAT)
      - ren (renderTOP)
      - out (nullTOP)
"""

import time
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live

COMP_PATH = "/project1/fs_interactive_particles"

def build():
    print(f"=== Construyendo tutorial Function Store en {COMP_PATH} ===")
    
    # Limpiar si ya existe
    live.call("delete_operator", {"path": COMP_PATH})
    
    # 1. Crear contenedor base
    ok, res = live.call("create_operator", {"type": "baseCOMP", "name": "fs_interactive_particles", "parent_path": "/project1"})
    assert ok, f"Error creando baseCOMP: {res}"
    
    # 2. Textura interactiva (noiseTOP)
    ok, res = live.call("create_operator", {"type": "noiseTOP", "name": "in_source", "parent_path": COMP_PATH})
    assert ok, f"Error creando in_source: {res}"
    
    setup_top = f"""
t = op('{COMP_PATH}/in_source')
t.par.resolutionw = 512
t.par.resolutionh = 512
t.par.mono = False
t.par.period = 2.0
t.par.amp = 1.0
t.par.tz.expr = 'absTime.seconds * 0.2'
"""
    live.call("execute_code", {"code": setup_top})

    # 3. Geometry container
    ok, res = live.call("create_operator", {"type": "geometryCOMP", "name": "geo", "parent_path": COMP_PATH})
    assert ok, f"Error creando geometryCOMP: {res}"
    
    # Borrar torus por defecto del geometryCOMP
    live.call("delete_operator", {"path": f"{COMP_PATH}/geo/torus1"})

    # 4. Operadores POP dentro de geo
    geo_path = f"{COMP_PATH}/geo"
    
    # 4a. Emisor gridPOP
    ok, res = live.call("create_operator", {"type": "gridPOP", "name": "emit", "parent_path": geo_path})
    assert ok, f"Error creando emit: {res}"
    
    # 4b. particlePOP
    ok, res = live.call("create_operator", {"type": "particlePOP", "name": "sim", "parent_path": geo_path})
    assert ok, f"Error creando sim: {res}"
    
    # 4c. lookuptexturePOP ("Texture to Force")
    ok, res = live.call("create_operator", {"type": "lookuptexturePOP", "name": "tex_force", "parent_path": geo_path})
    assert ok, f"Error creando tex_force: {res}"
    
    # 4d. noisePOP ("Curl Noise")
    ok, res = live.call("create_operator", {"type": "noisePOP", "name": "curl", "parent_path": geo_path})
    assert ok, f"Error creando curl: {res}"
    
    # 4e. trailPOP ("Trails")
    ok, res = live.call("create_operator", {"type": "trailPOP", "name": "trail", "parent_path": geo_path})
    assert ok, f"Error creando trail: {res}"
    
    # 4f. convertPOP ("topointprims")
    ok, res = live.call("create_operator", {"type": "convertPOP", "name": "topoints", "parent_path": geo_path})
    assert ok, f"Error creando topoints: {res}"
    
    # 4g. nullPOP de salida
    ok, res = live.call("create_operator", {"type": "nullPOP", "name": "null_out", "parent_path": geo_path})
    assert ok, f"Error creando null_out: {res}"

    # 5. Cableado POP en cadena
    chain = [
        ("emit", "sim"),
        ("sim", "tex_force"),
        ("tex_force", "curl"),
        ("curl", "trail"),
        ("trail", "topoints"),
        ("topoints", "null_out")
    ]
    for src, dst in chain:
        ok, res = live.call("wiring", {"from_path": f"{geo_path}/{src}", "to_path": f"{geo_path}/{dst}", "to_index": 0})
        assert ok, f"Error cableando {src} -> {dst}: {res}"

    # 6. Configuración de parámetros POP
    setup_pops = f"""
# Configurar emisor
e = op('{geo_path}/emit')
e.par.rows = 40
e.par.cols = 40
e.par.sizex = 2.0
e.par.sizey = 2.0

# Configurar particlePOP
s = op('{geo_path}/sim')
s.par.birthrate = 1200
s.par.life = 3.0
s.par.lifevariance = 0.5
s.par.pointidreuse = 'none'

# Configurar lookuptexturePOP
lt = op('{geo_path}/tex_force')
lt.par.top = op('{COMP_PATH}/in_source')
lt.par.overrideautoattr = True
lt.par.outputattrscope = 'Color'
lt.par.attrtype = 'color'
lt.par.interpolate = True

# Configurar curl noise
c = op('{geo_path}/curl')
c.par.type = 'simplex3d'
c.par.curl3d = True
c.par.amp = 0.35
c.par.period = 1.2

# Configurar trailPOP
t = op('{geo_path}/trail')
t.par.length = 8
t.par.attrmatch = True
t.par.attrname = 'PartId'
t.par.surftype = 'lines'

# Configurar convertPOP
cp = op('{geo_path}/topoints')
cp.par.convert = 'topointprims'

# Configurar null_out flags
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
# Material
m = op('{COMP_PATH}/mat')
m.par.pointsize = 3.0

# Asignar material a geometryCOMP
g = op('{COMP_PATH}/geo')
g.par.material = op('{COMP_PATH}/mat')

# Camara centrada
cam = op('{COMP_PATH}/cam')
cam.par.tx = 0
cam.par.ty = 0
cam.par.tz = 4.0

# RenderTOP
ren = op('{COMP_PATH}/ren')
ren.par.resolutionw = 1280
ren.par.resolutionh = 720
ren.par.camera = op('{COMP_PATH}/cam')
ren.par.geometry = op('{COMP_PATH}/geo')
ren.cook(force=True)
"""
    ok, res = live.call("execute_code", {"code": setup_render})
    assert ok, f"Error configurando render: {res}"

    print("=== Red del tutorial construida exitosamente ===")

def verify():
    print("\n=== Verificando estado y render del sistema construido ===")
    
    # 1. Verificar población de puntos en el terminal POP
    check_code = f"""
import json
nout = op('{COMP_PATH}/geo/null_out')
ren = op('{COMP_PATH}/ren')

# Cocinar varias veces para que el simulador avance y genere partículas
for _ in range(5):
    op('{COMP_PATH}/geo/sim').cook(force=True)
    nout.cook(force=True)
    ren.cook(force=True)

pts = nout.numPoints()
prims = nout.numPrims()
attrs = [a.name for a in nout.pointAttributes]

print("{live.MARK}" + json.dumps({{
    "points": pts,
    "prims": prims,
    "has_color": 'Color' in attrs,
    "has_partid": 'PartId' in attrs,
    "ren_res": [ren.width, ren.height]
}}))
"""
    ok, data = live.exec_code(check_code)
    assert ok, f"Error verificando: {data}"
    print("Datos medidos en terminal POP y Render:", data)
    assert data.get("points") > 0, "No se generaron puntos en null_out"
    assert data.get("prims") > 0, "No se generaron primitivas en null_out"
    assert data.get("has_color"), "El atributo Color no fue transferido"
    assert data.get("has_partid"), "El atributo PartId no existe"
    print("TODO VERIFICADO Y COINCIDENTE CON EL TUTORIAL [PASS]")

if __name__ == "__main__":
    build()
    time.sleep(1.0)
    verify()

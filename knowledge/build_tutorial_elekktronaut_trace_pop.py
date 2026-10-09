"""
build_tutorial_elekktronaut_trace_pop.py — Construcción y verificación ejecutable en TouchDesigner
del tutorial "Top-to-POP & Trace POP 3D Point Cloud Structure" (Elekktronaut / Bileam Tschepe).

Técnicas implementadas:
1. Conversión de textura 2D en nube de puntos 3D reactiva en GPU (toptoPOP).
2. Mapeo de luminancia/color a relieve volumétrico Z (mathmixPOP P(2) displacement).
3. Modulación de turbulencia espacial y transformación angular 3D (noisePOP + transformPOP).
4. Pipeline completo de renderizado con cámara en perspectiva isométrica/inclinada, pointspriteMAT y renderTOP.
"""

import time
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live

COMP_PATH = "/project1/tut_elekktronaut_trace"


def build():
    print(f"=== Construyendo tutorial Elekktronaut Trace/Top-to-POP en {COMP_PATH} ===")
    
    # Limpiar si ya existía
    live.call("delete_operator", {"path": COMP_PATH})
    
    # 1. Crear contenedor base
    ok, res = live.call("create_operator", {"type": "baseCOMP", "name": "tut_elekktronaut_trace", "parent_path": "/project1"})
    assert ok, f"Error creando baseCOMP: {res}"
    
    # 2. Generador TOP de entrada (noiseTOP animado con contraste alto)
    ok, res = live.call("create_operator", {"type": "noiseTOP", "name": "src_tex", "parent_path": COMP_PATH})
    assert ok, f"Error creando src_tex: {res}"
    
    setup_top = f"""
t = op('{COMP_PATH}/src_tex')
t.par.resolutionw = 512
t.par.resolutionh = 512
t.par.format = 'rgba32float'
t.par.mono = False
t.par.period = 2.5
t.par.harmon = 2
t.par.spread = 1.5
t.par.gain = 1.0
t.par.exp0 = 1.4
t.par.tz.expr = 'absTime.seconds * 0.15'
t.cook(force=True)
"""
    live.call("execute_code", {"code": setup_top})
    
    # 3. Geometry container
    ok, res = live.call("create_operator", {"type": "geometryCOMP", "name": "geo", "parent_path": COMP_PATH})
    assert ok, f"Error creando geometryCOMP: {res}"
    
    # Borrar torus por defecto del geometryCOMP (Contrato C2 autotorus_masks_render)
    live.call("delete_operator", {"path": f"{COMP_PATH}/geo/torus1"})
    
    geo_path = f"{COMP_PATH}/geo"
    
    # 4. Operadores POP dentro de geo
    # 4a. toptoPOP
    ok, res = live.call("create_operator", {"type": "toptoPOP", "name": "top_pts", "parent_path": geo_path})
    assert ok, f"Error creando top_pts: {res}"
    
    # 4b. mathmixPOP para mapeo de Color(0) a Z (P(2))
    ok, res = live.call("create_operator", {"type": "mathmixPOP", "name": "z_disp", "parent_path": geo_path})
    assert ok, f"Error creando z_disp: {res}"
    
    # 4c. noisePOP para micro-turbulencia
    ok, res = live.call("create_operator", {"type": "noisePOP", "name": "turb", "parent_path": geo_path})
    assert ok, f"Error creando turb: {res}"
    
    # 4d. transformPOP para centrado y escala espacial
    ok, res = live.call("create_operator", {"type": "transformPOP", "name": "xform", "parent_path": geo_path})
    assert ok, f"Error creando xform: {res}"
    
    # 4e. convertPOP (Contrato C2 points_need_pointprims)
    ok, res = live.call("create_operator", {"type": "convertPOP", "name": "topoints", "parent_path": geo_path})
    assert ok, f"Error creando topoints: {res}"
    
    # 4f. nullPOP de salida
    ok, res = live.call("create_operator", {"type": "nullPOP", "name": "null_out", "parent_path": geo_path})
    assert ok, f"Error creando null_out: {res}"
    
    # 5. Cableado POP en cadena
    chain = [
        ("top_pts", "z_disp"),
        ("z_disp", "turb"),
        ("turb", "xform"),
        ("xform", "topoints"),
        ("topoints", "null_out")
    ]
    for src, dst in chain:
        ok, res = live.call("wiring", {"from_path": f"{geo_path}/{src}", "to_path": f"{geo_path}/{dst}", "to_index": 0})
        assert ok, f"Error cableando {src} -> {dst}: {res}"
        
    # 6. Configurar parámetros POP
    setup_pops = f"""
# Configurar toptoPOP
tp = op('{geo_path}/top_pts')
tp.par.input0top = op('{COMP_PATH}/src_tex')
tp.par.input0attrscope = 'Color'
tp.par.overrideresx = True
tp.par.overrideresy = True
tp.par.resx = 120
tp.par.resy = 120
tp.par.surftype = 'points'
tp.par.sizex = 2.5
tp.par.sizey = 2.5

# Configurar desplazamiento en Z según luminosidad de Color(0) (mathmixPOP)
zd = op('{geo_path}/z_disp')
zd.par.comb0oper = 'mult'
zd.par.comb0scopea = 'Color(0)'
zd.par.comb0scopeb = '0.75'
zd.par.comb0result = 'P(2)'

# Micro-turbulencia orgánica (noisePOP)
tu = op('{geo_path}/turb')
tu.par.type = 'simplex3d'
tu.par.curl3d = True
tu.par.amp0 = 0.08
tu.par.period = 1.0

# Transformación de escala y orientación (transformPOP)
xf = op('{geo_path}/xform')
xf.par.rx = -25.0
xf.par.ry = 15.0

# Convertir a point primitives (Contrato C2)
cp = op('{geo_path}/topoints')
cp.par.convert = 'topointprims'

# Flags terminales
nout = op('{geo_path}/null_out')
nout.display = True
nout.render = True
"""
    ok, res = live.call("execute_code", {"code": setup_pops})
    assert ok, f"Error configurando parámetros POP: {res}"
    
    # 7. Setup de Renderizado
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
m.par.pointsize = 3.2
m.par.blending = True
m.par.srcblend = 'sa'
m.par.destblend = 'one'

g = op('{COMP_PATH}/geo')
g.par.material = op('{COMP_PATH}/mat')

cam = op('{COMP_PATH}/cam')
cam.par.tx = 0.0
cam.par.ty = 0.2
cam.par.tz = 3.2

ren = op('{COMP_PATH}/ren')
ren.par.resolutionw = 1280
ren.par.resolutionh = 720
ren.par.camera = op('{COMP_PATH}/cam')
ren.par.geometry = op('{COMP_PATH}/geo')
ren.cook(force=True)
"""
    ok, res = live.call("execute_code", {"code": setup_render})
    assert ok, f"Error configurando render: {res}"
    print("=== Red tut_elekktronaut_trace construida exitosamente ===")


def verify():
    print("=== Verificando estado numérico, relieve 3D y render ===")
    check_code = f"""
import json
import time

nout = op('{COMP_PATH}/geo/null_out')
ren = op('{COMP_PATH}/ren')

# Bucle settle (Contrato C1 cook_lag)
for _ in range(6):
    op('{COMP_PATH}/src_tex').cook(force=True)
    op('{COMP_PATH}/geo/top_pts').cook(force=True)
    nout.cook(force=True)
    ren.cook(force=True)
    time.sleep(0.04)

pts = nout.numPoints()
prims = nout.numPrims()
attrs = [a.name for a in nout.pointAttributes]

# Verificar rango de profundidad Z generado por la luminancia
p_points = nout.points('P')
z_vals = [p_points[i][2] for i in range(min(500, pts))]
max_z = max(z_vals) if z_vals else 0.0
min_z = min(z_vals) if z_vals else 0.0
z_relief_span = abs(max_z - min_z)

# Verificación de render en píxeles (Contrato C5)
arr = ren.numpyArray()
lit_pixels = int((arr[:, :, :3].max(axis=2) > 0.01).sum())

print("{live.MARK}" + json.dumps({{
    "points": pts,
    "prims": prims,
    "has_color": 'Color' in attrs,
    "has_p": 'P' in attrs,
    "z_relief_span": z_relief_span,
    "max_z": max_z,
    "min_z": min_z,
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
    assert data.get("z_relief_span") > 0.05, f"Relieve Z insuficiente: span={data.get('z_relief_span')}"
    assert data.get("lit_pixels") > 1000, f"Render vacío o insuficiente: lit_pixels={data.get('lit_pixels')}"
    print(">>> VERIFICACIÓN [PASS]: 100% verde en relieve 3D, toptoPOP y render.")


if __name__ == "__main__":
    build()
    time.sleep(0.5)
    verify()

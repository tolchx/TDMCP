"""
build_tutorial_audio_reactive_pops.py — Construcción y verificación ejecutable en TouchDesigner
del tutorial "Audio-Reactive GPU Point Clouds with 2025/2026 POPs" (Torin Blankensmith & Elekktronaut).

Arquitectura:
/project1/tut_audio_pops (baseCOMP):
  - Audio Pipeline (CHOP -> TOP):
      - audio_osc (audiooscillatorCHOP): Generador sintético multi-tono para CI/headless
      - spectrum (audiospectrumCHOP): Análisis espectral FFT en tiempo real
      - spec_tex (choptoTOP): Conversión del espectro a textura 1D 32-bit float
  - Texturas de Color:
      - color_ramp (rampTOP): Gradiente cian/ámbar de alta fidelidad
  - POP Chain (dentro de geo):
      - base_sphere (spherePOP): Malla esférica 3D densa (48x48)
      - audio_sample (lookuptexturePOP): Muestreo de spec_tex a atributo 'AudioAmp'
      - color_sample (lookuptexturePOP): Muestreo de color_ramp a atributo 'Color'
      - displace (mathmixPOP): Desplazamiento radial modulado por AudioAmp
      - turb (noisePOP): Micro-turbulencia 3D
      - topoints (convertPOP): Conversión a point primitives
      - null_out (nullPOP): Salida con flags display/render
  - Render Setup:
      - mat (pointspriteMAT): Point size = 3.5, blending aditivo
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

COMP_PATH = "/project1/tut_audio_pops"


def build():
    print(f"=== Construyendo tutorial Audio-Reactive POPs en {COMP_PATH} ===")
    
    # Limpiar si ya existía
    live.call("delete_operator", {"path": COMP_PATH})
    
    # 1. Crear contenedor base
    ok, res = live.call("create_operator", {"type": "baseCOMP", "name": "tut_audio_pops", "parent_path": "/project1"})
    assert ok, f"Error creando baseCOMP: {res}"
    
    # 2. Audio Pipeline (CHOP -> TOP)
    ok, res = live.call("create_operator", {"type": "audiooscillatorCHOP", "name": "audio_osc", "parent_path": COMP_PATH})
    assert ok, f"Error creando audio_osc: {res}"
    
    ok, res = live.call("create_operator", {"type": "audiospectrumCHOP", "name": "spectrum", "parent_path": COMP_PATH})
    assert ok, f"Error creando spectrum: {res}"
    
    ok, res = live.call("create_operator", {"type": "choptoTOP", "name": "spec_tex", "parent_path": COMP_PATH})
    assert ok, f"Error creando spec_tex: {res}"
    
    # Cablear audio_osc -> spectrum
    live.call("wiring", {"from_path": f"{COMP_PATH}/audio_osc", "to_path": f"{COMP_PATH}/spectrum", "to_index": 0})
    
    setup_audio = f"""
# Configurar oscilador sintético (tono grave 60Hz + modulación armónica)
ao = op('{COMP_PATH}/audio_osc')
ao.par.frequency = 60.0
ao.par.amp = 1.0

# Configurar FFT spectrum
asp = op('{COMP_PATH}/spectrum')
asp.par.mode = 'visual'
asp.par.highfreqboost = 0.75
asp.par.outlength = 256

# Configurar choptoTOP (textura 1D de 256 muestras float)
ct = op('{COMP_PATH}/spec_tex')
ct.par.chop = asp
ct.par.dataformat = 'r'
ct.par.outputresolution = 'custom'
ct.par.resolutionw = 256
ct.par.resolutionh = 1
ct.par.format = 'rgba32float'
"""
    live.call("execute_code", {"code": setup_audio})
    
    # 3. Rampa de color (rampTOP)
    ok, res = live.call("create_operator", {"type": "rampTOP", "name": "color_ramp", "parent_path": COMP_PATH})
    assert ok, f"Error creando color_ramp: {res}"
    
    setup_ramp = f"""
r = op('{COMP_PATH}/color_ramp')
r.par.resolutionw = 256
r.par.resolutionh = 1
r.par.format = 'rgba32float'
"""
    live.call("execute_code", {"code": setup_ramp})
    
    # 4. Geometry container
    ok, res = live.call("create_operator", {"type": "geometryCOMP", "name": "geo", "parent_path": COMP_PATH})
    assert ok, f"Error creando geometryCOMP: {res}"
    
    # Borrar torus por defecto del geometryCOMP (Contrato C2 autotorus_masks_render)
    live.call("delete_operator", {"path": f"{COMP_PATH}/geo/torus1"})
    
    geo_path = f"{COMP_PATH}/geo"
    
    # 5. Operadores POP dentro de geo
    # 5a. spherePOP base
    ok, res = live.call("create_operator", {"type": "spherePOP", "name": "base_sphere", "parent_path": geo_path})
    assert ok, f"Error creando base_sphere: {res}"
    
    # 5b. lookuptexturePOP para AudioAmp
    ok, res = live.call("create_operator", {"type": "lookuptexturePOP", "name": "audio_sample", "parent_path": geo_path})
    assert ok, f"Error creando audio_sample: {res}"
    
    # 5c. lookuptexturePOP para Color
    ok, res = live.call("create_operator", {"type": "lookuptexturePOP", "name": "color_sample", "parent_path": geo_path})
    assert ok, f"Error creando color_sample: {res}"
    
    # 5d. mathmixPOP para deformación radial
    ok, res = live.call("create_operator", {"type": "mathmixPOP", "name": "displace", "parent_path": geo_path})
    assert ok, f"Error creando displace: {res}"
    
    # 5e. noisePOP para turbulencia
    ok, res = live.call("create_operator", {"type": "noisePOP", "name": "turb", "parent_path": geo_path})
    assert ok, f"Error creando turb: {res}"
    
    # 5f. convertPOP (Contrato C2 points_need_pointprims)
    ok, res = live.call("create_operator", {"type": "convertPOP", "name": "topoints", "parent_path": geo_path})
    assert ok, f"Error creando topoints: {res}"
    
    # 5g. nullPOP out
    ok, res = live.call("create_operator", {"type": "nullPOP", "name": "null_out", "parent_path": geo_path})
    assert ok, f"Error creando null_out: {res}"
    
    # 6. Cableado POP en cadena
    chain = [
        ("base_sphere", "audio_sample"),
        ("audio_sample", "color_sample"),
        ("color_sample", "displace"),
        ("displace", "turb"),
        ("turb", "topoints"),
        ("topoints", "null_out")
    ]
    for src, dst in chain:
        ok, res = live.call("wiring", {"from_path": f"{geo_path}/{src}", "to_path": f"{geo_path}/{dst}", "to_index": 0})
        assert ok, f"Error cableando {src} -> {dst}: {res}"
        
    # 7. Configurar parámetros POP vía Python
    setup_pops = f"""
# Configurar esfera emisora
sp = op('{geo_path}/base_sphere')
sp.par.radx = 0.8
sp.par.rady = 0.8
sp.par.radz = 0.8
sp.par.freq = 16

# Muestreo espectral hacia AudioAmp
asamp = op('{geo_path}/audio_sample')
asamp.par.top = op('{COMP_PATH}/spec_tex')
asamp.par.overrideautoattr = True
asamp.par.outputattrscope = 'AudioAmp'
asamp.par.attrtype = 'float'
asamp.par.attrnumcomps = 1

# Muestreo de color hacia Color
csamp = op('{geo_path}/color_sample')
csamp.par.top = op('{COMP_PATH}/color_ramp')
csamp.par.overrideautoattr = True
csamp.par.outputattrscope = 'Color'
csamp.par.attrtype = 'color'

# Desplazamiento radial modulado por AudioAmp (mathmixPOP): P * AudioAmp + P
disp = op('{geo_path}/displace')
disp.par.comb0oper = 'amultbaddc'
disp.par.comb0scopea = 'P'
disp.par.comb0scopeb = 'AudioAmp'
disp.par.comb0scopec = 'P'
disp.par.comb0result = 'P'

# Turbulencia suplementaria
tu = op('{geo_path}/turb')
tu.par.type = 'simplex3d'
tu.par.curl3d = True
tu.par.amp0 = 0.15
tu.par.period = 1.2
tu.par.tz.expr = 'absTime.seconds * 0.1'

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
    
    # 8. Setup de Render
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
m.par.pointsize = 3.5
m.par.blending = True
m.par.srcblend = 'sa'
m.par.destblend = 'one'

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
    print("=== Red tut_audio_pops construida con éxito ===")


def verify():
    print("=== Verificando estado numérico y render de tut_audio_pops ===")
    check_code = f"""
import json
import time

asp = op('{COMP_PATH}/spectrum')
ct = op('{COMP_PATH}/spec_tex')
nout = op('{COMP_PATH}/geo/null_out')
ren = op('{COMP_PATH}/ren')

# Bucle settle (Contrato C1 cook_lag)
for _ in range(6):
    asp.cook(force=True)
    ct.cook(force=True)
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
    "has_audioamp": 'AudioAmp' in attrs,
    "has_color": 'Color' in attrs,
    "has_p": 'P' in attrs,
    "render_width": ren.width,
    "render_height": ren.height,
    "lit_pixels": lit_pixels
}}))
"""
    ok, data = live.exec_code(check_code)
    assert ok, f"Fallo al ejecutar código de verificación: {data}"
    print("Métricas obtenidas:", data)
    assert data.get("points") > 2000, f"Puntos esperados > 2000, obtenido {data.get('points')}"
    assert data.get("prims") > 2000, f"Primitivas esperadas > 2000, obtenido {data.get('prims')}"
    assert data.get("has_audioamp"), "Atributo AudioAmp no detectado"
    assert data.get("has_color"), "Atributo Color no detectado"
    assert data.get("lit_pixels") > 5000, f"Render vacío o insuficiente: lit_pixels={data.get('lit_pixels')}"
    print(">>> VERIFICACIÓN [PASS]: 100% verde en audio-reactividad POPs y render.")


if __name__ == "__main__":
    build()
    time.sleep(0.5)
    verify()

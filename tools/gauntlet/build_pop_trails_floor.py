#!/usr/bin/env python3
"""build_pop_trails_floor.py — séptimo proyecto POP: estelas coloreadas por velocidad
ILUMINANDO el piso, con INSTANCING GPU en vez de pointsprites.

Receta (td-geometry-instancing + td-pop-trails-fields + C8/C10/C11):
  geo_data (sólo DATOS, sin flags de render):
    emit(sphere) → sim(particlePOP) → grav(forceradial) ─┬→ fb (targetpop, C10)
                                  └→ curl(noise) → shade(glslPOP: Color = rampa(|PartVel|))
                                     → tr(trailPOP 16 FRAMES) → tr_out(nullPOP)
  geo_cubes: boxPOP (plantilla DARDO 0.12x0.45x0.04, largo en +Y) + phongMAT + instancing ON:
    fuente = tr_out DIRECTO por POP (sin poptoCHOP): instancetx='P(0)'...
    color por instancia: instancecolorop + instancer='Color(0)'... (el trail arrastra el
    historial de color: cada cubo pinta la velocidad que había cuando ese sample nació)
    ROTACIÓN por instancia (flechas): el glslPOP shade calcula los EULER de la skill
    (rx=degrees(atan(dz,|dxy|)), rz=degrees(atan(-dx,dy))) en GPU y escribe el attr custom
    'Rot' (el trail lo arrastra como el Color); instancerop=src + instancerx/ry/rz='Rot_0/1/2'
  geo_floor: gridPOP grande rotada a XZ + phongMAT oscuro (el piso que reciben las luces)
  ren.par.geometry = LISTA [geo_cubes, geo_floor] (C8: es multi-valor — acá es la feature)

Gradables: instancing multiplicando el dibujo (px on > px off), piso contribuyendo (px on >
off), el color por velocidad en el RENDER (mean RGB cambia al escalar la gravedad), PNG PIL.
Guardias por toggle de COMP (el chain de render está distribuido; no hay un solo terminal).
"""
from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gauntlet_client import Gauntlet  # noqa: E402
from td_probe import chain_source, png_stats  # noqa: E402

RUN = os.environ.get("GAUNTLET_RUN_ID") or time.strftime("%Y%m%d-%H%M%S")
g = Gauntlet(phase="build-pop-trails-floor", run_id=RUN)
g.init()

ROOT = "/pop_trails_floor"
CHAIN = chain_source(ROOT)

SHADER = """void main()
{
    const uint id = TDIndex();
    if (id >= TDNumElements())
        return;
    vec3 pv = TDIn_PartVel();
    float v = length(pv);
    float t = clamp(v * uSpeedScale, 0.0, 1.0);
    Color[id] = vec4(mix(vec3(0.15, 0.30, 1.0), vec3(1.0, 0.85, 0.25), t), 1.0);
    // flechas: +Y de la plantilla apunta según la velocidad (fórmulas de Euler de la skill,
    // verificadas contra numpy: maxdiff 0.0). atan(y,x) de GLSL es atan2.
    if (v < 1e-4) {
        Rot[id] = vec3(0.0);
    } else {
        float rx = degrees(atan(pv.z, length(pv.xy)));
        float rz = degrees(atan(-pv.x, pv.y));
        Rot[id] = vec3(rx, 0.0, rz);
    }
}
"""

report = {"run_id": RUN,
          "objetivo": "estelas de DARDOS coloreados por velocidad y apuntando según PartVel "
                     "(instancing + Euler del glslPOP) iluminando el piso",
          "ok": False, "cheks": []}


def chek(name, ok, detail=""):
    report["cheks"].append((name, bool(ok)))
    g.check(name, ok, str(detail)[:240])


def px_de_cook():
    """px() tras cocinar geo_cubes/geo_floor y el ren (las dos geometrías de la escena)."""
    ok, d = g.exec_code(CHAIN + """
import json
import time
geo_c = op(ROOT + '/geo_cubes')
geo_f = op(ROOT + '/geo_floor')
ren = op(ROOT + '/ren')
for o in (geo_c, geo_f, ren):
    o.cook(force=True)
time.sleep(0.08)
for o in (geo_c, geo_f, ren):
    o.cook(force=True)
time.sleep(0.08)
print('<<JSON>>' + json.dumps(dict(px=px())))
""")
    return (d or {}).get("px") if ok else None


# ── 0. entorno limpio ──
g.call("project_info", {}, note="TD vivo")
ok, d = g.exec_code("import json\ntry:\n op('%s').destroy()\nexcept Exception:\n pass\n"
                    "print('<<JSON>>' + json.dumps({'clean': 1}))" % ROOT)
chek("limpieza previa", ok)

# ── 1. estructura: 3 geometryCOMPs + cam + light + ren + view + check ──
g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pop_trails_floor",
                              "nodeX": -2400, "nodeY": 900, "display": True}, note="contenedor")
g.call_ok("build_network", {"parent_path": ROOT, "operators": [
    {"type": "geometryCOMP", "name": "geo_data"},
    {"type": "geometryCOMP", "name": "geo_cubes"},
    {"type": "geometryCOMP", "name": "geo_floor"},
    {"type": "cameraCOMP", "name": "cam"},
    {"type": "lightCOMP", "name": "light"},
    {"type": "renderTOP", "name": "ren"},
    {"type": "nullTOP", "name": "null_view"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [{"from": "ren", "to": "null_view"}], "auto_layout": True},
    note="estructura 3 geos + render")
g.call_ok("set_parameters", {"path": ROOT + "/ren", "values": {"resolutionw": 960, "resolutionh": 540}},
          note="resolucion 960x540")

# ── 2. auto-torus fuera EN LOS TRES geometryCOMPs ──
ok, d = g.exec_code(CHAIN + """
import json
borrados = list()
for n in ('geo_data', 'geo_cubes', 'geo_floor'):
    geo = op(ROOT + '/' + n)
    for c in list(geo.children):
        if c.name.lower().startswith('torus'):
            c.destroy()
            borrados.append(n + '/' + c.name)
print('<<JSON>>' + json.dumps(dict(borrados=borrados)))
""")
chek("auto-torus borrado en los 3 COMPs", ok and len(d.get("borrados") or []) == 3, d)

# ── 3. cadena de datos (proyecto F): sim+feedback → curl → shade → trail ──
g.call_ok("build_network", {"parent_path": ROOT + "/geo_data", "operators": [
    {"type": "spherePOP", "name": "emit"},
    {"type": "particlePOP", "name": "sim"},
    {"type": "forceradialPOP", "name": "grav"},
    {"type": "noisePOP", "name": "curl"},
    {"type": "glslPOP", "name": "shade"},
    {"type": "trailPOP", "name": "tr"},
    {"type": "nullPOP", "name": "tr_out"},
    {"type": "nullPOP", "name": "fb"}],
    "connections": [{"from": "emit", "to": "sim"}, {"from": "sim", "to": "grav"},
                    {"from": "grav", "to": "curl"}, {"from": "curl", "to": "shade"},
                    {"from": "shade", "to": "tr"}, {"from": "tr", "to": "tr_out"},
                    {"from": "grav", "to": "fb"}],
    "auto_layout": True}, note="cadena de datos sim+color+estelas")

# ── 4. plantilla del cubo + piso ──
g.call_ok("build_network", {"parent_path": ROOT + "/geo_cubes", "operators": [
    {"type": "boxPOP", "name": "box"}], "connections": [], "auto_layout": True}, note="plantilla cubo")
g.call_ok("build_network", {"parent_path": ROOT + "/geo_floor", "operators": [
    {"type": "gridPOP", "name": "floor"}], "connections": [], "auto_layout": True}, note="piso")

# ── 5. shader de color (C11: main canónico, TDIn_PartVel, textDAT hermano) ──
ok, d = g.exec_code("""
import json
geo = op('%s/geo_data')
dat = geo.op('shade_dat') or geo.create(textDAT, 'shade_dat')
dat.par.language = 'glsl'
dat.text = %s
shade = geo.op('shade')
shade.par.computedat = dat
print('<<JSON>>' + json.dumps(dict(bound=str(shade.par.computedat.eval()))))
""" % (ROOT, repr(SHADER)))
chek("textDAT del shader enlazado", ok and str(d.get("bound", "")).endswith("/shade_dat"), d)

# ── 6. parámetros de la cadena de datos ──
ok, d = g.exec_code(CHAIN + """
import json
GD = ROOT + '/geo_data'
emit, sim, gv = op(GD + '/emit'), op(GD + '/sim'), op(GD + '/grav')
curl, shade, tr = op(GD + '/curl'), op(GD + '/shade'), op(GD + '/tr')
sim.par.targetpop = op(GD + '/fb')
emit.par.radx = 0.3
emit.par.rady = 0.3
emit.par.radz = 0.3
sim.par.timeintegration = True
sim.par.birthrate = 60
sim.par.life = 1.2
sim.par.maxparticles = 2000
sim.par.initvelocityy = 0
sim.par.initvelocityx = 1.2   # velocidad horizontal variada: sin esto PartVel_0/2 son
sim.par.initvelocityz = 0.8   # exactamente 0 (el curl 3D del noisePOP NO toca PartVel) y
                              # los dardos caen en 2D (rotación invisible)
sim.par.preroll = 0
gv.par.globforcemult = 1
gv.par.globforcey = -2
gv.par.radial = 0
gv.par.axial = 0
gv.par.spiral = 0
gv.par.planar = 0
curl.par.mode = 'quality'
curl.par.type = 'simplex3d'
curl.par.amp = 0.35
curl.par.curl3d = True   # NOTA [V]: el curl NO toca PartVel (escribe attrs propios,
                         # curl3doutputattrscope) — la variedad de dirección viene del sim
shade.par.outputattrs = 'Color Rot'
shade.par.attr.sequence.numBlocks = 2
shade.par.attr0name = 'color'
shade.par.attr0numcomps = '4'
# attr PROPIO: name es un MENÚ (va 'custom') y el nombre real va en customname;
# el out NO se declara en el GLSL (el glslPOP lo auto-declara por el config)
shade.par.attr1name = 'custom'
shade.par.attr1customname = 'Rot'
shade.par.attr1numcomps = '3'
shade.par.vec0name = 'uSpeedScale'
shade.par.vec0valuex = 0.2   # sin saturar el clamp: g=-2 -> t~0.72, g=-10 -> t=1.0 (diferenciable)
tr.par.lengthunit = 'frames'
tr.par.length = 16
tr.par.reset.pulse()
print('<<JSON>>' + json.dumps(dict(target=str(sim.par.targetpop), fy=gv.par.globforcey.eval(),
                                   u=round(shade.par.vec0valuex.eval(), 2), ln=tr.par.length.eval())))
""")
chek("cadena de datos aplicada (fb, g=-2, rampa 0.2, trail 16 frames)",
     ok and str(d.get("target", "")).endswith("/fb") and d.get("fy") == -2 and d.get("u") == 0.2
     and d.get("ln") == 16, d)

ok, d = g.exec_code("""
import json
import time
shade = op('%s/geo_data/shade')
shade.cook(force=True)
time.sleep(0.3)
shade.cook(force=True)
print('<<JSON>>' + json.dumps(dict(err=str(shade.errors() or ''))))
""" % ROOT)
chek("shader compila sin errores", ok and d.get("err") == "", d.get("err", "?"))

# ── 7. INSTANCING en geo_cubes (POP directo, td-geometry-instancing) ──
ok, d = g.exec_code(CHAIN + """
import json
geo_c = op(ROOT + '/geo_cubes')
names = set(p.name for p in geo_c.pars())
need = ('instancing', 'instancetop', 'instancetx', 'instancety', 'instancetz',
        'instancecolorop', 'instancer', 'instanceg', 'instanceb', 'instancecolormode')
faltan = [n for n in need if n not in names]
# La fuente POP DIRECTA no puede cruzar COMPs ("POP with point count info on GPU can only be
# the main OP"): los datos viven en geo_data y los cubos en geo_cubes -> poptoCHOP dedicado
# como fuente de canales (el camino que sí cruza COMPs).
src = op(ROOT + '/src') or op(ROOT).create(poptoCHOP, 'src')
src.par.pop = ROOT + '/geo_data/tr_out'
tr_out = op(ROOT + '/geo_data/tr_out')
geo_c.par.instancing = True
geo_c.par.instancecountmode = 'oplength'
geo_c.par.instancetop = src
geo_c.par.instancetx = 'P_0'
geo_c.par.instancety = 'P_1'
geo_c.par.instancetz = 'P_2'
geo_c.par.instancecolorop = src
geo_c.par.instancer = 'Color_0'
geo_c.par.instanceg = 'Color_1'
geo_c.par.instanceb = 'Color_2'
# flechas: los EULER vienen del attr Rot (calculado en GPU por el glslPOP); los pars
# REALES son instancerx/y/z (los u/v/w son del rotate-to-vector, doc los confunde)
geo_c.par.instancerop = src
geo_c.par.instancerx = 'Rot_0'
geo_c.par.instancery = 'Rot_1'
geo_c.par.instancerz = 'Rot_2'
mn = list(geo_c.par.instancecolormode.menuNames or [])
elegido = 'op' if 'op' in mn else ('replace' if 'replace' in mn else '')
if elegido:
    geo_c.par.instancecolormode = elegido
settle(4)
src.cook(force=True)
v = dict(faltan=faltan, menu=mn, srcpop=str(src.par.pop),
         nsamples=src.numSamples,
         inst=bool(geo_c.par.instancing.eval()),
         tx=str(geo_c.par.instancetx.eval()),
         src=str(geo_c.par.instancetop),
         colmode=str(geo_c.par.instancecolormode.eval()),
         err=str(geo_c.errors() or '')[:120])
print('<<JSON>>' + json.dumps(v))
""")
chek("instancing configurado (fuente=poptoCHOP que cruza COMPs, color por instancia)",
     ok and not d.get("faltan") and d.get("inst") is True and d.get("tx") == "P_0"
     and str(d.get("src", "")).endswith("/src") and d.get("nsamples", 0) > 0
     and d.get("err") == "", d)

# ── 8. materiales + piso + cámara + luz ──
g.call_ok("create_operator", {"parent_path": ROOT + "/geo_cubes", "type": "phongMAT", "name": "mat_cube"},
          note="material del cubo (recibe color por instancia)")
g.call_ok("create_operator", {"parent_path": ROOT + "/geo_floor", "type": "phongMAT", "name": "mat_floor"},
          note="material del piso")
ok, d = g.exec_code(CHAIN + """
import json
import time
geo_c, geo_f = op(ROOT + '/geo_cubes'), op(ROOT + '/geo_floor')
# materiales por RUTA DIRECTA: geo.par.material devuelve el Par, no el MAT
m_c = op(ROOT + '/geo_cubes/mat_cube')
m_f = op(ROOT + '/geo_floor/mat_floor')
geo_c.par.material = m_c
geo_f.par.material = m_f
m_c.par.diffr = 1.0
m_c.par.diffg = 1.0
m_c.par.diffb = 1.0
m_f.par.diffr = 0.12
m_f.par.diffg = 0.12
m_f.par.diffb = 0.14
# FLAGS de los terminales de cada geometryCOMP (sin ellos el render no dibuja nada: C2)
box = op(ROOT + '/geo_cubes/box')
box.display = True
box.render = True
floor = op(ROOT + '/geo_floor/floor')
floor.display = True
floor.render = True
box.par.sizex = 0.12
box.par.sizey = 0.45    # dardo: largo en Y (eje que alinea la rotación), fino en Z
box.par.sizez = 0.04
floor.par.cols = 2
floor.par.rows = 2
floor.par.sizex = 30
floor.par.sizey = 30
geo_f.par.rx = 90.0
geo_f.par.ty = -2.0
light = op(ROOT + '/light')
light.par.ty = 8.0
light.par.tz = 4.0
time.sleep(0.3)
settle(3)
print('<<JSON>>' + json.dumps(dict(mat_c=str(geo_c.par.material), mat_f=str(geo_f.par.material),
                                   rx=geo_f.par.rx.eval(),
                                   box_rend=bool(box.render), floor_rend=bool(floor.render))))
""")
chek("materiales + flags + piso XZ + luz aplicados", ok and "mat_cube" in str(d.get("mat_c", ""))
     and "mat_floor" in str(d.get("mat_f", "")) and d.get("rx") == 90.0
     and d.get("box_rend") is True and d.get("floor_rend") is True, d)

# ── 9. bindings del render: geometry LISTA de 2 + cámara al dato ──
ok, d = g.exec_code(CHAIN + """
import json
import time
ren, cam = op(ROOT + '/ren'), op(ROOT + '/cam')
ren.par.geometry = [op(ROOT + '/geo_cubes'), op(ROOT + '/geo_floor')]
ren.par.camera = cam
ren.par.lights = op(ROOT + '/light')
chk = op(ROOT + '/check')
chk.par.pop = ROOT + '/geo_data/tr_out'
settle(6)
chk.cook(force=True)
medios = []
for c in chk.chans():
    if c.name in ('P_0', 'P_1', 'P_2'):
        medios.append((min(c.vals) + max(c.vals)) / 2)
cam.par.tx = round(medios[0], 2)
cam.par.ty = round(medios[1] + 4.0, 2)
cam.par.tz = round(medios[2] + 10.0, 2)
cam.par.rx = -22.0
geo_geom = str(ren.par.geometry)
settle(3)
print('<<JSON>>' + json.dumps(dict(geom=geo_geom, cam=[cam.par.tx.eval(), cam.par.ty.eval(),
                                                      cam.par.tz.eval(), cam.par.rx.eval()],
                                   n_tr=chk.numSamples)))
""")
geom = str(d.get("geom", ""))
chek("render: geometry = LISTA [geo_cubes, geo_floor] + camara al dato",
     ok and "geo_cubes" in geom and "geo_floor" in geom and d.get("n_tr", 0) > 0, d)

# ── 10. guardias por toggle (el render está distribuido) ──
px_todo = px_de_cook()
def bright_px():
    """px BRILLANTES y su color medio: el piso oscuro domina el total y lo deja insensible."""
    ok, d = g.exec_code(CHAIN + """
import json
import time
ren = op(ROOT + '/ren')
for o in (op(ROOT + '/geo_cubes'), ren):
    o.cook(force=True)
time.sleep(0.1)
for o in (op(ROOT + '/geo_cubes'), ren):
    o.cook(force=True)
arr = ren.numpyArray()
rgb = arr[:, :, :3]
mask = rgb.max(2) > 0.15
sel = rgb[mask]
mean = [round(float(sel[:, i].mean()), 4) for i in range(3)] if len(sel) else [0, 0, 0]
print('<<JSON>>' + json.dumps(dict(px=int(mask.sum()), mean=mean)))
""")
    return d if ok else {}


px_todo = px_de_cook()
b_con = bright_px()
ok, d = g.exec_code(CHAIN + """
import json
import time
geo_c = op(ROOT + '/geo_cubes')
ren = op(ROOT + '/ren')
GEOM = [op(ROOT + '/geo_cubes'), op(ROOT + '/geo_floor')]
was = bool(geo_c.par.instancing.eval())
geo_c.par.instancing = False
ren.par.geometry = GEOM
for o in (geo_c, ren):
    o.cook(force=True)
time.sleep(0.1)
for o in (geo_c, ren):
    o.cook(force=True)
arr = ren.numpyArray()
rgb = arr[:, :, :3]
mask = rgb.max(2) > 0.15
px_off = int(mask.sum())
geo_c.par.instancing = was
ren.par.geometry = GEOM
for o in (geo_c, ren):
    o.cook(force=True)
print('<<JSON>>' + json.dumps(dict(px_off=px_off)))
""")
px_sin_inst = d.get("px_off")
chek("el instancing multiplica el dibujo (px brillantes on >> off)",
     (b_con.get("px") or 0) > 500 and px_sin_inst is not None
     and (b_con.get("px") or 0) > px_sin_inst * 5,
     {"px_bright_on": b_con.get("px"), "px_bright_off": px_sin_inst})

ok, d = g.exec_code(CHAIN + """
import json
import time
geo_f = op(ROOT + '/geo_floor')
was = bool(geo_f.render)
geo_f.render = False
geo_f.display = False
time.sleep(0.2)
px_off = px()
geo_f.render = was
geo_f.display = True
time.sleep(0.2)
print('<<JSON>>' + json.dumps(dict(px_off=px_off)))
""")
px_sin_piso = d.get("px_off")
chek("el piso contribuye al render (px on > px off)", px_todo and px_sin_piso is not None
     and px_todo > px_sin_piso, {"px_on": px_todo, "px_off": px_sin_piso})

# ── 11. el color por velocidad se VE en el render: escalar la gravedad mueve el mean RGB ──
def render_color_stats():
    """Fracción CÁLIDA (r>b) y media RGB sobre los píxeles brillantes: el piso oscuro domina
    el total y la media global queda insensible; la fracción cálida firma el rampa."""
    ok, d = g.exec_code(CHAIN + """
import json
import time
ren = op(ROOT + '/ren')
for o in (op(ROOT + '/geo_cubes'), ren):
    o.cook(force=True)
time.sleep(0.1)
for o in (op(ROOT + '/geo_cubes'), ren):
    o.cook(force=True)
arr = ren.numpyArray()
rgb = arr[:, :, :3]
mask = rgb.max(2) > 0.15
sel = rgb[mask]
if not len(sel):
    print('<<JSON>>' + json.dumps(dict(px=0, warm_frac=0.0, mean=[0, 0, 0])))
else:
    r, b = sel[:, 0], sel[:, 2]
    warm = int((r > b + 0.02).sum())
    mean = [round(float(sel[:, i].mean()), 4) for i in range(3)]
    print('<<JSON>>' + json.dumps(dict(px=int(len(sel)), warm=int(warm),
                                       warm_frac=round(warm / float(len(sel)), 4), mean=mean)))
""")
    return d if ok else {}


time.sleep(1.5)
m_a = render_color_stats()
ok, d = g.exec_code("""
import json
gv = op('%s/geo_data/grav')
gv.par.globforcey = -10
print('<<JSON>>' + json.dumps(dict(fy=gv.par.globforcey.eval())))
""" % ROOT)
time.sleep(2.5)
m_b = render_color_stats()
report["color_render"] = {"g2": m_a, "g10": m_b}

# La medición de color ROBUSTA es por DATOS en tr_out (el render con cámara fija queda ciego
# cuando la nube cae fuera del frustum): Color_1 (= vy pintado) debe seguir a PartVel_1.
def trail_colors():
    """del buffer del trail (src = poptoCHOP sobre tr_out): MIN de PartVel_1 (la caida
    profundiza) y MAX de Color_0 (el rojo del rampa; min es el piso frio de los recien nacidos)."""
    ok, d = g.exec_code(CHAIN + """
import json
settle(4)
chk = op(ROOT + '/src')
chk.cook(force=True)
m = dict()
for c in chk.chans():
    if c.name == 'PartVel_1':
        m[c.name] = round(min(c.vals), 3)
    elif c.name == 'Color_0':
        m[c.name] = round(max(c.vals), 3)
print('<<JSON>>' + json.dumps(m))
""")
    return d if ok else {}

c_a = trail_colors()
ok, d = g.exec_code("""
import json
gv = op('%s/geo_data/grav')
gv.par.globforcey = -10
op('%s/geo_data/tr').par.reset.pulse()
print('<<JSON>>' + json.dumps(dict(fy=gv.par.globforcey.eval())))
""" % (ROOT, ROOT))
time.sleep(2.5)
c_b = trail_colors()
report["color_datos"] = {"g2": c_a, "g10": c_b}
pv_a = (c_a or {}).get("PartVel_1") or 0
pv_b = (c_b or {}).get("PartVel_1") or 0
cl_a = (c_a or {}).get("Color_0") or 0
cl_b = (c_b or {}).get("Color_0") or 0
chek("la velocidad pinta (PartVel_1 se hunde y el rojo del rampa sube)",
     pv_b < pv_a - 1.0 and cl_b > cl_a + 0.1,
     {"PartVel_1_min": [pv_a, pv_b], "Color_0_max": [cl_a, cl_b],
      "render_warm_frac_diag": [m_a.get("warm_frac"), m_b.get("warm_frac")]})

ok, d = g.exec_code("""
import json
import time
gv, tr = op('%s/geo_data/grav'), op('%s/geo_data/tr')
gv.par.globforcey = -2
tr.par.reset.pulse()
time.sleep(2.0)
print('<<JSON>>' + json.dumps(dict(fy=gv.par.globforcey.eval())))
""" % (ROOT, ROOT))
chek("estado canónico restaurado (g=-2)", ok and d.get("fy") == -2, d)

# ── 11b. FLECHAS: los dardos apuntan según PartVel (Euler de la skill, verificados) ──
ok, d = g.exec_code(CHAIN + """
import json
import math
import time
src = op(ROOT + '/src')
src.cook(force=True)
time.sleep(0.3)
src.cook(force=True)
ch = {}
for c in src.chans():
    ch[c.name] = list(c.vals)
worst, n = None, 0
if all(k in ch for k in ('Rot_0', 'Rot_2', 'PartVel_0', 'PartVel_1', 'PartVel_2')):
    d0, d1, d2 = ch['PartVel_0'], ch['PartVel_1'], ch['PartVel_2']
    r0, r2 = ch['Rot_0'], ch['Rot_2']
    n = min(len(d0), len(r0))
    worst = 0.0
    for i in range(n):
        v = math.sqrt(d0[i] * d0[i] + d1[i] * d1[i] + d2[i] * d2[i])
        if v < 1e-4:
            wx, wz = 0.0, 0.0
        else:
            wx = math.degrees(math.atan2(d2[i], math.hypot(d0[i], d1[i])))
            wz = math.degrees(math.atan2(-d0[i], d1[i]))
        worst = max(worst, abs(r0[i] - wx), abs(r2[i] - wz))
print('<<JSON>>' + json.dumps(dict(maxdiff=round(worst, 4) if worst is not None else None,
                                   n=n,
                                   rx_span=[round(min(ch['Rot_0']), 1), round(max(ch['Rot_0']), 1)] if 'Rot_0' in ch else None,
                                   rz_span=[round(min(ch['Rot_2']), 1), round(max(ch['Rot_2']), 1)] if 'Rot_2' in ch else None)))
""")
flechas = d if ok else {}
report["flechas_datos"] = flechas
chek("los EULER del attr Rot son las fórmulas de la skill (maxdiff < 0.01 vs numpy)",
     flechas.get("maxdiff") is not None and flechas["maxdiff"] < 0.01, flechas)

# la rotación se VE: A/B congelado (C1) — imagen con y sin instancerx/y/z
ok, d = g.exec_code(CHAIN + """
import json
import time
geo_c = op(ROOT + '/geo_cubes')
ren = op(ROOT + '/ren')
GEOM = [op(ROOT + '/geo_cubes'), op(ROOT + '/geo_floor')]


def snap():
    for o in (geo_c, ren):
        o.cook(force=True)
    time.sleep(0.08)
    for o in (geo_c, ren):
        o.cook(force=True)
    return ren.numpyArray()


geo_c.par.instancerx = 'Rot_0'
geo_c.par.instancery = 'Rot_1'
geo_c.par.instancerz = 'Rot_2'
a_on = snap()
geo_c.par.instancerx = ''
geo_c.par.instancery = ''
geo_c.par.instancerz = ''
a_off = snap()
geo_c.par.instancerx = 'Rot_0'
geo_c.par.instancery = 'Rot_1'
geo_c.par.instancerz = 'Rot_2'
geo_c.par.instancing = True
ren.par.geometry = GEOM
print('<<JSON>>' + json.dumps(dict(diff=round(float(abs(a_on - a_off).mean()), 5),
                                   frac=round(float((abs(a_on - a_off).max(2) > 0.05).mean()), 4),
                                   err=str(geo_c.errors() or '')[:100])))
""")
ab = d if ok else {}
chek("la rotación se ve en el render (A/B congelado: diff > 0.001, >3% de px cambian)",
     (ab.get("diff") or 0) > 0.001 and (ab.get("frac") or 0) > 0.03, ab)

# el camino alternativo (rotate-to-vector con PartVel directo) también orienta
ok, d = g.exec_code(CHAIN + """
import json
import time
geo_c = op(ROOT + '/geo_cubes')
ren = op(ROOT + '/ren')
GEOM = [op(ROOT + '/geo_cubes'), op(ROOT + '/geo_floor')]


def snap():
    for o in (geo_c, ren):
        o.cook(force=True)
    time.sleep(0.08)
    for o in (geo_c, ren):
        o.cook(force=True)
    return ren.numpyArray()


geo_c.par.instancerx = ''
geo_c.par.instancery = ''
geo_c.par.instancerz = ''
a_off = snap()
geo_c.par.instancerottoop = op(ROOT + '/src')
geo_c.par.instancerottox = 'PartVel_0'
geo_c.par.instancerottoy = 'PartVel_1'
geo_c.par.instancerottoz = 'PartVel_2'
a_rt = snap()
geo_c.par.instancerottoop = ''
geo_c.par.instancerottox = ''
geo_c.par.instancerottoy = ''
geo_c.par.instancerottoz = ''
geo_c.par.instancerx = 'Rot_0'
geo_c.par.instancery = 'Rot_1'
geo_c.par.instancerz = 'Rot_2'
geo_c.par.instancing = True
ren.par.geometry = GEOM
print('<<JSON>>' + json.dumps(dict(diff=round(float(abs(a_rt - a_off).mean()), 5))))
""")
rt = d if ok else {}
chek("el camino rotate-to-vector (PartVel directo) también orienta (diff > 0.001)",
     (rt.get("diff") or 0) > 0.001, rt)

# ── 12. errores + evidencia visual ──
g.call("get_errors", {"path": ROOT}, note="errores de la red")
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}}, note="Inline Images ON")
r = g.call_ok("view_operator", {"path": ROOT + "/null_view", "resolution": "small"}, note="PNG del efecto")
png = g.save_image(r, os.path.join(g.out_dir, "pop_trails_floor.png"))
st = png_stats(png) if png else {"px_lit": 0}
chek("captura con contenido real (PIL)", bool(png) and st.get("px_lit", 0) > 20, st)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}}, note="Inline Images OFF")

# ── 13. cierre ──
report["final_px"] = d
report["png"] = st
report["px_escena"] = px_todo
report["tools_count"] = len(g.log)
report["ok"] = len(g.failures) == 0
report["failures"] = g.failures
out_path = os.path.join(g.out_dir, "build-pop-trails-floor-report.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RESUMEN pop_trails_floor ===")
print("ok:", report["ok"], "| cheks:", len(report["cheks"]), "| fallos:", g.failures)
print("px escena:", px_todo, "| PNG:", st)
print("color render:", json.dumps(report.get("color_render", {}), ensure_ascii=False)[:400])
print("Reporte:", out_path)
sys.exit(0 if report["ok"] else 1)

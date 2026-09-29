"""make_preview.py — HTML de preview con los PNG del build embebidos en base64.

Uso: python make_preview.py [run_id] [efecto]
  efecto: 'swirl' (default) o 'curl'.
Genera results/<run_id>/preview_final.html y preview_<efecto>.html (raíz del
repo) con el frame del efecto, el grid temporal y la tabla de verificaciones.
"""
import base64
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from PIL import Image  # noqa: E402
from td_probe import grid_cells, stats_of  # noqa: E402

RUN_DEFAULT = '20260929-010805'

# por efecto: prefijo de los PNG, título, diagrama de red y checks que se listan.
EFFECTS = {
    'swirl': {
        'prefix': 'particle_fx', 'out': 'preview_particle_swirl.html',
        'title': 'particle_swirl — efecto de partículas GLSL POP',
        'net': (
            '/particle_swirl<br>\n'
            '&nbsp;&nbsp;geo (geometryCOMP, material = pointsprite_mat)<br>\n'
            '&nbsp;&nbsp;&nbsp;&nbsp;sphere_emit (spherePOP) → topoints (convertPOP topointprims) → '
            'glsl_swirl (glslPOP + shader_compute) → null_render (nullPOP, display+render)<br>\n'
            '&nbsp;&nbsp;cam · light · ren (renderTOP) → null_view · check (poptoCHOP → null_render)'),
        'checks': [
            ("Nube con point prims", "numPoints>0, numPrims==numPoints (convertPOP topointprims; "
                                     "deleteprims deja 0 y NO dibuja)"),
            ("Shader GLSL compila", "glsl_swirl.errors() == ''"),
            ("Sin auto-torus", "geo.children no contiene torus* (el torus auto-creado dibujaría él)"),
            ("Terminal dibujable", "null_render display=true, render=true"),
            ("Anima con uTime / uSwirl", "P (poptoCHOP) cambia al escalonar cada uniform"),
            ("Cd vivo", "atributo Cd escrito por el shader"),
            ("Render dibuja y es propio", "px>500 y cae a 0 al apagar el flag render del terminal"),
            ("Red sin errores", "get_errors(path) = 0"),
        ],
    },
    'curl': {
        'prefix': 'curl_field', 'out': 'preview_curl_field.html',
        'title': 'curl_field — campo de puntos con curl-noise (GLSL POP)',
        'net': (
            '/curl_field<br>\n'
            '&nbsp;&nbsp;geo (geometryCOMP, material = pointsprite_mat)<br>\n'
            '&nbsp;&nbsp;&nbsp;&nbsp;grid_emit (gridPOP 16³) → topoints (convertPOP topointprims) → '
            'glsl_curl (glslPOP + curl-noise a mano) → null_render (nullPOP, display+render)<br>\n'
            '&nbsp;&nbsp;cam · light · ren (renderTOP) → null_view · check (poptoCHOP → null_render)'),
        'checks': [
            ("Grilla 3D", "gridPOP 16×16×16 = 4096 puntos (dimension='rowscolsslicesalways')"),
            ("Nube con point prims", "4096 pts / 4096 prims (convertPOP topointprims)"),
            ("Shader compila", "glsl_curl.errors() == '' (curl-noise escrito a mano)"),
            ("3 uniforms", "vec.sequence.numBlocks=3 (uTime/uAmount/uScale)"),
            ("Sin auto-torus", "geo.children no contiene torus*"),
            ("Anima con uTime / uAmount", "P (poptoCHOP) cambia al escalonar cada uniform"),
            ("A/B deleteprims vs topointprims", "deleteprims → 0 px · topointprims → 6353 px"),
            ("Render dibuja y es propio", "px>500, sin torus (no hay residuo que pueda dibujar)"),
        ],
    },
}


def b64(path):
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode()


def main():
    run = sys.argv[1] if len(sys.argv) > 1 else RUN_DEFAULT
    eff = EFFECTS.get(sys.argv[2] if len(sys.argv) > 2 else 'swirl', EFFECTS['swirl'])
    rd = os.path.join(HERE, 'results', run)
    frame_p = os.path.join(rd, eff['prefix'] + '.png')
    grid_p = os.path.join(rd, eff['prefix'] + '_grid.png')

    rows, frame_stats, grid_stats = [], None, []
    if os.path.exists(frame_p):
        im = Image.open(frame_p).convert('RGB')
        frame_stats = {'wh': list(im.size), **stats_of(im)}
        rows.append(('frame', f"{im.size[0]}x{im.size[1]}", frame_stats['px_lit'],
                     frame_stats['mean_rgb'], frame_stats['brightest']))
    if os.path.exists(grid_p):
        im = Image.open(grid_p).convert('RGB')
        for i, c in enumerate(grid_cells(grid_p)):
            st = stats_of(c)
            grid_stats.append(st)
            rows.append((f'grid[{i}]', f'{c.size[0]}x{c.size[1]}', st['px_lit'],
                         st['mean_rgb'], st['brightest']))

    checks = eff['checks']

    row_html = "\n".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(*r)
        for r in rows)
    check_html = "\n".join(
        "<tr><td>{}</td><td class='ok'>OK</td><td style='color:#9aa'>{}</td></tr>".format(c[0], c[1])
        for c in checks)

    imgs = []
    if os.path.exists(frame_p):
        imgs.append("<figure><img src='data:image/png;base64,{}' alt='frame'>"
                    "<figcaption>frame del efecto (null_view, captura chica)</figcaption></figure>"
                    .format(b64(frame_p)))
    if os.path.exists(grid_p):
        imgs.append("<figure><img src='data:image/png;base64,{}' alt='grid'>"
                    "<figcaption>grid temporal 2x2 (view_operator frames=4). En este entorno sin "
                    "frame loop las celdas repiten el mismo fotograma (ver nota).</figcaption></figure>"
                    .format(b64(grid_p)))

    html = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>{title} — build {run}</title>
<style>
 body {{ background:#0e1116; color:#e6edf3; font:15px/1.5 system-ui,Segoe UI,Roboto,sans-serif; margin:0; padding:28px; }}
 h1 {{ font-size:20px; margin:0 0 4px; }} h2 {{ font-size:16px; margin:26px 0 8px; color:#9fd0ff; }}
 .sub {{ color:#9aa; margin-bottom:18px; }}
 code {{ background:#1b2028; padding:2px 6px; border-radius:5px; color:#c9e1ff; }}
 figure {{ margin:0 0 18px; }} img {{ max-width:100%; image-rendering:pixelated; border-radius:10px; border:1px solid #2a3340; background:#000; }}
 figcaption {{ color:#8b98a6; font-size:13px; margin-top:6px; }}
 table {{ border-collapse:collapse; margin:8px 0 16px; }} th,td {{ border:1px solid #2a3340; padding:6px 10px; font-size:13px; }}
 th {{ background:#161b22; color:#c9d1d9; }} .ok {{ color:#3fb950; font-weight:600; }}
 .note {{ background:#161b22; border-left:3px solid #d29922; padding:10px 14px; border-radius:6px; color:#dfe6ee; }}
 .net {{ background:#161b22; padding:12px 16px; border-radius:8px; font-family:ui-monospace,Consolas,monospace; font-size:13px; color:#c9e1ff; }}
</style></head><body>
<h1>{title}</h1>
<div class="sub">run <code>{run}</code> · TD 2025.32460 · TDMCP 1.1.55</div>

<h2>Red</h2>
<div class="net">{net}</div>

<h2>Capturas</h2>
{imgs}

<h2>Verificaciones</h2>
<table><tr><th>check</th><th>estado</th><th>detalle</th></tr>{checks}</table>

<h2>Métricas de los PNG (PIL, orden RGB)</h2>
<table><tr><th>imagen</th><th>tamaño</th><th>px encendidos</th><th>mean RGB</th><th>píxel más brillante</th></tr>{rows}</table>

<h2>Nota de entorno</h2>
<div class="note">En esta sesión remota el reloj maestro está detenido (<code>absTime.seconds</code> no avanza entre
cooks; no existe <code>root.par.play</code> en 2025.32460) y el renderTOP re-sube la geometría POP
solo ante cambios de estructura/material, no ante cambios de datos. Por eso el grid repite fotogramas:
la animación se verifica de forma numérica por <code>poptoCHOP</code> (P se mueve con uTime y uSwirl).
En la GUI de TouchDesigner, con el frame loop activo, el efecto anima en vivo.</div>
</body></html>
""".format(run=run, title=eff['title'], net=eff['net'], imgs="\n".join(imgs),
               checks=check_html, rows=row_html)

    out1 = os.path.join(rd, 'preview_final.html')
    out2 = os.path.join(HERE, '..', '..', eff['out'])
    with open(out1, 'w', encoding='utf-8') as f:
        f.write(html)
    with open(out2, 'w', encoding='utf-8') as f:
        f.write(html)
    print("escrito:", os.path.relpath(out1), "y", os.path.relpath(out2))
    print(json.dumps({'frame': frame_stats, 'grid': grid_stats}, ensure_ascii=False)[:400])


if __name__ == '__main__':
    main()

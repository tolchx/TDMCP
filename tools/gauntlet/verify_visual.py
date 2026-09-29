"""verify_visual.py — decodifica los PNG del build y reporta metricas reales.

Uso: python verify_visual.py [run_id]

Usa PIL (un decoder casero fallaba en los filtros Sub/Paeth y daba colores
falsos). Verifica:
  * el frame tiene contenido (px encendidos > 100) y reporta color medio y
    pixel mas brillante;
  * el grid temporal: en este entorno sin frame loop las celdas suelen repetir
    el mismo fotograma, asi que se reporta INFO, no fallo (la animacion se
    verifica por poptoCHOP; ver docs/particle-fx-2026-09-29.md).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gauntlet_client import Gauntlet  # noqa: E402
from td_probe import grid_cells, stats_of  # noqa: E402

from PIL import Image  # noqa: E402


def main():
    g = Gauntlet('verify-visual')
    run = sys.argv[1] if len(sys.argv) > 1 else '20260929-010805'
    rd = os.path.join(HERE, 'results', run)
    out = {'run': run}

    fp = os.path.join(rd, 'particle_fx.png')
    if os.path.exists(fp):
        im = Image.open(fp).convert('RGB')
        st = stats_of(im)
        out['frame'] = {'wh': list(im.size), **st}
        print('PNG frame:', json.dumps(out['frame'], ensure_ascii=False))
        g.check('frame con contenido real', st['px_lit'] > 100, json.dumps(st)[:200])

    gp = os.path.join(rd, 'particle_fx_grid.png')
    if os.path.exists(gp):
        im = Image.open(gp).convert('RGB')
        out['grid_wh'] = list(im.size)
        cells = grid_cells(gp)
        subs = [stats_of(c) for c in cells]
        out['grid_subs'] = subs
        sigs = {json.dumps(s, sort_keys=True) for s in subs}
        out['grid_unicos'] = len(sigs)
        print('PNG grid:', json.dumps({'wh': out['grid_wh'], 'subs': subs}, ensure_ascii=False))
        print('    INFO  grid: %d sub-frames distintos de %d (sin frame loop las celdas '
              'suelen repetirse; la animacion se verifica por poptoCHOP)'
              % (len(sigs), len(subs)))
        g.check('grid capturado con contenido', all(s['px_lit'] > 100 for s in subs),
                json.dumps(subs)[:200])

    s = g.summary()
    print('RESUMEN:', json.dumps({'ok': s['ok'], 'failures': s['failures']}, ensure_ascii=False)[:200])
    sys.exit(0 if s['ok'] else 1)


if __name__ == '__main__':
    main()

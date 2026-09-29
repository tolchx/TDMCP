"""td_probe.py — el ÚNICO lugar para asentar, releer y medir un render en TD.

Cada pieza encapsula un contrato verificado (`knowledge/contracts/VERIFIED_CONTRACTS.md`):

  * `chain_source(root)` — fuente para `execute_code` con `settle()`, `px()` y
    `render_is_ours()`, atadas a una red. Es la **única** forma de asentar (C1/cook_lag),
    de contar píxeles y de probar que el render es del chain (C2/autotorus_masks_render).
  * `set_and_verify()`  — escribir un par y RELEERLO (C4: `set_parameters` puede no aplicarlo).
  * `stats_of()` / `png_stats()` / `grid_cells()` — métricas de PNG con PIL (C1/png_use_pil).
  * `selftest_render_ownership()` — autoprueba de la guardia: monta el auto-torus dibujando
    y exige que la guardia **falle**; sin él, que pase.

Los scripts de build importan de acá en vez de copiar sus propias versiones.
"""
from __future__ import annotations

# ── lo que se inyecta en un `execute_code` ───────────────────────────────────
_CHAIN_TEMPLATE = '''
def settle(n=4, pause=0.04):
    """Asienta la red {root} (cook lag >= 1 en DAT/uniforms). Releé DESPUÉS de esto."""
    import time as _t
    for _ in range(n):
        for o in (op('{root}/geo'), op('{root}/ren')):
            try:
                o.cook(force=True)
            except Exception:
                pass
        _t.sleep(pause)


def px():
    """Píxeles encendidos del renderTOP de la red {root} (asentá antes)."""
    arr = op('{root}/ren').numpyArray()
    return int((arr[:, :, :3].max(2) > 0.02).sum())


def render_is_ours(term):
    """¿Los píxeles del render son del chain de la red {root}?

    True SOLO si apagar el flag `render` del terminal `term` lleva el render a 0. Si otro
    nodo dibuja (p.ej. el `torus1` que auto-crea el geometryCOMP) devuelve False — ese es
    el falso positivo que mantuvo una verificación falsa durante sesiones.
    Devuelve (ok, px_con_terminal, px_sin_terminal).
    """
    settle()
    on = px()
    term.render = False
    settle()
    off = px()
    term.render = True
    settle()
    return (on > 0 and off == 0), on, off
'''


def chain_source(root: str) -> str:
    """Fuente de `settle()`, `px()` y `render_is_ours()` para la red `root`."""
    return _CHAIN_TEMPLATE.format(root=root)


# ── escribir y releer (contrato C4) ─────────────────────────────────────────
def set_and_verify(g, path: str, values: dict, label: str = ""):
    """Escribe `values` por `set_parameters` y los RELEE de TD.

    Devuelve `(bad, got)`: `bad` = {par: (pedido, leído)} de los que NO se aplicaron
    (la tool puede responder ok sin aplicarlos).
    """
    g.call_ok("set_parameters", {"path": path, "values": values}, note=label)
    code = ("import json\no = op(%r)\nv = {}\nfor n in %r:\n"
            "    try:\n        v[n] = o.par[n].eval()\n"
            "    except Exception:\n        v[n] = 'ERR'\n"
            "print('<<JSON>>' + json.dumps(v))\n") % (path, list(values))
    ok, got = g.exec_code(code)
    got = got if ok else {}
    bad = {}
    for k, want in values.items():
        have = got.get(k, "<missing>")
        if isinstance(want, bool):
            same = bool(have) == want
        else:
            try:
                same = abs(float(have) - float(want)) <= 1e-6
            except (TypeError, ValueError):
                same = str(have) == str(want)
        if not same:
            bad[k] = (want, have)
    return bad, got


# ── métricas de PNG con PIL (contrato png_use_pil) ──────────────────────────
def stats_of(img, threshold: int = 5) -> dict:
    """img: PIL.Image RGB → px encendidos, color medio, bbox y píxel más brillante."""
    px = img.load()
    w, h = img.size
    n = sr = sg = sb = 0
    best, bv = None, -1
    x0 = y0 = 10 ** 9
    x1 = y1 = -1
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            v = max(r, g, b)
            if v > bv:
                bv, best = v, [r, g, b]
            if v > threshold:
                n += 1
                sr += r
                sg += g
                sb += b
                x0, y0 = min(x0, x), min(y0, y)
                x1, y1 = max(x1, x), max(y1, y)
    if not n:
        return {"px_lit": 0, "mean_rgb": [0, 0, 0], "bbox": None, "brightest": best}
    return {"px_lit": n,
            "mean_rgb": [round(sr / n / 255, 3), round(sg / n / 255, 3), round(sb / n / 255, 3)],
            "bbox": [x0, y0, x1, y1], "brightest": best}


def png_stats(path: str, threshold: int = 5) -> dict:
    """Métricas de un PNG de `view_operator` (PIL), con su tamaño."""
    from PIL import Image  # import perezoso: el resto del módulo no depende de PIL

    im = Image.open(path).convert("RGB")
    return {"wh": list(im.size), **stats_of(im, threshold)}


def grid_cells(path: str, n: int = 4):
    """`view_operator frames=4`: tira 1×n si la imagen es muy ancha, si no grid 2×2."""
    from PIL import Image

    im = Image.open(path).convert("RGB")
    w, h = im.size
    if w / h > 2.5:
        return [im.crop((i * w // n, 0, (i + 1) * w // n, h)) for i in range(n)]
    cw, ch = w // 2, h // 2
    return [im.crop((0, 0, cw, ch)), im.crop((cw, 0, w, ch)),
            im.crop((0, ch, cw, h)), im.crop((cw, ch, w, h))]


# ── autoprueba de la guardia de propiedad del render ────────────────────────
def selftest_render_ownership(g, root: str = "/guard_selftest"):
    """Prueba que `render_is_ours` puede FALLAR.

    Monta una escena donde el `torus1` auto-creado dibuja además de la cadena de puntos y
    exige que la guardia devuelva False (hay píxeles, pero no son del terminal); borrado el
    torus, exige True. Borra el scratch. Devuelve (ok, evidencia).
    """
    code = chain_source(root) + """
import json
root = %r
old = op(root)
if old:
    old.destroy()
c = op('/').create(baseCOMP, 'guard_selftest')
geo = c.create(geometryCOMP, 'geo')                 # auto-crea torus1 (y dibuja)
sph = geo.create(spherePOP, 'sphere_emit')
conv = geo.create(convertPOP, 'topoints')
conv.par.convert = 'topointprims'
sph.outputConnectors[0].connect(conv)
term = geo.create(nullPOP, 'null_render')
conv.outputConnectors[0].connect(term)
term.display = True
term.render = True
geo.par.material = geo.create(pointspriteMAT, 'pointsprite_mat')
cam = c.create(cameraCOMP, 'cam')
cam.par.tz = 5.0
ren = c.create(renderTOP, 'ren')
ren.par.camera = cam
ren.par.geometry = geo
ren.par.resolutionw = 320
ren.par.resolutionh = 240
res = {}
res['with_torus'] = list(render_is_ours(term))
for n in [x.name for x in geo.children if x.name.lower().startswith('torus')]:
    geo.op(n).destroy()
res['without_torus'] = list(render_is_ours(term))
op(root).destroy()
print('<<JSON>>' + json.dumps(res))
""" % root
    ok, d = g.exec_code(code)
    with_t, without_t = (d or {}).get("with_torus"), (d or {}).get("without_torus")
    # con el torus hay píxeles pero la guardia dice que NO son nuestros; sin él, son nuestros.
    good = bool(ok and with_t and without_t and with_t[1] > 0 and not with_t[0] and without_t[0])
    return good, d

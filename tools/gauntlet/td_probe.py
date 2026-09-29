"""td_probe.py — los helpers del HOST para asentar, releer y medir un render en TD.

Cada pieza encapsula un contrato verificado (`knowledge/contracts/VERIFIED_CONTRACTS.md`):

  * `chain_source(root)` — serializa el programa inyectado (`td_chain.py`, dueño de
    `settle()` / `px()` / `render_is_ours()`) con `ROOT` fijado a una red. Es la **única**
    forma de asentar (C1/cook_lag), de contar píxeles y de probar que el render es del
    chain (C2/autotorus_masks_render).
  * `set_and_verify()`  — escribir un par y RELEERLO (C4: `set_parameters` puede no aplicarlo).
  * `stats_of()` / `png_stats()` / `grid_cells()` — métricas de PNG con PIL (C1/png_use_pil).
  * `selftest_render_ownership()` — autoprueba contra TD: monta el auto-torus dibujando
    y exige que la guardia **falle**; sin él, que pase.

La parte inyectada se prueba sin TD en `_selftest_local()` (`python td_probe.py`).
Los scripts de build importan de acá en vez de copiar sus propias versiones.
"""
from __future__ import annotations

import contextlib
import inspect
import io
import json
from types import SimpleNamespace

import td_chain
from gauntlet_client import MARK  # el contrato del marcador es del cliente


# ── host → TD: serializar el programa inyectado ─────────────────────────────
def chain_source(root: str) -> str:
    """Fuente para `execute_code`: `td_chain` con `ROOT` fijado a `root`.

    El `repr` mantiene el literal válido incluso con comillas en `root`, y se compila
    antes de mandarlo: un `td_chain.py` roto falla acá y no dentro del sandbox de TD.
    """
    src = "ROOT = %r\n\n%s" % (root, inspect.getsource(td_chain))
    compile(src, "<td_chain:%s>" % root, "exec")
    return src


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
    # UN solo print al final: `exec_code` parsea lo que sigue al PRIMER marcador.
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
    """Prueba CONTRA TD que `render_is_ours` puede FALLAR.

    Monta una escena donde el `torus1` auto-creado dibuja además de la cadena de puntos y
    exige que la guardia devuelva False (hay píxeles, pero no son del terminal); borrado el
    torus, exige True. Además fuerza un error de `px()` con el terminal apagado y exige que
    el flag `render` vuelva a su valor. Borra el scratch. Devuelve (ok, evidencia).
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
# camino de error: px() explota MIENTRAS el terminal esta apagado -> el flag debe volver
before = bool(term.render)
calls = {'n': 0}
real_px = px
def boom():
    calls['n'] += 1
    if calls['n'] == 2:
        raise RuntimeError('sabotaje de px')
    return real_px()
px = boom
raised = False
try:
    render_is_ours(term)
except RuntimeError:
    raised = True
px = real_px
res['restored_on_error'] = [raised, bool(term.render) == before]
for n in [x.name for x in geo.children if x.name.lower().startswith('torus')]:
    geo.op(n).destroy()
res['without_torus'] = list(render_is_ours(term))
op(root).destroy()
print('<<JSON>>' + json.dumps(res))
""" % root
    ok, d = g.exec_code(code)
    with_t = (d or {}).get("with_torus")
    without_t = (d or {}).get("without_torus")
    restored = (d or {}).get("restored_on_error")
    # con el torus hay píxeles pero la guardia dice que NO son nuestros; sin él, son nuestros;
    # y un error en el medio igual deja el flag `render` como estaba.
    good = bool(ok and with_t and without_t and restored
                and with_t[1] > 0 and not with_t[0] and without_t[0]
                and restored[0] and restored[1])
    return good, d


def _selftest_local() -> int:
    """Chequeos sin TD: el programa inyectado se ejercita como código, no como texto."""
    results = []

    src = chain_source("/net")
    results.append(("chain_source fija ROOT en el programa inyectado",
                    "ROOT = '/net'" in src and "def render_is_ours" in src))
    results.append(("chain_source mantiene válido un root con comilla",
                    chain_source("a'b").startswith('ROOT = "a\'b"')))

    # `set_and_verify` de punta a punta sin TD, con el cliente de mentira que parsea la
    # salida igual que `exec_code`: un read-back que imprime de más tiene que caer acá.
    vals = {"radx": 1.5, "rady": 1.5}

    class _Op:
        par = {k: SimpleNamespace(eval=lambda v=v: v) for k, v in vals.items()}

    class _ReadG:
        def call_ok(self, *a, **k):
            pass

        def exec_code(self, code):
            """Como `Gauntlet.exec_code`: parsea lo que sigue al PRIMER marcador."""
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                exec(code, {"op": lambda p: _Op()})
            out = buf.getvalue()
            if MARK not in out:
                return False, {}
            try:
                return True, json.loads(out.split(MARK, 1)[1].strip())
            except ValueError:
                return False, {}

    bad, got = set_and_verify(_ReadG(), "/x", vals)
    results.append(("set_and_verify relee lo escrito (un solo marcador)",
                    got == vals and not bad))

    real_px, real_settle = td_chain.px, td_chain.settle
    td_chain.settle = lambda *a, **k: None          # sin TD no hay nada que asentar
    try:
        for name, marks, want_ok in (("apagar el terminal lleva los px a 0", (5, 0), True),
                                     ("los px sobreviven al apagado (otro nodo dibuja)", (5, 5), False)):
            seq = iter(marks)
            td_chain.px = lambda: next(seq)
            term = SimpleNamespace(render=True)
            ok, _on, _off = td_chain.render_is_ours(term)
            results.append(("render_is_ours: %s" % name, ok == want_ok and term.render))

        # px() explota con el terminal ya apagado -> el flag tiene que volver a su valor
        calls = {"n": 0}

        def boom():
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("sabotaje de px")
            return 5

        td_chain.px = boom
        term = SimpleNamespace(render=True)
        raised = False
        try:
            td_chain.render_is_ours(term)
        except RuntimeError:
            raised = True
        results.append(("render_is_ours restaura el flag si px() lanza",
                        raised and bool(term.render)))
    finally:
        td_chain.px, td_chain.settle = real_px, real_settle

    fails = [name for name, ok in results if not ok]
    for name in fails:
        print("FAIL ", name)
    print("td_probe: %d/%d chequeos locales OK" % (len(results) - len(fails), len(results)))
    return 1 if fails else 0


if __name__ == "__main__":
    import sys

    sys.exit(_selftest_local())

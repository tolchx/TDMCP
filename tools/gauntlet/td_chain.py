"""td_chain.py — el programa que se INYECTA en TouchDesigner.

`td_probe.chain_source(root)` lo serializa y le antepone `ROOT = ...`; ese texto es lo
que viaja por `execute_code`. Es código, no una plantilla: el módulo se importa, se
compila y se puede ejercitar en el host con un `op`/`px` de mentira (los `op()` viven
dentro de las funciones, así que importarlo NO toca TD).

`ROOT` a propósito NO se declara acá: lo fija `chain_source()` al inyectar, y así el
nombre tiene un solo dueño (el host) y no hay línea que reescribir.
"""


def _render_top():
    """El renderTOP de la red ROOT, buscado por TIPO: el nombre del nodo no es contrato."""
    net = op(ROOT)
    if net is None:
        return None
    for c in net.children:
        if c.OPType == 'renderTOP':
            return c
    return None


def settle(n=4, pause=0.04):
    """Asienta la red ROOT (cook lag >= 1 en DAT/uniforms). Releé DESPUÉS de esto."""
    import time as _t
    for _ in range(n):
        for o in (op(ROOT + '/geo'), _render_top()):
            try:
                o.cook(force=True)
            except Exception:
                pass
        _t.sleep(pause)


def px():
    """Píxeles encendidos del renderTOP de la red ROOT (asentá antes).

    Falla con un mensaje claro si no hay qué medir: `render_is_ours` se apoya en
    esto para NEGARSE a decir "es nuestro" cuando el render (o la red) no existe.
    """
    if op(ROOT) is None:
        raise RuntimeError("no existe la red %s" % ROOT)
    ren = _render_top()
    if ren is None:
        raise RuntimeError("la red %s no tiene un renderTOP" % ROOT)
    arr = ren.numpyArray()
    return int((arr[:, :, :3].max(2) > 0.02).sum())


def ownership_selftest(root='/guard_selftest'):
    """Prueba CONTRA TD que `render_is_ours` puede FALLAR (la usa `td_probe`).

    Monta un scratch donde el `torus1` auto-creado dibuja ADEMÁS de la cadena de puntos: con el
    torus, la guardia tiene que decir que los píxeles NO son del terminal; borrado el torus, que sí.
    Fuerza además un error de `px()` con el terminal apagado y exige que el flag `render` vuelva a
    su valor. Deja el scratch borrado. Devuelve el dict de evidencia.
    """
    global px                      # el sabotaje tiene que verlo `render_is_ours`

    if op(root):
        op(root).destroy()
    parent, _, name = root.rpartition('/')
    c = op(parent or '/').create(baseCOMP, name)
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

    res = {'with_torus': list(render_is_ours(term))}
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
    return res


def render_is_ours(term):
    """¿Los píxeles del render son del chain de la red ROOT?

    True SOLO si apagar el flag `render` del terminal `term` lleva el render a 0. Si otro
    nodo dibuja (p.ej. el `torus1` que auto-crea el geometryCOMP) devuelve False — ese es
    el falso positivo que mantuvo una verificación falsa durante sesiones.
    Devuelve (ok, px_con_terminal, px_sin_terminal).
    """
    settle()
    on = px()
    was = bool(term.render)
    try:
        term.render = False
        settle()
        off = px()
    finally:
        # el terminal se toca sobre la RED VIVA: se restaura pase lo que pase (aunque px()
        # explote), o una corrida fallida deja la red con el render apagado.
        term.render = was
        settle()
    return (on > 0 and off == 0), on, off

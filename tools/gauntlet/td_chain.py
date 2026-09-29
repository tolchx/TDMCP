"""td_chain.py — el programa que se INYECTA en TouchDesigner.

`td_probe.chain_source(root)` lo serializa y le antepone `ROOT = ...`; ese texto es lo
que viaja por `execute_code`. Es código, no una plantilla: el módulo se importa, se
compila y se puede ejercitar en el host con un `op`/`px` de mentira (los `op()` viven
dentro de las funciones, así que importarlo NO toca TD).

`ROOT` a propósito NO se declara acá: lo fija `chain_source()` al inyectar, y así el
nombre tiene un solo dueño (el host) y no hay línea que reescribir.
"""


def settle(n=4, pause=0.04):
    """Asienta la red ROOT (cook lag >= 1 en DAT/uniforms). Releé DESPUÉS de esto."""
    import time as _t
    for _ in range(n):
        for o in (op(ROOT + '/geo'), op(ROOT + '/ren')):
            try:
                o.cook(force=True)
            except Exception:
                pass
        _t.sleep(pause)


def px():
    """Píxeles encendidos del renderTOP de la red ROOT (asentá antes)."""
    arr = op(ROOT + '/ren').numpyArray()
    return int((arr[:, :, :3].max(2) > 0.02).sum())


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

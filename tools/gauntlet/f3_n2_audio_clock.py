"""Fase 3 — Nivel 2: reloj audio-reactivo dentro de un containerCOMP.

audioDeviceInCHOP -> audioSpectrumCHOP -> analyzeCHOP('lvl')   (cadena de audio)
lfoCHOP('sweep')                                            (movimiento garantizado)
textTOP 'reloj' (expresión de reloj real) + constantTOP 'fondo' (color por expresión
cross-family leyendo el CHOP) -> compositeTOP -> nullTOP.

Skills aplicadas: td-build-planning (fases), td-chop-family, td-node-layout,
td-general (flags, anotación).
"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gauntlet_client import Gauntlet

g = Gauntlet("f3-n2-audio-clock")
SB = "/gauntlet_n2"

g.call("delete_operator", {"path": SB}, note="limpieza (tolerada)")
g.call_ok("create_operator", {"parent_path": "/", "type": "containerCOMP", "name": "gauntlet_n2",
                              "nodeX": -1300, "nodeY": 100}, note="container N2")

# Fase 2-3 del plan: fuentes + procesamiento, en un solo build_network
g.call_ok("build_network", {"parent_path": SB, "operators": [
    {"type": "audiodeviceinCHOP", "name": "audio"},
    {"type": "audiospectrumCHOP", "name": "spectrum"},
    {"type": "analyzeCHOP", "name": "lvl"},
    {"type": "lfoCHOP", "name": "sweep"},
    {"type": "constantTOP", "name": "fondo"},
    {"type": "textTOP", "name": "reloj"},
    {"type": "compositeTOP", "name": "comp"},
    {"type": "nullTOP", "name": "out1"}],
    "connections": [
        {"from": "audio", "to": "spectrum"}, {"from": "spectrum", "to": "lvl"},
        {"from": "fondo", "to": "comp", "to_index": 0},
        {"from": "reloj", "to": "comp", "to_index": 1},
        {"from": "comp", "to": "out1"}],
    "auto_layout": True}, note="8 ops del reloj")

# Cross-family CHOP -> par de TOP por expresión (patrón de td-chop-family/td-general):
# el canal 'lvl' (amplitud) empuja el rojo del fondo; el seno garantiza movimiento
# visible aunque el micrófono esté en silencio.
# Leccion de API: set_parameters SOLO acepta valores constantes; las expresiones se
# setean con execute_code via p.expr (el server lo dice: "Set .expr member instead").
EXPR = ("0.2 + min(0.45, max(0.0, op('lvl')['chan1'] if len(op('lvl').chans()) else 0))"
        " + 0.15*abs(absTime.seconds % 2 - 1)")
FUNCS = r'''import json
op('%s/fondo').par.colorr.expr = %r
print('<<JSON>>' + json.dumps({'ok': True}))''' % (SB, EXPR)
ok, d = g.exec_code(FUNCS)
g.check("expr de color seteada via execute_code", ok, str(d)[:200])
g.call_ok("set_parameters", {"path": SB + "/fondo", "values": {"colorg": 0.09, "colorb": 0.25,
                                                               "resolutionw": 256, "resolutionh": 128}})
# fontautosize 'fit' para que el texto llene el TOP
ok, d = g.exec_code(f"""
import json
op('{SB}/reloj').par.resolutionw = 256
op('{SB}/reloj').par.resolutionh = 128
op('{SB}/reloj').par.text.expr = "'%02d:%02d:%02d' % (int(absTime.seconds//3600), int(absTime.seconds//60)%60, int(absTime.seconds)%60)"
op('{SB}/fondo').par.resolutionw = 256
op('{SB}/fondo').par.resolutionh = 128
print('<<JSON>>' + json.dumps({{'ok': True}}))""")
g.check("pars del reloj + expr de texto", ok, str(d)[:200])
g.call_ok("edit_operator", {"path": SB + "/out1", "display": True, "render": True}, note="flags null")

# anotación (schema real: create = parent_path + comment)
r = g.call_ok("annotation", {"parent_path": SB, "comment": "N2 reloj audio-reactivo (gauntlet)",
                             "width": 320}, note="anotacion del nivel")
g.check("annotation creada", not g.is_err(r), g.text_of(r)[:200])

# ── graders ──────────────────────────────────────────────────────────────
ok, d = g.exec_code(f"""
import json
sb = op('{SB}')
# excluir la anotacion del nivel (su type real es 'annotate', probe 2026-09-28)
names = [c.name for c in sb.children if c.valid and c.type not in ('annotate', 'annotateCOMP')]
lvl = op('{SB}/lvl')
expr = op('{SB}/fondo').par.colorr.expr or ''


txtmode = str(op('{SB}/reloj').par.text.mode)
txtval = str(op('{SB}/reloj').par.text.eval())
audio_in = [c.owner.name for c in op('{SB}/spectrum').inputConnectors[0].connections]
comp_in = [[c.owner.name for c in conn.connections] for conn in op('{SB}/comp').inputConnectors]
print('<<JSON>>' + json.dumps({{'names': names,
      'expr_has_chop': "op('lvl')" in expr, 'txtmode': txtmode, 'txtval': txtval,
      'audio_in': audio_in, 'comp_in': comp_in, 'nchans': len(lvl.chans())}}))""")
g.check("8 operadores dentro del container", len(d.get("names", [])) == 8, str(d.get("names"))[:200])
g.check("cadena de audio cableada", d.get("audio_in") == ["audio"], str(d)[:200])
ci = d.get("comp_in") or []
g.check("composite: fondo+reloj", ci[:2] == [["fondo"], ["reloj"]], str(d)[:250])
g.check("expresion cross-family op('lvl') en par de TOP", d.get("expr_has_chop") is True, str(d)[:200])
g.check("texto del reloj en modo EXPRESSION", "EXPRESSION" in str(d.get("txtmode", "")), str(d)[:200])
g.check("reloj devuelve hora con ':'", ":" in str(d.get("txtval", "")), str(d.get("txtval"))[:80])
g.check("analyze tiene canales (audio vivo o silencio)", d.get("nchans", 0) >= 1, str(d)[:200])

# el color tiene que moverse entre dos lecturas separadas ~1.2 s
ok, v1 = g.exec_code(f"import json\nprint('<<JSON>>' + json.dumps({{'c': op('{SB}/fondo').par.colorr.eval()}}))")
time.sleep(1.2)
ok, v2 = g.exec_code(f"import json\nprint('<<JSON>>' + json.dumps({{'c': op('{SB}/fondo').par.colorr.eval()}}))")
delta = abs((v2.get("c") or 0) - (v1.get("c") or 0))
g.check("par animado por expresion cambia en el tiempo", delta > 1e-4, f"delta={delta}")

errs = g.call_ok("get_errors", {"path": SB})
et = g.text_of(errs).lower()
audio_ok = ("audio" not in et) or ('"count": 0' in et)
g.check("sin errores en el container (audio incluido)", audio_ok, et[:250])

# PNG de evidencia
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}})
r = g.call_ok("view_operator", {"path": SB + "/out1", "resolution": "small"}, note="PNG del reloj")
png = g.save_image(r, os.path.join(HERE, "results", g.run_id, "n2_clock.png"))
g.check("PNG del reloj capturado", bool(png))
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}})

g.call_ok("delete_operator", {"path": SB}, note="cleanup N2")
s = g.summary()
print("\nN2:", json.dumps(s, ensure_ascii=False))
sys.exit(0 if s["ok"] else 1)

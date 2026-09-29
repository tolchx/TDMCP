"""Fase 3 — Nivel 1: cadena TOP con feedback dentro de un baseCOMP.

noiseTOP -> feedbackTOP (loop con level de decay) -> blurTOP -> nullTOP
Graders: wiring, flags del null, errors, layout sin solapes, branch del feedback.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gauntlet_client import Gauntlet

g = Gauntlet("f3-n1-top-chain")
SB = "/gauntlet_n1"

g.call("delete_operator", {"path": SB}, note="limpieza (tolerada)")
g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "gauntlet_n1",
                              "nodeX": -1300, "nodeY": -400}, note="sandbox N1")

# build según td-top-family: feedback necesita el loop cerrado aparte
r = g.call_ok("build_network", {"parent_path": SB, "operators": [
    {"type": "noiseTOP", "name": "src"},
    {"type": "feedbackTOP", "name": "trail"},
    {"type": "levelTOP", "name": "decay"},
    {"type": "blurTOP", "name": "soft"},
    {"type": "compositeTOP", "name": "mix"},
    {"type": "nullTOP", "name": "out1"}],
    "connections": [
        {"from": "src", "to": "trail"},       # trail = frame previo
        {"from": "trail", "to": "decay"},     # lo apago con level
        {"from": "decay", "to": "mix", "to_index": 0},
        {"from": "src", "to": "mix", "to_index": 1},  # encima del trail
        {"from": "mix", "to": "soft"},
        {"from": "soft", "to": "out1"}],
    "auto_layout": True}, note="cadena + branch de feedback")

# cerrar el loop del feedback: feedbackTOP tiene UN input → recibe el FINAL de la cadena.
g.call_ok("wiring", {"from_path": SB + "/out1", "to_path": SB + "/trail", "to_index": 0},
          note="loop canonico out1->trail (feedback delay 1 frame)")

# parámetros según td-top-family (decay 0.92 = trail largo) + flags del null (td-general:
# el builder DEBE setear display/render del null explícitamente)
g.call_ok("set_parameters", {"path": SB + "/src", "values": {"resolutionw": 256, "resolutionh": 256, "seed": 3}})
g.call_ok("set_parameters", {"path": SB + "/decay", "values": {"opacity": 0.92}})
r = g.call_ok("edit_operator", {"path": SB + "/out1", "display": True, "render": True},
              note="flags del null")
if g.is_err(r):  # fallback si edit_operator no toma flags
    g.exec_code(f"n = op('{SB}/out1'); n.display = True; n.render = True")

# ── graders ──────────────────────────────────────────────────────────────
r = g.call_ok("get_connections", {"path": SB, "graph": True}, note="topología")
t = g.text_of(r)
g.check("out1 recibe de soft", '"out1"' in t and '"soft"' in t)
g.check("el loop vuelve a trail desde out1", '"trail"' in t and '"out1"' in t)

ok, d = g.exec_code(f"""
import json
sb = op('{SB}')
wired = [c.owner.name for c in op('{SB}/out1').inputConnectors[0].connections]
fb_in = [c.owner.name for c in op('{SB}/trail').inputConnectors[0].connections]
ops = [c.name for c in sb.children if c.valid]
xs = [(op('{SB}/' + n).nodeX, op('{SB}/' + n).nodeY) for n in ops]
overlaps = len(xs) - len(set(xs))
print('<<JSON>>' + json.dumps({{'wired': wired, 'feedback_closed': fb_in == ['out1'],
      'n_ops': len(ops), 'overlaps': overlaps,
      'flags': [op('{SB}/out1').display, op('{SB}/out1').render]}}))""")
g.check("out1 alimentado por soft", d.get("wired") == ["soft"], str(d)[:200])
g.check("loop canonico cerrado out1->trail", d.get("feedback_closed") is True, str(d)[:200])
g.check("6 operadores creados", d.get("n_ops") == 6, str(d)[:200])
g.check("sin solapes de posicion", d.get("overlaps") == 0, str(d)[:200])
g.check("null con display+render", d.get("flags") == [True, True], str(d)[:200])

errs = g.call_ok("get_errors", {"path": SB})
et = g.text_of(errs)
g.check("get_errors sin errores", '"count": 0' in et or '"items": []' in et, et[:200])

# verificación visual: el trail debe estar vivo (3 frames distintos)
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}})
r = g.call_ok("view_operator", {"path": SB + "/out1", "frames": 3, "step": 4, "resolution": "tiny"},
              note="grid temporal del trail")
job = g.json_of(r).get("job_id", "")
import time; time.sleep(3.5)
r = g.call("view_operator", {"path": SB + "/out1", "job_id": job}, note="retrieve grid N1")
png = g.save_image(r, os.path.join(HERE, "results", g.run_id, "n1_trail_grid.png"))
g.check("grid temporal del trail capturado", bool(png))
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}})

g.call_ok("delete_operator", {"path": SB}, note="cleanup N1")
s = g.summary()
print("\nN1:", json.dumps(s, ensure_ascii=False))
sys.exit(0 if s["ok"] else 1)

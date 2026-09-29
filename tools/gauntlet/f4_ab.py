"""Fase 4 — A/B skills ON vs OFF.

Reconstruye las metas de N2 (reloj audio-reactivo) y N3 (módulo+clon) en modo
"naive": SOLO el schema de las 26 tools, sin get_help, sin convenciones de las
skills, sin coreografía. Mismo suite de graders esenciales. Compara contra las
corridas guiadas (results de f3-n2/f3-n3): llamadas, errores de tool, graders.

Esto simula lo que un agente SIN skills puede lograr con el nucleo oficial.
"""
import json, os, sys, time, glob
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gauntlet_client import Gauntlet

def count_jsonl(run_dir, name):
    p = os.path.join(run_dir, name)
    if not os.path.exists(p):
        return {"calls": None, "tool_errors": None}
    calls, errs = 0, 0
    for line in open(p, encoding="utf-8"):
        d = json.loads(line)
        calls += 1
        if d["response"].startswith("*** isError=true ***"):
            errs += 1
    return {"calls": calls, "tool_errors": errs}

# ── NAIVE N2: reloj audio-reactivo (meta igual a la guiada) ─────────────
g = Gauntlet("f4-naive-n2")
SB = "/gauntlet_ab_n2"
g.call("delete_operator", {"path": SB}, note="limpieza (tolerada)")
# Un agente sin skills usa los nombres "oficiales" de la doc web (PascalCase audio)
g.call_ok("create_operator", {"parent_path": "/", "type": "containerCOMP", "name": "gauntlet_ab_n2"})
g.call("create_operator", {"parent_path": SB, "type": "audioDeviceInCHOP", "name": "audio"},
       note="naive: nombre PascalCase")
g.call("create_operator", {"parent_path": SB, "type": "audioSpectrumCHOP", "name": "spectrum"},
       note="naive: nombre PascalCase")
g.call_ok("create_operator", {"parent_path": SB, "type": "analyzeCHOP", "name": "lvl"})
g.call_ok("create_operator", {"parent_path": SB, "type": "constantTOP", "name": "fondo"})
g.call_ok("create_operator", {"parent_path": SB, "type": "textTOP", "name": "reloj"})
g.call_ok("create_operator", {"parent_path": SB, "type": "compositeTOP", "name": "comp"})
g.call_ok("create_operator", {"parent_path": SB, "type": "nullTOP", "name": "out1"})
for a, b in [("audio", "spectrum"), ("spectrum", "lvl"), ("fondo", "comp"),
             ("reloj", "comp"), ("comp", "out1")]:
    g.call("wiring", {"from_path": SB + "/" + a, "to_path": SB + "/" + b})
# naive: adivina pars (no get_help), expresa cross-family por values (no sabe que no)
g.call("set_parameters", {"path": SB + "/fondo", "values": {"color1r": "op('lvl')['chan1']"}})
g.call("set_parameters", {"path": SB + "/reloj", "values": {"fontsize": 36}})
g.call("set_parameters", {"path": SB + "/reloj", "values": {"text": "absTime.datetime.strftime('%H:%M:%S')"}})
g.call("annotation", {"path": SB, "text": "naive clock"})
# graders esenciales (mismos que N2 guiado)
ok, d = g.exec_code(f"""
import json
sb = op('{SB}')
names = [c.name for c in sb.children if c.valid]
r = {{'n_ops': len(names), 'names': sorted(names),
      'comp_in': [[c.owner.name for c in conn.connections] for conn in op('{SB}/comp').inputConnectors],
      'txtmode': str(op('{SB}/reloj').par.text.mode),
      'expr_has_chop': bool(op('{SB}/fondo').par.colorr.expr or op('{SB}/fondo').par.color1r if hasattr(op('{SB}/fondo').par, 'color1r') else op('{SB}/fondo').par.colorr.expr)}}
print('<<JSON>>' + json.dumps(r))""")
g.check("[naive] composite alimentado", (d.get("comp_in") or [[None]])[0] == ["fondo"], str(d)[:200])
g.check("[naive] reloj en modo EXPRESSION (no lo lograra)", "EXPRESSION" in str(d.get("txtmode", "")), str(d)[:150])
g.call("delete_operator", {"path": SB}, note="cleanup naive-n2")
naive_n2 = g.summary()
print("\nNAIVE N2:", json.dumps(naive_n2, ensure_ascii=False))

# ── NAIVE N3: modulo + clon (meta igual a la guiada) ─────────────────────
g = Gauntlet("f4-naive-n3")
SB = "/gauntlet_ab_n3"
g.call("delete_operator", {"path": SB}, note="limpieza (tolerada)")
g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "gauntlet_ab_n3"})
g.call_ok("create_operator", {"parent_path": SB, "type": "inTOP", "name": "in1"})
g.call_ok("create_operator", {"parent_path": SB, "type": "blurTOP", "name": "blur"})
g.call_ok("create_operator", {"parent_path": SB, "type": "nullTOP", "name": "out1"})
g.call("wiring", {"from_path": SB + "/in1", "to_path": SB + "/blur"})
g.call("wiring", {"from_path": SB + "/blur", "to_path": SB + "/out1"})
# naive: custom pars con la shape que parece obvia (action/parameters, no es el schema real)
g.call("edit_custom_parameters", {"path": SB, "action": "add",
       "parameters": [{"name": "Blur", "style": "Float", "defaultValue": 0.5}]})
g.call("set_parameters", {"path": SB, "values": {"parentshortcut": "MyMod"}})
g.call("set_parameters", {"path": SB + "/blur", "values": {"parblur": "parent().par.Blur"}})
# naive: querer clonar sin conocer copy_to -> prueba duplicate (no existe)
g.call("edit_operator", {"path": SB, "duplicate_to": "/", "name": "mymod2"})
# graders esenciales
ok, d = g.exec_code(f"""
import json
sb = op('{SB}')
r = {{'has_custom_blur': bool(sb.customPars),
      'shortcut': sb.par.parentshortcut.eval(),
      'blur_size_expr': bool(op('{SB}/blur').par.size.expr),
      'n_custom': len(sb.customPars)}}
print('<<JSON>>' + json.dumps(r))""")
g.check("[naive] custom pars creados", d.get("n_custom", 0) >= 1, str(d)[:200])
g.check("[naive] blur referenciado al parent (no lo lograra)", d.get("blur_size_expr") is True, str(d)[:150])
g.call("delete_operator", {"path": SB}, note="cleanup naive-n3")
naive_n3 = g.summary()
print("\nNAIVE N3:", json.dumps(naive_n3, ensure_ascii=False))

# ── metricas de las corridas guiadas (de los jsonl de Fase 3) ───────────
runs = sorted(d for d in glob.glob(os.path.join(HERE, "results", "*")) if os.path.isdir(d))
def best_run(prefix):
    for rd in reversed(runs):
        name = [f for f in os.listdir(rd) if f.startswith(prefix) and f.endswith(".jsonl")]
        if name:
            return rd, name[0]
    return None, None
summary = {"naive_n2": naive_n2, "naive_n3": naive_n3}
for tag, prefix in [("guided_n2", "f3-n2-audio-clock"), ("guided_n3", "f3-n3-module-clone")]:
    rd, fn = best_run(prefix)
    m = count_jsonl(rd, fn) if rd else {"calls": None, "tool_errors": None}
    sm = [f for f in os.listdir(rd) if f.startswith(prefix) and f.endswith("summary.json")] if rd else []
    if sm:
        summ = json.load(open(os.path.join(rd, sm[0]), encoding="utf-8"))
        m["grader_failures"] = len(summ.get("failures", []))
        m["guided_ok"] = summ.get("ok")
    summary[tag] = m
out = os.path.join(HERE, "results", "f4-ab-comparison.json")
json.dump(summary, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("\nCOMPARISON:", json.dumps(summary, ensure_ascii=False, indent=1))

"""Fase 3 — Nivel 6: GLSL POP con el flujo completo conocimiento->construcción->verificación.

PARTE A (offline, sin TD): td-knowledge/glsl_analyze analiza dos shaders POP —
  uno mal (sin TDIndex, sin guarda, P leída y escrita) y uno bien. Del análisis
  del bueno salen los parámetros EXACTOS de Create Attributes (R3).

PARTE B (en vivo, TD): boxPOP -> glslPOP -> nullPOP (+ poptoCHOP como lector
CPU). Contratos verificados en sondas 2026-09-28:
  - el menú real de attr0name espera 'custom' lowercase (el analyzer decía
    'Custom': drift de la KB que este nivel documenta)
  - glslPOP NO auto-dockea DATs: el shader va a un textDAT hermano enlazado por
    el par `computedat`, con language=glsl explícito
  - poptoCHOP no tiene input connectors: se referencia con el par `pop`
"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
KB_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "knowledge"))
sys.path.insert(0, HERE)
sys.path.insert(0, KB_DIR)
from gauntlet_client import Gauntlet
import server as kb  # td-knowledge: las MISMAS funciones que sirve el MCP por stdio

g = Gauntlet("f3-n6-glsl-pop")

BAD = """void main()
{
    P[id] = P[id] * 1.001;
    Cd[id] = vec4(1.0);
}
"""

GOOD = """// uScale: uniform declarado por la secuencia vec del glslPOP
void main()
{
    const uint id = TDIndex();
    if (id >= TDNumElements()) return;
    vec3 src = TDIn_P(0, id);
    P[id] = src * uScale;
    Cd[id] = vec4(1.0, 0.5, 0.25, 1.0);
}
"""

def kb_call(tool, args):
    """Corre una tool de td-knowledge en el mismo proceso y la deja en el log."""
    t0 = time.time()
    try:
        fn = getattr(kb, "t_" + tool)
        r = fn(args)
    except Exception as e:
        r = {"error": f"{type(e).__name__}: {e}"}
    entry = {"tool": f"td-knowledge:{tool}", "args": args,
             "ms": round((time.time() - t0) * 1000, 1),
             "note": "offline (sin TD)", "response": json.dumps(r, ensure_ascii=False)[:4000]}
    g.log.append(entry)
    with open(g.log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"  [kb ] {tool:<24} {entry['ms']:>6} ms  (offline)")
    return r

# ══ PARTE A: conocimiento offline ═══════════════════════════════════════
print("  -- Parte A: glsl_analyze (offline, sin TD) --")
bad = kb_call("glsl_analyze", {"code": BAD, "family": "pop"})
g.check("analyzer rechaza el shader malo", bad.get("ok") is False, json.dumps(bad)[:200])
g.check("detecta R2 sin TDIndex", any("R2" in e.get("regla", "") and "TDIndex" in e.get("mensaje", "")
                                      for e in bad.get("errores", [])), json.dumps(bad.get("errores"))[:250])
g.check("detecta R2 guarda de rango", any("R2" in e.get("regla", "") and "guarda" in e.get("mensaje", "")
                                          for e in bad.get("errores", [])), json.dumps(bad.get("errores"))[:250])
g.check("detecta R4 (P leida y escrita)", any("R4" in e.get("regla", "")
                                              for e in bad.get("errores", [])), json.dumps(bad.get("errores"))[:250])

good = kb_call("glsl_analyze", {"code": GOOD, "family": "pop"})
g.check("analyzer acepta el shader bueno", good.get("ok") is True, json.dumps(good)[:250])
g.check("sin errores en el bueno", not good.get("errores"), json.dumps(good.get("errores"))[:200])

# R3: del analisis salen los params de Create Attributes para el build en vivo
r3 = next((n for n in good.get("notas", []) if isinstance(n, dict) and n.get("attr") == "Cd"), None)
g.check("R3 entrega params de Cd", bool(r3), json.dumps(good.get("notas"))[:250])
params_r3 = dict((r3 or {}).get("parametros", {}))
g.check("params R3 correctos (custom/Cd/4)",
        params_r3.get("attr0name") == "custom" and params_r3.get("attr0customname") == "Cd"
        and str(params_r3.get("attr0numcomps")) == "4", str(params_r3))

# ══ PARTE B: construcción en vivo ══════════════════════════════════════
print("  -- Parte B: build en vivo con lo que dicto el analisis --")
SB = "/gauntlet_n6"
g.call("delete_operator", {"path": SB}, note="limpieza (tolerada)")
g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "gauntlet_n6",
                              "nodeX": -1300, "nodeY": 1200}, note="sandbox N6")

# tipo glsl POP: verificar contra el build (glslPOP, si no glslcopyPOP)
GLSLPOP = None
for cand in ("glslPOP", "glslcopyPOP"):
    r = g.call("create_operator", {"parent_path": SB, "type": cand, "name": "shader"},
               note=f"probar {cand}")
    if not g.is_err(r):
        GLSLPOP = cand
        break
g.check("tipo glsl POP creado (" + str(GLSLPOP) + ")", bool(GLSLPOP))
g.meta.update({"glsl_pop_type": GLSLPOP})

g.call_ok("build_network", {"parent_path": SB, "operators": [
    {"type": "boxPOP", "name": "src"},
    {"type": "nullPOP", "name": "out1"},
    {"type": "poptoCHOP", "name": "check"}],
    "connections": [],
    "auto_layout": True}, note="out1 + check (referencia por par, no por cable)")
# el glslPOP se creo en la sonda de tipo: cablear la cadena src->shader->out1
# (TDIn_P lee input 0 del shader; out1 es el endpoint estable para medir el shader)
g.call_ok("wiring", {"from_path": SB + "/src", "to_path": SB + "/shader", "to_index": 0},
          note="src->shader")
g.call_ok("wiring", {"from_path": SB + "/shader", "to_path": SB + "/out1", "to_index": 0},
          note="shader->out1")

# shader: textDAT hermano + language=glsl + bind por computedat (sin auto-dock en este build)
# ORDEN importado: bind del DAT PRIMERO, params despues (enlazar resetea la secuencia vec)
g.call_ok("create_operator", {"parent_path": SB, "type": "textDAT", "name": "shader_compute"})
g.call_ok("set_dat_content", {"path": SB + "/shader_compute", "text": GOOD},
          note="shader bueno (validado offline)")
g.call_ok("set_parameters", {"path": SB + "/shader_compute", "values": {"language": "glsl"}},
          note="language explicito (set_dat_content no lo setea)")
ok, d = g.exec_code(f"""
import json
op('{SB}/shader').par.computedat = op('{SB}/shader_compute')
print('<<JSON>>' + json.dumps({{'computedat': str(op('{SB}/shader').par.computedat.eval())}}))""")
g.check("computedat enlazado al DAT", ok and "shader_compute" in str(d.get("computedat", "")), str(d)[:200])

# aplicar lo que dictó el análisis R3 — el analyzer ya emite el case que el menú
# VIVO espera ('custom' lowercase; corregido en server.py tras detectarlo en vivo).
r3_case = params_r3.get("attr0name", "custom")
vals = dict(params_r3)
vals["attr0name"] = r3_case.lower() if r3_case in ("Custom", "custom") else r3_case
g.check("analyzer emite case del menu vivo ('custom')", r3_case == "custom", str(r3_case))
vals.update({"vec0name": "uScale", "vec0valuex": 1.05,
             "outputattrs": "P"})  # P existe en el input: se DECLARA en outputattrs
# (hallazgo del nivel: sin esto el preamble no declara P -> 'P' : undeclared identifier)
g.call_ok("set_parameters", {"path": SB + "/shader", "values": vals},
          note="attrs R3 (case del menu vivo) + uniform uScale")

# re-set defensivo: si el bind del DAT o el rebuild reseteo vec0valuex, volver a setearlo
ok, d = g.exec_code(f"""
import json
s = op('{SB}/shader')
if abs(s.par.vec0valuex.eval() - 1.05) > 1e-9 or str(s.par.vec0name.eval()) != 'uScale':
    s.par.vec0name = 'uScale'
    s.par.vec0valuex = 1.05
print('<<JSON>>' + json.dumps({{'attr0customname': str(s.par.attr0customname.eval()),
      'attr0numcomps': str(s.par.attr0numcomps.eval()),
      'vec0name': str(s.par.vec0name.eval()), 'uScale': s.par.vec0valuex.eval(),
      'outputattrs': str(s.par.outputattrs.eval())}}))""")
g.check("attrs R3 aplicados al glslPOP", ok and d.get("attr0customname") == "Cd"
        and str(d.get("attr0numcomps")) == "4", str(d)[:250])
g.check("uniform uScale vivo (1.05)", ok and d.get("vec0name") == "uScale"
        and abs((d.get("uScale") or 0) - 1.05) < 1e-9, str(d)[:200])

# poptoCHOP: referencia por par pop AL SHADER (no tiene input connectors)
ok, d = g.exec_code(f"""
import json
chk = op('{SB}/check')
chk.par.pop = op('{SB}/shader')
print('<<JSON>>' + json.dumps({{'pop': str(chk.par.pop.eval()), 'active': int(chk.par.active)}}))""")
g.check("poptoCHOP referencia al shader por par pop", ok and "shader" in str(d.get("pop", "")), str(d)[:200])
g.meta.update({"popto_binding": "par pop (sin input connectors)"})

# ══ verificación en vivo: compila, cocina y transforma ═════════════════
ok, d = g.exec_code(f"""
import json, time
op('{SB}/shader').cook(force=True)
op('{SB}/out1').cook(force=True)
op('{SB}/check').cook(force=True)
time.sleep(0.3)
op('{SB}/shader').cook(force=True)
op('{SB}/check').cook(force=True)
r = {{'errors_shader': str(op('{SB}/shader').errors() or ''),
      'npts_src': op('{SB}/src').numPoints(), 'npts_out': op('{SB}/shader').numPoints()}}
print('<<JSON>>' + json.dumps(r))""")
g.check("glslPOP compila sin errores", ok and not d.get("errors_shader"), str(d)[:250])
g.check("numPoints se conserva (guarda R2 ok)",
        ok and d.get("npts_src") and d.get("npts_src") == d.get("npts_out"), str(d)[:200])

ok, d = g.exec_code(f"""
import json
chk = op('{SB}/check')
chk.cook(force=True)
chans = {{}}
for c in chk.chans():
    vals = [c[i] for i in range(chk.numSamples)]
    chans[c.name] = {{'min': round(min(vals), 4), 'max': round(max(vals), 4)}}
print('<<JSON>>' + json.dumps(chans))""")
print("  (info) canales poptoCHOP:", json.dumps(d, ensure_ascii=False)[:400])
g.check("poptoCHOP extrae P (GPU->CPU)", ok and all(k in d for k in ("P_0", "P_1", "P_2")), str(list(d))[:200])
pext = [abs(v["max"]) for k, v in d.items() if k.startswith("P_")] + \
       [abs(v["min"]) for k, v in d.items() if k.startswith("P_")]
pmax = max(pext) if pext else 0
g.check("P escalada por uScale (max ~0.525 > 0.5)", abs(pmax - 0.525) < 0.005, f"pmax={pmax}")
g.check("Cd creado por R3 y vivo (Cd_0~1, Cd_1~0.5, Cd_2~0.25, Cd_3~1)",
        all(k in d and abs(d[k]["max"] - v) < 1e-3 for k, v in
            (("Cd_0", 1.0), ("Cd_1", 0.5), ("Cd_2", 0.25), ("Cd_3", 1.0))),
        json.dumps({k: d.get(k) for k in ("Cd_0", "Cd_1", "Cd_2", "Cd_3")}, ensure_ascii=False)[:250])

errs = g.call_ok("get_errors", {"path": SB})
et = g.text_of(errs)
g.check("get_errors del sandbox limpio", '"count": 0' in et or '"items": []' in et, et[:250])

g.call_ok("delete_operator", {"path": SB}, note="cleanup N6")
s = g.summary()
print("\nN6:", json.dumps(s, ensure_ascii=False))
sys.exit(0 if s["ok"] else 1)

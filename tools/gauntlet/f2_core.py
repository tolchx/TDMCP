"""Fase 2 — API core con asserts: build_network, errores estructurados, undo,
file-sync de DAT, inspect_values (grid + record), grid temporal view_operator,
get_help/get_docs, y los 6 wrappers live de knowledge/live.py."""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "knowledge"))
from gauntlet_client import Gauntlet
import live  # knowledge/live.py — los wrappers reales de producción

g = Gauntlet("f2-core")
SB = "/gauntlet_core"

# ── setup sandbox ────────────────────────────────────────────────────────
g.call("delete_operator", {"path": SB}, note="limpieza (tolerada)")
g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "gauntlet_core",
                              "nodeX": -1300, "nodeY": -900}, note="sandbox")

# ── 1. build_network multi-hop + wiring verificado ──────────────────────
g.call_ok("build_network", {"parent_path": SB, "operators": [
    {"type": "noiseTOP", "name": "src"}, {"type": "levelTOP", "name": "lvl"},
    {"type": "blurTOP", "name": "blur"}, {"type": "nullTOP", "name": "out1"}],
    "connections": [{"from": "src", "to": "lvl"}, {"from": "lvl", "to": "blur"},
                    {"from": "blur", "to": "out1"}], "auto_layout": True},
    note="4 ops cableadas")
ok, d = g.exec_code(f"""
conns = op('{SB}/out1').inputConnectors[0].connections
print('<<JSON>>' + __import__('json').dumps({{'wired': [c.owner.name for c in conns]}}))""")
g.check("wiring blur->out1 verificado in-TD", ok and d.get("wired") == ["blur"], str(d)[:200])

# ── 2. errores estructurados ────────────────────────────────────────────
r = g.call("set_parameters", {"path": SB + "/src", "values": {"type": "perlin_99"}},
           note="menu invalido (esperado)")
t = g.text_of(r)
g.check("error menu con valid_values", '"invalid_menu_value"' in t and "valid_values" in t, t[:300])
r = g.call("wiring", {"from_path": SB + "/lvl", "to_path": SB + "/out1", "to_index": 5},
           note="input inexistente (esperado)")
t = g.text_of(r)
g.check("error de rango/indice estructurado", g.is_err(r), t[:250])

# ── 3. undo por llamada ─────────────────────────────────────────────────
# En este build ui.undo es un OBJETO td.Undo: ui.undo.undo() (hallazgo de la sonda).
g.call_ok("set_parameters", {"path": SB + "/lvl", "values": {"brightness1": 2.5}})
ok, d = g.exec_code(f"""
import json
u = ui.undo
label = str(u.undoStack[-1]) if len(u.undoStack) else ''
u.undo()
print('<<JSON>>' + json.dumps({{'label': label, 'brightness': op('{SB}/lvl').par.brightness1.eval()}}))""")
g.check("undo revierte set_parameters (funcional)", ok and abs((d.get("brightness") or 1) - 1.0) < 1e-6, str(d)[:200])
print(f"    (info) etiqueta undo top: {d.get('label')!r}")

# ── 4. file-sync de DAT (GLSL) ──────────────────────────────────────────
glsl_path = os.path.join(HERE, "results", g.run_id, "shader.glsl")
g.call_ok("create_operator", {"parent_path": SB, "type": "textDAT", "name": "shader"})
r = g.call_ok("set_dat_content", {"path": SB + "/shader",
    "file_content": "out vec4 fragColor;\nvoid main(){ fragColor = TDOutputSwizzle(vec4(1.0,0.5,0.0,1.0)); }\n",
    "file_type": "glsl"}, note="file-sync glsl")
ok, d = g.exec_code(f"""
import json
n = op('{SB}/shader')
print('<<JSON>>' + json.dumps({{'syncfile': int(n.par.syncfile), 'file': n.par.file.eval(),
      'ontext': open(n.par.file.eval()).read()[:40] if n.par.file.eval() else ''}}))""")
g.check("DAT sincronizado a disco", ok and d.get("syncfile") == 1 and "fragColor" in str(d.get("ontext", "")), str(d)[:250])

# ── 5. inspect_values: sample_grid + record_seconds ─────────────────────
r = g.call_ok("inspect_values", {"path": SB + "/src", "sample_grid": 4}, note="grid 4x4 RGBA")
t = g.text_of(r)
g.check("sample_grid devuelve pixeles", ('"sample' in t.lower() or 'grid' in t.lower()) and not g.is_err(r), t[:200])
g.call_ok("create_operator", {"parent_path": SB, "type": "lfoCHOP", "name": "lfo"})
r = g.call_ok("inspect_values", {"path": SB + "/lfo", "record_seconds": 0.5}, note="record async CHOP")
time.sleep(1.5)
r = g.call("inspect_values", {"path": SB + "/lfo"}, note="retrieve record CHOP")
t = g.text_of(r)
g.check("record_seconds devuelve muestras", ('sample' in t.lower() or 'chan' in t.lower() or 'value' in t.lower()) and not g.is_err(r), t[:250])

# ── 6. grid temporal (view_operator frames) ─────────────────────────────
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": True}})
r = g.call_ok("view_operator", {"path": SB + "/out1", "frames": 3, "step": 5, "resolution": "tiny"},
              note="job grid temporal")
job = g.json_of(r).get("job_id", "")
time.sleep(3.5)
r = g.call("view_operator", {"path": SB + "/out1", "job_id": job}, note=f"retrieve grid {job}")
png = g.save_image(r, os.path.join(HERE, "results", g.run_id, "grid_temporal.png"))
g.check("grid temporal PNG", bool(png), "sin imagen inline: " + g.text_of(r)[:150])
g.call_ok("set_parameters", {"path": "/TDMCP", "values": {"Inlineimages": False}})

# ── 7. get_help del build vivo + get_docs ───────────────────────────────
r = g.call_ok("get_help", {"types": ["noiseTOP"], "pattern": "type,resolution*"}, note="help vivo")
g.check("get_help devuelve pars del build", "resolution" in g.text_of(r))
r = g.call_ok("get_docs", {"query": "Noise TOP", "kind": "concept", "section": "Parameters - Noise Page"},
              note="docs locales")
g.check("get_docs local responde", len(g.text_of(r)) > 100 and not g.is_err(r))

# ── 8. wrappers live de knowledge/live.py (produccion real) ───────────
print("\n  -- wrappers live (td-knowledge) --")

def as_dict(r):
    """live.py mezcla contratos: unas tools devuelven dict, otras (ok, data)."""
    return r[1] if isinstance(r, tuple) and len(r) == 2 else r

d = as_dict(live.t_status({}))
g.check("td_status", d.get("td_up"), str(d)[:200])

r = as_dict(live.t_find_in_ops({"query": "fragColor", "root_path": SB}))
g.check("find_in_ops encuentra en DAT", bool(r.get("matches")) and any(m.get("where") == "dat" for m in r["matches"]), str(r)[:250])

r = as_dict(live.t_auto_layout({"parent_path": SB, "dry_run": True}))
g.check("auto_layout dry_run calcula capas", r.get("ok") and r.get("levels", 0) >= 2, str({k: r.get(k) for k in ('ok', 'levels', 'nodes')})[:200])

g.exec_code(f"""
op('{SB}').create('constantCHOP', 'k1')
op('{SB}/k1').par.value0 = 0.5""")
r = as_dict(live.t_smart_connect({"from_path": SB + "/k1", "to_path": SB + "/out1"}))
g.check("smart_connect detecta familia incompatible", (not r.get("ok")) or ("probablemente no" in str(r.get("hint", ""))), str(r.get("hint", r.get("error", "")))[:200])

f1 = os.path.join(HERE, "results", g.run_id, "v1.tdn")
r = as_dict(live.t_tdn_export({"root_path": SB, "out_path": f1}))
g.check("tdn_export escribe .tdn", r.get("ok") and os.path.exists(f1), str(r)[:200])

g.call_ok("create_operator", {"parent_path": SB, "type": "nullTOP", "name": "extra"})
ok, d = g.exec_code(f"""
import json
op('{SB}/extra').inputConnectors[0].connect(op('{SB}/out1'))
pos = {{n: [op('{SB}/' + n).nodeX, op('{SB}/' + n).nodeY] for n in ['src', 'lvl', 'blur', 'out1', 'extra']}}
print('<<JSON>>' + json.dumps(pos))""")
ok2, _ = live.call("reposition_operators", {"parent_path": SB,
    "positions": {"src": [-300, 200], "lvl": [0, 200], "blur": [300, 200],
                  "out1": [600, 200], "extra": [900, 200]}})
ok3, chk = g.exec_code(f"""
import json
print('<<JSON>>' + json.dumps({{n: [op('{SB}/' + n).nodeX, op('{SB}/' + n).nodeY]
      for n in ['src', 'extra']}}))""")
g.check("reposition_operators mueve de verdad", ok2 and ok3 and chk.get("extra") == [900, 200], str(chk)[:200])
r2 = as_dict(live.t_tdn_export({"root_path": SB, "out_path": f1.replace("v1", "v2")}))
rd = as_dict(live.t_tdn_diff({"path_a": f1, "path_b": f1.replace("v1", "v2")}))
g.check("tdn_diff detecta op agregado", rd.get("summary", {}).get("added") == 1, str(rd.get("summary"))[:200])

# ── cleanup ─────────────────────────────────────────────────────────────
g.call_ok("delete_operator", {"path": SB}, note="cleanup")
s = g.summary()
print("\nCORE:", json.dumps(s, ensure_ascii=False))
sys.exit(0 if s["ok"] else 1)

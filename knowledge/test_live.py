"""Prueba real de las tools live de td-knowledge contra TouchDesigner vivo."""
import sys, os, json, tempfile
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import live


def show(t, r, n=700):
    print("\n" + "=" * 74)
    print("###", t)
    print(json.dumps(r, indent=1, ensure_ascii=False)[:n])


SB = "/hermes_live"
TMP = os.path.join(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()), "Temp")

print("### 1. td_status")
show("status", live.t_status({}))

print("\n### 2. setup del sandbox")
ok, r = live.exec_code(r'''
import json
root = op('/')
for c in list(root.children):
    if c.name.startswith('hermes_live') and c.valid: c.destroy()
sb = root.create('baseCOMP', 'hermes_live')
a = sb.create('noiseTOP', 'a')
b = sb.create('levelTOP', 'b')
c = sb.create('compositeTOP', 'c')
d = sb.create('textDAT', 'code')
tb = sb.create('tableDAT', 'tbl')
k = sb.create('constantCHOP', 'k')
d.text = 'linea uno\nMAGIC_TOKEN aca\nlinea tres'
tb.appendRow(['h1', 'h2']); tb.appendRow(['v1', 'v2'])
b.par.brightness1.expr = 'absTime.seconds % 2'
a.par.seed = 7
b.inputConnectors[0].connect(a); c.inputConnectors[0].connect(b)
sb.nodeX = 900; sb.nodeY = 600
a.nodeX = 900; a.nodeY = 700
b.nodeX = 1050; b.nodeY = 850
c.nodeX = 950; c.nodeY = 950
d.nodeX = 900; d.nodeY = 1000
tb.nodeX = 1050; tb.nodeY = 1000
print('<<JSON>>' + json.dumps({'ok': True, 'ops': [x.name for x in sb.children]}))
''')
print(json.dumps(r, ensure_ascii=False))

print("\n### 3. find_in_ops (texto en un DAT)")
show("MAGIC_TOKEN", live.t_find_in_ops({"query": "MAGIC_TOKEN", "root_path": SB}), 900)

print("\n### 4. find_in_ops (expresión de parámetro)")
show("absTime", live.t_find_in_ops({"query": "absTime", "root_path": SB}), 900)

print("\n### 5. auto_layout dry_run (debería ordenar por capas)")
lay = live.t_auto_layout({"parent_path": SB, "dry_run": True})
show("dry_run", lay, 1200)

print("\n### 6. auto_layout real + verificación de posiciones")
show("apply", live.t_auto_layout({"parent_path": SB}), 500)
ok, chk = live.exec_code(r'''
import json
sb = op('/hermes_live')
print('<<JSON>>' + json.dumps({x.name: [x.nodeX, x.nodeY] for x in sb.children}))
''')
print("posiciones tras el layout:", json.dumps(chk, ensure_ascii=False))

print("\n### 7. smart_connect b -> c (auto)")
show("smart_connect TOP->TOP", live.t_smart_connect({"from_path": SB + "/b", "to_path": SB + "/c"}), 1000)

print("\n### 8. smart_connect NEGATIVO (un CHOP a un input de TOP)")
show("negativo", live.t_smart_connect({"from_path": SB + "/k", "to_path": SB + "/c"}), 900)

print("\n### 9. tdn_export v1 (sin contenido de DATs)")
f1 = os.path.join(TMP, "hermes_live_v1.tdn")
show("export1", live.t_tdn_export({"root_path": SB, "out_path": f1}), 600)

print("\n### 10. cambio + tdn_export v2 (un op nuevo y un par cambiado)")
live.exec_code(r'''
import json
sb = op('/hermes_live')
n = sb.create('nullTOP', 'nuevo')
n.inputConnectors[0].connect(op('/hermes_live/c'))
op('/hermes_live/a').par.seed = 99
print('<<JSON>>' + json.dumps({'ok': True}))
''')
f2 = os.path.join(TMP, "hermes_live_v2.tdn")
show("export2", live.t_tdn_export({"root_path": SB, "out_path": f2, "include_dat_content": True}), 600)

print("\n### 11. tdn_diff (offline)")
show("diff", live.t_tdn_diff({"path_a": f1, "path_b": f2}), 1500)

print("\n### 12. cleanup")
ok, r = live.call("delete_operator", {"path": SB})
print(json.dumps(r, ensure_ascii=False)[:200])
for f in (f1, f2):
    if os.path.exists(f):
        os.remove(f)
print("temporales borrados")

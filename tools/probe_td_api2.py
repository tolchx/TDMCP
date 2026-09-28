"""Probe 2: API necesaria para TDN export (OPType, inputs por conector, flags, custom pars)."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tdmcp_client import init, notify, call, text_of

init(); notify("notifications/initialized")

CODE = r'''
import json
res = {}
root = op('/')
for _c in list(root.children):
    if _c.name.startswith('probe_tdn') and _c.valid:
        _c.destroy()
sb = root.create('baseCOMP', 'probe_tdn')
a = sb.create('noiseTOP', 'a')
b = sb.create('levelTOP', 'b')
c = sb.create('compositeTOP', 'c')
t = sb.create('textDAT', 'code')
tb = sb.create('tableDAT', 'tbl')
tab = sb.create('constantCHOP', 'k')
b.par.brightness1.expr = 'absTime.seconds % 2'
a.par.seed = 7
b.inputConnectors[0].connect(a)
c.inputConnectors[0].connect(b)
c.inputConnectors[1].connect(a)
b.bypass = True
b.lock = False
b.display = True
t.text = 'hola\nmundo'
tb.clear()
tb.appendRow(['x', 'y'])
tb.appendRow(['1', '2'])
b.setDocked(t, 'left') if hasattr(b, 'setDocked') else None

res['optype'] = {'a.type': a.type, 'a.OPType': getattr(a, 'OPType', 'NO'), 'b.OPType': getattr(b, 'OPType', 'NO')}
res['inputs'] = {}
for i, conn in enumerate(c.inputConnectors):
    try:
        res['inputs'][str(i)] = [x.name for x in conn.connections]
    except Exception as e:
        res['inputs'][str(i)] = 'ERR ' + str(e)
res['flags'] = {}
for f in ['bypass', 'lock', 'display', 'render', 'viewer', 'expose', 'allowCooking']:
    res['flags'][f] = str(getattr(b, f, 'NO'))
res['custompars'] = {'has': hasattr(sb, 'customPars'), 'n': len(getattr(sb, 'customPars', []))}
res['dat'] = {'t_isText': getattr(t, 'isText', 'NO'), 't_isTable': getattr(t, 'isTable', 'NO'),
              'tb_isTable': getattr(tb, 'isTable', 'NO'), 'tb_rows': [list(r) for r in tb.rows()],
              't_file_par': str(getattr(t.par, 'file', 'NO')), 't_sync': str(getattr(t.par, 'syncfile', 'NO'))}
res['docked'] = {'b_docked': getattr(b, 'docked', 'NO') and b.docked.name, 't_par_dock': str(getattr(t.par, 'dock', 'NO'))}
res['position'] = {'nodeX': sb.nodeX, 'nodeY': sb.nodeY, 'nodeWidth': sb.nodeWidth, 'nodeHeight': sb.nodeHeight}
res['color'] = [round(x, 3) for x in sb.color]
res['parent'] = getattr(sb, 'parent', lambda: None)() and sb.parent().name
res['storage'] = {'has': hasattr(sb, 'storage'), 'keys': list(sb.storage.keys())[:5] if hasattr(sb, 'storage') else 'NO'}
res['seq_pars'] = {'has_pars': 'sequence' in str([p.name for p in sb.pars()])}
print('<<PROBE>>' + json.dumps(res, default=str))
'''

r = call("execute_code", {"code": CODE}, timeout=90)
txt = text_of(r)
print("RAW (primeros 700):", txt[:700])
clean = txt.replace("*** isError=true ***", "").strip()
try:
    d = json.loads(clean)
except Exception as e:
    print("no parsea como JSON:", e); raise SystemExit(1)
if not d.get("success"):
    print("ERROR:", json.dumps(d)[:800]); raise SystemExit(1)
out = d.get("output", "")
print(json.dumps(json.loads(out.split("<<PROBE>>", 1)[1]), indent=1, ensure_ascii=False)[:3000])

# limpieza
print("\ncleanup:", text_of(call("delete_operator", {"path": "/probe_tdn"}))[:200])

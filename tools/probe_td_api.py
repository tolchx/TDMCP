"""Probe en vivo: que propiedades de la API de TD puedo usar para TDN/find/layout."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tdmcp_client import init, notify, call, text_of

init(); notify("notifications/initialized")

CODE = r'''
import json
res = {}
o = op('/TDMCP')
res['baseCOMP_attrs'] = {
    'position': str(getattr(o, 'position', None)),
    'nodeX_attr': getattr(o, 'nodeX', 'NO'),
    'nodeWidth': getattr(o, 'nodeWidth', 'NO'),
    'color': str(getattr(o, 'color', 'NO')),
    'tags': str(getattr(o, 'tags', 'NO')),
    'comment': repr(getattr(o, 'comment', 'NO')),
    'type': o.type, 'family': o.family, 'name': o.name,
}
p = o.par.Port
res['par_attrs'] = {
    'default': str(getattr(p, 'default', 'NO')),
    'mode': str(getattr(p, 'mode', 'NO')),
    'expr': repr(getattr(p, 'expr', 'NO')),
    'isDefault': str(getattr(p, 'isDefault', 'NO')),
    'eval': str(p.eval()),
    'style': str(getattr(p, 'style', 'NO')),
    'label': str(getattr(p, 'label', 'NO')),
    'tuplet': str(getattr(p, 'tuplet', 'NO')),
    'page': str(getattr(p, 'page', 'NO')),
}
res['has_pars_method'] = str(hasattr(o, 'pars'))
res['non_default_count'] = len([q for q in o.pars() if not q.isDefault]) if hasattr(o, 'pars') else 'NO'
tn = None
for c in op('/TDMCP').findChildren(depth=4):
    if c.family == 'DAT' and getattr(c, 'isText', False):
        tn = c; break
if tn is None:
    for c in op('/TDMCP').findChildren(depth=4):
        if c.family == 'DAT' and not hasattr(c, 'rows') :
            tn = c; break
res['dat'] = {}
if tn:
    res['dat'] = {'type': tn.type, 'has_rows': hasattr(tn, 'rows'), 'has_text': hasattr(tn, 'text'),
                  'numRows': getattr(tn, 'numRows', 'NO'), 'numCols': getattr(tn, 'numCols', 'NO'),
                  'readOnly': getattr(tn, 'readOnly', 'NO')}
    try:
        res['dat']['rows0_2'] = [list(r) for r in tn.rows()[:2]]
    except Exception as e:
        res['dat']['rows_err'] = str(e)
inp = tn
res['inputs'] = {'inputs': [x.path for x in inp.inputs], 'inputConnectors': len(inp.inputConnectors)}
res['root_children'] = sorted([(c.name, c.type, c.family) for c in op('/').children])
try:
    res['ui'] = {'selection': [x.path for x in (ui.selection or [])][:5]}
except Exception as e:
    res['ui'] = {'selection_err': str(e), 'ui_attrs': [x for x in dir(ui) if 'sel' in x.lower()]}
print('<<PROBE>>' + json.dumps(res, default=str))
'''

r = call("execute_code", {"code": CODE}, timeout=60)
txt = text_of(r)
try:
    d = json.loads(txt)
except Exception:
    print("RAW:", txt[:500]); raise SystemExit(1)
if not d.get("success"):
    print("ERROR EN TD:", json.dumps(d)[:600]); raise SystemExit(1)
out = d.get("output", "")
payload = out.split("<<PROBE>>", 1)[1] if "<<PROBE>>" in out else ""
print(json.dumps(json.loads(payload), indent=1, ensure_ascii=False)[:3000])

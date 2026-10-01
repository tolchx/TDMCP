#!/usr/bin/env python3
"""probe_pop5c_bound.py — SONDA DESECHABLE (no se commitea)."""
from __future__ import annotations
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gauntlet_client import Gauntlet  # noqa: E402
from td_probe import chain_source  # noqa: E402

g = Gauntlet(phase="probe-pop5c-bound")
g.init()
CHAIN = chain_source("/pop_group")

ok, d = g.exec_code(CHAIN + """
import json
import time
gp = op('/pop_group/geo/gp')
chk = op(ROOT + '/check')

def color():
    chk.par.pop = gp
    settle(2)
    chk.cook(force=True)
    time.sleep(0.2)
    chk.cook(force=True)
    time.sleep(0.1)
    chk.cook(force=True)
    return sorted(set(round(c.vals[i], 4) for c in chk.chans() if c.name == 'Color_0' for i in range(len(c.vals))))

pin = gp.par.bound0inattr
sal = {'inattr_menu': list(pin.menuNames or []), 'inattr_default': pin.eval(),
       'type_menu': list(gp.par.bound0type.menuNames or [])}
gp.par.debugcolor = True
gp.par.thinenabled = False
gp.par.bound0type = 'usebsphere'
for ia in ('P', 'P(0)'):
    try:
        gp.par.bound0inattr = ia
    except Exception as e:
        sal['set_' + ia] = 'ERR %s' % str(e)[:60]
        continue
    for sc in (0.3, 1.0, 3.0):
        gp.par.bound0scalex = sc
        gp.par.bound0scaley = sc
        gp.par.bound0scalez = sc
        sal['%s@%s' % (ia, sc)] = {'colors': color(), 'err': gp.errors()[:80]}
sal['out_menu'] = list(gp.par.bound0scalex.menuNames or [])[:3]
print('<<JSON>>' + json.dumps(sal))
""")
print(json.dumps(d, ensure_ascii=False, indent=1))

# limpieza: dejar gp sin bound y sin debugcolor
g.exec_code("""
import json
gp = op('/pop_group/geo/gp')
gp.par.bound.numBlocks = 0
gp.par.debugcolor = False
print('<<JSON>>' + json.dumps({'ok': 1}))
""")

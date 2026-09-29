"""Fase 3 — Nivel 4: extensión Python (patrón state-output de td-comp-architecture).

baseCOMP 'pwm_lfo' + textDAT 'extPWM' (clase PWM_LFO) + ext0object='extPWM' +
custom pars Rate (control) / Dutyout (readonly state output) + reinitextensions.
Graders: extension viva, Init() resetea, Update() anima en [0,1], Dutyout refleja.
"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gauntlet_client import Gauntlet

g = Gauntlet("f3-n4-extension")
SB = "/pwm_lfo"
g.call("delete_operator", {"path": SB}, note="limpieza (tolerada)")

CLASS_CODE = '''class PWM_LFO:
    def __init__(self, ownerComp):
        self.ownerComp = ownerComp
        self.Dutycycle = 0.5
        return

    def Init(self):
        self.Dutycycle = 0.5
        return 1

    def Update(self):
        rate = max(0.1, self.ownerComp.par.Rate.eval())
        t = (absTime.seconds * rate) % 1.0
        self.Dutycycle = 0.1 + 0.8 * t
        return 1
'''

# 1) COMP + DAT de extension + custom pars
g.call_ok("create_operator", {"parent_path": "/", "type": "baseCOMP", "name": "pwm_lfo",
                              "nodeX": -1300, "nodeY": -1200}, note="COMP del modulo")
g.call_ok("create_operator", {"parent_path": SB, "type": "textDAT", "name": "extPWM"})
g.call_ok("set_dat_content", {"path": SB + "/extPWM", "text": CLASS_CODE}, note="clase PWM_LFO")
# skill td-python-extension paso 4: language=python SIEMPRE explicito
r = g.call_ok("set_parameters", {"path": SB + "/extPWM", "values": {"language": "python"}},
              note="language=python")
r = g.call_ok("edit_custom_parameters", {"path": SB, "page": "PWM", "add": [
    {"name": "Rate", "type": "Float", "default": 2.0, "min": 0.1, "max": 10.0},
    {"name": "Dutyout", "type": "Float", "default": 0.0}]}, note="custom pars PWM")
d = g.json_of(r)
g.check("custom pars agregados", len(d.get("added", [])) == 2, g.text_of(r)[:250])

# 2) vincular extension (paso 5 de la skill: binding string + promote) + readonly + reinit
r = g.call_ok("set_parameters", {"path": SB, "values": {
    "ext0object": "op('./extPWM').module.PWM_LFO(me)", "ext0promote": True}},
    note="ext0object binding + promote")
ok, d = g.exec_code(f"""
import json
op('{SB}/..').par  # noop estabilidad
op('{SB}').par.Dutyout.readOnly = True
op('{SB}').par.reinitextensions.pulse()
print('<<JSON>>' + json.dumps({{'ok': True}}))""")
g.check("reinitextensions pulso", ok, str(d)[:200])
time.sleep(1.0)

# 3) graders de la extension
ok, d = g.exec_code(f"""
import json
c = op('{SB}')
r = {{'has_ext': hasattr(c.ext, 'PWM_LFO'), 'promoted': None}}
if r['has_ext']:
    r['init_dc'] = c.ext.PWM_LFO.Dutycycle
    c.ext.PWM_LFO.Update()
    r['u1'] = c.ext.PWM_LFO.Dutycycle
print('<<JSON>>' + json.dumps(r))""")
g.check("ext.PWM_LFO instanciada", d.get("has_ext") is True, str(d)[:250])
g.check("Dutycycle inicial 0.5", abs((d.get("init_dc") or -1) - 0.5) < 1e-6, str(d)[:250])
g.check("Update() anima (u1 en [0,1] y distinto de 0.5)",
        isinstance(d.get("u1"), (int, float)) and 0 <= d["u1"] <= 1 and abs(d["u1"] - 0.5) > 1e-9,
        str(d)[:250])
u1_val = d.get("u1")  # se usa en el check de animacion continua (d se reasigna abajo)

time.sleep(0.6)
ok, d = g.exec_code(f"""
import json
c = op('{SB}')
c.ext.PWM_LFO.Update()
u2 = c.ext.PWM_LFO.Dutycycle
c.ext.PWM_LFO.Init()
init_dc = c.ext.PWM_LFO.Dutycycle
r = {{'u2': u2, 'init_dc': init_dc,
      'dutyout_expr_set': False, 'dutyout_val': None}}
c.par.Dutyout.expr = "ext.PWM_LFO.Dutycycle"
r['dutyout_expr_set'] = str(c.par.Dutyout.mode).endswith('EXPRESSION')
r['dutyout_val'] = c.par.Dutyout.eval()
r['readonly'] = bool(c.par.Dutyout.readOnly)
print('<<JSON>>' + json.dumps(r))""")
u2, init_dc = d.get("u2"), d.get("init_dc")
# determinista: dos Updates separados ~0.6 s deben dar valores distintos (rate=2)
g.check("Update() anima (u2 != u1, ambos en [0,1])",
        isinstance(u2, (int, float)) and 0 <= u2 <= 1 and abs(u2 - (u1_val if isinstance(u1_val, (int, float)) else -99)) > 1e-6,
        str(d)[:250])
g.check("Init() resetea a 0.5", abs((init_dc or -1) - 0.5) < 1e-6, str(d)[:250])
g.check("Dutyout en modo EXPRESSION", d.get("dutyout_expr_set") is True, str(d)[:250])
g.check("Dutyout evalua en [0,1]", isinstance(d.get("dutyout_val"), (int, float)) and 0 <= d["dutyout_val"] <= 1, str(d)[:250])
g.check("Dutyout readonly", d.get("readonly") is True, str(d)[:250])

errs = g.call_ok("get_errors", {"path": SB})
g.check("sin errores en el modulo", '"count": 0' in g.text_of(errs) or '"items": []' in g.text_of(errs),
        g.text_of(errs)[:200])

g.call_ok("delete_operator", {"path": SB}, note="cleanup N4")
s = g.summary()
print("\nN4:", json.dumps(s, ensure_ascii=False))
sys.exit(0 if s["ok"] else 1)

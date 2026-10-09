#!/usr/bin/env python3
"""test_tdxn_build_live.py — Prueba en vivo de tdxn_build y round-trip TDXN v2.1 YAML."""

import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import live

SANDBOX = "/project1/test_tdxn_build_sandbox"

TDXN_YAML = f"""
format: tdxn
version: '2.0'
generator: test_tdxn_build_live
network_path: {SANDBOX}
type_defaults:
  mathCHOP:
    parameters:
      gain: 2.5
operators:
  - name: osc_source
    type: waveCHOP
    position: [0, 0]
    parameters:
      wavetype: sine
      period: 0.25
      amp: 0.8
    flags: [viewer]

  - name: gain_mult
    type: mathCHOP
    position: [200, 0]
    inputs: [osc_source]
    # No define gain: debe tomar el default 2.5 de type_defaults

  - name: out_null
    type: nullCHOP
    position: [400, 0]
    inputs: [gain_mult]
    flags: [display]

  - name: data_table
    type: tableDAT
    position: [0, -200]
    dat_content:
      - [param, value]
      - [speed, '120.5']
      - [mode, active]
    dat_content_format: table

  - name: logic_code
    type: textDAT
    position: [200, -200]
    dat_content: |
      # TDXN Generated Script
      def compute(val):
          return val * 2
    dat_content_format: text
"""

def main():
    print("=== Test 1: dry_run de tdxn_build ===")
    dry = live.t_tdxn_build({"tdxn": TDXN_YAML, "dry_run": True})
    print("Dry run result:", dry)
    assert dry.get("ok") and dry.get("dry_run"), f"Dry run falló: {dry}"
    assert dry.get("operators_count") == 5, f"Operadores incorrectos: {dry}"
    print("PASS: dry_run validado correctamente.\n")

    print(f"=== Test 2: Construcción real en TouchDesigner ({SANDBOX}) ===")
    res = live.t_tdxn_build({"tdxn": TDXN_YAML, "clear_first": True})
    print("Build result:", res)
    assert res.get("ok"), f"Build falló: {res}"
    assert len(res.get("created", [])) == 5, f"No se crearon los 5 nodos: {res}"
    assert len(res.get("connections", [])) == 2, f"Conexiones incorrectas: {res}"
    assert res.get("parameters_set", 0) >= 3, f"Parámetros seteados insuficientes: {res}"
    print("PASS: Construcción en vivo exitosa.\n")

    print("=== Test 3: Verificación profunda del estado en TD ===")
    verify_script = f"""
import json
p = op('{SANDBOX}')
osc = p.op('osc_source')
gain = p.op('gain_mult')
out = p.op('out_null')
tbl = p.op('data_table')
txt = p.op('logic_code')

chk = {{
    'osc_period': osc.par.period.eval(),
    'gain_val': gain.par.gain.eval(),
    'out_input': out.inputs[0].name if out.inputs else None,
    'tbl_rows': tbl.numRows,
    'tbl_cell': tbl[1, 1].val if tbl.numRows > 1 else None,
    'txt_has_code': 'TDXN Generated Script' in txt.text,
    'out_display': getattr(out, 'display', False)
}}
print('{live.MARK}' + json.dumps(chk))
"""
    ok, chk = live.exec_code(verify_script)
    print("TD State check:", chk)
    assert ok, f"Error ejecutando script de verificación: {chk}"
    assert chk.get("osc_period") == 0.25, f"Period erróneo: {chk}"
    assert chk.get("gain_val") == 2.5, f"Gain default no aplicado: {chk}"
    assert chk.get("out_input") == "gain_mult", f"Wiring erróneo: {chk}"
    assert chk.get("tbl_rows") == 3 and chk.get("tbl_cell") == "120.5", f"Tabla errónea: {chk}"
    assert chk.get("txt_has_code") is True, f"Texto DAT erróneo: {chk}"
    print("PASS: Estado verificado exactamente en TouchDesigner.\n")

    print("=== Test 4: Round-trip tdxn_export de la red construida ===")
    tmp_out = os.path.join(tempfile.gettempdir(), "tdxn_roundtrip_test.yaml")
    exp = live.t_tdxn_export({"root_path": SANDBOX, "out_path": tmp_out})
    print("Export result:", exp)
    assert exp.get("ok"), f"Export falló: {exp}"
    assert exp.get("operators") == 5, f"Export no vio los 5 operadores: {exp}"
    assert os.path.exists(tmp_out) and os.path.getsize(tmp_out) > 200
    print(f"PASS: Round-trip completado ({exp.get('bytes')} bytes exportados).\n")

    # Cleanup
    print("=== Limpieza ===")
    live.call("delete_operator", {"path": SANDBOX})
    if os.path.exists(tmp_out):
        os.remove(tmp_out)
    print(f"PASS: Sandbox {SANDBOX} eliminado limpiamente.")

if __name__ == "__main__":
    main()

"""
test_snippet_patterns_suite3.py — Tercera suite de pruebas en vivo de patrones POP extraídos de OP Snippets.

Redes a construir y verificar en vivo:
1. Red G: blendPOP con múltiples entradas combinando dos morfologías (grid y sphere) con blendtype='differencing' o 'proportional'.
2. Red H: curvePOP generando curvas analíticas 2D con segmentos y simetría.
3. Red I: normalPOP recomputando normales y generando tangentes para sombreado PBR ('alwayscompute').
4. Red J: attributeconvertPOP migrando atributos entre clases (pointtovert / pointtoprim).
"""

import time
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live

SANDBOX = "/project1/snippets_validation_suite3"

def run_tests():
    print(f"=== Creando sandbox en {SANDBOX} ===")
    ok, res = live.call("create_operator", {"type": "baseCOMP", "name": "snippets_validation_suite3", "parent_path": "/project1"})
    assert ok, f"Error creando sandbox: {res}"

    try:
        # -------------------------------------------------------------
        # Test 1: blendPOP (Red G)
        # -------------------------------------------------------------
        print("\n--- Test 1: blendPOP mezclando dos formas ---")
        ok, res = live.call("create_operator", {"type": "gridPOP", "name": "blend_src1", "parent_path": SANDBOX})
        assert ok, f"Error creando blend_src1: {res}"
        ok, res = live.call("create_operator", {"type": "spherePOP", "name": "blend_src2", "parent_path": SANDBOX})
        assert ok, f"Error creando blend_src2: {res}"
        ok, res = live.call("create_operator", {"type": "blendPOP", "name": "blend_node", "parent_path": SANDBOX})
        assert ok, f"Error creando blend_node: {res}"

        ok, res = live.call("wiring", {"from_path": f"{SANDBOX}/blend_src1", "to_path": f"{SANDBOX}/blend_node", "to_index": 0})
        assert ok, f"Error cableando src1 -> blend: {res}"
        ok, res = live.call("wiring", {"from_path": f"{SANDBOX}/blend_src2", "to_path": f"{SANDBOX}/blend_node", "to_index": 1})
        assert ok, f"Error cableando src2 -> blend: {res}"

        setup_blend = f"""
b = op('{SANDBOX}/blend_node')
b.par.blendtype = 'differencing'
b.cook(force=True)
"""
        ok, res = live.call("execute_code", {"code": setup_blend})
        assert ok, f"Error configurando blendPOP: {res}"

        check_blend = f"""
import json
b = op('{SANDBOX}/blend_node')
print("{live.MARK}" + json.dumps({{"blendtype": b.par.blendtype.eval(), "num_points": b.numPoints()}}))
"""
        ok, data = live.exec_code(check_blend)
        assert ok and data.get("blendtype") == "differencing", f"blendPOP config errónea: {data}"
        print(f"PASS: blendPOP verificado exitosamente: {data}")

        # -------------------------------------------------------------
        # Test 2: curvePOP (Red H)
        # -------------------------------------------------------------
        print("\n--- Test 2: curvePOP generando curva paramétrica ---")
        ok, res = live.call("create_operator", {"type": "curvePOP", "name": "curve_node", "parent_path": SANDBOX})
        assert ok, f"Error creando curve_node: {res}"

        setup_curve = f"""
c = op('{SANDBOX}/curve_node')
c.par.totallength = 100
c.par.outputcurve = 'linestrip'
c.par.symmetric = True
c.cook(force=True)
"""
        ok, res = live.call("execute_code", {"code": setup_curve})
        assert ok, f"Error configurando curvePOP: {res}"

        check_curve = f"""
import json
c = op('{SANDBOX}/curve_node')
print("{live.MARK}" + json.dumps({{"length": c.par.totallength.eval(), "curve_type": c.par.outputcurve.eval(), "symmetric": c.par.symmetric.eval(), "num_points": c.numPoints()}}))
"""
        ok, data = live.exec_code(check_curve)
        assert ok and data.get("symmetric") and data.get("curve_type") == "linestrip", f"curvePOP config errónea: {data}"
        print(f"PASS: curvePOP verificado exitosamente: {data}")

        # -------------------------------------------------------------
        # Test 3: normalPOP con tangentes (Red I)
        # -------------------------------------------------------------
        print("\n--- Test 3: normalPOP calculando normales y tangentes ---")
        ok, res = live.call("create_operator", {"type": "spherePOP", "name": "sphere_geom", "parent_path": SANDBOX})
        assert ok, f"Error creando sphere_geom: {res}"
        ok, res = live.call("create_operator", {"type": "normalPOP", "name": "normal_node", "parent_path": SANDBOX})
        assert ok, f"Error creando normal_node: {res}"

        ok, res = live.call("wiring", {"from_path": f"{SANDBOX}/sphere_geom", "to_path": f"{SANDBOX}/normal_node", "to_index": 0})
        assert ok, f"Error cableando sphere -> normal: {res}"

        setup_normal = f"""
n = op('{SANDBOX}/normal_node')
n.par.nml = 'alwayscompute'
n.par.tang = 'alwayscompute'
n.cook(force=True)
"""
        ok, res = live.call("execute_code", {"code": setup_normal})
        assert ok, f"Error configurando normalPOP: {res}"

        check_normal = f"""
import json
n = op('{SANDBOX}/normal_node')
pt_attrs = [a.name for a in n.pointAttributes]
vert_attrs = [a.name for a in n.vertAttributes]
print("{live.MARK}" + json.dumps({{"pt_attrs": pt_attrs, "vert_attrs": vert_attrs, "nml": n.par.nml.eval(), "tang": n.par.tang.eval()}}))
"""
        ok, data = live.exec_code(check_normal)
        assert ok and "N" in data.get("pt_attrs", []) and "T" in data.get("vert_attrs", []), f"normalPOP config errónea: {data}"
        print(f"PASS: normalPOP (N en points y T en vertices) verificado exitosamente: {data}")

        # -------------------------------------------------------------
        # Test 4: attributeconvertPOP (Red J)
        # -------------------------------------------------------------
        print("\n--- Test 4: attributeconvertPOP migrando Point -> Vertex ---")
        ok, res = live.call("create_operator", {"type": "attributeconvertPOP", "name": "att_convert", "parent_path": SANDBOX})
        assert ok, f"Error creando att_convert: {res}"

        ok, res = live.call("wiring", {"from_path": f"{SANDBOX}/sphere_geom", "to_path": f"{SANDBOX}/att_convert", "to_index": 0})
        assert ok, f"Error cableando sphere -> att_convert: {res}"

        setup_att_conv = f"""
ac = op('{SANDBOX}/att_convert')
ac.par.convertop = 'pointtovert'
ac.par.inputattrs = 'P'
ac.cook(force=True)
"""
        ok, res = live.call("execute_code", {"code": setup_att_conv})
        assert ok, f"Error configurando attributeconvertPOP: {res}"

        check_att_conv = f"""
import json
ac = op('{SANDBOX}/att_convert')
vert_attrs = [a.name for a in ac.vertAttributes]
print("{live.MARK}" + json.dumps({{"vert_attrs": vert_attrs, "convertop": ac.par.convertop.eval()}}))
"""
        ok, data = live.exec_code(check_att_conv)
        assert ok and "P" in data.get("vert_attrs", []) and data.get("convertop") == "pointtovert", f"attributeconvert config errónea: {data}"
        print(f"PASS: attributeconvertPOP (P migrado a vertAttributes) verificado exitosamente: {data}")

    finally:
        print(f"\n=== Destruyendo sandbox {SANDBOX} ===")
        live.call("delete_operator", {"path": SANDBOX})
        print("Sandbox destruido. Canvas limpio.")

if __name__ == "__main__":
    run_tests()

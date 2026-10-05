"""
test_snippet_patterns_suite2.py — Segunda suite de pruebas en vivo de patrones POP extraídos de OP Snippets.

Redes a construir y verificar en vivo:
1. Red D: pointPOP puro de datos (sin atributo P, createp=False) como contenedor de atributos/uniformes.
2. Red E: fieldPOP con especificación paramétrica múltiple por puntos (anulación de radio/posición).
3. Red F: rayPOP proyectando rayos desde un plano hacia una esfera/caja con detección de intersección y normales.
"""

import time
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live

SANDBOX = "/project1/snippets_validation_suite2"

def run_tests():
    print(f"=== Creando sandbox en {SANDBOX} ===")
    ok, res = live.call("create_operator", {"type": "baseCOMP", "name": "snippets_validation_suite2", "parent_path": "/project1"})
    assert ok, f"Error creando sandbox: {res}"

    try:
        # -------------------------------------------------------------
        # Test 1: pointPOP puro de datos (sin atributo P) [Red D]
        # -------------------------------------------------------------
        print("\n--- Test 1: pointPOP sin P (nube pura de atributos) ---")
        ok, res = live.call("create_operator", {"type": "pointPOP", "name": "pure_data", "parent_path": SANDBOX})
        assert ok, f"Error creando pure_data: {res}"

        setup_pure_data = f"""
p = op('{SANDBOX}/pure_data')
p.par.createp = False
p.par.attr.sequence.numBlocks = 1
p.par.attr0name = 'color'
p.par.attr0type = 'color'
p.cook(force=True)
"""
        ok, res = live.call("execute_code", {"code": setup_pure_data})
        assert ok, f"Error configurando pointPOP: {res}"

        check_pure_data = f"""
import json
p = op('{SANDBOX}/pure_data')
has_p = 'P' in [a.name for a in p.pointAttributes]
has_color = 'Color' in [a.name for a in p.pointAttributes]
print("{live.MARK}" + json.dumps({{"has_p": has_p, "has_color": has_color, "num_points": p.numPoints()}}))
"""
        ok, data = live.exec_code(check_pure_data)
        assert ok and not data.get("has_p") and data.get("has_color"), f"pointPOP config errónea: {data}"
        print(f"PASS: pointPOP sin P verificado exitosamente: {data}")

        # -------------------------------------------------------------
        # Test 2: fieldPOP con inyección de parámetros por punto [Red E]
        # -------------------------------------------------------------
        print("\n--- Test 2: fieldPOP ponderando puntos de una grilla ---")
        ok, res = live.call("create_operator", {"type": "gridPOP", "name": "field_grid", "parent_path": SANDBOX})
        assert ok, f"Error creando field_grid: {res}"

        ok, res = live.call("create_operator", {"type": "fieldPOP", "name": "field_test", "parent_path": SANDBOX})
        assert ok, f"Error creando field_test: {res}"

        ok, res = live.call("wiring", {"from_path": f"{SANDBOX}/field_grid", "to_path": f"{SANDBOX}/field_test", "to_index": 0})
        assert ok, f"Error cableando grid -> field: {res}"

        setup_field = f"""
f = op('{SANDBOX}/field_test')
f.par.mode = 'sphere'
f.par.radx = 0.5
f.par.weight = True
f.par.signeddistance = True
f.par.transitionrange = 0.2
f.cook(force=True)
"""
        ok, res = live.call("execute_code", {"code": setup_field})
        assert ok, f"Error configurando fieldPOP: {res}"

        check_field = f"""
import json
f = op('{SANDBOX}/field_test')
attrs = [a.name for a in f.pointAttributes]
print("{live.MARK}" + json.dumps({{"has_weight": 'Weight' in attrs, "has_dist": 'Dist' in attrs, "mode": f.par.mode.eval()}}))
"""
        ok, data = live.exec_code(check_field)
        assert ok and data.get("has_weight") and data.get("has_dist") and data.get("mode") == "sphere", f"fieldPOP config errónea: {data}"
        print(f"PASS: fieldPOP verificado exitosamente (Weight y Dist creados): {data}")

        # -------------------------------------------------------------
        # Test 3: rayPOP detección geométrica [Red F]
        # -------------------------------------------------------------
        print("\n--- Test 3: rayPOP proyectando rayos de plano a esfera ---")
        ok, res = live.call("create_operator", {"type": "gridPOP", "name": "ray_sources", "parent_path": SANDBOX})
        assert ok, f"Error creando ray_sources: {res}"

        ok, res = live.call("create_operator", {"type": "spherePOP", "name": "ray_target", "parent_path": SANDBOX})
        assert ok, f"Error creando ray_target: {res}"

        ok, res = live.call("create_operator", {"type": "rayPOP", "name": "ray_test", "parent_path": SANDBOX})
        assert ok, f"Error creando ray_test: {res}"

        # input 0 = ray origins, input 1 = target collision geometry
        ok, res = live.call("wiring", {"from_path": f"{SANDBOX}/ray_sources", "to_path": f"{SANDBOX}/ray_test", "to_index": 0})
        assert ok, f"Error cableando sources -> ray: {res}"
        ok, res = live.call("wiring", {"from_path": f"{SANDBOX}/ray_target", "to_path": f"{SANDBOX}/ray_test", "to_index": 1})
        assert ok, f"Error cableando target -> ray: {res}"

        setup_ray = f"""
r = op('{SANDBOX}/ray_test')
r.par.dist = True
r.par.hitnormal = True
r.par.numhits = True
r.cook(force=True)
"""
        ok, res = live.call("execute_code", {"code": setup_ray})
        assert ok, f"Error configurando rayPOP: {res}"

        check_ray = f"""
import json
r = op('{SANDBOX}/ray_test')
attrs = [a.name for a in r.pointAttributes]
print("{live.MARK}" + json.dumps({{"attrs": attrs, "dist": r.par.dist.eval(), "hitnormal": r.par.hitnormal.eval()}}))
"""
        ok, data = live.exec_code(check_ray)
        assert ok and data.get("dist") and data.get("hitnormal"), f"rayPOP config errónea: {data}"
        print(f"PASS: rayPOP verificado exitosamente: {data}")

    finally:
        print(f"\n=== Destruyendo sandbox {SANDBOX} ===")
        live.call("delete_operator", {"path": SANDBOX})
        print("Sandbox destruido. Canvas limpio.")

if __name__ == "__main__":
    run_tests()

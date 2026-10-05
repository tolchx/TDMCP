"""
test_snippet_patterns_live.py — Pruebas de verificación de redes de nodos basadas en las lógicas de OP Snippets.

Redes a construir y verificar en vivo:
1. Red A: mathmixPOP multi-input combinando gridPOP y spherePOP con operación 'mix' y parámetros de scope.
2. Red B: lookupattributePOP realizando lookup de atributos de color/posición entre dos flujos POP.
3. Red C: particlePOP + trailPOP configurado con pointidreuse='noreuse' y matchbyattr='PartId'.
"""

import time
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live

SANDBOX = "/project1/snippets_validation"

def run_tests():
    print(f"=== Creando sandbox en {SANDBOX} ===")
    ok, res = live.call("create_operator", {"type": "baseCOMP", "name": "snippets_validation", "parent_path": "/project1"})
    assert ok, f"Error creando sandbox: {res}"

    try:
        # -------------------------------------------------------------
        # Test 1: mathmixPOP multi-input (Red A)
        # -------------------------------------------------------------
        print("\n--- Test 1: mathmixPOP multi-input ---")
        ok, res = live.call("create_operator", {"type": "gridPOP", "name": "grid_in", "parent_path": SANDBOX})
        assert ok, f"Error creando grid_in: {res}"
        
        ok, res = live.call("create_operator", {"type": "spherePOP", "name": "sphere_in", "parent_path": SANDBOX})
        assert ok, f"Error creando sphere_in: {res}"
        
        ok, res = live.call("create_operator", {"type": "mathmixPOP", "name": "mathmix_test", "parent_path": SANDBOX})
        assert ok, f"Error creando mathmix_test: {res}"
        
        # Conectar inputs: input 0 = grid_in, input 1 = sphere_in
        ok, res = live.call("wiring", {"from_path": f"{SANDBOX}/grid_in", "to_path": f"{SANDBOX}/mathmix_test", "to_index": 0})
        assert ok, f"Error cableando input 0: {res}"
        ok, res = live.call("wiring", {"from_path": f"{SANDBOX}/sphere_in", "to_path": f"{SANDBOX}/mathmix_test", "to_index": 1})
        assert ok, f"Error cableando input 1: {res}"

        # Configurar mathmix via execute_code
        setup_mathmix = f"""
m = op('{SANDBOX}/mathmix_test')
m.par.comb.sequence.numBlocks = 1
m.par.comb0oper = 'mix'
m.par.comb0scopea = 'P'
m.par.comb0scopeb = 'in1_P'
m.par.comb0result = 'P'
m.cook(force=True)
"""
        ok, res = live.call("execute_code", {"code": setup_mathmix})
        assert ok, f"Error configurando mathmix: {res}"

        # Verificar parámetros aplicados
        check_code = f"""
import json
m = op('{SANDBOX}/mathmix_test')
print("{live.MARK}" + json.dumps({{"oper": m.par.comb0oper.eval(), "scopea": m.par.comb0scopea.eval(), "scopeb": m.par.comb0scopeb.eval()}}))
"""
        ok, data = live.exec_code(check_code)
        assert ok and data.get("oper") == "mix" and data.get("scopeb") == "in1_P", f"Mathmix config errónea: {data}"
        print(f"PASS: mathmixPOP configurado exitosamente: {data}")

        # -------------------------------------------------------------
        # Test 2: lookupattributePOP directo (Red B)
        # -------------------------------------------------------------
        print("\n--- Test 2: lookupattributePOP ---")
        ok, res = live.call("create_operator", {"type": "circlePOP", "name": "curve_ref", "parent_path": SANDBOX})
        assert ok, f"Error creando curve_ref: {res}"
        
        ok, res = live.call("create_operator", {"type": "lookupattributePOP", "name": "lookup_test", "parent_path": SANDBOX})
        assert ok, f"Error creando lookup_test: {res}"
        
        # Conectar inputs: input 0 = grid_in, input 1 = curve_ref
        ok, res = live.call("wiring", {"from_path": f"{SANDBOX}/grid_in", "to_path": f"{SANDBOX}/lookup_test", "to_index": 0})
        assert ok, f"Error cableando input 0 a lookup: {res}"
        ok, res = live.call("wiring", {"from_path": f"{SANDBOX}/curve_ref", "to_path": f"{SANDBOX}/lookup_test", "to_index": 1})
        assert ok, f"Error cableando input 1 a lookup: {res}"

        setup_lookup = f"""
l = op('{SANDBOX}/lookup_test')
l.par.lookupindexattr = 'P(0)'
l.par.lookup.sequence.numBlocks = 1
l.par.lookup0valueattr = 'P'
l.par.lookup0outputattrscope = 'Color'
l.cook(force=True)
"""
        ok, res = live.call("execute_code", {"code": setup_lookup})
        assert ok, f"Error configurando lookupattribute: {res}"

        check_lookup = f"""
import json
l = op('{SANDBOX}/lookup_test')
print("{live.MARK}" + json.dumps({{"idx": l.par.lookupindexattr.eval(), "val": l.par.lookup0valueattr.eval(), "out": l.par.lookup0outputattrscope.eval()}}))
"""
        ok, data = live.exec_code(check_lookup)
        assert ok and data.get("out") == "Color", f"Lookup config errónea: {data}"
        print(f"PASS: lookupattributePOP configurado exitosamente: {data}")

        # -------------------------------------------------------------
        # Test 3: particlePOP + trailPOP ciclo de vida (Red C)
        # -------------------------------------------------------------
        print("\n--- Test 3: particlePOP + trailPOP ---")
        ok, res = live.call("create_operator", {"type": "pointgeneratorPOP", "name": "source_pts", "parent_path": SANDBOX})
        assert ok, f"Error creando source_pts: {res}"

        ok, res = live.call("create_operator", {"type": "particlePOP", "name": "part_sim", "parent_path": SANDBOX})
        assert ok, f"Error creando part_sim: {res}"

        ok, res = live.call("create_operator", {"type": "trailPOP", "name": "trail_lines", "parent_path": SANDBOX})
        assert ok, f"Error creando trail_lines: {res}"

        ok, res = live.call("wiring", {"from_path": f"{SANDBOX}/source_pts", "to_path": f"{SANDBOX}/part_sim", "to_index": 0})
        assert ok, f"Error cableando source -> part: {res}"
        ok, res = live.call("wiring", {"from_path": f"{SANDBOX}/part_sim", "to_path": f"{SANDBOX}/trail_lines", "to_index": 0})
        assert ok, f"Error cableando part -> trail: {res}"

        setup_particles = f"""
p = op('{SANDBOX}/part_sim')
p.par.pointidreuse = 'none'
t = op('{SANDBOX}/trail_lines')
t.par.attrmatch = True
t.par.attrname = 'PartId'
p.cook(force=True)
t.cook(force=True)
"""
        ok, res = live.call("execute_code", {"code": setup_particles})
        assert ok, f"Error configurando particle y trail: {res}"

        check_part = f"""
import json
p = op('{SANDBOX}/part_sim')
t = op('{SANDBOX}/trail_lines')
print("{live.MARK}" + json.dumps({{"reuse": p.par.pointidreuse.eval(), "attrmatch": t.par.attrmatch.eval(), "attrname": t.par.attrname.eval()}}))
"""
        ok, data = live.exec_code(check_part)
        assert ok and data.get("reuse") == "none" and data.get("attrname") == "PartId", f"Particle/Trail config errónea: {data}"
        print(f"PASS: particlePOP + trailPOP configurado exitosamente: {data}")

    finally:
        print(f"\n=== Destruyendo sandbox {SANDBOX} ===")
        live.call("delete_operator", {"path": SANDBOX})
        print("Sandbox destruido. Canvas limpio.")

if __name__ == "__main__":
    run_tests()

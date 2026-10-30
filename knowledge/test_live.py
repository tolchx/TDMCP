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
st = live.t_status({})
if not st.get("td_up"):
    import time
    toe_path = os.path.join(os.path.dirname(HERE), "local", "TDMCP.toe")
    if os.path.exists(toe_path):
        print(f"TD cerrado; abriendo {toe_path}...")
        os.startfile(toe_path)
        for _ in range(30):
            time.sleep(1.5)
            st = live.t_status({})
            if st.get("td_up"):
                break
show("status", st)
assert st.get("td_up") is True, f"TouchDesigner no levantó: {st}"

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
b.inputConnectors[0].connect(a); c.inputConnectors[0].connect(b); c.inputConnectors[1].connect(a)
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

print("\n### 12. td_measure (CHOP + TOP)")
show("measure CHOP", live.t_measure({"path": SB + "/k"}), 800)
show("measure TOP", live.t_measure({"path": SB + "/a"}), 800)

print("\n### 13. td_glsl_apply (POP shader + auto Create Attributes + compile check) + td_measure POP")
live.exec_code(r'''
import json
sb = op('/hermes_live')
sp = sb.create('spherePOP', 'sp')
sp.cook(force=True)
print('<<JSON>>' + json.dumps({'ok': True, 'sp': sp.path}))
''')
glsl_res = live.t_glsl_apply({
    "parent_path": SB,
    "name": "glsl_test",
    "family": "pop",
    "source_path": SB + "/sp",
    "uniforms": {"uScale": [1.5, 1.5, 1.5, 1.0]},
    "code": (
        "void main() {\n"
        "    const uint id = TDIndex();\n"
        "    if (id >= TDNumElements()) return;\n"
        "    P[id] = TDIn_P(0, id) * uScale.xyz;\n"
        "    Color[id] = vec4(1.0, 0.5, 0.2, 1.0);\n"
        "}\n"
    ),
})
show("glsl_apply POP", glsl_res, 1200)
assert glsl_res.get("ok") is True, f"td_glsl_apply falló: {glsl_res}"
pop_meas = live.t_measure({"path": SB + "/glsl_test"})
show("measure POP (glsl_test)", pop_meas, 900)
assert pop_meas.get("numPoints", 0) > 0, f"glsl_test sin puntos: {pop_meas}"

print("\n### 14. td_explore_project")
exp_res = live.t_explore_project({"root_path": SB})
show("explore_project", exp_res, 1000)
assert exp_res.get("ok") is True and exp_res.get("total_operators", 0) >= 7

print("\n### 15. td_compare_networks")
live.exec_code(r'''
import json
root = op('/')
sb2 = root.create('baseCOMP', 'hermes_live_b')
a2 = sb2.create('noiseTOP', 'a')
a2.par.seed = 42
print('<<JSON>>' + json.dumps({'ok': True}))
''')
cmp_res = live.t_compare_networks({"path_a": SB, "path_b": "/hermes_live_b"})
show("compare_networks", cmp_res, 1000)
assert cmp_res.get("ok") is True and cmp_res.get("identical") is False

print("\n### 16. td_spatial_context")
sp_ctx = live.t_spatial_context({})
show("spatial_context", sp_ctx, 800)
assert sp_ctx.get("ok") is True and "timeline" in sp_ctx

print("\n### 17. td_build_pop_render (Pilar 1)")
pop_ren = live.t_build_pop_render({
    "parent_path": SB,
    "name": "p1_scene",
    "source_pop": SB + "/glsl_test",
    "primitive_mode": "points",
    "material": "pointsprite",
    "resolution": "640x360",
    "point_size": 5.0,
})
show("build_pop_render", pop_ren, 1200)
assert pop_ren.get("ok") is True and pop_ren.get("torus1_deleted") is True and pop_ren.get("numPrims", 0) > 0, f"td_build_pop_render falló: {pop_ren}"

print("\n### 18. td_verify_network (Pilar 2)")
ver_res = live.t_verify_network({"container_path": SB, "render_top": pop_ren.get("out_top_path")})
show("verify_network", ver_res, 1200)
assert ver_res.get("ok") is True and ver_res.get("verdict") == "PASS", f"td_verify_network falló: {ver_res}"

print("\n### 19. td_instantiate_template (Pilar 1)")
tpl_res = live.t_instantiate_template({
    "template_name": "feedback_loop_top",
    "parent_path": SB,
    "container_name": "tpl_feedback",
    "clear_first": True,
})
show("instantiate_template", tpl_res, 1200)
assert tpl_res.get("ok") is True and tpl_res.get("created_count", 0) >= 4, f"td_instantiate_template falló: {tpl_res}"

print("\n### 20. td_profile_network (Pilar 5)")
prof_res = live.t_profile_network({"root_path": SB, "force_cook": True})
show("profile_network", prof_res, 1200)
assert prof_res.get("ok") is True and prof_res.get("scanned_nodes", 0) >= 10, f"td_profile_network falló: {prof_res}"

print("\n### 21. td_scaffold_component (Pilar 6)")
scaf_res = live.t_scaffold_component({
    "comp_path": SB,
    "page_name": "FXControls",
    "custom_pars": [
        {"name": "Noiseamp", "style": "Float", "label": "Noise Amp", "default": 0.75, "min": 0.0, "max": 2.0, "targets": ["a.amp"]},
    ],
    "extension_class": "HermesFx",
    "extension_code": "class HermesFx:\n    def __init__(self, ownerComp):\n        self.ownerComp = ownerComp\n    def Ping(self):\n        return 'pong'\n",
})
show("scaffold_component", scaf_res, 1200)
assert scaf_res.get("ok") is True and scaf_res.get("extension", {}).get("initialized") is True, f"td_scaffold_component falló: {scaf_res}"

print("\n### 22. td_wire_reactive (Pilar 7)")
wire_res = live.t_wire_reactive({
    "source_chop": SB + "/k",
    "target_op": SB + "/b",
    "target_par": "gamma1",
    "target_min": 0.8,
    "target_max": 1.4,
    "lag_up": 0.02,
    "lag_down": 0.05,
})
show("wire_reactive", wire_res, 1200)
assert wire_res.get("ok") is True and len(wire_res.get("chain_nodes", [])) >= 3, f"td_wire_reactive falló: {wire_res}"

print("\n### 23. td_frame_camera_to_geo (Pilar 8a)")
cam_res = live.t_frame_camera_to_geo({"container_path": SB, "padding": 1.4})
show("frame_camera_to_geo", cam_res, 1200)
assert cam_res.get("ok") is True and cam_res.get("computed_distance", 0) > 0, f"td_frame_camera_to_geo falló: {cam_res}"

print("\n### 24. td_visual_diff (Pilar 8b)")
vdiff_res = live.t_visual_diff({"top_a": SB + "/a", "top_b": SB + "/p1_scene_out"})
show("visual_diff", vdiff_res, 1000)
assert vdiff_res.get("ok") is True and vdiff_res.get("verdict") == "SIGNIFICANT_CHANGE", f"td_visual_diff falló: {vdiff_res}"

print("\n### 25. td_control_simulation (Pilar 9)")
sim_res = live.t_control_simulation({"container_path": SB, "action": "reset_and_preroll", "preroll_steps": 6})
show("control_simulation", sim_res, 1200)
assert sim_res.get("ok") is True and sim_res.get("simulation_state") in ("STABLE_DYNAMIC", "STABLE_STATIC"), f"td_control_simulation falló: {sim_res}"

print("\n### 26. td_harvest_pattern + re-instanciación (Pilar 10)")
harv_res = live.t_harvest_pattern({
    "container_path": SB + "/tpl_feedback",
    "name": "hermes-test-harvest",
    "description": "Template de prueba cosechado en vivo",
    "tags": "test, feedback, top",
})
show("harvest_pattern", harv_res, 1000)
assert harv_res.get("ok") is True and os.path.exists(harv_res.get("template_json", "")), f"td_harvest_pattern falló: {harv_res}"
reinst_res = live.t_instantiate_template({
    "template_name": "hermes-test-harvest",
    "parent_path": SB,
    "container_name": "tpl_reinstantiated",
    "clear_first": True,
})
show("re-instantiate harvested pattern", reinst_res, 1000)
assert reinst_res.get("ok") is True and reinst_res.get("created_count", 0) >= 5, f"re-instanciación falló: {reinst_res}"

print("\n### 27. cleanup")
for p in (SB, "/hermes_live_b"):
    ok, r = live.call("delete_operator", {"path": p})
    print(p, "->", json.dumps(r, ensure_ascii=False)[:160])
for f in (f1, f2, harv_res.get("template_json"), harv_res.get("template_tdxn")):
    if f and os.path.exists(f):
        os.remove(f)
print("temporales borrados")

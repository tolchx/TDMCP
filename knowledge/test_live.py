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
assert ver_res.get("checks", {}).get("layout_tidy_ok") is True, f"layout_tidy_ok falló: {ver_res}"
assert ver_res.get("tidy_layout") is not None, f"tidy_layout ausente: {ver_res}"

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

print("\n### 27. td_build_control_panel (Pilar 11)")
panel_res = live.t_build_control_panel({
    "parent_path": SB,
    "name": "studio_ui",
    "target_ops": [SB],
    "preview_top": SB + "/p1_scene_out",
    "title": "HERMES STUDIO UI",
    "create_window": True,
})
show("build_control_panel", panel_res, 1200)
assert panel_res.get("ok") is True and len(panel_res.get("parameter_widgets", [])) >= 1 and panel_res.get("window_comp_path"), f"td_build_control_panel falló: {panel_res}"

print("\n### 28. td_render_contact_sheet (Pilar 12)")
cs_res = live.t_render_contact_sheet({
    "top_path": SB + "/p1_scene_out",
    "num_frames": 4,
    "step_frames": 2,
    "cols": 2,
    "tile_width": 160,
})
show("render_contact_sheet", cs_res, 1200)
assert cs_res.get("ok") is True and os.path.exists(cs_res.get("contact_sheet_path", "")), f"td_render_contact_sheet falló: {cs_res}"

print("\n### 29. td_setup_audio_analyzer (Pilar 13)")
aud_res = live.t_setup_audio_analyzer({
    "parent_path": SB,
    "name": "audio_fx",
    "source_type": "test_oscillator",
    "bindings": [
        {"band": "bass", "target_op": SB + "/b", "target_par": "brightness1", "scale": 0.5, "offset": 0.8},
    ],
})
show("setup_audio_analyzer", aud_res, 1200)
assert aud_res.get("ok") is True and "bass" in aud_res.get("live_channels", {}) and len(aud_res.get("wired_bindings", [])) == 1, f"td_setup_audio_analyzer falló: {aud_res}"

print("\n### 30. td_setup_scene_switcher (Pilar 14)")
sw_res = live.t_setup_scene_switcher({
    "parent_path": SB,
    "name": "master_switcher",
    "scene_paths": [SB + "/tpl_feedback", SB + "/tpl_reinstantiated"],
    "active_scene": 0,
    "transition_seconds": 0.8,
    "smart_cooking": True,
})
show("setup_scene_switcher", sw_res, 1200)
assert sw_res.get("ok") is True and len(sw_res.get("scenes", [])) == 2 and sw_res["scenes"][0]["allow_cooking"] is True and sw_res["scenes"][1]["allow_cooking"] is False, f"td_setup_scene_switcher falló: {sw_res}"

print("\n### 31. td_preset_manager (Pilar 15)")
pr_cap_a = live.t_preset_manager({"comp_path": SB, "action": "capture", "preset_name": "calm"})
live.exec_code(f"import json; op({SB!r}).par.Noiseamp = 1.8; print('<<JSON>>' + json.dumps({{'ok': True}}))")
pr_cap_b = live.t_preset_manager({"comp_path": SB, "action": "capture", "preset_name": "intense"})
pr_blend = live.t_preset_manager({"comp_path": SB, "action": "blend", "preset_a": "calm", "preset_b": "intense", "alpha": 0.5})
show("preset_manager (blend)", pr_blend, 1200)
assert pr_blend.get("ok") is True and set(pr_blend.get("presets_available", [])) >= {"calm", "intense"} and pr_blend.get("parameters_affected", 0) >= 1, f"td_preset_manager falló: {pr_blend}"

print("\n### 32. td_setup_gpu_instancing (Pilar 16)")
inst_res = live.t_setup_gpu_instancing({
    "parent_path": SB,
    "name": "my_instances",
    "instance_source": SB + "/glsl_test",
    "base_geometry": "box",
    "create_render_pipeline": True,
})
show("setup_gpu_instancing", inst_res, 1200)
assert inst_res.get("ok") is True and inst_res.get("instancing_enabled") is True, f"td_setup_gpu_instancing falló: {inst_res}"

print("\n### 33. td_setup_postfx_chain (Pilar 17)")
postfx_res = live.t_setup_postfx_chain({
    "parent_path": SB,
    "name": "master_postfx",
    "input_top": SB + "/p1_scene_out",
})
show("setup_postfx_chain", postfx_res, 1200)
assert postfx_res.get("ok") is True and len(postfx_res.get("custom_parameters", [])) >= 5, f"td_setup_postfx_chain falló: {postfx_res}"

print("\n### 34. td_setup_io_bridge (Pilar 18)")
io_res = live.t_setup_io_bridge({
    "parent_path": SB,
    "name": "osc_bridge",
    "protocol": "osc",
    "port": 7120,
    "loopback_test": True,
})
show("setup_io_bridge", io_res, 1200)
assert io_res.get("ok") is True and io_res.get("out_channel_path"), f"td_setup_io_bridge falló: {io_res}"

print("\n### 35. td_record_movie (Pilar 19)")
rec_res = live.t_record_movie({
    "top_path": SB + "/p1_scene_out",
    "num_frames": 6,
    "fps": 30.0,
    "reset_first": False,
})
show("record_movie", rec_res, 1200)
assert rec_res.get("ok") is True and os.path.exists(rec_res.get("file_path", "")), f"td_record_movie falló: {rec_res}"

print("\n### 36. td_heal_network (Pilar 20)")
# Crear un geometryCOMP con torus1 y desactivar flags para probar que td_heal_network lo repara
live.exec_code(f'''
import json
sb = op({SB!r})
g = sb.create(geometryCOMP, 'sick_geo')
p = g.create(spherePOP, 'p_target')
p.display = False
p.render = False
print('<<JSON>>' + json.dumps({{'ok': True}}))
''')
heal_dry = live.t_heal_network({"container_path": SB, "dry_run": True})
show("heal_network (dry_run)", heal_dry, 1000)
assert heal_dry.get("ok") is True and heal_dry.get("fixes_count", 0) >= 1, f"heal dry_run falló: {heal_dry}"

heal_real = live.t_heal_network({"container_path": SB, "dry_run": False})
show("heal_network (applied)", heal_real, 1000)
assert heal_real.get("ok") is True and heal_real.get("fixes_count", 0) >= 1, f"heal real falló: {heal_real}"

print("\n### 37. td_setup_display_canvas (Pilar 21)")
canvas_res = live.t_setup_display_canvas({
    "parent_path": SB,
    "name": "master_canvas",
    "num_displays": 2,
    "display_width": 1920,
    "display_height": 1080,
    "overlap_pixels": 80,
    "input_top": SB + "/p1_scene_out",
    "test_pattern": True,
})
show("setup_display_canvas", canvas_res, 1200)
assert canvas_res.get("ok") is True and len(canvas_res.get("displays", [])) == 2, f"setup_display_canvas falló: {canvas_res}"

print("\n### 38. td_setup_pbr_stage (Pilar 22)")
pbr_res = live.t_setup_pbr_stage({
    "parent_path": SB,
    "name": "stage_pbr",
    "include_ground": True,
    "resolution": "1280x720",
})
show("setup_pbr_stage", pbr_res, 1200)
assert pbr_res.get("ok") is True and len(pbr_res.get("lights", [])) == 4 and pbr_res.get("render_top"), f"setup_pbr_stage falló: {pbr_res}"

print("\n### 39. td_sync_external_tox (Pilar 23)")
tox_insp = live.t_sync_external_tox({"comp_path": SB, "action": "inspect"})
show("sync_external_tox (inspect)", tox_insp, 1200)
assert tox_insp.get("ok") is True and tox_insp.get("total_comps_audited", 0) >= 1, f"tox inspect falló: {tox_insp}"

tox_tmp = os.path.join(tempfile.gettempdir(), "test_stage_pbr.tox").replace("\\", "/")
tox_exp = live.t_sync_external_tox({"comp_path": SB + "/stage_pbr", "action": "export", "tox_path": tox_tmp})
show("sync_external_tox (export)", tox_exp, 1000)
assert tox_exp.get("ok") is True and os.path.exists(tox_tmp), f"tox export falló: {tox_exp}"

tox_rel = live.t_sync_external_tox({"comp_path": SB + "/stage_pbr", "action": "reload"})
show("sync_external_tox (reload)", tox_rel, 1000)
assert tox_rel.get("ok") is True, f"tox reload falló: {tox_rel}"

print("\n### 40. td_setup_ai_stream (Pilar 24)")
ai_res = live.t_setup_ai_stream({
    "parent_path": SB,
    "name": "ai_gateway",
    "backend": "comfyui",
    "server_url": "http://127.0.0.1:8188",
    "input_top": SB + "/p1_scene_out",
})
show("setup_ai_stream", ai_res, 1200)
assert ai_res.get("ok") is True and ai_res.get("queue_table") and ai_res.get("api_client"), f"setup_ai_stream falló: {ai_res}"

print("\n### 41. td_benchmark_longevity (Pilar 25)")
soak_res = live.t_benchmark_longevity({
    "container_path": SB,
    "duration_frames": 20,
    "sample_interval": 5,
    "audit_buffers": True,
})
show("benchmark_longevity", soak_res, 1200)
assert soak_res.get("ok") is True and soak_res.get("verdict") in ("EXHIBITION_READY", "MONITOR_RECOMMENDED", "MEMORY_LEAK_RISK"), f"benchmark_longevity falló: {soak_res}"

print("\n### 42. td_network_tidy (NetworkTidy Layout & Undo)")
# Setup messy nodes inside a sub-container in SB
live.exec_code(f'''
import json
sb = op({SB!r})
sub = sb.op('tidy_test') or sb.create(baseCOMP, 'tidy_test')
for c in list(sub.children): c.destroy()
o1 = sub.create(constantTOP, 'src')
o2 = sub.create(levelTOP, 'filter')
o3 = sub.create(nullTOP, 'final_out')
o4 = sub.create(noiseCHOP, 'loose_noise')
o1.outputConnectors[0].connect(o2)
o2.outputConnectors[0].connect(o3)
o1.nodeX, o1.nodeY = 800, 100
o2.nodeX, o2.nodeY = 300, 500
o3.nodeX, o3.nodeY = -150, 0
o4.nodeX, o4.nodeY = 900, 900
print('<<JSON>>' + json.dumps({{'ok': True}}))
''')
tidy_res = live.t_network_tidy({
    "network_path": SB + "/tidy_test",
    "action": "tidy",
    "column_gap": 60,
    "row_gap": 30,
    "straighten_wires": True,
    "grid_loose": True,
    "animate": False,
})
show("network_tidy (tidy)", tidy_res, 1200)
assert tidy_res.get("ok") is True and tidy_res.get("moved_count", 0) >= 3, f"network_tidy tidy falló: {tidy_res}"

undo_res = live.t_network_tidy({
    "network_path": SB + "/tidy_test",
    "action": "undo",
})
show("network_tidy (undo)", undo_res, 1200)
assert undo_res.get("ok") is True and undo_res.get("restored_nodes_count", 0) >= 3, f"network_tidy undo falló: {undo_res}"

print("\n### 43. cleanup")
for p in (SB, "/hermes_live_b"):
    ok, r = live.call("delete_operator", {"path": p})
    print(p, "->", json.dumps(r, ensure_ascii=False)[:160])
for f in (f1, f2, harv_res.get("template_json"), harv_res.get("template_tdxn"), cs_res.get("contact_sheet_path"), rec_res.get("file_path"), tox_tmp):
    if f and os.path.exists(f):
        try: os.remove(f)
        except: pass
print("temporales borrados")
print("\nALL 43 LIVE STAGES PASSED OK.")

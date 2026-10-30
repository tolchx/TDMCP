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

print("\n### 21. cleanup")
for p in (SB, "/hermes_live_b"):
    ok, r = live.call("delete_operator", {"path": p})
    print(p, "->", json.dumps(r, ensure_ascii=False)[:160])
for f in (f1, f2):
    if os.path.exists(f):
        os.remove(f)
print("temporales borrados")

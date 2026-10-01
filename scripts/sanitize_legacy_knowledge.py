#!/usr/bin/env python3
"""Sanitiza y corrige inconsistencias heredadas del MCP viejo.

Corrige:
1. Reemplazo de operadores inexistentes (renderPOP, colorPOP, forcePOP, dragPOP, lookupPOP, spritePOP, panelCOMP)
   por sus equivalentes reales verificados en TouchDesigner 2025.
2. Reemplazo de pointgenPOP por pointgeneratorPOP en workflows y documentación.
3. Reemplazo de lookupattPOP por lookuptablePOP y lookuptexPOP por lookuptexturePOP.
4. Actualización de recipes, templates, topology y TYPE_SYNONYMS.
"""
import json, os, re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB = os.path.join(HERE, "knowledge", "kb")

def sanitize_synonyms_and_recipes():
    ts_p = os.path.join(KB, "ts-extract", "ts-data.json")
    if not os.path.exists(ts_p):
        return
    with open(ts_p, "r", encoding="utf-8") as f:
        d = json.load(f)

    syn = d.get("semantic", {}).get("TYPE_SYNONYMS", {})
    if "renderPOP" in syn:
        syn.setdefault("poptoTOP", []).extend(syn.pop("renderPOP"))
    if "colorPOP" in syn:
        syn.setdefault("attributePOP", []).extend(syn.pop("colorPOP"))
    if "forcePOP" in syn:
        syn.setdefault("noisePOP", []).extend(syn.pop("forcePOP"))
    if "dragPOP" in syn:
        syn.setdefault("particlePOP", []).extend(syn.pop("dragPOP"))
    if "lookupPOP" in syn:
        syn.setdefault("lookuptablePOP", []).extend(syn.pop("lookupPOP"))
    if "spritePOP" in syn:
        syn.setdefault("pointspriteMAT", []).extend(syn.pop("spritePOP"))
    if "panelCOMP" in syn:
        syn.setdefault("containerCOMP", []).extend(syn.pop("panelCOMP"))

    syn["pointgeneratorPOP"] = ["point generator", "point gen", "point generator pop", "generate points", "ray points"]
    syn["convertPOP"] = ["convert pop", "topointprims", "point primitives", "points to primitives"]
    syn["pointspriteMAT"] = ["point sprite", "pointsprite", "pointsprite mat", "sprite mat", "particle sprite material"]

    # Recipes
    recipes = d.get("recipes", {}).get("listRecipes", [])
    for r in recipes:
        if r.get("name") == "particle-system-pop":
            r["description"] = "GPU particle system with feedback solver loop: spherePOP emits seed points, particlePOP simulates physics, noisePOP adds turbulence, trailPOP draws trails, poptoTOP converts to texture data. A nullPOP serves as the feedback target."
            r["nodes"] = [n if n != "renderPOP" else "poptoTOP" for n in r.get("nodes", [])]
            code = r.get("pythonCode", "")
            code = code.replace("render = parent.create(renderPOP, 'render')", "p2t = parent.create(poptoTOP, 'pop_to_top')")
            code = code.replace("render.inputConnectors[0].connect(trail)", "p2t.inputConnectors[0].connect(trail)")
            code = code.replace("output.inputConnectors[0].connect(render)", "output.inputConnectors[0].connect(p2t)")
            code = code.replace("render.nodeX", "p2t.nodeX")
            code = code.replace("render.nodeY", "p2t.nodeY")
            code = code.replace("render.par.camera = 'top'", "# poptoTOP converts point buffer directly to 2D texture data")
            code = code.replace("render.par.displaypoints = False", "p2t.par.fillmode = 'fill'")
            code = code.replace("render.par.pointscale = 2.0", "p2t.par.rgbamode = 'rgb'")
            r["pythonCode"] = code
            r["gotchas"] = [g for g in r.get("gotchas", []) if "renderPOP" not in g]
            r["gotchas"].append("POP rendering: to render 3D particles to an image, use geometryCOMP (with default torus1 cleared) + pointspriteMAT + cameraCOMP + renderTOP (Contract C2); to convert points directly to a data texture without camera, use poptoTOP.")

    # Templates
    templates = d.get("templates", {}).get("NETWORK_TEMPLATES", [])
    for t in templates:
        if t.get("name") == "particle-system-basic":
            t["description"] = t["description"].replace("renderPOP", "poptoTOP")
            for op_entry in t.get("operators", []):
                if op_entry.get("opType") == "renderPOP":
                    op_entry["opType"] = "poptoTOP"
                    op_entry["label"] = "POP to TOP"
            for conn in t.get("connections", []):
                if conn.get("to") == "render":
                    conn["note"] = conn["note"].replace("renderPOP", "poptoTOP")
                if conn.get("from") == "render":
                    conn["note"] = conn["note"].replace("renderPOP", "poptoTOP")
            builder = t.get("pythonBuilder", "")
            builder = builder.replace("render = parent.create(renderPOP, 'render')", "p2t = parent.create(poptoTOP, 'pop_to_top')")
            builder = builder.replace("render.inputConnectors[0].connect(trail)", "p2t.inputConnectors[0].connect(trail)")
            builder = builder.replace("output.inputConnectors[0].connect(render)", "output.inputConnectors[0].connect(p2t)")
            builder = builder.replace("render.nodeX", "p2t.nodeX")
            builder = builder.replace("render.nodeY", "p2t.nodeY")
            t["pythonBuilder"] = builder

    with open(ts_p, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
    print("  Sanitizado ts-extract/ts-data.json")


def sanitize_builtin_templates():
    bt_p = os.path.join(KB, "templates", "builtin-templates.json")
    if not os.path.exists(bt_p):
        return
    with open(bt_p, "r", encoding="utf-8") as f:
        bt = json.load(f)
    for t in bt.get("templates", []):
        if t.get("name") == "particle-system-basic":
            t["description"] = t["description"].replace("renderPOP", "poptoTOP")
            for op_entry in t.get("operators", []):
                if op_entry.get("opType") == "renderPOP":
                    op_entry["opType"] = "poptoTOP"
                    op_entry["label"] = "POP to TOP"
            for conn in t.get("connections", []):
                conn["note"] = conn["note"].replace("renderPOP", "poptoTOP")
            b = t.get("pythonBuilder", "")
            b = b.replace("render = parent.create(renderPOP, 'render')", "p2t = parent.create(poptoTOP, 'pop_to_top')")
            b = b.replace("render.inputConnectors[0].connect(trail)", "p2t.inputConnectors[0].connect(trail)")
            b = b.replace("output.inputConnectors[0].connect(render)", "output.inputConnectors[0].connect(p2t)")
            b = b.replace("render.nodeX", "p2t.nodeX")
            b = b.replace("render.nodeY", "p2t.nodeY")
            t["pythonBuilder"] = b
    with open(bt_p, "w", encoding="utf-8") as f:
        json.dump(bt, f, indent=2, ensure_ascii=False)
    print("  Sanitizado templates/builtin-templates.json")


def sanitize_workflows_and_tutorials():
    wf_fixes = {
        "ray-pop-physics.md": [("pointgenPOP", "pointgeneratorPOP"), ("pointgen POP", "pointgenerator POP")],
        "particle-follow-curve.md": [("pointgenPOP", "pointgeneratorPOP"), ("pointgen POP", "pointgenerator POP")],
        "nebrarray-pathtracer.md": [("pointgenPOP", "pointgeneratorPOP"), ("pointgen POP", "pointgenerator POP")],
        "phased-blending.md": [("lookupattPOP", "lookuptablePOP")],
        "pop-ray-scene.md": [("lookuptexPOP", "lookuptexturePOP")],
    }
    wf_dir = os.path.join(KB, "workflows")
    if os.path.isdir(wf_dir):
        for fn, pairs in wf_fixes.items():
            p = os.path.join(wf_dir, fn)
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                for old, new in pairs:
                    content = content.replace(old, new)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"  Sanitizado workflow: {fn}")

    tut_p = os.path.join(KB, "tutorials", "gaussian-splatting.md")
    if os.path.exists(tut_p):
        with open(tut_p, "r", encoding="utf-8", errors="replace") as f:
            c = f.read().replace("pointfileselectPOP", "pointfileinPOP")
        with open(tut_p, "w", encoding="utf-8") as f:
            f.write(c)
        print("  Sanitizado tutorial: gaussian-splatting.md")

    graph_p = os.path.join(KB, "workflows", "graphs", "particle-system-basic.json")
    if os.path.exists(graph_p):
        with open(graph_p, "r", encoding="utf-8") as f:
            g = json.load(f)
        g["description"] = g.get("description", "").replace("renderPOP", "poptoTOP")
        for n in g.get("nodes", []):
            if n.get("opType") == "renderPOP":
                n["opType"] = "poptoTOP"
                n["label"] = "POP to TOP"
        with open(graph_p, "w", encoding="utf-8") as f:
            json.dump(g, f, indent=2, ensure_ascii=False)
        print("  Sanitizado graph particle-system-basic.json")

    top_p = os.path.join(KB, "real-world-topology.json")
    if os.path.exists(top_p):
        with open(top_p, "r", encoding="utf-8") as f:
            t_content = f.read().replace("renderPOP", "poptoTOP")
        with open(top_p, "w", encoding="utf-8") as f:
            f.write(t_content)
        print("  Sanitizado real-world-topology.json")


def main():
    print("[sanitize] Aplicando correcciones de compatibilidad TD 2025+ a la KB:")
    sanitize_synonyms_and_recipes()
    sanitize_builtin_templates()
    sanitize_workflows_and_tutorials()
    print("[sanitize] Completado exitosamente.")

if __name__ == "__main__":
    main()

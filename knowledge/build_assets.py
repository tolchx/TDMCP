r"""Extrae los assets de conocimiento al port offline.

Uso:  python build_assets.py [--repo RUTA_REPO] [--dest RUTA_DEST]

Hace cuatro cosas:
  1. Copia los datasets curados del repo a <dest>/kb/ (SQLite brain, matrix POP, ops, pops, docs md,
     workflows, tutoriales, referencias de API, shaders, templates y contratos).
  2. Dumpa los datos que viven en TypeScript (sinónimos, family hints, templates, recipes)
     a JSON, usando el dist compilado con node -> <dest>/kb/ts-extract/ts-data.json.
  3. Sanitiza operadores inexistentes o inconsistencias heredadas del MCP viejo (renderPOP, colorPOP, etc.).
  4. Indexa los activos en SQLite FTS5 (knowledge_brain.db) para que kb_search y kb_get
     puedan consultar workflows, tutoriales, soluciones GLSL, auditorías y bitácoras empíricas.
  5. Escribe <dest>/kb/MANIFEST.json con tamaño + sha256 + origen de cada archivo.

Idempotente: se puede correr de nuevo cuando la KB del repo cambie.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, sqlite3, subprocess, sys, tempfile

DEFAULT_REPO = os.environ.get("TD_KNOWLEDGE_REPO") or r"C:\Users\Tolch\Documents\AI_Code\Touchdesigner_MCP\Main"
DEFAULT_DEST = os.path.dirname(os.path.abspath(__file__))

# (ruta relativa en el repo, ruta relativa en kb/)
FILES = [
    ("mcp/data/knowledge_brain.db",          "knowledge_brain.db"),
    ("docs/pop_matrix.json",                 "pop_matrix.json"),
    ("mcp/data/topology.json",               "topology.json"),
    ("mcp/data/real-world-topology.json",    "real-world-topology.json"),
    ("mcp/data/webtoe-pop-specs.json",       "webtoe-pop-specs.json"),
    ("mcp/data/webtoe-top-specs.json",       "webtoe-top-specs.json"),
    ("mcp/data/ops/index.json",              "ops/index.json"),
    ("mcp/data/glsl_curriculum.json",        "pops/glsl_curriculum.json"),
    ("data/templates/builtin-templates.json","templates/builtin-templates.json"),
    ("mcp/data/templates/pop-chains.json",   "templates/pop-chains.json"),
    ("docs/pop_networks.json",               "templates/pop_networks.json"),
    ("mcp/data/reference/python-api-classes.json", "reference/python-api-classes.json"),
    ("mcp/data/reference/pop-parameters.json",     "reference/pop-parameters.json"),
    ("references/discovery-log.md",          "references/discovery-log.md"),
    ("references/pop-parameter-mapping.md",  "references/pop-parameter-mapping.md"),
    ("glsl_pop_projects/GLSL_ERROR_SOLUTIONS.md", "rules/GLSL_ERROR_SOLUTIONS.md"),
    ("docs/GLSL_POP_RULES.md",               "rules/GLSL_POP_RULES.md"),
    ("docs/GLSL_TOP_RULES.md",               "rules/GLSL_TOP_RULES.md"),
    ("docs/glsl_pop_shader_guide.md",        "rules/glsl_pop_shader_guide.md"),
    ("docs/GLSL_POP_SUITE_GUIDE.md",         "rules/GLSL_POP_SUITE_GUIDE.md"),
    ("docs/GLSL_POP_TEST_COVERAGE.md",       "rules/GLSL_POP_TEST_COVERAGE.md"),
    ("docs/GLSL_TEST_COVERAGE_SUMMARY.md",   "rules/GLSL_TEST_COVERAGE_SUMMARY.md"),
    ("docs/POPs_KNOWLEDGE.md",               "rules/POPs_KNOWLEDGE.md"),
    ("docs/POPs_CORRECTIONS.md",             "rules/POPs_CORRECTIONS.md"),
    ("docs/POPs_VALIDATION.md",              "rules/POPs_VALIDATION.md"),
    ("docs/TD_PARAMETER_CHEATSHEET.md",      "rules/TD_PARAMETER_CHEATSHEET.md"),
    ("docs/BRIDGE_CONTRACT.md",              "rules/BRIDGE_CONTRACT.md"),
    ("docs/2026-09-28 TDMCP oficial vs propio - informe de testeo.md", "rules/2026-09-28_TDMCP_oficial_vs_propio.md"),
    ("docs/API_CONTRACT_AUDIT.md",           "rules/API_CONTRACT_AUDIT.md"),
    ("docs/TOE_REPLICATION.md",              "rules/TOE_REPLICATION.md"),
    ("docs/MCP_REAL_CASES.md",               "rules/MCP_REAL_CASES.md"),
    ("docs/discord-twozero/ANALISIS-TWOZERO-para-TD-MCP.md", "rules/ANALISIS_COMMUNITY_MCP.md"),
    ("docs/discord-twozero/transcript.md",                  "rules/COMMUNITY_FEEDBACK_LOG.md"),
    ("docs/PERFORMANCE.md",                                  "rules/PERFORMANCE.md"),
    ("docs/pathtracer-glsl.md",                              "workflows/pathtracer-glsl.md"),
    ("docs/glsl_pops_reference.json",                        "pops/glsl_pops_reference.json"),
]
DIRS = [
    ("mcp/data/ops/operators", "ops/operators"),
    ("mcp/data/pops",          "pops"),
    ("mcp/data/workflows",     "workflows"),
    ("mcp/data/tutorials",     "tutorials"),
    ("docs/tutorials/pop_tutorial", "tutorials/pop_tutorial"),
    ("mcp/data/prompts/master", "prompts/master"),
    ("glsl_files",             "shaders"),
    ("glsl_pop_projects/shaders", "shaders"),
    ("toe/templates",          "templates/specs"),
    ("mcp/data/docs",          "docs_internal"),
]

NODE_DUMP = r"""
const [out, R] = process.argv.slice(2);   // node script.cjs <out> <repo>
const fs = require('fs');
const j = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
(async () => {
  const res = { generated_at: new Date().toISOString(), source: R };
  const dyn = async (name, mod, keys) => {
    try {
      const m = await import('file://' + R + '/mcp/dist/' + mod);
      res[name] = {};
      for (const k of keys) res[name][k] = m[k] ?? null;
    } catch (e) { res[name] = { error: String(e) }; }
  };
  await dyn('semantic', 'semantic.js', ['TYPE_SYNONYMS', 'FAMILY_HINTS']);
  await dyn('templates', 'networkTemplates.js', ['NETWORK_TEMPLATES', 'listTemplateNames', 'listAllTags']);
  await dyn('pops_validate', 'popsValidate.js', ['POP_NETWORK_TEMPLATES']);
  await dyn('pop_validation', 'tools/popValidation.js', ['POP_RULES', 'INVALID_CROSS_FAMILY', 'VALID_BRIDGES', 'ATTRIBUTE_RULES']);
  await dyn('topology_data', 'topologyData.js', ['MULTI_INPUT_PATTERNS']);
  await dyn('catalog', 'catalogManager.js', ['FAMILY_MAP', 'PARAMETER_STYLE_MAP', 'POP_PARAMETER_STYLE', 'CREATION_DEFAULTS']);
  // las recetas viven en un const NO exportado: se extraen llamando la funcion exportada
  try {
    const r = await import('file://' + R + '/mcp/dist/builderRecipes.js');
    res.recipes = { listRecipes: r.listRecipes(), listRecipeNames: r.listRecipeNames(), recipeTags: r.recipeTags() };
  } catch (e) { res.recipes = { error: String(e) }; }
  // GLSL TOP recetas visuales de Book of Shaders
  try {
    const topRec = await import('file://' + R + '/mcp/dist/tools/glslTopRecipes.js');
    res.glsl_top_recipes = topRec.GLSL_TOP_RECIPES ?? null;
  } catch (e) { res.glsl_top_recipes = { error: String(e) }; }
  fs.writeFileSync(out, JSON.stringify(res, null, 1));
  console.log('dump ok ->', out);
})();
"""

CURATED_CONCEPTS = [
    {"concept": "feedback loop", "canonical": "particlesupdatepop / feedbackPOP", "aliases": ["feedback", "feedback loop", "update loop", "solver loop", "loop de particulas"], "note": "En sistemas POP de partículas se apunta al nullPOP final del solver."},
    {"concept": "field weight", "canonical": "Weight", "aliases": ["weight", "peso del campo", "peso", "influencia del campo", "falloff", "field weight", "field influence", "dist"], "note": "Field POP calcula Weight (0..1) y Dist."},
    {"concept": "particle force", "canonical": "PartForce", "aliases": ["force", "particle force", "fuerza", "turbulencia"]},
    {"concept": "particle velocity", "canonical": "PartVel", "aliases": ["velocity", "velocidad", "speed"]},
    {"concept": "particle life", "canonical": "PartLife / lifeexpect", "aliases": ["life", "lifespan", "vida", "edad", "age"]},
    {"concept": "point size", "canonical": "pointsize / pointscale", "aliases": ["point scale", "point size", "size", "tamaño", "escala de punto"], "note": "En pointspriteMAT el parámetro real es pointsize (Contrato C2)."},
    {"concept": "rotation vector", "canonical": "Rot", "aliases": ["rotation", "rot", "direccion", "direction", "orientacion", "orientation"]},
    {"concept": "point color", "canonical": "Color", "aliases": ["color", "cd", "colour"], "note": "En POPs el atributo built-in de color es Color (float4), no Cd (Contrato C11)."},
    {"concept": "curl noise", "canonical": "CurlNoise", "aliases": ["curl noise", "curl", "divergence-free", "fluido", "fluid", "turbulencia"], "note": "Ruido libre de divergencia para fluidos en noisePOP o glslPOP."},
    {"concept": "boids / flocking", "canonical": "Boids", "aliases": ["boids", "flocking", "separation", "alignment", "cohesion", "bandada"], "note": "Algoritmo de flocking: separation + alignment + cohesion (neighborPOP + glslPOP)."},
    {"concept": "SPH fluid", "canonical": "SPH", "aliases": ["sph", "smoothed particle hydrodynamics", "hidrodinámica"], "note": "Simulación de fluidos SPH vía GLSL POP compute."},
    {"concept": "instancing", "canonical": "Instancing", "aliases": ["instancing", "instance", "instancia", "copias", "copy sop", "geometry comp", "copy pop"], "note": "Instanciado en GPU con geometryCOMP o copyPOP (input 0=template, input 1=target points)."},
    {"concept": "audio reactive", "canonical": "AudioReactive", "aliases": ["audio reactive", "audio reactivo", "sound reactive", "music reactive", "sonido"], "note": "Audio Device In / Audio File In CHOP -> Audio Spectrum / Analyze CHOP -> Math CHOP -> CHOP to POP / expr."},
    {"concept": "dmx lighting", "canonical": "DMX", "aliases": ["dmx", "lighting", "iluminación", "art-net", "artnet", "sacn", "sACN", "dmx fixture"], "note": "Control DMX mediante dmxoutCHOP / dmxfixturePOP."},
    {"concept": "trail / motion blur", "canonical": "Trail", "aliases": ["trail", "trails", "motion blur", "estela", "rastro", "persistencia", "trail pop"]},
    {"concept": "cache / playback", "canonical": "Cache", "aliases": ["cache", "caching", "playback", "reproducción", "buffer", "cache pop", "cache select pop"]},
    {"concept": "neighbor detection", "canonical": "Neighbor", "aliases": ["neighbor", "neighbour", "vecino", "proximity", "cerca", "interaction", "neighbor pop"], "note": "Detección de vecinos con neighborPOP / proximityPOP."},
    {"concept": "particle lifecycle", "canonical": "ParticleLifecycle", "aliases": ["particle lifecycle", "lifecycle", "normalized age", "normalizedage", "life curve", "lookup curve"], "note": "Edad normalizada (PartAge/PartLife) + curvePOP + lookuptablePOP."},
    {"concept": "pre-roll particles", "canonical": "PreRoll", "aliases": ["pre-roll", "preroll", "pre roll", "initial simulation", "simulación inicial", "steady state"], "note": "Atención Contrato C10: initializepulse/preroll en particlePOP pueden enfermar el buffer en loops de feedback."},
    {"concept": "lookup texture", "canonical": "LookupTexture", "aliases": ["lookup texture", "lookup texture pop", "uv sampling", "muestreo uv", "texture lookup", "color from texture"], "note": "lookuptexturePOP muestrea color desde un TOP hacia atributos POP."},
    {"concept": "pop render pipeline", "canonical": "PopRenderPipeline", "aliases": ["render pop", "dibujar puntos", "renderizar particulas", "point cloud render", "pointsprite"], "note": "Contrato C2: convertPOP(convert='topointprims') -> nullPOP -> geometryCOMP (borrar torus1!) + cameraCOMP + renderTOP + pointspriteMAT."},
    {"concept": "pathtracer 3 josef pelz", "canonical": "Pathtracer + PT_GEO + PT_MAT + PT_LIGHT (PT_FAM)", "aliases": ["pathtracer", "pathtracer 3", "pathtracer 3.0", "josef pelz", "pt_fam", "pt_geo", "pt_mat", "pt_light", "dlss ray reconstruction", "pachtracer", "pach tracer", "patch tracy", "patch tracer", "pach tracy", "pathtracer haze", "humo volumetrico"], "note": "Contrato C23: PathTracer 3.0.1 de Josef Pelz sobre POPs. Reglas críticas: (1) allowCooking=True recursivo al clonar PT_GEO/PT_MAT/PT_LIGHT; (2) scene.par.Software=1 (LBVH síncrono GPU) en escenas POP animadas para evitar caída de ~25% de frames; (3) Humo volumétrico: apagar Haze=False en luces Rect de relleno y encender Haze=True en luces Sphere/Spot con Gobo noiseTOP, Hazevariation=1.0, Hazescale=2.6, Hazemultiple=False; (4) 60 FPS en tiempo real: piso gridPOP rows=2, cols=2, sizex=45, sizey=45 (2 triángulos sin línea de horizonte), 64-96 esferas analíticas (pointPrims), Samples=1, Bounces=4, Hazesamples=4, Quality='Balanced'. Usar td_setup_pathtracer3 (presets 'studio' o 'vortex_haze_60fps')."},
]

CURATED_PARAM_ALIASES = [
    {"requested": "life", "canonical": "lifeexpect / PartLife", "note": "Expectativa de vida en particlePOP."},
    {"requested": "size", "canonical": "pointsize (pointspriteMAT) / pointscale", "note": "En pointspriteMAT usar pointsize (Contrato C2)."},
    {"requested": "feedback target", "canonical": "particlesupdatepop / targetop", "note": "Apunta al nullPOP al final del loop de simulación."},
    {"requested": "radius", "canonical": "radx / rady / radz", "note": "En spherePOP / tubePOP / fieldPOP es tupla radx, rady, radz."},
    {"requested": "res", "canonical": "outputresolution + resolutionw / resolutionh", "note": "En TOPs fijar outputresolution='custom' antes de resolutionw/h."},
    {"requested": "birth rate", "canonical": "birthrate", "note": "Tasa de emisión por segundo en particlePOP."},
    {"requested": "drag", "canonical": "drag", "note": "Amortiguación en particlePOP / forcePOP."},
    {"requested": "amplitude", "canonical": "amp", "note": "En noiseTOP y noisePOP el parámetro real es 'amp', no 'amplitude'."},
    {"requested": "frequency", "canonical": "period / freq", "note": "En noiseTOP/noisePOP se controla con 'period' (inverso de frecuencia)."},
    {"requested": "translate", "canonical": "tx / ty / tz", "note": "Traslación 3D en transformPOP, geometryCOMP y cameraCOMP."},
    {"requested": "rotate", "canonical": "rx / ry / rz", "note": "Rotación 3D en grados."},
    {"requested": "scale", "canonical": "sx / sy / sz", "note": "Escala 3D por eje."},
    {"requested": "rectangle", "canonical": "Rect", "note": "En PT_LIGHT.par.Type el menuName real para luz rectangular es 'Rect', no 'Rectangle' (Contrato C23)."},
    {"requested": "dlss", "canonical": "Dlss", "note": "En Pathtracer.par.Method el menuName real es 'Dlss' (Contrato C23)."},
    {"requested": "haze", "canonical": "Hazedensity / Hazeanisotropy / Hazesamples / Hazevariation / Hazescale / Hazedrift", "note": "En Pathtracer 3.0 (página Atmosphere), controlar humo volumétrico con Hazedensity=0.14, Hazeanisotropy=0.68, Hazevariation=1.0, Hazescale=2.6, Hazesamples=4, Hazemultiple=False y PT_LIGHT.par.Haze selectivo (Contrato C23)."},
]

CURATED_ATTR_ALIASES = [
    {"requested": "p", "canonical": "P", "note": "Posición 3D (vec3)."},
    {"requested": "n", "canonical": "N", "note": "Normal 3D (vec3)."},
    {"requested": "cd", "canonical": "Color", "note": "En POPs de TD el atributo estándar de color es Color (vec4), no Cd (Contrato C11)."},
    {"requested": "color", "canonical": "Color", "note": "Color RGBA por punto (vec4): crear con attrNname='custom', attrNcustomname='Color', attrNnumcomps=4."},
    {"requested": "scale", "canonical": "pointscale / PScale", "note": "Escala por punto (en PathTracer 3.0 PointScale controla radio de esferas analíticas o mitad de ancho de tubos 3D)."},
    {"requested": "roughness", "canonical": "Roughness", "note": "En PathTracer 3.0 (PT_GEO), el atributo float Roughness reemplaza el Roughness del PT_MAT por punto/vértice."},
    {"requested": "metallic", "canonical": "Metallic", "note": "En PathTracer 3.0 (PT_GEO), el atributo float Metallic reemplaza el Metallic del PT_MAT por punto/vértice."},
    {"requested": "transmission", "canonical": "Transmission", "note": "En PathTracer 3.0 (PT_GEO), el atributo float Transmission reemplaza el Transmission del PT_MAT por punto/vértice."},
    {"requested": "emit", "canonical": "Emit", "note": "En PathTracer 3.0 (PT_GEO), el atributo float Emit reemplaza el Emitstrength del PT_MAT por punto/vértice."},
    {"requested": "vel", "canonical": "PartVel / v", "note": "Velocidad en particlePOP es PartVel (vec3)."},
    {"requested": "uv", "canonical": "Tex / uv", "note": "Coordenadas de textura en POPs suelen ser Tex (vec3/vec2)."},
    {"requested": "age", "canonical": "PartAge", "note": "Edad actual de la partícula en particlePOP."},
    {"requested": "life", "canonical": "PartLife", "note": "Vida máxima de la partícula en particlePOP."},
    {"requested": "weight", "canonical": "Weight", "note": "Peso de influencia (float 0..1) generado por fieldPOP."},
    {"requested": "dist", "canonical": "Dist", "note": "Distancia al centro generada por fieldPOP."},
    {"requested": "force", "canonical": "PartForce", "note": "Fuerza acumulada en particlePOP."},
]


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def sanitize_legacy_knowledge(kb_dir: str):
    """Corrige operadores inexistentes o inconsistencias heredadas del MCP viejo."""
    ts_p = os.path.join(kb_dir, "ts-extract", "ts-data.json")
    if os.path.exists(ts_p):
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

        sem = d.setdefault("semantic", {})
        sem["CONCEPTS"] = CURATED_CONCEPTS
        sem["PARAMETER_ALIASES"] = CURATED_PARAM_ALIASES
        sem["ATTRIBUTE_ALIASES"] = CURATED_ATTR_ALIASES

        pv = d.get("pop_validation", {})
        if isinstance(pv, dict):
            vb = pv.get("VALID_BRIDGES")
            if isinstance(vb, dict):
                vb["POP→SOP"] = "poptoSOP or geometryCOMP"
                vb["SOP→POP"] = "soptoPOP"
                vb["POP→TOP"] = "poptoTOP (data texture) or geometryCOMP + cameraCOMP + renderTOP + pointspriteMAT (Contract C2)"
                vb["TOP→POP"] = "toptoPOP or lookuptexturePOP"
                vb["POP→CHOP"] = "poptoCHOP"
                vb["CHOP→POP"] = "choptoPOP"
                vb["POP→DAT"] = "poptoDAT"
                vb["DAT→POP"] = "dattoPOP"

        td_data = d.get("topology_data", {})
        if isinstance(td_data, dict):
            mip = td_data.get("MULTI_INPUT_PATTERNS")
            if isinstance(mip, dict) and "colorPOP" in mip:
                mip.pop("colorPOP", None)

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

    bt_p = os.path.join(kb_dir, "templates", "builtin-templates.json")
    if os.path.exists(bt_p):
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

    wf_fixes = {
        "ray-pop-physics.md": [("pointgenPOP", "pointgeneratorPOP"), ("pointgen POP", "pointgenerator POP")],
        "particle-follow-curve.md": [("pointgenPOP", "pointgeneratorPOP"), ("pointgen POP", "pointgenerator POP")],
        "nebrarray-pathtracer.md": [("pointgenPOP", "pointgeneratorPOP"), ("pointgen POP", "pointgenerator POP")],
        "phased-blending.md": [("lookupattPOP", "lookuptablePOP")],
        "pop-ray-scene.md": [("lookuptexPOP", "lookuptexturePOP")],
    }
    wf_dir = os.path.join(kb_dir, "workflows")
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

    tut_p = os.path.join(kb_dir, "tutorials", "gaussian-splatting.md")
    if os.path.exists(tut_p):
        with open(tut_p, "r", encoding="utf-8", errors="replace") as f:
            c = f.read().replace("pointfileselectPOP", "pointfileinPOP")
        with open(tut_p, "w", encoding="utf-8") as f:
            f.write(c)

    graph_p = os.path.join(kb_dir, "workflows", "graphs", "particle-system-basic.json")
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

    top_p = os.path.join(kb_dir, "real-world-topology.json")
    if os.path.exists(top_p):
        with open(top_p, "r", encoding="utf-8") as f:
            t_content = f.read().replace("renderPOP", "poptoTOP")
        with open(top_p, "w", encoding="utf-8") as f:
            f.write(t_content)

    # Sanitizar templates/specs (17 arquitecturas modulares)
    specs_dir = os.path.join(kb_dir, "templates", "specs")
    if os.path.isdir(specs_dir):
        for fn in os.listdir(specs_dir):
            if fn.endswith(".md"):
                sp = os.path.join(specs_dir, fn)
                with open(sp, "r", encoding="utf-8", errors="replace") as f:
                    c = f.read()
                c = c.replace("Render POP", "POP Render Pipeline (geometryCOMP + cameraCOMP + renderTOP + pointspriteMAT) / poptoTOP")
                c = c.replace("renderPOP", "poptoTOP / geometryCOMP render")
                c = c.replace("Sprite POP", "pointspriteMAT")
                c = c.replace("spritePOP", "pointspriteMAT")
                c = c.replace("Color POP", "attributePOP / glslPOP")
                c = c.replace("colorPOP", "attributePOP")
                c = c.replace("Force POP", "noisePOP / windPOP")
                c = c.replace("forcePOP", "noisePOP")
                c = c.replace("Drag POP", "particlePOP")
                c = c.replace("dragPOP", "particlePOP")
                c = c.replace("Pointgen POP", "pointgeneratorPOP")
                c = c.replace("pointgenPOP", "pointgeneratorPOP")
                c = c.replace("Point File Select POP", "pointfileinPOP")
                c = c.replace("pointfileselectPOP", "pointfileinPOP")
                c = c.replace("deleteprims", "topointprims")
                c = c.replace("attensizenear", "pointsize")
                with open(sp, "w", encoding="utf-8") as f:
                    f.write(c)

    # Sanitizar pathtracer-glsl
    pt_p = os.path.join(kb_dir, "workflows", "pathtracer-glsl.md")
    if os.path.exists(pt_p):
        with open(pt_p, "r", encoding="utf-8", errors="replace") as f:
            c = f.read()
        c = c.replace("renderPOP", "poptoTOP / geometryCOMP render")
        c = c.replace("Render POP", "POP Render Pipeline / poptoTOP")
        with open(pt_p, "w", encoding="utf-8") as f:
            f.write(c)

    # Anonimización de nombres de proyectos externos, artistas y usuarios de la comunidad
    anon_repls = [
        (r"TWOZERO \(Discord\)", "Auditoría de MCPs Comunitarios"),
        (r"servidor Discord TWOZERO \(`1489238980942757908`\)", "servidor de comunidad técnica"),
        (r"servidor Discord TWOZERO", "servidor de comunidad técnica"),
        (r"discord-twozero", "community-feedback"),
        (r"03-twozero-evaluation\.md", "03-community-mcp-evaluation.md"),
        (r"inspiradas en TWOZERO", "inspiradas en toolkits comunitarios"),
        (r"TWOZERO se describe como", "El toolkit comunitario se describe como"),
        (r"sin depender de TWOZERO", "sin depender de toolkits externos"),
        (r"compara contra TWOZERO", "compara contra toolkits comunitarios"),
        (r"twozero_td", "community_td"),
        (r"twozero\.ai", "community-docs.local"),
        (r"twozero_chain_live", "community_chain_live"),
        (r"twozero_http_live", "community_http_live"),
        (r"twozero_measure_live", "community_measure_live"),
        (r"\bTWOZERO\b", "Community-MCP"),
        (r"\bTwoZero\b", "Community-MCP"),
        (r"\btwozero\b", "community_mcp"),
        (r"\b404\.zero\b", "Lead-Dev"),
        (r"\b404zero\b", "Lead-Dev"),
        (r"\btolch\.x\b", "Auditor"),
        (r"\bmykul0rr\b", "User_A"),
        (r"\bMetaKan\b", "User_B"),
        (r"\bDenne\b", "User_C"),
        (r"\bKaromm\b", "User_D"),
        (r"\bverygeeky\b", "User_E"),
        (r"\bniccab\b", "User_F"),
        (r"\bDisintegrationLoops\b", "User_G"),
        (r"\bDean_LJ\b", "User_H"),
        (r"\bnika_sur_ma\b", "User_I"),
        (r"\bgwra\b", "User_J"),
        (r"\bHesi\b", "User_K"),
        (r"\bevia's\b", "User_L"),
        (r"\bvacuum\b", "User_M"),
    ]
    for root, _, files in os.walk(kb_dir):
        for f in files:
            if f.endswith(('.md', '.json', '.txt')):
                p = os.path.join(root, f)
                try:
                    with open(p, 'r', encoding='utf-8', errors='replace') as fh:
                        cnt = fh.read()
                    mod = cnt
                    for pat, rep in anon_repls:
                        mod = re.sub(pat, rep, mod)
                    if mod != cnt:
                        with open(p, 'w', encoding='utf-8') as fh:
                            fh.write(mod)
                except Exception:
                    pass

    # Anonimización directa en knowledge_brain.db para registros heredados (ops, pops)
    db_p = os.path.join(kb_dir, "knowledge_brain.db")
    if os.path.exists(db_p):
        try:
            con = sqlite3.connect(db_p)
            cur = con.cursor()
            rows = cur.execute("SELECT rowid, name, pageTitle, summary, body FROM docs WHERE body LIKE '%twozero%' OR body LIKE '%404.zero%' OR body LIKE '%mykul0rr%'").fetchall()
            if rows:
                def _anon(txt):
                    if not txt:
                        return txt
                    for pat, rep in anon_repls:
                        txt = re.sub(pat, rep, txt)
                    return txt
                for r in rows:
                    cur.execute(
                        "UPDATE docs SET name = ?, pageTitle = ?, summary = ?, body = ? WHERE rowid = ?",
                        (_anon(r[1]), _anon(r[2]), _anon(r[3]), _anon(r[4]), r[0])
                    )
                con.commit()
            con.execute("VACUUM")
            con.close()
        except Exception as e:
            print("  DB anon warning:", e)

    print("  Sanitización de operadores legacy y anonimización completada.")


def index_markdown_assets(kb_dir: str):
    db_path = os.path.join(kb_dir, "knowledge_brain.db")
    if not os.path.exists(db_path):
        return
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    # Limpieza previa de tipos custom para garantizar idempotencia
    custom_types = ("workflow", "tutorial", "glsl-solution", "empirical", "rules", "master-prompt", "glsl-shader", "template-spec", "recipe", "glsl-recipe", "skill")
    placeholders = ",".join("?" for _ in custom_types)
    cur.execute(f"DELETE FROM docs WHERE sourceType IN ({placeholders})", custom_types)

    # 1. Workflows
    wf_dir = os.path.join(kb_dir, "workflows")
    if os.path.isdir(wf_dir):
        for fn in sorted(os.listdir(wf_dir)):
            if fn.endswith(".md"):
                p = os.path.join(wf_dir, fn)
                with open(p, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                stem = fn[:-3]
                lines = content.splitlines()
                title = stem
                summary = ""
                for l in lines:
                    if l.startswith("# "):
                        title = l[2:].strip()
                        break
                for l in lines:
                    ls = l.strip()
                    if ls and not ls.startswith("#") and not ls.startswith("---"):
                        summary = ls[:300]
                        break
                fam = "GENERAL"
                cl = (stem + " " + content[:600]).lower()
                if "pop" in stem or "particle" in stem or "glslpop" in cl:
                    fam = "POP"
                elif "top" in stem or "blend" in stem or "blur" in stem or "texture" in cl or "key" in stem:
                    fam = "TOP"
                elif "chop" in stem or "audio" in stem:
                    fam = "CHOP"
                elif "sop" in stem or "geometry" in stem or "mesh" in cl:
                    fam = "SOP"
                elif "dat" in stem:
                    fam = "DAT"

                cur.execute(
                    "INSERT INTO docs(name, family, pageTitle, pageSlug, url, summary, trustTier, sourceType, body) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (stem, fam, title, f"workflow-{stem}", f"workflow://{stem}", summary or f"Workflow {stem}", "empirical", "workflow", content)
                )

    # 2. Tutoriales
    tut_dir = os.path.join(kb_dir, "tutorials")
    if os.path.isdir(tut_dir):
        for fn in sorted(os.listdir(tut_dir)):
            if fn.endswith(".md"):
                p = os.path.join(tut_dir, fn)
                with open(p, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                stem = fn[:-3]
                lines = content.splitlines()
                title = stem
                summary = ""
                for l in lines:
                    if l.startswith("# "):
                        title = l[2:].strip()
                        break
                for l in lines:
                    ls = l.strip()
                    if ls and not ls.startswith("#") and not ls.startswith("---"):
                        summary = ls[:300]
                        break
                fam = "GENERAL"
                if "pop" in stem or "particle" in stem or "flocking" in stem:
                    fam = "POP"
                elif "glsl" in stem:
                    fam = "GLSL"
                elif "audio" in stem:
                    fam = "CHOP"
                elif "color" in stem or "bloom" in stem or "feedback" in stem:
                    fam = "TOP"

                cur.execute(
                    "INSERT INTO docs(name, family, pageTitle, pageSlug, url, summary, trustTier, sourceType, body) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (stem, fam, title, f"tutorial-{stem}", f"tutorial://{stem}", summary or f"Tutorial {stem}", "community", "tutorial", content)
                )

    # 3. Soluciones de errores GLSL, logs empíricos y auditorías
    rules_map = [
        ("rules/GLSL_ERROR_SOLUTIONS.md", "glsl_error_solutions", "GLSL", "GLSL Error Solutions & Catalog", "glsl-solution", "live-verified"),
        ("references/discovery-log.md", "discovery_log", "GENERAL", "TouchDesigner Empirical Discovery Log", "empirical", "live-verified"),
        ("references/pop-parameter-mapping.md", "pop_parameter_mapping", "POP", "POP Parameter Mapping & Quirks", "empirical", "live-verified"),
        ("rules/2026-09-28_TDMCP_oficial_vs_propio.md", "tdmcp_oficial_vs_propio_report", "GENERAL", "TDMCP Oficial vs Propio - Test Report", "empirical", "live-verified"),
        ("rules/API_CONTRACT_AUDIT.md", "api_contract_audit", "GENERAL", "TouchDesigner API Contract Audit", "empirical", "live-verified"),
        ("rules/TOE_REPLICATION.md", "toe_replication", "GENERAL", "TOE Replication and Network Architecture", "empirical", "live-verified"),
        ("rules/MCP_REAL_CASES.md", "mcp_real_cases", "GENERAL", "MCP Real Production Cases in TouchDesigner", "empirical", "live-verified"),
        ("rules/ANALISIS_COMMUNITY_MCP.md", "analisis_community_mcp", "GENERAL", "Análisis Crítico de MCPs Comunitarios - Pitfalls y Lecciones de Integración", "empirical", "community-audit"),
        ("rules/COMMUNITY_FEEDBACK_LOG.md", "community_feedback_log", "GENERAL", "Bitácora Anónima de Casos de Soporte y Fallas en Integración TD", "empirical", "community-audit"),
        ("rules/PERFORMANCE.md", "performance_tuning_guide", "GENERAL", "TouchDesigner Performance & Cook Budgeting Guide", "empirical", "live-verified"),
    ]
    for rel, name, fam, title, stype, trust in rules_map:
        p = os.path.join(kb_dir, rel.replace("/", os.sep))
        if os.path.exists(p):
            with open(p, encoding="utf-8", errors="replace") as f:
                content = f.read()
            summary = content[:280].replace("\n", " ").strip()
            cur.execute(
                "INSERT INTO docs(name, family, pageTitle, pageSlug, url, summary, trustTier, sourceType, body) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (name, fam, title, f"rules-{name}", f"local://{rel}", summary, trust, stype, content)
            )

    # 4. Master Prompts
    pr_dir = os.path.join(kb_dir, "prompts", "master")
    if os.path.isdir(pr_dir):
        for fn in sorted(os.listdir(pr_dir)):
            if fn.endswith(".md"):
                p = os.path.join(pr_dir, fn)
                with open(p, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                stem = fn[:-3]
                cur.execute(
                    "INSERT INTO docs(name, family, pageTitle, pageSlug, url, summary, trustTier, sourceType, body) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (stem, "PROMPT", f"Master Prompt: {stem}", f"prompt-{stem}", f"prompt://master/{stem}", f"Directive for {stem}", "live-verified", "master-prompt", content)
                )

    # 5. Template Specs (17 arquitecturas modulares de redes)
    specs_dir = os.path.join(kb_dir, "templates", "specs")
    if os.path.isdir(specs_dir):
        for fn in sorted(os.listdir(specs_dir)):
            if fn.endswith(".md"):
                p = os.path.join(specs_dir, fn)
                with open(p, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                stem = fn[:-3]
                lines = content.splitlines()
                title = stem
                summary = ""
                for l in lines:
                    if l.startswith("# "):
                        title = l[2:].strip()
                        break
                for l in lines:
                    ls = l.strip()
                    if ls and not ls.startswith("#") and not ls.startswith("---"):
                        summary = ls[:300]
                        break
                fam = "POP" if any(k in stem for k in ("pop", "boids", "particle", "fluid", "spring", "field")) else "GENERAL"
                cur.execute(
                    "INSERT INTO docs(name, family, pageTitle, pageSlug, url, summary, trustTier, sourceType, body) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (stem, fam, f"Template Spec: {title}", f"template-spec-{stem}", f"template://spec/{stem}", summary or f"Template Spec {stem}", "curated", "template-spec", content)
                )

    # 6. GLSL Shaders (67+ compute, pixel y vertex shaders)
    sh_dir = os.path.join(kb_dir, "shaders")
    if os.path.isdir(sh_dir):
        for fn in sorted(os.listdir(sh_dir)):
            if fn.endswith(".glsl") or fn.endswith(".txt"):
                p = os.path.join(sh_dir, fn)
                with open(p, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                stem = fn.rsplit(".", 1)[0]
                lines = [l.strip() for l in content.splitlines() if l.strip()]
                summary = ""
                for l in lines:
                    if l.startswith("//") or l.startswith("/*"):
                        summary = l.lstrip("/*# ").strip()
                        if len(summary) > 10:
                            break
                fam = "GLSL"
                if stem.startswith("top_") or stem.startswith("recipe_t") or "top" in stem:
                    fam = "TOP"
                elif stem.startswith("pop_") or stem.startswith("tut_") or stem.startswith("suite_") or any(k in stem for k in ("particle", "spring", "wave", "fountain", "boids")):
                    fam = "POP"
                elif stem.startswith("vertex_"):
                    fam = "MAT"

                cur.execute(
                    "INSERT INTO docs(name, family, pageTitle, pageSlug, url, summary, trustTier, sourceType, body) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (stem, fam, f"GLSL Shader: {stem}", f"shader-{stem}", f"shader://{stem}", summary or f"TouchDesigner GLSL Shader {stem}", "live-verified", "glsl-shader", content)
                )

    # 7. GLSL TOP Recipes (Book of Shaders)
    rec_file = os.path.join(kb_dir, "recipes", "glsl_top_recipes.json")
    if os.path.exists(rec_file):
        try:
            with open(rec_file, encoding="utf-8") as f:
                rec_list = json.load(f)
            for r in rec_list:
                rid = r.get("id") or r.get("title")
                cur.execute(
                    "INSERT INTO docs(name, family, pageTitle, pageSlug, url, summary, trustTier, sourceType, body) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (rid, "TOP", f"GLSL Recipe: {r.get('title')}", f"recipe-{rid}", f"recipe://glsl-top/{rid}",
                     f"{r.get('title')} ({r.get('category')}) - Book of Shaders TouchDesigner Recipe", "live-verified", "glsl-recipe",
                     json.dumps(r, ensure_ascii=False, indent=2))
                )
        except Exception as e:
            print("  error indexando glsl_top_recipes:", e)

    # 8. Skills Hermes (SKILL.md + reference.md + examples.md + glsladvancedPOP.md)
    skills_root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills-hermes")
    if os.path.isdir(skills_root):
        for sk in sorted(os.listdir(skills_root)):
            sk_dir = os.path.join(skills_root, sk)
            if not os.path.isdir(sk_dir):
                continue
            for fn in sorted(os.listdir(sk_dir)):
                if not fn.endswith(".md"):
                    continue
                p = os.path.join(sk_dir, fn)
                with open(p, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                stem = fn[:-3]
                doc_name = sk if stem == "SKILL" else f"{sk}/{stem}"
                fam = "GENERAL"
                for fk in ("pop", "top", "chop", "sop", "dat", "mat", "comp", "glsl"):
                    if f"-{fk}" in sk.lower() or fk in stem.lower():
                        fam = fk.upper()
                        break
                summary = content[:280].replace("\n", " ").strip()
                cur.execute(
                    "INSERT INTO docs(name, family, pageTitle, pageSlug, url, summary, trustTier, sourceType, body) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (doc_name, fam, f"Skill: {doc_name}", f"skill-{doc_name.replace('/', '-')}",
                     f"skill://{sk}/{fn}", summary, "live-verified", "skill", content)
                )

    con.commit()
    total_docs = cur.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
    by_type = cur.execute("SELECT sourceType, COUNT(*) FROM docs GROUP BY sourceType").fetchall()
    print(f"  SQLite FTS5 indexado: {total_docs} documentos totales. Por sourceType: {dict(by_type)}")
    con.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--dest", default=DEFAULT_DEST)
    ap.add_argument("--export-archive", help="Empaqueta kb/ en un archivo .zip portable (para backup o migración sin repo viejo)")
    ap.add_argument("--import-archive", help="Restaura kb/ desde un archivo .zip portable")
    a = ap.parse_args()
    kb = os.path.join(a.dest, "kb")
    os.makedirs(kb, exist_ok=True)

    if a.import_archive:
        import zipfile
        if not os.path.exists(a.import_archive):
            print(f"[build_assets] ERROR: no existe el archivo {a.import_archive}")
            return 1
        print(f"[build_assets] Restaurando kb/ desde {a.import_archive} -> {kb}")
        with zipfile.ZipFile(a.import_archive, "r") as zf:
            zf.extractall(kb)
        print("[build_assets] Restauración completada.")

    repo_exists = bool(a.repo and os.path.isdir(a.repo))
    manifest_p = os.path.join(kb, "MANIFEST.json")
    manifest = {"repo": a.repo if repo_exists else "standalone (local kb/)", "kb": kb, "files": [], "ts_extract": None}

    if repo_exists:
        print(f"[build_assets] Extrayendo conocimiento desde: {a.repo}")
        print(f"[build_assets] Destino kb/: {kb}\n")

        for src_rel, dst_rel in FILES:
            src = os.path.join(a.repo, src_rel.replace("/", os.sep))
            if not os.path.exists(src):
                print(f"  FALTA {src_rel}")
                continue
            dst = os.path.join(kb, dst_rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            manifest["files"].append({"path": dst_rel, "bytes": os.path.getsize(dst), "sha256_16": sha256(dst)})
            print(f"  {os.path.getsize(dst)/1024:9.1f} KB  {dst_rel}")

        for src_rel, dst_rel in DIRS:
            src = os.path.join(a.repo, src_rel.replace("/", os.sep))
            dst = os.path.join(kb, dst_rel.replace("/", os.sep))
            if not os.path.isdir(src):
                print(f"  FALTA dir {src_rel}")
                continue
            os.makedirs(dst, exist_ok=True)
            shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("*.log", "__pycache__"))
            n = sum(len(f) for _, _, f in os.walk(dst))
            size = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(dst) for f in fs)
            manifest["files"].append({"path": dst_rel + "/", "files": n, "bytes": size})
            print(f"  {size/1024:9.1f} KB  {dst_rel}/  ({n} archivos)")

        # dump de los datos TS via node
        ext = os.path.join(kb, "ts-extract")
        os.makedirs(ext, exist_ok=True)
        script = os.path.join(tempfile.gettempdir(), "td_kb_node_dump.cjs")
        with open(script, "w", encoding="utf-8") as f:
            f.write(NODE_DUMP)
        out = os.path.join(ext, "ts-data.json")
        try:
            p = subprocess.run(["node", script, out, a.repo], capture_output=True, text=True, timeout=180)
            print("  node:", (p.stdout or p.stderr).strip()[:200])
            if os.path.exists(out):
                d = json.load(open(out, encoding="utf-8"))
                if d.get("glsl_top_recipes") and isinstance(d["glsl_top_recipes"], list):
                    rec_dir = os.path.join(kb, "recipes")
                    os.makedirs(rec_dir, exist_ok=True)
                    with open(os.path.join(rec_dir, "glsl_top_recipes.json"), "w", encoding="utf-8") as rf:
                        json.dump(d["glsl_top_recipes"], rf, indent=2, ensure_ascii=False)
                shape = {k: (len(v) if isinstance(v, (dict, list)) else v) for k, v in d.items()}
                manifest["ts_extract"] = {"path": "ts-extract/ts-data.json", "bytes": os.path.getsize(out),
                                          "extracted": shape}
                print("  ts-data.json:", json.dumps(shape, ensure_ascii=False)[:300])
        except Exception as e:
            print("  node dump FALLO:", e)
    else:
        print(f"[build_assets] Modo autónomo (sin repo externo '{a.repo}'): operando sobre {kb}")
        if os.path.exists(manifest_p):
            try:
                old_man = json.load(open(manifest_p, encoding="utf-8"))
                manifest["files"] = old_man.get("files", [])
                manifest["ts_extract"] = old_man.get("ts_extract")
            except Exception:
                pass

    # Sanitización de operadores legacy o alucinados
    print("\n[build_assets] Sanitizando y alineando con TD 2025+...")
    try:
        sanitize_legacy_knowledge(kb)
    except Exception as e:
        print("  Sanitizing warning:", e)

    # Actualizar shape de ts_extract después de sanitizar
    out_ts = os.path.join(kb, "ts-extract", "ts-data.json")
    if os.path.exists(out_ts):
        try:
            d = json.load(open(out_ts, encoding="utf-8"))
            shape = {k: (len(v) if isinstance(v, (dict, list)) else v) for k, v in d.items()}
            manifest["ts_extract"] = {"path": "ts-extract/ts-data.json", "bytes": os.path.getsize(out_ts),
                                      "extracted": shape}
        except Exception:
            pass

    # Ingesta en SQLite FTS5 de workflows, tutoriales, soluciones GLSL y auditorías
    print("\n[build_assets] Indexando documentos markdown y reglas en SQLite FTS5...")
    try:
        index_markdown_assets(kb)
    except Exception as e:
        print("  FTS5 indexing error:", e)

    total = sum(f.get("bytes", 0) for f in manifest["files"])
    manifest["total_bytes"] = total
    with open(manifest_p, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False)
    print(f"\nTOTAL kb/: {total/1024/1024:.1f} MB -> {kb}")

    if a.export_archive:
        import zipfile
        print(f"[build_assets] Exportando archivo portable -> {a.export_archive}")
        with zipfile.ZipFile(a.export_archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for r_dir, _, files in os.walk(kb):
                for fn in files:
                    if fn.endswith(("-shm", "-wal")):
                        continue
                    full_p = os.path.join(r_dir, fn)
                    rel_p = os.path.relpath(full_p, kb)
                    zf.write(full_p, rel_p)
        print(f"[build_assets] Archivo creado ({os.path.getsize(a.export_archive)/1024/1024:.1f} MB).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

r"""Extrae los assets de conocimiento al port offline.

Uso:  python build_assets.py [--repo RUTA_REPO] [--dest RUTA_DEST]

Hace cuatro cosas:
  1. Copia los datasets curados del repo a <dest>/kb/ (SQLite brain, matrix POP, ops, pops, docs md,
     workflows, tutoriales, referencias de API, shaders, templates y contratos).
  2. Dumpa los datos que viven en TypeScript (sinónimos, family hints, templates, recipes)
     a JSON, usando el dist compilado con node -> <dest>/kb/ts-extract/ts-data.json.
  3. Indexa los nuevos activos en SQLite FTS5 (knowledge_brain.db) para que kb_search y kb_get
     puedan consultar workflows, tutoriales, soluciones GLSL, auditorías y bitácoras empíricas.
  4. Escribe <dest>/kb/MANIFEST.json con tamaño + sha256 + origen de cada archivo.

Idempotente: se puede correr de nuevo cuando la KB del repo cambie.
"""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, sqlite3, subprocess, sys, tempfile

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
]
DIRS = [
    ("mcp/data/ops/operators", "ops/operators"),
    ("mcp/data/pops",          "pops"),
    ("mcp/data/workflows",     "workflows"),
    ("mcp/data/tutorials",     "tutorials"),
    ("docs/tutorials/pop_tutorial", "tutorials/pop_tutorial"),
    ("mcp/data/prompts/master", "prompts/master"),
    ("glsl_pop_projects/shaders", "shaders"),
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
  // las recetas viven en un const NO exportado: se extraen llamando la funcion exportada
  try {
    const r = await import('file://' + R + '/mcp/dist/builderRecipes.js');
    res.recipes = { listRecipes: r.listRecipes(), listRecipeNames: r.listRecipeNames(), recipeTags: r.recipeTags() };
  } catch (e) { res.recipes = { error: String(e) }; }
  fs.writeFileSync(out, JSON.stringify(res, null, 1));
  console.log('dump ok ->', out);
})();
"""


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def index_markdown_assets(kb_dir: str):
    db_path = os.path.join(kb_dir, "knowledge_brain.db")
    if not os.path.exists(db_path):
        return
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    # Limpieza previa de tipos custom para garantizar idempotencia
    custom_types = ("workflow", "tutorial", "glsl-solution", "empirical", "rules", "master-prompt")
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

    con.commit()
    total_docs = cur.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
    by_type = cur.execute("SELECT sourceType, COUNT(*) FROM docs GROUP BY sourceType").fetchall()
    print(f"  SQLite FTS5 indexado: {total_docs} documentos totales. Por sourceType: {dict(by_type)}")
    con.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--dest", default=DEFAULT_DEST)
    a = ap.parse_args()
    kb = os.path.join(a.dest, "kb")
    os.makedirs(kb, exist_ok=True)
    manifest = {"repo": a.repo, "kb": kb, "files": [], "ts_extract": None}

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
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("*.log", "__pycache__"))
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
            shape = {k: (len(v) if isinstance(v, (dict, list)) else v) for k, v in d.items()}
            manifest["ts_extract"] = {"path": "ts-extract/ts-data.json", "bytes": os.path.getsize(out),
                                      "extracted": shape}
            print("  ts-data.json:", json.dumps(shape, ensure_ascii=False)[:300])
    except Exception as e:
        print("  node dump FALLO:", e)

    # Ingesta en SQLite FTS5 de workflows, tutoriales, soluciones GLSL y auditorías
    print("\n[build_assets] Indexando documentos markdown y reglas en SQLite FTS5...")
    try:
        index_markdown_assets(kb)
    except Exception as e:
        print("  FTS5 indexing error:", e)

    total = sum(f.get("bytes", 0) for f in manifest["files"])
    manifest["total_bytes"] = total
    with open(os.path.join(kb, "MANIFEST.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False)
    print(f"\nTOTAL kb/: {total/1024/1024:.1f} MB -> {kb}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

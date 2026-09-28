r"""Extrae los assets de conocimiento al port offline.

Uso:  python build_assets.py [--repo RUTA_REPO] [--dest RUTA_DEST]

Hace tres cosas:
  1. Copia los datasets curados del repo a <dest>/kb/ (SQLite brain, matrix POP, ops, pops, docs md).
  2. Dumpa los datos que viven en TypeScript (sinonimos, family hints, templates, recipes)
     a JSON, usando el dist compilado con node -> <dest>/kb/ts-extract/*.json.
  3. Escribe <dest>/kb/MANIFEST.json con tamano + sha256 + origen de cada archivo.

Idempotente: se puede correr de nuevo cuando la KB del repo cambie.
"""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, subprocess, sys, tempfile

DEFAULT_REPO = os.environ.get("TD_KNOWLEDGE_REPO") or r"C:\Users\Tolch\Documents\AI_Code\Touchdesigner_MCP\Main"
DEFAULT_DEST = os.path.dirname(os.path.abspath(__file__))

# (ruta relativa en el repo, ruta relativa en kb/)
FILES = [
    ("mcp/data/knowledge_brain.db",          "knowledge_brain.db"),
    ("docs/pop_matrix.json",                 "pop_matrix.json"),
    ("mcp/data/topology.json",               "topology.json"),
    ("mcp/data/webtoe-pop-specs.json",       "webtoe-pop-specs.json"),
    ("mcp/data/ops/index.json",              "ops/index.json"),
    ("docs/GLSL_POP_RULES.md",               "rules/GLSL_POP_RULES.md"),
    ("docs/GLSL_TOP_RULES.md",               "rules/GLSL_TOP_RULES.md"),
    ("docs/glsl_pop_shader_guide.md",        "rules/glsl_pop_shader_guide.md"),
    ("docs/GLSL_POP_SUITE_GUIDE.md",         "rules/GLSL_POP_SUITE_GUIDE.md"),
    ("docs/POPs_KNOWLEDGE.md",               "rules/POPs_KNOWLEDGE.md"),
    ("docs/POPs_CORRECTIONS.md",             "rules/POPs_CORRECTIONS.md"),
    ("docs/POPs_VALIDATION.md",              "rules/POPs_VALIDATION.md"),
    ("docs/TD_PARAMETER_CHEATSHEET.md",      "rules/TD_PARAMETER_CHEATSHEET.md"),
    ("docs/BRIDGE_CONTRACT.md",              "rules/BRIDGE_CONTRACT.md"),
]
DIRS = [
    ("mcp/data/ops/operators", "ops/operators"),
    ("mcp/data/pops",          "pops"),
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--dest", default=DEFAULT_DEST)
    a = ap.parse_args()
    kb = os.path.join(a.dest, "kb")
    os.makedirs(kb, exist_ok=True)
    manifest = {"repo": a.repo, "kb": kb, "files": [], "ts_extract": None}

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

    total = sum(f.get("bytes", 0) for f in manifest["files"])
    manifest["total_bytes"] = total
    with open(os.path.join(kb, "MANIFEST.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False)
    print(f"\nTOTAL kb/: {total/1024/1024:.1f} MB -> {kb}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

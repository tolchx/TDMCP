#!/usr/bin/env python3
r"""td-knowledge — MCP offline para TouchDesigner (capa de conocimiento).

MCP server por stdio, **Python puro (stdlib)**: no necesita TouchDesigner abierto,
no necesita el bridge (:44444), no necesita Node. Sirve la capa de conocimiento que
el MCP oficial (TDMCP) no cubre: KB curada, matriz POP medida en vivo, análisis
estático GLSL POP/TOP, catálogo de operadores, sinónimos ES/EN, plantillas y recetas.

Uso:
    python server.py [--kb RUTA_KB]

KB por defecto: <dir del script>/kb   (override con --kb o env TD_KNOWLEDGE_KB)

Compatible con MCP 2025-06-18 (initialize / tools/list / tools/call), transporte stdio
mensajes JSON-RPC delimitados por salto de línea.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import traceback

SERVER_NAME = "td-knowledge"
SERVER_VERSION = "0.1.0"
PROTOCOL = "2025-06-18"

def _default_kb() -> str:
    """kb/ al lado del server, o un nivel arriba (layout extras/port/{kb,td-knowledge})."""
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(here, "kb"), os.path.join(os.path.dirname(here), "kb")):
        if os.path.isdir(cand):
            return cand
    return os.path.join(here, "kb")


KB_DIR = os.environ.get("TD_KNOWLEDGE_KB") or _default_kb()

_CACHE: dict[str, object] = {}


# ----------------------------------------------------------------------------- utils
def kb(*parts: str) -> str:
    return os.path.join(KB_DIR, *parts)


def load_json(rel: str):
    if rel not in _CACHE:
        path = kb(rel)
        if not os.path.exists(path):
            raise FileNotFoundError(f"falta el asset '{rel}' en la KB ({KB_DIR}). Correr build_assets.py.")
        with open(path, encoding="utf-8") as f:
            _CACHE[rel] = json.load(f)
    return _CACHE[rel]


def db() -> sqlite3.Connection:
    if "db" not in _CACHE:
        con = sqlite3.connect(f"file:{kb('knowledge_brain.db')}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        _CACHE["db"] = con
    return _CACHE["db"]  # type: ignore[return-value]


def ts(*section: str):
    d = load_json("ts-extract/ts-data.json")
    cur = d
    for s in section:
        cur = (cur or {}).get(s)
    return cur


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def clip(s: str, n: int) -> str:
    s = s or ""
    return s if len(s) <= n else s[:n] + f"\n…[cortado: {len(s)} chars en total]"


# ----------------------------------------------------------------------------- tools
def t_kb_info(_: dict) -> dict:
    man = load_json("MANIFEST.json")
    con = db()
    counts = {
        "docs_total": con.execute("SELECT COUNT(*) FROM docs").fetchone()[0],
        "por_familia": dict(con.execute("SELECT family, COUNT(*) FROM docs GROUP BY 1 ORDER BY 2 DESC")),
        "por_trust_tier": dict(con.execute("SELECT trustTier, COUNT(*) FROM docs GROUP BY 1 ORDER BY 2 DESC")),
        "por_source_type": dict(con.execute("SELECT sourceType, COUNT(*) FROM docs GROUP BY 1 ORDER BY 2 DESC")),
    }
    pm = load_json("pop_matrix.json")
    return {
        "kb_dir": KB_DIR,
        "kb_total_bytes": man.get("total_bytes"),
        "kb_origen": man.get("repo"),
        "assets": [f.get("path") for f in man.get("files", [])],
        "ts_extract": (man.get("ts_extract") or {}).get("extracted"),
        "docs": counts,
        "pop_matrix": {
            "generado": pm.get("generated_at"),
            "build_medido": pm.get("td_build"),
            "tipos": pm.get("type_count"),
            "creados_ok": pm.get("created_ok"),
            "creados_fail": pm.get("created_fail"),
            "ok_con_input": pm.get("ok_con_input_count"),
            "params_medidos": pm.get("total_params"),
        },
    }


def t_kb_taxonomy(a: dict) -> dict:
    con = db()
    family = a.get("family")
    if a.get("list_docs"):
        fam = family or "POP"
        rows = con.execute(
            "SELECT name, family, pageTitle, trustTier, sourceType FROM docs WHERE family = ? ORDER BY name",
            (fam,),
        ).fetchall()
        return {"family": fam, "count": len(rows), "docs": [dict(r) for r in rows]}
    return {
        "familias": dict(con.execute("SELECT family, COUNT(*) FROM docs GROUP BY 1 ORDER BY 2 DESC")),
        "trust_tier": dict(con.execute("SELECT trustTier, COUNT(*) FROM docs GROUP BY 1 ORDER BY 2 DESC")),
        "source_type": dict(con.execute("SELECT sourceType, COUNT(*) FROM docs GROUP BY 1 ORDER BY 2 DESC")),
        "nota": "trustTier: official = docs.derivative.ca | live-verified/empirical = medido en TD por nosotros | community = fuentes de terceros",
    }


def _fts(q: str, mode: str) -> str:
    terms = [t for t in re.findall(r"[\w\-\.]+", q.lower()) if len(t) > 1]
    if not terms:
        return ""
    joiner = " AND " if mode == "AND" else " OR "
    return joiner.join(f'"{t}"*' for t in terms)


def t_kb_search(a: dict) -> dict:
    q = (a.get("query") or "").strip()
    if not q:
        return {"error": "falta 'query'"}
    limit = max(1, min(int(a.get("limit") or 8), 25))
    con = db()
    where, params = [], []
    if a.get("family"):
        where.append("family = ?")
        params.append(a["family"])
    if a.get("trust_tier"):
        where.append("trustTier = ?")
        params.append(a["trust_tier"])
    if a.get("source_type"):
        where.append("sourceType = ?")
        params.append(a["source_type"])
    sql_extra = (" AND " + " AND ".join(where)) if where else ""
    used = "AND"
    rows = []
    for mode in ("AND", "OR"):
        match = _fts(q, mode)
        if not match:
            return {"error": "sin términos de búsqueda válidos"}
        sql = (
            "SELECT name, family, pageTitle, pageSlug, trustTier, sourceType, summary, "
            "snippet(docs, 8, '[', ']', ' … ', 12) AS frag "
            f"FROM docs WHERE docs MATCH ?{sql_extra} ORDER BY bm25(docs, 4.0, 1.0) LIMIT ?"
        )
        try:
            rows = con.execute(sql, [match, *params, limit]).fetchall()
        except sqlite3.OperationalError as e:
            return {"error": f"FTS5: {e}", "match": match}
        if rows:
            used = mode
            break
    return {
        "query": q, "match": used, "count": len(rows), "filters": {k: a.get(k) for k in ("family", "trust_tier", "source_type") if a.get(k)},
        "results": [
            {"name": r["name"], "family": r["family"], "page": r["pageTitle"], "slug": r["pageSlug"],
             "trust_tier": r["trustTier"], "source_type": r["sourceType"],
             "summary": clip(r["summary"], 260), "fragmento": clip(r["frag"], 400)}
            for r in rows
        ],
    }


def t_kb_get(a: dict) -> dict:
    key = (a.get("name_or_slug") or a.get("name") or "").strip()
    if not key:
        return {"error": "falta 'name_or_slug'"}
    con = db()
    row = con.execute(
        "SELECT name, family, pageTitle, pageSlug, url, trustTier, sourceType, summary, body FROM docs "
        "WHERE name = ? OR pageSlug = ? OR name = ? COLLATE NOCASE LIMIT 1",
        (key, key, key),
    ).fetchone()
    if row is None:
        like = con.execute(
            "SELECT name, family, pageTitle, pageSlug FROM docs WHERE name LIKE ? OR pageSlug LIKE ? LIMIT 8",
            (f"%{key}%", f"%{key}%"),
        ).fetchall()
        return {"error": f"no existe '{key}' en la KB", "quizas": [dict(r) for r in like]}
    maxc = max(400, min(int(a.get("max_chars") or 6000), 40000))
    return {
        "name": row["name"], "family": row["family"], "page": row["pageTitle"], "slug": row["pageSlug"],
        "url": row["url"], "trust_tier": row["trustTier"], "source_type": row["sourceType"],
        "summary": row["summary"], "body": clip(row["body"], maxc), "body_total_chars": len(row["body"] or ""),
    }


def t_pop_matrix(a: dict) -> dict:
    pm = load_json("pop_matrix.json")
    t = a.get("type")
    if t:
        for r in pm.get("results", []):
            if str(r.get("type", "")).lower() == t.lower():
                return {"type": r["type"], "medido_en": pm.get("td_build"), "metodo": pm.get("method"), "registro": r}
        return {"error": f"'{t}' no está en la matriz (97 tipos medidos)", "tipos": sorted(x["type"] for x in pm.get("results", []))}
    cat = a.get("category")
    if cat:
        if cat not in pm.get("categories", {}):
            return {"error": f"categoría desconocida '{cat}'", "categorias": list(pm.get("categories", {}).keys())}
        return {"category": cat, "count": len(pm["categories"][cat]), "tipos": pm["categories"][cat]}
    return {
        "generado": pm.get("generated_at"), "build_medido": pm.get("td_build"), "sandbox": pm.get("sandbox"),
        "metodo": pm.get("method"), "tipos": pm.get("type_count"),
        "creados_ok": pm.get("created_ok"), "creados_fail": pm.get("created_fail"),
        "ok_con_input": pm.get("ok_con_input_count"), "cableados": pm.get("wired_count"),
        "multi_source": pm.get("multi_source_count"), "params_totales": pm.get("total_params"),
        "categorias": {k: len(v) for k, v in pm.get("categories", {}).items()},
        "sin_geometria": pm.get("sin_geometria"), "con_errores": pm.get("con_errores"), "no_creables": pm.get("no_creables"),
        "nota": "Matriz medida en vivo: qué POP se crea, cocina y acepta inputs. Usá type='<popType>' para el registro completo.",
    }


def _op_files() -> dict:
    if "opindex" in _CACHE:
        return _CACHE["opindex"]  # type: ignore[return-value]
    root = kb("ops", "operators")
    idx: dict[str, str] = {}
    for fam in os.listdir(root):
        d = os.path.join(root, fam)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if fn.endswith(".json"):
                stem = fn[:-5]
                idx[norm(stem)] = os.path.join(d, fn)
                idx.setdefault(norm(stem.replace("_", "")), os.path.join(d, fn))
    _CACHE["opindex"] = idx
    return idx


def _load_op(op_key: str):
    idx = _op_files()
    p = idx.get(norm(op_key))
    if not p:
        return None, sorted({os.path.basename(v)[:-5] for v in idx.values()})
    return load_json(os.path.relpath(p, KB_DIR)), None


def t_ops_doc(a: dict) -> dict:
    key = a.get("op_type") or a.get("slug") or ""
    doc, all_ops = _load_op(key)
    if doc is None:
        close = [s for s in all_ops if norm(key) in norm(s)][:10]
        return {"error": f"sin doc para '{key}'", "quizas": close or all_ops[:10]}
    sec = a.get("section")
    base = {"family": doc.get("family"), "page": doc.get("pageTitle"), "slug": doc.get("pageSlug"),
            "url": doc.get("url"), "summary": clip(doc.get("summary"), 900)}
    if sec and sec in doc:
        return {**base, "section": sec, "content": clip(json.dumps(doc[sec], ensure_ascii=False, indent=1), 8000)}
    for k in ("inputs", "useCases", "commonCombinations", "troubleshooting", "localNotes", "examples"):
        if doc.get(k):
            base[k] = clip(json.dumps(doc[k], ensure_ascii=False, indent=1), 1500)
    base["secciones_disponibles"] = [k for k in doc if k not in base]
    return base


def t_ops_params(a: dict) -> dict:
    key = a.get("op_type") or ""
    doc, all_ops = _load_op(key)
    if doc is None:
        return {"error": f"sin doc para '{key}'", "quizas": [s for s in all_ops if norm(key) in norm(s)][:10]}
    pars = doc.get("parameters") or []
    out = []
    for p in pars:
        if isinstance(p, dict):
            out.append({k: p.get(k) for k in ("name", "label", "type", "default", "page", "menuNames", "summary") if p.get(k) is not None})
        else:
            out.append(p)
    return {"op_type": doc.get("tdOpTypeGuess"), "page": doc.get("pageTitle"), "count": len(out),
            "parameters": out[:400], "nota": "Doc offline. Con TD abierto usá get_help del MCP oficial: lee los nombres del build vivo."}


def t_pop_knowledge(a: dict) -> dict:
    kind = (a.get("kind") or "").strip()
    files = {"patterns": "pops/patterns.json", "wiki_params": "pops/wiki_params.json",
             "pop_inventory": "pops/pop_inventory.json", "validation": "pops/validation.json",
             "glsl_library": "pops/glsl_library.json"}
    if not kind:
        return {"error": "falta 'kind'", "kinds_disponibles": list(files)}
    if kind not in files or not os.path.exists(kb(files[kind])):
        return {"error": f"kind inválido '{kind}'", "kinds_disponibles": [k for k, v in files.items() if os.path.exists(kb(v))]}
    d = load_json(files[kind])
    q = (a.get("query") or "").strip().lower()
    if q and isinstance(d, dict):
        hit = {}
        for k, v in d.items():
            if q in k.lower() or q in json.dumps(v, ensure_ascii=False).lower():
                hit[k] = clip(json.dumps(v, ensure_ascii=False, indent=1), 3000)
        return {"kind": kind, "query": q, "keys": list(hit), "content": hit}
    return {"kind": kind, "keys": list(d.keys()) if isinstance(d, dict) else f"lista({len(d)})",
            "content": clip(json.dumps(d, ensure_ascii=False, indent=1), 9000)}


def t_resolve_operator(a: dict) -> dict:
    q = (a.get("text") or "").strip().lower()
    if not q:
        return {"error": "falta 'text'"}
    syn = ts("semantic", "TYPE_SYNONYMS") or {}
    hints = ts("semantic", "FAMILY_HINTS") or {}
    scores = []
    toks = [t for t in re.findall(r"[a-záéíóúñ0-9]+", q) if len(t) > 2]
    for op_type, words in syn.items():
        s = 0
        for w in words or []:
            wl = w.lower()
            if wl == q:
                s = max(s, 100)
            elif wl in q or any(wl in t or t in wl for t in toks):
                s = max(s, 60 - abs(len(wl) - len(q)))
        if s:
            scores.append((s, op_type, [w for w in words if q in w.lower() or w.lower() in q][:6]))
    scores.sort(reverse=True)
    fam = []
    if isinstance(hints, dict):
        for f, ws in hints.items():
            blob = " ".join(str(w).lower() for w in (ws or []))
            if any(t in blob or t in f.lower() for t in toks) or q in blob:
                fam.append(f)
    return {"texto": q, "familia_sugerida": fam[:4],
            "candidatos": [{"type": t, "score": s, "coincidencias": m} for s, t, m in scores[: int(a.get("limit") or 6)]],
            "tipos_indexados": len(syn)}


def t_templates(a: dict) -> dict:
    tl = ts("templates", "NETWORK_TEMPLATES") or []
    action = a.get("action") or "list"
    if action == "list":
        q = (a.get("query") or "").lower()
        items = [{"name": t["name"], "description": clip(t.get("description"), 200), "tags": t.get("tags"),
                  "complexity": t.get("complexity"), "operadores": len(t.get("operators") or [])} for t in tl
                 if not q or q in json.dumps(t, ensure_ascii=False).lower()]
        return {"count": len(items), "templates": items}
    name = (a.get("name") or "").lower()
    for t in tl:
        if t["name"].lower() == name or name in t["name"].lower():
            return {"template": t}
    return {"error": f"sin template '{a.get('name')}'", "nombres": [t["name"] for t in tl]}


def t_recipes(a: dict) -> dict:
    rd = ts("recipes") or {}
    rs = rd.get("listRecipes") or []
    action = a.get("action") or "list"
    if action == "list":
        q = (a.get("query") or "").lower()
        items = [{"name": r["name"], "title": r.get("title"), "description": clip(r.get("description"), 240),
                  "tags": r.get("tags"), "complexity": r.get("complexity"), "nodos": len(r.get("nodes") or [])} for r in rs
                 if not q or q in json.dumps(r, ensure_ascii=False).lower()]
        return {"count": len(items), "recetas": items, "tags": rd.get("recipeTags")}
    name = (a.get("name") or "").lower()
    for r in rs:
        if r["name"].lower() == name or name in r["name"].lower():
            return {"recipe": r}
    return {"error": f"sin receta '{a.get('name')}'", "nombres": [r["name"] for r in rs]}


def _rules_md(family: str) -> str:
    f = "rules/GLSL_POP_RULES.md" if (family or "pop").lower().startswith("pop") else "rules/GLSL_TOP_RULES.md"
    with open(kb(f), encoding="utf-8") as fh:
        return fh.read()


def t_glsl_rules(a: dict) -> dict:
    family = a.get("family") or "pop"
    md = _rules_md(family)
    parts = re.split(r"(?m)^(##\s+Regla\s+\d+\s+—.*)$", md)
    rules = []
    for i in range(1, len(parts), 2):
        head = parts[i].strip("# ").strip()
        rules.append({"regla": head, "texto": clip(parts[i + 1].strip(), 1400)})
    want = (a.get("rule") or "").strip()
    q = (a.get("query") or "").lower()
    sel = rules
    if want:
        sel = [r for r in rules if want.lower() in r["regla"].lower()]
    elif q:
        sel = [r for r in rules if q in r["texto"].lower()]
    return {"family": family, "archivo": "GLSL_POP_RULES.md" if family.lower().startswith("pop") else "GLSL_TOP_RULES.md",
            "reglas_totales": len(rules), "reglas": sel or rules,
            "titulos": [r["regla"] for r in rules]}


# --- contratos verificados en vivo: fichero VERSIONADO (no kb/, que es derivado)
CONTRACTS_MD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "contracts",
                            "VERIFIED_CONTRACTS.md")


def _contracts_text() -> str:
    if not os.path.exists(CONTRACTS_MD):
        raise FileNotFoundError(f"falta el fichero de contratos: {CONTRACTS_MD}")
    with open(CONTRACTS_MD, encoding="utf-8") as f:
        return f.read()


def t_contracts(a: dict) -> dict:
    """Sirve knowledge/contracts/VERIFIED_CONTRACTS.md por seccion / texto / listado."""
    md = _contracts_text()
    items = []
    for block in re.split(r"(?m)^(?=##\s)", md):
        m = re.match(r"##\s+(.*)", block)
        if not m:
            continue
        seccion = m.group(1).strip()
        body = block[m.end():].strip()
        subs = []
        for sub in re.split(r"(?m)^(?=###\s)", body):
            ms = re.match(r"###\s+(.*)", sub)
            if ms:
                subs.append({"id": ms.group(1).strip(), "texto": sub[ms.end():].strip()})
        if not subs and body:  # seccion sin subtitulos: entra como una sola pieza
            subs = [{"id": seccion, "texto": body}]
        for s in subs:
            items.append({"seccion": seccion, **s})
    if a.get("list"):
        return {"archivo": os.path.relpath(CONTRACTS_MD, os.path.dirname(os.path.abspath(__file__))),
                "secciones": sorted({i["seccion"] for i in items}),
                "contratos": [i["id"] for i in items], "total": len(items)}
    want = (a.get("section") or "").strip().lower()
    q = (a.get("query") or "").strip().lower()
    sel = items
    if want:
        sel = [i for i in sel if want in i["id"].lower() or want in i["seccion"].lower()]
    if q:
        sel = [i for i in sel if q in i["texto"].lower() or q in i["id"].lower()]
    if not sel:
        return {"total": 0, "contratos": [],
                "sin_coincidencias": "query=%r section=%r" % (q, want),
                "contratos_disponibles": [i["id"] for i in items]}
    n = int(a.get("max_chars") or 9000)
    return {"total": len(sel), "contratos": [{"seccion": i["seccion"], "id": i["id"],
                                              "texto": clip(i["texto"], n)} for i in sel],
            "nota": "Contratos verificados contra TD vivo 2025.32460 + TDMCP 1.1.55."}


# --- analyzer: puerto fiel de las reglas verificadas (POP R1-R4, TOP R1-R2, Python R6)
COMPONENTS = {"cd": 4, "n": 3, "uv": 2, "p": 3, "v": 3, "alpha": 1, "mass": 1, "masa": 1}
BUILTIN_WRITE_OK = {"p"}  # P ya existe si hay TDIn_P; igual conviene no leerla (R1)
# Menus reales de attr0name en TD 2025.32460: 'custom' lowercase (verificado en vivo
# 2026-09-28; el valor con mayuscula es rechazado por set_parameters).
ATTR_MENU_CASE = "lowercase"


def _writes_and_reads(code: str):
    writes, reads = {}, []
    for m in re.finditer(r"([A-Za-z_]\w*)\s*\[([^\]]*)\]", code):
        attr, idx = m.group(1), m.group(2)
        after = code[m.end():m.end() + 3]
        is_write = re.match(r"\s*=(?!=)", after) is not None
        if is_write:
            writes.setdefault(attr, []).append(idx.strip())
        else:
            reads.append(attr)
    return writes, reads


def t_glsl_analyze(a: dict) -> dict:
    code = a.get("code") or ""
    family = (a.get("family") or "pop").lower()
    if not code.strip():
        return {"error": "falta 'code'"}
    errors, warns, notes = [], [], []

    if family.startswith("py"):
        for m in re.finditer(r"\.(numPoints|numPrims|bounds|points)\b(?!\s*\()", code):
            errors.append({"regla": "POP R6", "mensaje": f".{m.group(1)} es MÉTODO en la clase POP, no propiedad",
                           "fix": f".{m.group(1)}()", "pos": m.start()})
        return {"family": "python", "ok": not errors, "errores": errors, "warnings": warns, "notas": notes}

    writes, reads = _writes_and_reads(code)

    if family.startswith("top"):
        if not re.search(r"\bout\s+vec4\s+\w+", code):
            errors.append({"regla": "TOP R1", "mensaje": "falta la declaración explícita de salida",
                           "fix": "out vec4 fragColor;"})
        if re.search(r"vUV\s*\.\s*uv\b", code):
            errors.append({"regla": "TOP R2", "mensaje": "vUV no se swizzlea con .uv",
                           "fix": "vUV.st  (o vUV.xy)"})
        if re.search(r"\b(TDIndex|TDIn_P|TDNumElements)\b", code):
            warns.append({"regla": "TOP R4", "mensaje": "idiomas de GLSL POP en un shader TOP (las reglas NO trasladan)",
                          "fix": "revisar R4 de GLSL_TOP_RULES.md"})
        if not re.search(r"fragColor\s*=", code) and "out vec4" in code:
            warns.append({"regla": "TOP R1", "mensaje": "la salida se declara pero nunca se asigna", "fix": "fragColor = ..."})
        if re.search(r"\bTDOutputSwizzle\b", code):
            notes.append("TDOutputSwizzle detectado: es el idiom correcto para el canal de salida.")
        return {"family": "top", "ok": not errors, "errores": errors, "warnings": warns, "notas": notes}

    # ---- POP
    out_attrs = sorted(writes)
    if "TDIndex" not in code:
        errors.append({"regla": "POP R2", "mensaje": "no usa TDIndex() para iterar los puntos",
                       "fix": "const uint id = TDIndex();"})
    if not re.search(r">=\s*TDNumElements\s*\(\s*\)", code):
        errors.append({"regla": "POP R2", "mensaje": "falta la guarda de rango",
                       "fix": "if (id >= TDNumElements()) return;"})
    for attr in sorted(set(reads)):
        if attr in writes:
            errors.append({"regla": "POP R4 (y R1 si es P)", "mensaje": f"'{attr}' se escribe y se lee en el mismo main()",
                           "fix": f"si es la salida [{attr}] usá TDIn_{attr}(0, id); si necesitás leerla, poné outputaccess='readwrite'"})
    if "P[" in code and "TDIn_P" not in code:
        warns.append({"regla": "POP R1", "mensaje": "escribe P sin leer la entrada (TDIn_P): verificá el origen de los valores",
                      "fix": "P[id] = TDIn_P(0, id) * ...;"})
    create = [x for x in out_attrs if x.lower() not in BUILTIN_WRITE_OK]
    if create:
        notes.append({"regla": "POP R3", "mensaje": "los atributos que se escriben y no vienen en la entrada hay que crearlos "
                       "en la página Create Attributes (outputattrs solo selecciona atributos existentes)"})
        for i, x in enumerate(create):
            name_val = "custom" if ATTR_MENU_CASE == "lowercase" else "Custom"
            notes.append({"attr": x, "parametros": {"attr%dname" % i: name_val, "attr%dcustomname" % i: x,
                                                     "attr%dnumcomps" % i: COMPONENTS.get(x.lower(), 1)}})
        out_inputs = [x for x in out_attrs if x.lower() in BUILTIN_WRITE_OK]
        if out_inputs:
            notes.append({"regla": "POP R3 (outputattrs)", "mensaje": "los atributos que SI vienen en la entrada y se "
                           "reescriben (ej. P) hay que listarlos en el par 'outputattrs' para que el preamble "
                           "los declare — sin eso: \"'P' : undeclared identifier\" al compilar (verificado 2026-09-28)",
                          "outputattrs": " ".join(sorted(x for x in out_attrs if x.lower() in BUILTIN_WRITE_OK))})
    if "readwrite" in code:
        notes.append("Menciona readwrite: recordá que es un parámetro del nodo (outputaccess), no una línea de GLSL.")
    return {"family": "pop", "ok": not errors, "escribe": out_attrs, "lee": sorted(set(reads)),
            "errores": errors, "warnings": warns, "notas": notes}


def t_glsl_curriculum(a: dict) -> dict:
    p = kb("pops", "glsl_library.json")
    if not os.path.exists(p):
        return {"error": "falta pops/glsl_library.json"}
    d = load_json("pops/glsl_library.json")
    q = (a.get("query") or "").lower()
    if isinstance(d, dict):
        if q:
            sel = {k: v for k, v in d.items() if q in json.dumps(v, ensure_ascii=False).lower()}
            return {"query": q, "keys": list(sel)[:12], "content": clip(json.dumps(sel, ensure_ascii=False, indent=1), 8000)}
        return {"keys": list(d.keys())[:30], "content": clip(json.dumps(d, ensure_ascii=False, indent=1), 8000)}
    return {"content": clip(json.dumps(d, ensure_ascii=False, indent=1), 8000)}


def t_workflows(a: dict) -> dict:
    action = a.get("action") or "list"
    wf_dir = kb("workflows")
    if not os.path.isdir(wf_dir):
        return {"error": "no se encontró el directorio de workflows en kb/"}
    files = [f for f in sorted(os.listdir(wf_dir)) if f.endswith(".md")]
    if action == "list":
        q = (a.get("query") or "").lower()
        items = []
        for fn in files:
            stem = fn[:-3]
            p = os.path.join(wf_dir, fn)
            with open(p, encoding="utf-8", errors="replace") as f:
                head = [line.strip() for line in f if line.strip()][:6]
            title = stem
            summary = ""
            for l in head:
                if l.startswith("# "):
                    title = l[2:].strip()
                elif not summary and not l.startswith("#") and not l.startswith("---"):
                    summary = l[:200]
            blob = f"{stem} {title} {summary}".lower()
            if not q or q in blob:
                items.append({"name": stem, "title": title, "summary": summary, "file": fn})
        return {"count": len(items), "workflows": items, "total_available": len(files)}
    name = (a.get("name") or "").strip().lower()
    if not name:
        return {"error": "falta 'name' para action=get", "ejemplos": [f[:-3] for f in files[:8]]}
    for fn in files:
        stem = fn[:-3]
        if stem.lower() == name or name in stem.lower():
            p = os.path.join(wf_dir, fn)
            with open(p, encoding="utf-8", errors="replace") as f:
                content = f.read()
            return {"name": stem, "file": fn, "content": clip(content, int(a.get("max_chars") or 15000))}
    return {"error": f"workflow '{name}' no encontrado", "quizas": [f[:-3] for f in files if name in f.lower()][:8]}


def t_tutorials(a: dict) -> dict:
    action = a.get("action") or "list"
    tut_dir = kb("tutorials")
    if not os.path.isdir(tut_dir):
        return {"error": "no se encontró el directorio de tutoriales en kb/"}
    files = [f for f in sorted(os.listdir(tut_dir)) if f.endswith(".md")]
    if action == "list":
        q = (a.get("query") or "").lower()
        items = []
        for fn in files:
            stem = fn[:-3]
            p = os.path.join(tut_dir, fn)
            with open(p, encoding="utf-8", errors="replace") as f:
                head = [line.strip() for line in f if line.strip()][:6]
            title = stem
            summary = ""
            for l in head:
                if l.startswith("# "):
                    title = l[2:].strip()
                elif not summary and not l.startswith("#") and not l.startswith("---"):
                    summary = l[:200]
            blob = f"{stem} {title} {summary}".lower()
            if not q or q in blob:
                items.append({"name": stem, "title": title, "summary": summary, "file": fn})
        pop_tut = kb("tutorials", "pop_tutorial", "INDEX.md")
        has_pop_tut = os.path.exists(pop_tut)
        return {"count": len(items), "tutorials": items, "pop_tutorial_suite": has_pop_tut, "total": len(files)}
    name = (a.get("name") or "").strip().lower()
    if not name:
        return {"error": "falta 'name' para action=get", "ejemplos": [f[:-3] for f in files[:8]]}
    if name in ("pop_tutorial", "pop_index", "pop-tutorial"):
        p = kb("tutorials", "pop_tutorial", "INDEX.md")
        if os.path.exists(p):
            with open(p, encoding="utf-8", errors="replace") as f:
                return {"name": "pop_tutorial", "content": clip(f.read(), int(a.get("max_chars") or 15000))}
    for fn in files:
        stem = fn[:-3]
        if stem.lower() == name or name in stem.lower():
            p = os.path.join(tut_dir, fn)
            with open(p, encoding="utf-8", errors="replace") as f:
                content = f.read()
            return {"name": stem, "file": fn, "content": clip(content, int(a.get("max_chars") or 15000))}
    return {"error": f"tutorial '{name}' no encontrado", "quizas": [f[:-3] for f in files if name in f.lower()][:8]}


def t_glsl_solutions(a: dict) -> dict:
    p = kb("rules", "GLSL_ERROR_SOLUTIONS.md")
    if not os.path.exists(p):
        return {"error": "falta rules/GLSL_ERROR_SOLUTIONS.md"}
    with open(p, encoding="utf-8", errors="replace") as f:
        md = f.read()
    q = (a.get("error_query") or a.get("query") or "").strip().lower()
    sections = []
    blocks = re.split(r"(?m)^(?=###?\s+)", md)
    for b in blocks:
        b_str = b.strip()
        if not b_str:
            continue
        first_line = b_str.splitlines()[0].strip("# ")
        if not q or q in b_str.lower():
            sections.append({"title": first_line, "content": clip(b_str, int(a.get("max_chars") or 4000))})
    return {"query": q, "count": len(sections), "solutions": sections[: int(a.get("limit") or 6)],
            "nota": "Soluciones verificadas a errores comunes del compilador GLSL en TouchDesigner."}


def _get_py_api():
    if "py_api" in _CACHE:
        return _CACHE["py_api"]
    raw = load_json("reference/python-api-classes.json")
    classes_by_fam = raw.get("classes") or {}
    flat = {}
    for fam, items in classes_by_fam.items():
        if isinstance(items, list):
            for it in items:
                name = it.get("name") or it.get("class")
                if name:
                    it_copy = dict(it)
                    it_copy["family"] = fam
                    flat[name.lower()] = it_copy
                    if it.get("class"):
                        flat[it["class"].lower()] = it_copy
    _CACHE["py_api"] = (raw, flat)
    return _CACHE["py_api"]


def t_python_api(a: dict) -> dict:
    p = kb("reference", "python-api-classes.json")
    if not os.path.exists(p):
        return {"error": "falta reference/python-api-classes.json"}
    raw, flat = _get_py_api()
    cname = (a.get("class_name") or a.get("op_type") or a.get("name") or "").strip().lower()
    q = (a.get("search") or a.get("query") or "").strip().lower()

    if cname:
        it = flat.get(cname)
        if not it:
            for k, v in flat.items():
                if k == cname or k.startswith(cname) or cname in k:
                    it = v
                    break
        if not it:
            close = [k for k in flat if cname in k][:10]
            return {"error": f"clase '{cname}' no encontrada", "quizas": close}
        member = (a.get("member_or_method") or a.get("method") or "").strip().lower()
        if member:
            meths = it.get("methods") or []
            pars = it.get("parameters") or []
            matched_meth = [m for m in meths if member in json.dumps(m, ensure_ascii=False).lower()]
            matched_par = [p for p in pars if member in json.dumps(p, ensure_ascii=False).lower()]
            return {"class": it.get("name"), "matched_methods": matched_meth, "matched_parameters": matched_par}
        return {
            "name": it.get("name"),
            "class": it.get("class"),
            "family": it.get("family"),
            "description": clip(it.get("description"), 500),
            "parameters_count": len(it.get("parameters") or []),
            "methods_count": len(it.get("methods") or []),
            "methods": [m.get("name") for m in (it.get("methods") or []) if isinstance(m, dict)][:30],
            "url": it.get("url")
        }
    if q:
        matches = []
        for k, it in flat.items():
            desc = it.get("description") or ""
            if q in k or q in desc.lower():
                matches.append({"name": it.get("name"), "class": it.get("class"), "family": it.get("family"), "description": clip(desc, 180)})
        return {"query": q, "count": len(matches), "classes": matches[: int(a.get("limit") or 8)]}
    return {"total_classes": len(flat), "familias": list((raw.get("classes") or {}).keys()),
            "total_raw": raw.get("totalClasses"),
            "nota": "Consultá con class_name='noiseTOP' o search='curl'"}


def t_discovery(a: dict) -> dict:
    targets = [
        ("references/discovery-log.md", "discovery-log"),
        ("references/pop-parameter-mapping.md", "pop-parameter-mapping"),
        ("rules/2026-09-28_TDMCP_oficial_vs_propio.md", "tdmcp-oficial-vs-propio"),
        ("contracts/VERIFIED_CONTRACTS.md", "verified-contracts"),
    ]
    q = (a.get("query") or a.get("topic") or "").strip().lower()
    terms = [t for t in re.findall(r"[\w]+", q) if len(t) > 1]
    items = []
    for rel, tag in targets:
        p = kb(rel) if os.path.exists(kb(rel)) else os.path.join(os.path.dirname(os.path.abspath(__file__)), rel)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8", errors="replace") as f:
            text = f.read()
        blocks = re.split(r"(?m)^(?=###?\s+)", text)
        for b in blocks:
            b_str = b.strip()
            if not b_str:
                continue
            b_low = b_str.lower()
            if not terms or all(t in b_low for t in terms):
                first_line = b_str.splitlines()[0].strip("# ")
                items.append({"source": tag, "title": first_line, "content": clip(b_str, 2500)})
    return {"query": q, "count": len(items), "findings": items[: int(a.get("limit") or 6)],
            "nota": "Descubrimientos empíricos, notas de hardware, contratos y quirks de parámetros en TouchDesigner."}


def t_master_prompts(a: dict) -> dict:
    pr_dir = kb("prompts", "master")
    if not os.path.isdir(pr_dir):
        return {"error": "no se encontró prompts/master en kb/"}
    files = [f for f in sorted(os.listdir(pr_dir)) if f.endswith(".md")]
    action = a.get("action") or "list"
    if action == "list":
        return {"count": len(files), "prompts": [f[:-3] for f in files]}
    name = (a.get("name") or "").strip().lower()
    for fn in files:
        stem = fn[:-3]
        if stem.lower() == name or name in stem.lower():
            with open(os.path.join(pr_dir, fn), encoding="utf-8", errors="replace") as f:
                return {"name": stem, "content": f.read()}
    return {"error": f"master prompt '{name}' no encontrado", "disponibles": [f[:-3] for f in files]}


TOOLS = [
    ("kb_info", "Provenance de esta KB offline: ruta, tamaño, origen, conteos de docs y de la matriz POP. Llamala primero si dudás de la frescura.", {}, t_kb_info),
    ("kb_taxonomy", "Qué hay en la KB: conteos por familia/trustTier/sourceType. Con list_docs=true y family='POP' lista los nombres.", {"family": "string", "list_docs": "boolean"}, t_kb_taxonomy),
    ("kb_search", "Búsqueda full-text (BM25) sobre 1128 documentos curados: ops, POPs, patrones, GLSL, workflows, tutoriales. Filtrable por familia y trustTier. NO necesita TouchDesigner.", {"query": "string (requerido)", "family": "POP|TOP|CHOP|SOP|DAT", "trust_tier": "official|live-verified|empirical|community", "source_type": "ops|pops|pop-pattern|pop-live|pop-glsl|workflow|tutorial|glsl-solution|empirical|master-prompt", "limit": "int 1-25"}, t_kb_search),
    ("kb_get", "Devuelve el documento completo (cuerpo paginado) por nombre de operador o slug de página.", {"name_or_slug": "string (requerido)", "max_chars": "int 400-40000"}, t_kb_get),
    ("pop_matrix", "Matriz POP medida en vivo (97 tipos): qué se crea, qué cocina, qué acepta input. Sin args = resumen; type='particlePOP' = registro completo; category='ok_con_input' = miembros.", {"type": "string", "category": "ok_con_input|sin_geometria|..."}, t_pop_matrix),
    ("ops_doc", "Doc curado de un operador (cualquier familia): summary, inputs, useCases, combinaciones, troubleshooting. Secciones: inputs/useCases/commonCombinations/troubleshooting/localNotes/examples.", {"op_type": "string (requerido)", "section": "string"}, t_ops_doc),
    ("ops_params", "Parámetros documentados de un tipo de operador (offline). Con TD abierto preferí get_help del MCP oficial: lee del build vivo.", {"op_type": "string (requerido)"}, t_ops_params),
    ("pop_knowledge", "Datos POP no-oficiales: 'patterns' (mapas de red reales), 'wiki_params', 'pop_inventory', 'validation', 'glsl_library'.", {"kind": "patterns|wiki_params|pop_inventory|validation|glsl_library", "query": "string"}, t_pop_knowledge),
    ("resolve_operator", "Traduce lenguaje natural (ES/EN) a tipo de operador canónico con 99 tipos indexados ('video por webcam' -> videodeviceinTOP).", {"text": "string (requerido)", "limit": "int"}, t_resolve_operator),
    ("templates", "14 plantillas de red con wiring, parámetros y builder Python: action=list|get.", {"action": "list|get", "name": "string", "query": "string"}, t_templates),
    ("recipes", "5 recetas builder verificadas (feedback, partículas POP, GLSL TOP, audio-reactivo, render 3D) con gotchas y código: action=list|get.", {"action": "list|get", "name": "string", "query": "string"}, t_recipes),
    ("workflows", "42 workflows de producción completos (alpha blend, audio viz, feedback trails, fluid solver, gaussian splatting, pathtracer): action=list|get.", {"action": "list|get", "name": "string", "query": "string"}, t_workflows),
    ("tutorials", "28 tutoriales paso a paso de TouchDesigner avanzado (audio-reactivo, boids, god rays, fluid solver, instancing): action=list|get.", {"action": "list|get", "name": "string", "query": "string"}, t_tutorials),
    ("glsl_solutions", "Catálogo de soluciones y fixes a errores frecuentes del compilador GLSL en TouchDesigner.", {"error_query": "string", "limit": "int"}, t_glsl_solutions),
    ("python_api", "Referencia offline de la API Python de TouchDesigner: inspección de clases, métodos, atributos y docstrings sin TD abierto.", {"class_name": "string", "member_or_method": "string", "search": "string", "limit": "int"}, t_python_api),
    ("discovery", "Bitácora empírica de TouchDesigner: quirks de parámetros, límites medidos, cook lag y lecciones de hardware.", {"query": "string", "limit": "int"}, t_discovery),
    ("master_prompts", "Directivas maestras para orquestación de sistemas complejos (feedback sim, pathtracing, validación): action=list|get.", {"action": "list|get", "name": "string"}, t_master_prompts),
    ("glsl_rules", "Reglas GLSL verificadas en vivo, por familia: 6 de POP (write-only, TDIndex, Create Attributes, outputaccess) y 12 de TOP.", {"family": "pop|top", "rule": "texto a buscar en el título", "query": "texto en el cuerpo"}, t_glsl_rules),
    ("glsl_analyze", "Análisis ESTÁTICO (sin TD) de un shader o snippet Python contra las reglas verificadas: POP R1/R2/R3/R4, TOP R1/R2, Python R6. Devuelve errores con el fix y los parámetros exactos de Create Attributes.", {"code": "string (requerido)", "family": "pop|top|python"}, t_glsl_analyze),
    ("glsl_curriculum", "Ejemplos GLSL POP con fuentes citadas (Book of Shaders por capítulo + corpus verificado).", {"query": "string"}, t_glsl_curriculum),
    ("contracts", "Contratos verificados EN VIVO contra TD 2025.32460 + TDMCP 1.1.55 (cook lag, render POP, pointspriteMAT, API Python, verificación). list=true = índice; section='cook_lag' / 'pop_render_network' / 'C2' para filtrar; query= texto libre.", {"query": "string", "section": "string", "list": "boolean", "max_chars": "int 1000-40000"}, t_contracts),
]
# ── tools que necesitan TouchDesigner: hablan MCP contra el server OFICIAL (13316) ──
try:
    from live import LIVE_TOOLS
    TOOLS = TOOLS + LIVE_TOOLS
except Exception as _e:  # el server sigue arrancando aunque no esté TD
    print(f"[{SERVER_NAME}] tools live no cargadas: {_e}", file=sys.stderr)

TOOL_MAP = {name: (desc, schema, fn) for name, desc, schema, fn in TOOLS}


def _schema(props: dict) -> dict:
    out = {"type": "object", "properties": {}, "required": []}
    for k, v in props.items():
        t = "string"
        if isinstance(v, str) and v.startswith("int"):
            t = "integer"
        elif isinstance(v, str) and v.startswith("boolean"):
            t = "boolean"
        out["properties"][k] = {"type": t, "description": v}
        if isinstance(v, str) and "requerido" in v:
            out["required"].append(k)
    return out


def handle(msg: dict):
    method = msg.get("method")
    mid = msg.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": PROTOCOL,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION,
                           "title": "td-knowledge — capa de conocimiento offline de TouchDesigner"}}}
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": [
            {"name": n, "description": d, "inputSchema": _schema(s)} for n, d, s, _ in TOOLS]}}
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        if name not in TOOL_MAP:
            return {"jsonrpc": "2.0", "id": mid, "result": {"content": [
                {"type": "text", "text": json.dumps({"error": f"tool desconocida '{name}'", "tools": list(TOOL_MAP)})}], "isError": True}}
        try:
            res = TOOL_MAP[name][2](args)
            is_err = isinstance(res, dict) and "error" in res
            return {"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False, indent=1)}], "isError": bool(is_err)}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": json.dumps(
                {"error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()[-1200:]})}], "isError": True}}
    if mid is None:
        return None
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}


def main() -> int:
    global KB_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", default=KB_DIR)
    ap.add_argument("--selftest", action="store_true", help="corre todas las tools con args de prueba y sale")
    a = ap.parse_args()
    KB_DIR = a.kb
    os.environ["TD_KNOWLEDGE_KB"] = KB_DIR
    print(f"[{SERVER_NAME}] kb={KB_DIR}", file=sys.stderr, flush=True)
    if a.selftest:
        try:
            from live import LIVE_NAMES
        except Exception:
            LIVE_NAMES = []
        for n, _d, _s, fn in TOOLS:
            if n in LIVE_NAMES:
                print(f"  {n:<22} live (probar con test_live.py)")
                continue
            try:
                r = fn({"query": "noise", "text": "webcam", "op_type": "noiseTOP", "kind": "patterns",
                        "action": "list", "family": "pop", "code": "P[id] = P[id] * 1.0;\n",
                        "name_or_slug": "particlePOP", "class_name": "noiseTOP", "topic": "cook lag",
                        "error_query": "undeclared"})
                print(f"  {n:<22} ok={not (isinstance(r, dict) and 'error' in r)}")
            except Exception as e:
                print(f"  {n:<22} EXC {type(e).__name__}: {e}")
        return 0
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            print(f"[{SERVER_NAME}] JSON inválido: {e}", file=sys.stderr, flush=True)
            continue
        reply = handle(msg)
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())

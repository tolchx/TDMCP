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
import difflib
import json
import os
import re
import sqlite3
import sys
import traceback

SERVER_NAME = "td-knowledge"
SERVER_VERSION = "0.2.0"
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


def arg_int(a: dict, key: str, default: int, lo: int | None = None, hi: int | None = None) -> int:
    """Entero tolerante: los clientes MCP mandan a veces "8", 8.0, "" o basura.
    Nunca levanta: lo inválido cae al default y después se acota a [lo, hi]."""
    v = a.get(key)
    try:
        n = int(float(v)) if v not in (None, "", True, False) else default
    except (TypeError, ValueError):
        n = default
    if lo is not None:
        n = max(lo, n)
    if hi is not None:
        n = min(hi, n)
    return n


def arg_bool(v, default: bool = False) -> bool:
    """Booleano tolerante: acepta true/false reales y también "true"/"0"/"no"/"sí"."""
    if v is None or v == "":
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "y", "si", "sí", "on"):
        return True
    if s in ("0", "false", "no", "n", "off"):
        return False
    return default


def pick(names: list[str], query: str) -> tuple[str | None, list[str]]:
    """Elige por nombre con prioridad exacta > prefijo > substring (case-insensitive).
    -> (elegido o None, otras coincidencias). Query vacía no elige nada (antes devolvía
    el primer elemento porque '' está contenido en todo)."""
    q = (query or "").strip().lower()
    if not q:
        return None, []
    low = [(n, n.lower()) for n in names]
    for tier in (lambda l: l == q, lambda l: l.startswith(q), lambda l: q in l):
        hits = [n for n, l in low if tier(l)]
        if hits:
            return hits[0], hits[1:8]
    return None, []


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
    if arg_bool(a.get("list_docs")):
        fam = (family or "POP").strip().upper()
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
    # Sólo caracteres de palabra: el tokenizer unicode61 de la tabla parte en '.', '-', '+',
    # comillas, etc. Antes 'feedbackTOP.par' quedaba como UN término y no matcheaba nada.
    terms = [t for t in re.findall(r"\w+", q.lower()) if len(t) > 1]
    if not terms:
        return ""
    joiner = " AND " if mode == "AND" else " OR "
    return joiner.join(f'"{t}"*' for t in dict.fromkeys(terms))


def _distinct(col: str) -> list[str]:
    key = f"distinct:{col}"
    if key not in _CACHE:
        _CACHE[key] = [r[0] for r in db().execute(f"SELECT DISTINCT {col} FROM docs") if r[0]]
    return _CACHE[key]  # type: ignore[return-value]


def _norm_filter(col: str, value) -> tuple[str | None, str | None]:
    """Normaliza el valor de un filtro contra los valores reales de la columna
    (case-insensitive). -> (valor canónico o None, aviso o None)."""
    if value in (None, ""):
        return None, None
    v = str(value).strip()
    for real in _distinct(col):
        if real.lower() == v.lower():
            return real, None
    return v, f"'{v}' no es un valor de {col}; válidos: {sorted(_distinct(col))}"


def t_kb_search(a: dict) -> dict:
    q = str(a.get("query") or "").strip()
    if not q:
        return {"error": "falta 'query'"}
    limit = arg_int(a, "limit", 8, 1, 25)
    con = db()
    where, params, avisos, filters = [], [], [], {}
    for arg, col in (("family", "family"), ("trust_tier", "trustTier"), ("source_type", "sourceType")):
        val, aviso = _norm_filter(col, a.get(arg))
        if val is None:
            continue
        if aviso:
            avisos.append(aviso)
        where.append(f"{col} = ?")
        params.append(val)
        filters[arg] = val
    sql_extra = (" AND " + " AND ".join(where)) if where else ""
    used = "AND"
    rows = []
    for mode in ("AND", "OR"):
        match = _fts(q, mode)
        if not match:
            return {"error": "sin términos de búsqueda válidos (mínimo 2 caracteres por término)"}
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
    out = {
        "query": q, "match": used, "count": len(rows), "filters": filters,
        "results": [
            {"name": r["name"], "family": r["family"], "page": r["pageTitle"], "slug": r["pageSlug"],
             "trust_tier": r["trustTier"], "source_type": r["sourceType"],
             "summary": clip(r["summary"], 260), "fragmento": clip(r["frag"], 400)}
            for r in rows
        ],
    }
    if avisos:
        out["avisos"] = avisos
    return out


def _like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def t_kb_get(a: dict) -> dict:
    key = str(a.get("name_or_slug") or a.get("name") or "").strip()
    if not key:
        return {"error": "falta 'name_or_slug'"}
    con = db()
    row = con.execute(
        "SELECT name, family, pageTitle, pageSlug, url, trustTier, sourceType, summary, body FROM docs "
        "WHERE name = ? OR pageSlug = ? OR name = ? COLLATE NOCASE OR pageSlug = ? COLLATE NOCASE LIMIT 1",
        (key, key, key, key),
    ).fetchone()
    if row is None:
        pat = f"%{_like_escape(key)}%"
        like = con.execute(
            "SELECT name, family, pageTitle, pageSlug FROM docs "
            "WHERE name LIKE ? ESCAPE '\\' OR pageSlug LIKE ? ESCAPE '\\' LIMIT 8",
            (pat, pat),
        ).fetchall()
        return {"error": f"no existe '{key}' en la KB", "quizas": [dict(r) for r in like],
                "hint": "probá kb_search con texto libre"}
    maxc = arg_int(a, "max_chars", 6000, 400, 40000)
    return {
        "name": row["name"], "family": row["family"], "page": row["pageTitle"], "slug": row["pageSlug"],
        "url": row["url"], "trust_tier": row["trustTier"], "source_type": row["sourceType"],
        "summary": row["summary"], "body": clip(row["body"], maxc), "body_total_chars": len(row["body"] or ""),
    }


def t_pop_matrix(a: dict) -> dict:
    pm = load_json("pop_matrix.json")
    t = str(a.get("type") or "").strip()
    if t:
        tipos = sorted(str(x.get("type", "")) for x in pm.get("results", []))
        for r in pm.get("results", []):
            if str(r.get("type", "")).lower() in (t.lower(), t.lower() + "pop"):
                return {"type": r["type"], "medido_en": pm.get("td_build"), "metodo": pm.get("method"), "registro": r}
        base = re.sub(r"pop$", "", norm(t)) or norm(t)
        close = [x for x in tipos if base and base in x.lower()]
        return {"error": f"'{t}' no está en la matriz ({len(tipos)} tipos medidos)",
                "quizas": close[:10], "tipos": tipos if not close else f"{len(tipos)} tipos (pedí sin 'type' para el resumen)"}
    cat = str(a.get("category") or "").strip()
    if cat:
        cats = pm.get("categories", {})
        real = next((k for k in cats if k.lower() == cat.lower()), None)
        if real is None:
            return {"error": f"categoría desconocida '{cat}'", "categorias": list(cats.keys())}
        return {"category": real, "count": len(cats[real]), "tipos": cats[real]}
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


def _topology_info(op_key: str, td_guess: str | None = None) -> dict | None:
    if not os.path.exists(kb("topology.json")):
        return None
    topo = (load_json("topology.json") or {}).get("operators") or {}
    for cand in (op_key, td_guess or ""):
        if not cand:
            continue
        if cand in topo:
            return topo[cand]
        nc = norm(cand)
        for k, v in topo.items():
            if norm(k) == nc:
                return v
    return None


def t_ops_doc(a: dict) -> dict:
    key = str(a.get("op_type") or a.get("slug") or "").strip()
    if not key:
        return {"error": "falta 'op_type' (ej. 'noiseTOP' o 'Noise_TOP')"}
    doc, all_ops = _load_op(key)
    if doc is None:
        close = [s for s in all_ops if norm(key) in norm(s)][:10]
        return {"error": f"sin doc para '{key}'", "quizas": close or all_ops[:10]}
    sec = str(a.get("section") or "").strip()
    td_guess = doc.get("tdOpTypeGuess")
    topo = _topology_info(key, td_guess)
    cdefs = (ts("catalog", "CREATION_DEFAULTS") or {}).get(td_guess or key)
    base = {"family": doc.get("family"), "op_type": td_guess, "page": doc.get("pageTitle"),
            "slug": doc.get("pageSlug"), "url": doc.get("url"), "summary": clip(doc.get("summary"), 900)}
    if topo:
        base["topology"] = {k: topo.get(k) for k in ("inputCount", "isMultiInput", "inputs", "outputs", "connectsTo", "warnings") if topo.get(k) is not None}
    if cdefs:
        base["creation_defaults"] = cdefs
    if sec:
        if sec.lower() == "topology" and topo:
            return {**base, "section": "topology", "content": topo}
        real = next((k for k in doc if k.lower() == sec.lower()), None)
        if real is not None:
            return {**base, "section": real, "content": clip(json.dumps(doc[real], ensure_ascii=False, indent=1), 8000)}
        base["aviso"] = f"la sección '{sec}' no existe en este doc; devuelvo el resumen"
    for k in ("inputs", "useCases", "commonCombinations", "troubleshooting", "localNotes", "examples"):
        if doc.get(k):
            base[k] = clip(json.dumps(doc[k], ensure_ascii=False, indent=1), 1500)
    base["secciones_disponibles"] = [k for k in doc if k not in base] + (["topology"] if topo else [])
    return base


def t_ops_params(a: dict) -> dict:
    key = str(a.get("op_type") or "").strip()
    if not key:
        return {"error": "falta 'op_type' (ej. 'noiseTOP')"}
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
    kind = str(a.get("kind") or "").strip().lower()
    files = {
        "patterns": "pops/patterns.json",
        "wiki_params": "pops/wiki_params.json",
        "pop_inventory": "pops/pop_inventory.json",
        "validation": "pops/validation.json",
        "glsl_library": "pops/glsl_library.json",
        "glsl_pops_reference": "pops/glsl_pops_reference.json",
        "glsl_curriculum": "pops/glsl_curriculum.json",
        "pop_chains": "templates/pop-chains.json",
        "pop_networks": "templates/pop_networks.json",
        "pop_parameters": "reference/pop-parameters.json",
        "real_world_topology": "real-world-topology.json",
    }
    ts_kinds = {
        "pop_rules": ("pop_validation", "POP_RULES"),
        "attribute_rules": ("pop_validation", "ATTRIBUTE_RULES"),
        "bridges": ("pop_validation", "VALID_BRIDGES"),
        "pop_style": ("catalog", "POP_PARAMETER_STYLE"),
    }
    avail = [k for k, v in files.items() if os.path.exists(kb(v))] + list(ts_kinds.keys())
    if not kind:
        return {"error": "falta 'kind'", "kinds_disponibles": avail}
    if kind in ts_kinds:
        d = ts(*ts_kinds[kind])
    elif kind in files and os.path.exists(kb(files[kind])):
        d = load_json(files[kind])
    else:
        return {"error": f"kind inválido '{kind}'", "kinds_disponibles": avail}
    q = str(a.get("query") or "").strip().lower()
    if q:
        if isinstance(d, dict):
            hit = {}
            for k, v in d.items():
                if q in k.lower() or q in json.dumps(v, ensure_ascii=False).lower():
                    hit[k] = clip(json.dumps(v, ensure_ascii=False, indent=1), 3000)
            return {"kind": kind, "query": q, "keys": list(hit), "content": hit}
        if isinstance(d, list):
            hit_list = [it for it in d if q in json.dumps(it, ensure_ascii=False).lower()]
            return {"kind": kind, "query": q, "count": len(hit_list),
                    "content": clip(json.dumps(hit_list, ensure_ascii=False, indent=1), 9000)}
    return {"kind": kind, "keys": list(d.keys()) if isinstance(d, dict) else f"lista({len(d) if isinstance(d, list) else 1})",
            "content": clip(json.dumps(d, ensure_ascii=False, indent=1), 9000)}


# --- resolve_operator: los sinónimos de la KB están en inglés; este glosario ES→EN es lo que
# hace verdad el "ES/EN" de la descripción (antes 'ruido' o 'desenfoque' devolvían 0 candidatos).
_ES_EN_PHRASES = {
    "camara web": "webcam", "fondo verde": "green screen", "nube de puntos": "point cloud",
    "en vivo": "live", "llave de croma": "chroma key", "deteccion de bordes": "edge detect",
}
_ES_EN = {
    "ruido": "noise", "desenfoque": "blur", "desenfocar": "blur", "difuminar": "blur", "borroso": "blur",
    "camara": "camera", "particula": "particle", "particulas": "particle", "sonido": "audio",
    "microfono": "audio device", "musica": "audio file", "retroalimentacion": "feedback",
    "realimentacion": "feedback", "mezcla": "composite", "mezclar": "composite", "combinar": "composite",
    "componer": "composite", "texto": "text", "tabla": "table", "esfera": "sphere", "caja": "box",
    "cubo": "box", "circulo": "circle", "linea": "line", "lineas": "line", "grilla": "grid",
    "rejilla": "grid", "cuadricula": "grid", "toro": "torus", "luz": "light", "luces": "light",
    "pelicula": "movie", "imagen": "image", "archivo": "file", "umbral": "threshold",
    "recortar": "crop", "recorte": "crop", "transformar": "transform", "mover": "transform",
    "rotar": "transform", "escalar": "transform", "desplazar": "displace", "desplazamiento": "displace",
    "brillo": "level", "contraste": "level", "espejo": "mirror", "reflejar": "mirror", "voltear": "flip",
    "oscilador": "lfo", "onda": "wave", "filtro": "filter", "filtrar": "filter", "suavizar": "filter",
    "retraso": "delay", "demora": "delay", "contador": "count", "contar": "count", "aleatorio": "random",
    "azar": "random", "estela": "trail", "estelas": "trail", "rastro": "trail", "instancia": "instance",
    "instancias": "instance", "instanciar": "instance", "geometria": "geometry", "malla": "mesh",
    "sombreador": "shader", "teclado": "keyboard", "raton": "mouse", "colores": "color",
    "gradiente": "ramp", "degradado": "ramp", "resplandor": "glow", "borde": "edge", "bordes": "edge",
    "croma": "chroma key", "renderizar": "render", "salida": "out", "entrada": "in", "pantalla": "screen",
    "ventana": "window", "tiempo": "time", "reloj": "clock", "temporizador": "timer",
    "velocidad": "speed", "fuerza": "force", "gravedad": "gravity", "viento": "wind", "punto": "point",
    "puntos": "point", "vivo": "live",
}
_STOP = {
    "que", "quiero", "necesito", "una", "uno", "unos", "unas", "los", "las", "del", "por", "para",
    "con", "sin", "como", "hacer", "crear", "usar", "algo", "sobre", "desde", "hasta", "mas", "muy",
    "the", "and", "for", "with", "want", "need", "make", "create", "use", "some", "from", "into",
    "operator", "operador", "nodo", "node",
}


def _deaccent(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _family_hints(hints) -> list[tuple[str, list[str]]]:
    """FAMILY_HINTS viene como LISTA de {family, aliases}; se acepta también dict family->aliases."""
    if isinstance(hints, dict):
        return [(str(f), [str(w) for w in (ws or [])]) for f, ws in hints.items()]
    out = []
    for h in hints or []:
        if isinstance(h, dict) and h.get("family"):
            out.append((str(h["family"]), [str(w) for w in (h.get("aliases") or [])]))
    return out


def t_resolve_operator(a: dict) -> dict:
    raw = str(a.get("text") or "").strip()
    if not raw:
        return {"error": "falta 'text'"}
    limit = arg_int(a, "limit", 6, 1, 25)
    q = _deaccent(raw.lower())
    syn = ts("semantic", "TYPE_SYNONYMS") or {}
    toks = [t for t in re.findall(r"[a-z0-9]+", q) if len(t) > 2 and t not in _STOP]
    trad = [en for es, en in _ES_EN_PHRASES.items() if es in q]
    trad += [_ES_EN[t] for t in toks if t in _ES_EN]
    trad = list(dict.fromkeys(trad))
    en_q = " ".join(trad)
    hay = f" {q} {en_q} "
    words = set(toks) | {w for e in trad for w in e.split() if len(w) > 2}

    scores = []
    for op_type, ws in syn.items():
        s, hits = 0, []
        for w in [*(ws or []), re.sub(r"(TOP|CHOP|SOP|DAT|COMP|POP|MAT)$", "", op_type)]:
            wl = _deaccent(str(w).lower()).strip()
            if not wl:
                continue
            if wl == q or wl == en_q or wl in trad:
                sc = 100
            elif re.search(rf"(?<![a-z0-9]){re.escape(wl)}(?![a-z0-9])", hay):
                sc = 70 + min(len(wl), 20)          # la frase entera aparece en el pedido
            elif words & set(wl.split()):
                sc = 50                              # comparte una palabra completa
            elif any(len(t) >= 4 and t in wl for t in words):
                sc = 30                              # coincidencia parcial
            else:
                continue
            if sc > s:
                s = sc
            if sc >= 50 and w in (ws or []):
                hits.append(w)
        if s:
            scores.append((s, op_type, hits[:6]))

    # Conceptos curados (CONCEPTS: lista de {concept, canonical, aliases, note} o dict)
    concepts_raw = ts("semantic", "CONCEPTS") or []
    matched_concepts = []
    if isinstance(concepts_raw, dict):
        concept_iter = [{"concept": k, **v} for k, v in concepts_raw.items() if isinstance(v, dict)]
    else:
        concept_iter = [c for c in concepts_raw if isinstance(c, dict)]
    for cinfo in concept_iter:
        cname = str(cinfo.get("concept") or "")
        ckws = [cname, *(cinfo.get("aliases") or cinfo.get("keywords") or [])]
        if any(re.search(rf"(?<![a-z0-9]){re.escape(_deaccent(str(kw).lower()))}(?![a-z0-9])", hay) for kw in ckws if kw):
            matched_concepts.append(cinfo)
            existing_ops = {op for _, op, _ in scores}
            for pop_op in cinfo.get("primaryOperators") or []:
                if pop_op not in existing_ops:
                    scores.append((65, pop_op, [f"concept:{cname}"]))

    scores.sort(key=lambda x: (-x[0], x[1]))
    cands = [{"type": t, "score": s, "coincidencias": m} for s, t, m in scores[:limit]]
    origen = "sinonimos"
    if not cands:  # fallback: FTS sobre los docs de operadores
        match = _fts(f"{q} {en_q}", "OR")
        if match:
            try:
                rows = db().execute(
                    "SELECT name, family FROM docs WHERE docs MATCH ? AND sourceType IN ('ops','pops') "
                    "ORDER BY bm25(docs, 4.0, 1.0) LIMIT ?", (match, limit)).fetchall()
                cands = [{"type": r["name"], "score": 20, "coincidencias": ["kb_search"]} for r in rows]
                origen = "kb_search (sin sinónimo directo)"
            except sqlite3.OperationalError:
                pass
    fam = []
    for f, aliases in _family_hints(ts("semantic", "FAMILY_HINTS")):
        for al in aliases:
            al_l = _deaccent(al.lower())
            if len(al_l) > 2 and re.search(rf"(?<![a-z0-9]){re.escape(al_l)}(?![a-z0-9])", hay):
                fam.append(f)
                break
    for c in cands:  # la familia del mejor candidato también es una pista
        m = re.search(r"(TOP|CHOP|SOP|DAT|COMP|POP|MAT)$", str(c["type"]))
        if m and m.group(1) not in fam:
            fam.append(m.group(1))

    # Parameter aliases & Attribute aliases (lista de {requested, canonical, note} o dict)
    param_aliases = []
    pa_raw = ts("semantic", "PARAMETER_ALIASES") or []
    pa_iter = [{"requested": k, **(v if isinstance(v, dict) else {"canonical": v})} for k, v in pa_raw.items()] if isinstance(pa_raw, dict) else [x for x in pa_raw if isinstance(x, dict)]
    for item in pa_iter:
        pkl = _deaccent(str(item.get("requested") or "").lower())
        if pkl and re.search(rf"(?<![a-z0-9]){re.escape(pkl)}(?![a-z0-9])", hay):
            param_aliases.append(item)

    attr_aliases = []
    aa_raw = ts("semantic", "ATTRIBUTE_ALIASES") or []
    aa_iter = [{"requested": k, **(v if isinstance(v, dict) else {"canonical": v})} for k, v in aa_raw.items()] if isinstance(aa_raw, dict) else [x for x in aa_raw if isinstance(x, dict)]
    for item in aa_iter:
        akl = _deaccent(str(item.get("requested") or "").lower())
        if akl and re.search(rf"(?<![a-z0-9]){re.escape(akl)}(?![a-z0-9])", hay):
            attr_aliases.append(item)

    # Templates sugeridos
    sug_templates = []
    all_tpls = (ts("templates", "NETWORK_TEMPLATES") or []) + (ts("pops_validate", "POP_NETWORK_TEMPLATES") or [])
    seen_tpls = set()
    for tpl in all_tpls:
        tname = tpl.get("name")
        if not tname or tname in seen_tpls:
            continue
        ttags = {str(x).lower() for x in (tpl.get("tags") or [])} | set(re.findall(r"[a-z0-9]+", tname.lower()))
        if words & ttags:
            seen_tpls.add(tname)
            sug_templates.append(tname)

    out = {"texto": raw, "familia_sugerida": fam[:4], "candidatos": cands, "origen": origen,
           "tipos_indexados": len(syn)}
    if trad:
        out["traduccion"] = trad
    if matched_concepts:
        out["conceptos"] = matched_concepts[:4]
    if param_aliases:
        out["alias_parametros"] = param_aliases
    if attr_aliases:
        out["alias_atributos"] = attr_aliases
    if sug_templates:
        out["templates_sugeridos"] = sug_templates[:5]
    return out


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _bad_action(action: str):
    if action not in ("list", "get"):
        return {"error": f"action inválida '{action}'", "acciones": ["list", "get"]}
    return None


def _all_network_templates() -> list[dict]:
    tl = list(ts("templates", "NETWORK_TEMPLATES") or [])
    seen = {t.get("name") for t in tl if isinstance(t, dict)}
    for extra in (ts("pops_validate", "POP_NETWORK_TEMPLATES") or []):
        if isinstance(extra, dict) and extra.get("name") and extra["name"] not in seen:
            seen.add(extra["name"])
            tl.append(extra)
    if os.path.exists(kb("templates", "pop-chains.json")):
        try:
            chains = (load_json("templates/pop-chains.json") or {}).get("templates") or []
            for ch in chains:
                if isinstance(ch, dict) and ch.get("name") and ch["name"] not in seen:
                    seen.add(ch["name"])
                    tl.append(ch)
        except Exception:
            pass
    custom_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "custom_templates")
    if os.path.isdir(custom_dir):
        for fn in sorted(os.listdir(custom_dir)):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(custom_dir, fn), encoding="utf-8") as fh:
                    ct = json.load(fh)
                if isinstance(ct, dict) and ct.get("name"):
                    if ct["name"] in seen:
                        tl = [x for x in tl if x.get("name") != ct["name"]]
                    seen.add(ct["name"])
                    tl.append(ct)
            except Exception:
                pass
    return tl


def t_templates(a: dict) -> dict:
    tl = _all_network_templates()
    action = str(a.get("action") or "list").strip().lower()
    if _bad_action(action):
        return _bad_action(action)
    specs_dir = kb("templates", "specs")
    spec_files = [f for f in sorted(os.listdir(specs_dir)) if f.endswith(".md")] if os.path.isdir(specs_dir) else []
    if action == "list":
        q = str(a.get("query") or "").lower()
        items = [{"name": t["name"], "type": "network_template", "description": clip(t.get("description"), 200), "tags": t.get("tags"),
                  "complexity": t.get("complexity"), "operadores": len(t.get("operators") or t.get("chain") or [])} for t in tl
                 if not q or q in json.dumps(t, ensure_ascii=False).lower()]
        specs = []
        for sf in spec_files:
            stem = sf[:-3]
            if not q or q in stem.lower():
                specs.append({"name": stem, "type": "template_spec", "file": sf})
        return {"count": len(items) + len(specs), "templates": items, "specs": specs}
    names = [t["name"] for t in tl] + [s[:-3] for s in spec_files]
    name = str(a.get("name") or "").strip()
    if not name:
        return {"error": "falta 'name' para action=get", "nombres": names}
    best, otros = pick(names, name)
    if best is None:
        return {"error": f"sin template '{name}'", "nombres": names}
    for t in tl:
        if t["name"] == best:
            return {"template": t, "otras_coincidencias": otros}
    sf = best + ".md"
    return {"name": best, "type": "template_spec", "file": sf, "otras_coincidencias": otros,
            "content": clip(_read_text(os.path.join(specs_dir, sf)), arg_int(a, "max_chars", 15000, 500, 60000))}


def t_recipes(a: dict) -> dict:
    rd = ts("recipes") or {}
    rs = rd.get("listRecipes") or []
    top_recipes = []
    top_p = kb("recipes", "glsl_top_recipes.json")
    if os.path.exists(top_p):
        try:
            with open(top_p, encoding="utf-8") as f:
                top_recipes = json.load(f)
        except Exception:
            pass
    action = str(a.get("action") or "list").strip().lower()
    if _bad_action(action):
        return _bad_action(action)
    if action == "list":
        q = str(a.get("query") or "").lower()
        items = [{"name": r["name"], "title": r.get("title"), "description": clip(r.get("description"), 240),
                  "tags": r.get("tags"), "complexity": r.get("complexity"), "nodos": len(r.get("nodes") or [])} for r in rs
                 if not q or q in json.dumps(r, ensure_ascii=False).lower()]
        top_items = [{"id": r["id"], "title": r["title"], "category": r.get("category"), "type": "glsl_top_recipe"}
                     for r in top_recipes if not q or q in json.dumps(r, ensure_ascii=False).lower()]
        return {"count": len(items) + len(top_items), "recetas": items, "glsl_top_recipes": top_items, "tags": rd.get("recipeTags")}
    names = [r["name"] for r in rs] + [tr["id"] for tr in top_recipes]
    name = str(a.get("name") or "").strip()
    if not name:
        return {"error": "falta 'name' para action=get", "nombres": names}
    best, otros = pick(names, name)
    if best is None:  # último intento: por título de las recetas glslTOP
        best, otros = pick([tr.get("title", "") for tr in top_recipes], name)
        if best is not None:
            tr = next(t for t in top_recipes if t.get("title") == best)
            return {"glsl_top_recipe": tr, "otras_coincidencias": otros}
        return {"error": f"sin receta '{name}'", "nombres": names}
    for r in rs:
        if r["name"] == best:
            return {"recipe": r, "otras_coincidencias": otros}
    for tr in top_recipes:
        if tr["id"] == best:
            return {"glsl_top_recipe": tr, "otras_coincidencias": otros}
    return {"error": f"sin receta '{a.get('name')}'", "nombres": [r["name"] for r in rs] + [tr["id"] for tr in top_recipes]}


def _rules_md(family: str) -> str:
    f = "rules/GLSL_POP_RULES.md" if (family or "pop").lower().startswith("pop") else "rules/GLSL_TOP_RULES.md"
    with open(kb(f), encoding="utf-8") as fh:
        return fh.read()


def t_glsl_rules(a: dict) -> dict:
    family = str(a.get("family") or "pop").strip().lower()
    if not (family.startswith("pop") or family.startswith("top")):
        return {"error": f"family inválida '{family}'", "families": ["pop", "top"]}
    md = _rules_md(family)
    parts = re.split(r"(?m)^(##\s+Regla\s+\d+\s+—.*)$", md)
    rules = []
    for i in range(1, len(parts), 2):
        head = parts[i].strip("# ").strip()
        rules.append({"regla": head, "texto": clip(parts[i + 1].strip(), 1400)})
    want = str(a.get("rule") or "").strip().lower()
    q = str(a.get("query") or "").strip().lower()
    sel = rules
    if want:
        if want.isdigit() or re.fullmatch(r"r\d+", want):  # '4' o 'R4' = Regla 4 exacta
            num = want.lstrip("r")
            sel = [r for r in rules if re.match(rf"regla\s+{num}\b", r["regla"].lower())]
        else:
            sel = [r for r in rules if want in r["regla"].lower()]
    if q:
        sel = [r for r in sel if q in r["texto"].lower() or q in r["regla"].lower()]
    out = {"family": family, "archivo": "GLSL_POP_RULES.md" if family.startswith("pop") else "GLSL_TOP_RULES.md",
           "reglas_totales": len(rules), "reglas": sel if (want or q) else rules,
           "titulos": [r["regla"] for r in rules]}
    if (want or q) and not sel:
        out["sin_coincidencias"] = f"rule={want!r} query={q!r}"
    return out


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
    if arg_bool(a.get("list")):
        return {"archivo": os.path.relpath(CONTRACTS_MD, os.path.dirname(os.path.abspath(__file__))),
                "secciones": sorted({i["seccion"] for i in items}),
                "contratos": [i["id"] for i in items], "total": len(items)}
    want = str(a.get("section") or "").strip().lower()
    q = str(a.get("query") or "").strip().lower()
    sel = items
    if want:
        if re.fullmatch(r"c\d+", want):
            # 'C1' = la sección C1 exacta (antes también traía C10..C17 por substring)
            sel = [i for i in sel if re.match(rf"{want}(?!\d)", i["seccion"].lower())]
        else:
            sel = [i for i in sel if want in i["id"].lower() or want in i["seccion"].lower()]
    if q:
        sel = [i for i in sel if q in i["texto"].lower() or q in i["id"].lower()]
    if not sel:
        return {"total": 0, "contratos": [],
                "sin_coincidencias": "query=%r section=%r" % (q, want),
                "contratos_disponibles": [i["id"] for i in items]}
    n = arg_int(a, "max_chars", 9000, 1000, 40000)
    return {"total": len(sel), "contratos": [{"seccion": i["seccion"], "id": i["id"],
                                              "texto": clip(i["texto"], n)} for i in sel],
            "nota": "Contratos verificados contra TD vivo 2025.32460 + TDMCP 1.1.55."}


# --- analyzer: puerto fiel de las reglas verificadas (POP R1-R4, F1, F4, multi-input; TOP R1-R2, T4, T10; Python R6, f-string, math)
COMPONENTS = {
    "cd": 4, "color": 4, "n": 3, "uv": 2, "tex": 3, "p": 3, "v": 3,
    "partvel": 3, "partforce": 3, "rot": 3,
    "alpha": 1, "mass": 1, "masa": 1, "partage": 1, "partlife": 1,
    "weight": 1, "dist": 1, "pscale": 1, "pointscale": 1,
}
BUILTIN_WRITE_OK = {"p"}  # P ya existe si hay TDIn_P; igual conviene no leerla (R1)
# Menus reales de attr0name en TD 2025.32460: 'custom' lowercase (verificado en vivo
# 2026-09-28; el valor con mayuscula es rechazado por set_parameters).
ATTR_MENU_CASE = "lowercase"


_GLSL_TYPES = r"(?:float|double|int|uint|bool|[biud]?vec[234]|mat[234](?:x[234])?)"
# escritura: opcional swizzle (Cd[id].rgb = …) y asignación simple o compuesta (+=, *=, …)
_WRITE_RE = re.compile(r"\s*(?:\.\s*[xyzwrgbastpq]{1,4})?\s*([+\-*/%]?=)(?!=)")


def _strip_comments(code: str) -> str:
    code = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), code, flags=re.S)
    return re.sub(r"//[^\n]*", "", code)


def _declared(code: str) -> set[str]:
    """Identificadores declarados en el propio shader (locales, arrays, uniforms, params):
    NO son atributos del POP. Antes `float w[4]; w[0] = 1.;` pedía crear el atributo 'w'."""
    return set(re.findall(rf"\b{_GLSL_TYPES}\s+([A-Za-z_]\w*)", code))


def _writes_and_reads(code: str):
    code = _strip_comments(code)
    skip = _declared(code)
    writes, reads = {}, []
    for m in re.finditer(r"([A-Za-z_]\w*)\s*\[([^\]]*)\]", code):
        attr, idx = m.group(1), m.group(2)
        if attr in skip or attr.startswith(("sTD", "uTD")):
            continue
        w = _WRITE_RE.match(code, m.end())
        if w:
            writes.setdefault(attr, []).append(idx.strip())
            if w.group(1) != "=":  # compuesta: lee la salida además de escribirla (R4)
                reads.append(attr)
        else:
            reads.append(attr)
    return writes, reads


def t_glsl_analyze(a: dict) -> dict:
    raw = str(a.get("code") or "")
    family = str(a.get("family") or "pop").strip().lower()
    if not raw.strip():
        return {"error": "falta 'code'"}
    if not family.startswith(("pop", "top", "py")):
        return {"error": f"family inválida '{family}'", "families": ["pop", "top", "python"]}
    code = _strip_comments(raw)
    errors, warns, notes = [], [], []

    if family.startswith("py"):
        for m in re.finditer(r"\.(numPoints|numPrims|bounds|points)\b(?!\s*\()", code):
            errors.append({"regla": "POP R6", "mensaje": f".{m.group(1)} es MÉTODO en la clase POP, no propiedad",
                           "fix": f".{m.group(1)}()", "pos": m.start()})
        # f-string con backslash dentro de {...} (falla en Python <= 3.11)
        for m in re.finditer(r'\bf(["\'])(.*?)\1', code):
            for expr in re.findall(r"\{([^}]*)\}", m.group(2)):
                if "\\" in expr:
                    errors.append({"regla": "PY F-STRING",
                                   "mensaje": "f-string con backslash (\\) dentro de {...} da SyntaxError en Python <= 3.11 (TouchDesigner)",
                                   "fix": "extraé la expresión con backslash a una variable antes del f-string"})
                    break
        # Funciones matemáticas sueltas sin prefijo math. o np.
        if not re.search(r"from\s+math\s+import", code):
            for m in re.finditer(r"(?<![.\w])\b(sin|cos|tan|asin|acos|atan|atan2|sqrt|exp|log|log10|floor|ceil|radians|degrees)\s*\(", code):
                warns.append({"regla": "PY MATH", "mensaje": f"'{m.group(1)}()' sin prefijo math. o np.",
                              "fix": f"import math; math.{m.group(1)}(...)"})
        if re.search(r"\.ops\s*\(", code):
            warns.append({"regla": "PY API", "mensaje": ".ops() no es estándar para buscar hijos en un COMP",
                          "fix": "usá comp.findChildren() o op('...')"})
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
        if re.search(r"\buniform\d+name\b", raw):
            errors.append({"regla": "TOP T4", "mensaje": "glslTOP NO tiene parámetros uniform0name..uniform9name",
                           "fix": "usá vec0name..vec9name + vec0valuex/y/z/w"})
        mo = re.search(r"\bout\s+vec4\s+(\w+)", code)
        if mo and not re.search(rf"\b{mo.group(1)}\s*(?:\.\s*\w+)?\s*=(?!=)", code):
            warns.append({"regla": "TOP R1", "mensaje": f"la salida '{mo.group(1)}' se declara pero nunca se asigna",
                          "fix": f"{mo.group(1)} = TDOutputSwizzle(...);"})
        if re.search(r"\bTDOutputSwizzle\b", code):
            notes.append("TDOutputSwizzle detectado: es el idiom correcto para el canal de salida.")
        if re.search(r"\bsTD2DInputs\b", code):
            notes.append("TOP T10: sTD2DInputs lee las texturas conectadas al glslTOP. Si armás un loop con feedbackTOP, necesita timeline corriendo para acumular.")
        return {"family": "top", "ok": not errors, "errores": errors, "warnings": warns, "notas": notes}

    # ---- POP
    out_attrs = sorted(writes)
    if not re.search(r"\bvoid\s+main\s*\(\s*\)", code):
        errors.append({"regla": "POP F1", "mensaje": "falta void main() en el compute shader POP",
                       "fix": "void main() { const uint id = TDIndex(); if (id >= TDNumElements()) return; ... }"})
    if "TDIndex" not in code:
        errors.append({"regla": "POP R2", "mensaje": "no usa TDIndex() para iterar los puntos",
                       "fix": "const uint id = TDIndex();"})
    if re.search(r"\bTDNumElements\s*\(\s*[^)\s]+\s*\)", code):
        errors.append({"regla": "POP F4", "mensaje": "TDNumElements() NO recibe argumentos; pasarle un índice no compila",
                       "fix": "usá TDNumElements() sin argumentos, o TDInputNumPoints(k) para consultar el input k"})
    if not re.search(r">=\s*TDNumElements\s*\(\s*\)|TDNumElements\s*\(\s*\)\s*<=|<\s*TDNumElements\s*\(\s*\)", code):
        errors.append({"regla": "POP R2", "mensaje": "falta la guarda de rango",
                       "fix": "if (id >= TDNumElements()) return;"})
    for attr in sorted(set(reads)):
        if attr in writes:
            errors.append({"regla": "POP R4 (y R1 si es P)", "mensaje": f"'{attr}' se escribe y se lee en el mismo main() "
                           "(incluye asignaciones compuestas como +=, *=)",
                           "fix": f"si es la salida [{attr}] usá TDIn_{attr}(0, id); si necesitás leerla, poné outputaccess='readwrite'"})
    if "P" in writes and "TDIn_P" not in code:
        warns.append({"regla": "POP R1", "mensaje": "escribe P sin leer la entrada (TDIn_P): verificá el origen de los valores",
                      "fix": "P[id] = TDIn_P(0, id) * ...;"})
    extra_inputs = sorted({int(m.group(1)) for m in re.finditer(r"\bTDIn_\w+\s*\(\s*(\d+)\s*,", code) if int(m.group(1)) > 0})
    if extra_inputs:
        notes.append({"regla": "POP MULTI-INPUT",
                      "mensaje": f"el shader lee TDIn_*(k, ...) de inputs secundarios {extra_inputs}; asegurate de cablear esos inputs en el glslPOP",
                      "inputs_requeridos": [0, *extra_inputs]})
    create = [x for x in out_attrs if x.lower() not in BUILTIN_WRITE_OK]
    if create:
        notes.append({"regla": "POP R3", "mensaje": "los atributos que se escriben y no vienen en la entrada hay que crearlos "
                       "en la página Create Attributes (outputattrs solo selecciona atributos existentes)"})
        for i, x in enumerate(create):
            name_val = "custom" if ATTR_MENU_CASE == "lowercase" else "Custom"
            notes.append({"attr": x, "parametros": {"attr%dname" % i: name_val, "attr%dcustomname" % i: x,
                                                     "attr%dnumcomps" % i: COMPONENTS.get(x.lower(), 1)}})
    out_inputs = sorted(x for x in out_attrs if x.lower() in BUILTIN_WRITE_OK)
    if out_inputs:  # antes sólo salía si además había atributos a crear
        notes.append({"regla": "POP R3 (outputattrs)", "mensaje": "los atributos que SI vienen en la entrada y se "
                       "reescriben (ej. P) hay que listarlos en el par 'outputattrs' para que el preamble "
                       "los declare — sin eso: \"'P' : undeclared identifier\" al compilar (verificado 2026-09-28)",
                      "outputattrs": " ".join(out_inputs)})
    if "readwrite" in raw:
        notes.append("Menciona readwrite: recordá que es un parámetro del nodo (outputaccess), no una línea de GLSL.")
    return {"family": "pop", "ok": not errors, "escribe": out_attrs, "lee": sorted(set(reads)),
            "errores": errors, "warnings": warns, "notas": notes}


_OP_PROPS = {
    "display": "op.display = True  (propiedad booleana del OP, NO existe en op.par — Contrato C2/C14)",
    "render": "op.render = True  (propiedad booleana del OP, NO existe en op.par — Contrato C2/C14)",
    "bypass": "op.bypass = True  (propiedad booleana del OP, NO existe en op.par)",
    "lock": "op.lock = True  (propiedad booleana del OP, NO existe en op.par)",
    "viewer": "op.viewer = True  (propiedad booleana del OP, NO existe en op.par)",
    "expose": "op.expose = True  (propiedad booleana del OP, NO existe en op.par)",
    "allowcooking": "op.allowCooking = True  (propiedad booleana del COMP, NO existe en op.par)",
    "nodex": "op.nodeX = 200  (coordenada X en el editor de red, propiedad del OP)",
    "nodey": "op.nodeY = 100  (coordenada Y en el editor de red, propiedad del OP)",
    "color": "op.color = (r, g, b)  (color del nodo en la red; si buscabas el atributo POP Color usá attr0customname='Color')",
    "comment": "op.comment = 'texto'  (comentario del nodo, propiedad del OP)",
}


def t_validate_pop_pars(a: dict) -> dict:
    """Valida nombres de parámetros contra la matriz POP (97 POPs), ops_doc (507 ops) y python_api (todas las familias), detectando propiedades OP y co-dependencias."""
    op_type = str(a.get("op_type") or a.get("type") or "").strip()
    if not op_type:
        return {"error": "falta 'op_type' (ej. 'noisePOP', 'particlePOP', 'renderTOP', 'pointspriteMAT')"}
    raw_pars = a.get("params") or a.get("parameters") or ""
    if isinstance(raw_pars, dict):
        want_pars = [str(k).strip() for k in raw_pars.keys() if str(k).strip()]
    elif isinstance(raw_pars, list):
        want_pars = [str(x).strip() for x in raw_pars if str(x).strip()]
    else:
        s = str(raw_pars).strip()
        if s.startswith(("[", "{")):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, dict):
                    want_pars = [str(k).strip() for k in parsed.keys() if str(k).strip()]
                elif isinstance(parsed, list):
                    want_pars = [str(x).strip() for x in parsed if str(x).strip()]
                else:
                    want_pars = [p for p in re.split(r"[\s,;]+", s) if p]
            except Exception:
                want_pars = [p for p in re.split(r"[\s,;]+", s) if p]
        else:
            want_pars = [p for p in re.split(r"[\s,;]+", s) if p]

    pm = load_json("pop_matrix.json")
    pop_rec = None
    for r in pm.get("results", []):
        rt = str(r.get("type", ""))
        if rt.lower() in (op_type.lower(), op_type.lower() + "pop"):
            pop_rec = r
            break

    real_params: dict[str, dict] = {}
    canonical = op_type
    source = "pop_matrix (live-verified)"
    if pop_rec:
        canonical = pop_rec["type"]
        for p in pop_rec.get("params") or []:
            if isinstance(p, dict) and p.get("name"):
                real_params[p["name"]] = p
            elif isinstance(p, str):
                real_params[p] = {"name": p}
    else:
        doc, all_ops = _load_op(op_type)
        if doc is not None:
            canonical = doc.get("tdOpTypeGuess") or op_type
            source = "ops_doc (offline)"
            for p in doc.get("parameters") or []:
                if isinstance(p, dict) and p.get("name"):
                    real_params[p["name"]] = p
        if not real_params and os.path.exists(kb("reference", "python-api-classes.json")):
            _, flat_py = _get_py_api()
            py_cls = flat_py.get(op_type.lower())
            if py_cls:
                canonical = py_cls.get("name") or canonical
                source = "python_api (offline)"
                for p in py_cls.get("parameters") or []:
                    if isinstance(p, dict) and p.get("name"):
                        real_params[p["name"]] = p
        if doc is None and not real_params:
            tipos = [str(x.get("type", "")) for x in pm.get("results", [])]
            close = [x for x in tipos if norm(op_type) in norm(x)][:10]
            return {"error": f"operador '{op_type}' no encontrado en pop_matrix, ops_doc ni python_api", "quizas": close}

    if not want_pars:
        return {
            "op_type": canonical,
            "source": source,
            "total_params": len(real_params),
            "param_names": sorted(real_params.keys())[:250],
            "nota": "Pasá params='seed, amp, period' para validar nombres específicos y co-dependencias contra el operador.",
        }

    valid, unknown, suggestions, codep_warnings = [], [], {}, []
    all_names = sorted(real_params.keys())
    pa_raw = ts("semantic", "PARAMETER_ALIASES") or []
    aliases = {str(x.get("requested") or "").lower(): x for x in pa_raw if isinstance(x, dict)} if isinstance(pa_raw, list) else pa_raw
    want_set = {w.lower() for w in want_pars}
    can_low = canonical.lower()

    for wp in want_pars:
        wpl = wp.lower()
        if wpl in _OP_PROPS:
            unknown.append(wp)
            suggestions[wp] = {"property_not_par": True, "fix": _OP_PROPS[wpl]}
            continue
        if wp in real_params:
            valid.append(wp)
            continue
        # Soportar expansión de componentes numéricos/vectoriales cuando el doc guarda el nombre base
        base_m = re.match(r"^([a-z0-9_]+?)(?:[xyzwrgb]|[0-3])$", wpl)
        if base_m and base_m.group(1) in real_params:
            valid.append(wp)
            continue
        tuple_exp = [n for n in all_names if n in (f"{wp}x", f"{wp}y", f"{wp}z", f"{wp}w", f"{wp}r", f"{wp}g", f"{wp}b", f"{wp}0", f"{wp}1", f"{wp}2", f"{wp}3", f"{wp}u", f"{wp}v")]
        unknown.append(wp)
        sug: dict = {}
        if tuple_exp:
            sug["tuple_components"] = tuple_exp
            sug["hint"] = f"'{wp}' es el prefijo de un parámetro compuesto; usá {tuple_exp}"
        if can_low == "rectanglepop" and wpl in ("sizex", "sizey", "sizez", "size"):
            sug["operator_trap"] = "En rectanglePOP el tamaño es 'sizeu' y 'sizev' (NO sizex/sizey — Contrato C15)"
        elif can_low == "pointspritemat" and wpl in ("attensizenear", "pscale", "size", "pointscale"):
            sug["operator_trap"] = "En pointspriteMAT el parámetro real de escala de punto es 'pointsize' (Contrato C2)"
        elif can_low == "spherepop" and wpl in ("radius", "columns"):
            sug["operator_trap"] = "En spherePOP los parámetros reales son 'radx/rady/radz' y 'cols/rows' (Contrato C10)"
        close = difflib.get_close_matches(wpl, all_names, n=5, cutoff=0.45)
        substr = [n for n in all_names if wpl in n.lower() or n.lower() in wpl][:5]
        cands = list(dict.fromkeys([*close, *substr]))
        if cands:
            sug["closest_in_op"] = cands[:6]
        if wpl in aliases:
            sug["semantic_alias"] = aliases[wpl]
        suggestions[wp] = sug

    # Co-dependency & Contract checks
    if can_low.endswith("top") and ({"resolutionw", "resolutionh"} & want_set) and "outputresolution" not in want_set:
        codep_warnings.append("TOP Resolution: al fijar 'resolutionw'/'resolutionh' debés incluir 'outputresolution=\"custom\"' para que surta efecto.")
    if can_low == "forceradialpop" and ({"globforcex", "globforcey", "globforcez"} & want_set) and "globforcemult" not in want_set:
        codep_warnings.append("forceradialPOP: 'globforcemult' viene en 0 por defecto; fijá 'globforcemult=1' o 'globforce*' no tendrá efecto.")
    if can_low == "windpop" and ({"windspeedx", "windspeedy", "windspeedz"} & want_set) and "windspeedmult" not in want_set:
        codep_warnings.append("windPOP: recordá verificar que 'windspeedmult' sea distinto de 0 al configurar 'windspeed*'.")
    if can_low == "particlepop" and "timeintegration" not in want_set:
        codep_warnings.append("particlePOP (Contrato C10): requiere 'timeintegration=1' (ON) y un loop de feedback (particlesupdatepop) para moverse.")
    if can_low == "triangulatepop" and "triangulatequads" not in want_set:
        codep_warnings.append("triangulatePOP (Contrato C18): no triangula quads a menos que actives 'triangulatequads=1'.")
    if can_low == "neighborpop" and "nebroutput" in want_set and "nebrptattrs" not in want_set:
        codep_warnings.append("neighborPOP (Contrato C17): con 'nebroutput=\"avg\"' debés fijar también 'nebrptattrs=\"P\"' (viene vacío por defecto).")
    if any(re.match(r"^(attr|vec|comb|mix)[1-9]", w) for w in want_set):
        codep_warnings.append("Secuencias TD (Contrato C2/C20): antes de setear bloques índice >= 1 (attr1*, vec1*, comb1*), expandí la secuencia con node.par.<seq>.numBlocks = N.")

    out_res = {
        "op_type": canonical,
        "source": source,
        "ok": len(unknown) == 0,
        "valid": valid,
        "unknown": unknown,
        "suggestions": suggestions,
        "total_measured_params": len(real_params),
    }
    if codep_warnings:
        out_res["codependency_warnings"] = codep_warnings
    return out_res


def t_glsl_curriculum(a: dict) -> dict:
    sh_dir = kb("shaders")
    shaders = sorted(f for f in os.listdir(sh_dir) if f.endswith((".glsl", ".txt"))) if os.path.isdir(sh_dir) else []
    curr_path = kb("pops", "glsl_curriculum.json")
    curr_data = load_json("pops/glsl_curriculum.json") if os.path.exists(curr_path) else {}
    curr_entries = curr_data.get("entries") or []

    # 1. Consulta puntual de una entrada del curriculum por id o nombre
    entry_q = str(a.get("entry") or a.get("id") or "").strip()
    if entry_q:
        eids = [str(e.get("id", "")) for e in curr_entries]
        best_id, otros_id = pick(eids, entry_q)
        if best_id is None:
            titles = [str(e.get("titulo_es", "")) for e in curr_entries]
            best_t, otros_id = pick(titles, entry_q)
            if best_t is not None:
                entry = next(e for e in curr_entries if e.get("titulo_es") == best_t)
                return {"entry": entry, "otras_coincidencias": otros_id}
            return {"error": f"entrada '{entry_q}' no encontrada en glsl_curriculum", "ids_disponibles": eids[:25]}
        entry = next(e for e in curr_entries if e.get("id") == best_id)
        return {"entry": entry, "otras_coincidencias": otros_id}

    # 2. Ruta de aprendizaje ordenada por prerrequisitos
    if arg_bool(a.get("learning_path")):
        path_items = [
            {"id": e.get("id"), "titulo_es": e.get("titulo_es"), "familia": e.get("familia"),
             "concepto": e.get("concepto"), "prerequisitos": e.get("prerequisitos")}
            for e in curr_entries
        ]
        return {"count": len(path_items), "metadata": curr_data.get("metadata"), "learning_path": path_items}

    # 3. Shader suelto por archivo
    sh_name = str(a.get("shader") or "").strip()
    if sh_name:
        best, otros = pick(shaders, sh_name)
        if best is None:
            return {"error": f"shader '{sh_name}' no encontrado", "ejemplos": shaders[:12],
                    "hint": "list_shaders=true para el índice completo, o entry='<id>' para el curriculum"}
        return {"shader": best, "otras_coincidencias": otros, "content": _read_text(os.path.join(sh_dir, best))}
    if arg_bool(a.get("list_shaders")):
        return {"count": len(shaders), "shaders": shaders,
                "curriculum_count": len(curr_entries),
                "curriculum_ids": [e.get("id") for e in curr_entries]}

    q = str(a.get("query") or "").strip().lower()
    out: dict = {}
    if q:
        hits = []
        for fn in shaders:
            txt = _read_text(os.path.join(sh_dir, fn))
            if q in fn.lower() or q in txt.lower():
                hits.append(fn)
        out["shaders"] = hits[:20]
        curr_hits = [
            {"id": e.get("id"), "titulo_es": e.get("titulo_es"), "familia": e.get("familia"),
             "concepto": e.get("concepto"), "efectos_visuales": e.get("efectos_visuales")}
            for e in curr_entries if q in json.dumps(e, ensure_ascii=False).lower()
        ]
        out["curriculum_entries"] = curr_hits[:15]
    else:
        out["curriculum_summary"] = {
            "total_entries": len(curr_entries),
            "sample_ids": [e.get("id") for e in curr_entries[:15]],
            "hint": "Usá entry='<id>' para ver el shader y parámetros completos, o learning_path=true para el recorrido pedagógico.",
        }
    p = kb("pops", "glsl_library.json")
    if not os.path.exists(p):
        if q:
            return {"query": q, **out}
        return {"error": "falta pops/glsl_library.json", **out}
    d = load_json("pops/glsl_library.json")
    if isinstance(d, dict):
        if q:
            sel = {k: v for k, v in d.items() if q in json.dumps(v, ensure_ascii=False).lower()}
            return {"query": q, "keys": list(sel)[:12], **out,
                    "content": clip(json.dumps(sel, ensure_ascii=False, indent=1), 8000),
                    "hint": "shader='<nombre>' o entry='<id>' devuelve el código completo"}
        return {"keys": list(d.keys())[:30], **out, "content": clip(json.dumps(d, ensure_ascii=False, indent=1), 8000)}
    return {"content": clip(json.dumps(d, ensure_ascii=False, indent=1), 8000), **out}


def _md_head(path: str) -> tuple[str, str]:
    """(título, resumen) de un .md: front-matter `title:`/`description:` o primer '# ' y primer párrafo."""
    stem = os.path.splitext(os.path.basename(path))[0]
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = [line.rstrip("\n") for _, line in zip(range(60), f)]
    title, summary, i = stem, "", 0
    if lines and lines[0].strip() == "---":
        for j in range(1, len(lines)):
            s = lines[j].strip()
            if s == "---":
                i = j + 1
                break
            m = re.match(r"(title|description|summary)\s*:\s*(.+)", s)
            if m:
                val = m.group(2).strip().strip("\"'")
                if m.group(1) == "title":
                    title = val
                elif not summary:
                    summary = val[:200]
    for s in (x.strip() for x in lines[i:]):
        if not s:
            continue
        if s.startswith("# ") and title == stem:
            title = s[2:].strip()
        elif not summary and not s.startswith(("#", "---", "|", "```")):
            summary = s[:200]
        if title != stem and summary:
            break
    return title, summary


def _md_collection(a: dict, folder: str, label: str, aliases: dict | None = None) -> dict:
    action = str(a.get("action") or "list").strip().lower()
    if _bad_action(action):
        return _bad_action(action)
    d = kb(folder)
    if not os.path.isdir(d):
        return {"error": f"no se encontró el directorio de {label} en kb/"}
    files = [f for f in sorted(os.listdir(d)) if f.endswith(".md")]
    stems = [f[:-3] for f in files]
    if action == "list":
        q = str(a.get("query") or "").strip().lower()
        items = []
        for fn in files:
            title, summary = _md_head(os.path.join(d, fn))
            if not q or q in f"{fn[:-3]} {title} {summary}".lower():
                items.append({"name": fn[:-3], "title": title, "summary": summary, "file": fn})
        return {"count": len(items), label: items, "total_available": len(files)}
    name = str(a.get("name") or "").strip()
    if not name:
        return {"error": "falta 'name' para action=get", "ejemplos": stems[:8]}
    maxc = arg_int(a, "max_chars", 15000, 500, 60000)
    for alias, rel in (aliases or {}).items():
        if name.lower() == alias.lower() and os.path.exists(kb(folder, rel)):
            return {"name": alias, "file": rel, "content": clip(_read_text(kb(folder, rel)), maxc)}
    best, otros = pick(stems, name)
    if best is None:
        all_cands = stems + list((aliases or {}).keys())
        best_al, otros_al = pick(list((aliases or {}).keys()), name)
        if best_al is not None and os.path.exists(kb(folder, aliases[best_al])):
            rel = aliases[best_al]
            return {"name": best_al, "file": rel, "otras_coincidencias": otros_al,
                    "content": clip(_read_text(kb(folder, rel)), maxc)}
        return {"error": f"{label[:-1]} '{name}' no encontrado",
                "quizas": [s for s in all_cands if any(t in s.lower() for t in re.findall(r"\w{3,}", name.lower()))][:10]}
    return {"name": best, "file": best + ".md", "otras_coincidencias": otros,
            "content": clip(_read_text(os.path.join(d, best + ".md")), maxc)}


def t_workflows(a: dict) -> dict:
    graphs_dir = kb("workflows", "graphs")
    graph_files = [f for f in sorted(os.listdir(graphs_dir)) if f.endswith(".json")] if os.path.isdir(graphs_dir) else []
    graph_stems = [f[:-5] for f in graph_files]
    action = str(a.get("action") or "list").strip().lower()
    out = _md_collection(a, "workflows", "workflows")
    if action == "list" and "error" not in out:
        q = str(a.get("query") or "").strip().lower()
        out["graphs"] = [g for g in graph_stems if not q or q in g.lower()]
        return out
    if action == "get":
        name = str(a.get("name") or "").strip()
        if "error" not in out:
            if out.get("name") in graph_stems:
                out["graph_available"] = f"graphs/{out['name']}.json"
            return out
        # Si no era un .md o pidió explícitamente el grafo JSON
        clean_name = re.sub(r"\.json$", "", re.sub(r"^graphs/", "", name))
        best_g, otros_g = pick(graph_stems, clean_name)
        if best_g is not None:
            return {"name": best_g, "type": "workflow_graph", "file": f"graphs/{best_g}.json",
                    "otras_coincidencias": otros_g, "graph": load_json(f"workflows/graphs/{best_g}.json")}
    return out


def t_tutorials(a: dict) -> dict:
    alias = {k: os.path.join("pop_tutorial", "INDEX.md") for k in ("pop_tutorial", "pop_index", "pop-tutorial")}
    pt_dir = kb("tutorials", "pop_tutorial")
    pt_files = sorted(os.listdir(pt_dir)) if os.path.isdir(pt_dir) else []
    for fn in pt_files:
        stem = os.path.splitext(fn)[0]
        alias[stem.lower()] = os.path.join("pop_tutorial", fn)
        alias[fn.lower()] = os.path.join("pop_tutorial", fn)
    out = _md_collection(a, "tutorials", "tutorials", alias)
    if str(a.get("action") or "list").strip().lower() == "list" and "error" not in out:
        out["pop_tutorial_suite"] = os.path.exists(kb("tutorials", "pop_tutorial", "INDEX.md"))
        out["pop_tutorial_files"] = [os.path.splitext(f)[0] for f in pt_files]
        out["total"] = out.get("total_available")  # clave histórica
    return out


def t_glsl_solutions(a: dict) -> dict:
    p = kb("rules", "GLSL_ERROR_SOLUTIONS.md")
    if not os.path.exists(p):
        return {"error": "falta rules/GLSL_ERROR_SOLUTIONS.md"}
    md = _read_text(p)
    q = str(a.get("error_query") or a.get("query") or "").strip().lower()
    maxc = arg_int(a, "max_chars", 4000, 500, 20000)
    sections = []
    blocks = re.split(r"(?m)^(?=###?\s+)", md)
    for b in blocks:
        b_str = b.strip()
        if not b_str:
            continue
        first_line = b_str.splitlines()[0].strip("# ")
        if not q or q in b_str.lower():
            sections.append({"title": first_line, "content": clip(b_str, maxc)})
    return {"query": q, "count": len(sections), "solutions": sections[: arg_int(a, "limit", 6, 1, 50)],
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
    cname = str(a.get("class_name") or a.get("op_type") or a.get("name") or "").strip().lower()
    cname = re.sub(r"^td\.", "", cname)
    q = str(a.get("search") or a.get("query") or "").strip().lower()

    if cname:
        it = flat.get(cname)
        aprox = None
        if not it:
            # antes: el primer substring ganaba ('OP' devolvía addTOP). Ahora prefijo > substring y,
            # si hay más de una clase distinta, se devuelven candidatos en vez de adivinar.
            cands = [k for k in flat if k.startswith(cname)] or [k for k in flat if cname in k]
            uniq = list(dict.fromkeys(flat[k].get("name") for k in cands))
            if len(uniq) == 1:
                it, aprox = flat[cands[0]], uniq[0]
            else:
                return {"error": f"clase '{cname}' no encontrada" + (" (ambigua)" if uniq else ""),
                        "quizas": uniq[:12],
                        "nota": "La referencia offline cubre las clases de operador (TOP/CHOP/SOP/DAT/POP). "
                                "Para clases base (OP, Par, App...) usá kb_search o get_docs del MCP oficial."}
        member = str(a.get("member_or_method") or a.get("method") or "").strip().lower()
        if member:
            meths = it.get("methods") or []
            pars = it.get("parameters") or []
            matched_meth = [m for m in meths if member in json.dumps(m, ensure_ascii=False).lower()]
            matched_par = [p for p in pars if member in json.dumps(p, ensure_ascii=False).lower()]
            return {"class": it.get("name"), "matched_methods": matched_meth, "matched_parameters": matched_par}
        out = {
            "name": it.get("name"),
            "class": it.get("class"),
            "family": it.get("family"),
            "description": clip(it.get("description"), 500),
            "parameters_count": len(it.get("parameters") or []),
            "methods_count": len(it.get("methods") or []),
            "methods": [m.get("name") for m in (it.get("methods") or []) if isinstance(m, dict)][:30],
            "url": it.get("url")
        }
        if aprox:
            out["nota"] = f"coincidencia aproximada para '{cname}'"
        return out
    if q:
        matches, seen = [], set()
        for k, it in flat.items():
            desc = it.get("description") or ""
            if (q in k or q in desc.lower()) and it.get("name") not in seen:
                seen.add(it.get("name"))
                matches.append({"name": it.get("name"), "class": it.get("class"), "family": it.get("family"), "description": clip(desc, 180)})
        return {"query": q, "count": len(matches), "classes": matches[: arg_int(a, "limit", 8, 1, 50)]}
    return {"total_classes": len({v.get("name") for v in flat.values()}), "familias": list((raw.get("classes") or {}).keys()),
            "total_raw": raw.get("totalClasses"),
            "nota": "Consultá con class_name='noiseTOP' o search='curl'"}


def _discovery_targets() -> list[tuple[str, str]]:
    targets = [
        ("references/discovery-log.md", "discovery-log"),
        ("references/pop-parameter-mapping.md", "pop-parameter-mapping"),
        ("rules/2026-09-28_TDMCP_oficial_vs_propio.md", "tdmcp-oficial-vs-propio"),
        ("contracts/VERIFIED_CONTRACTS.md", "verified-contracts"),
    ]
    seen_rel = {r for r, _ in targets}
    skip = {"GLSL_POP_RULES.md", "GLSL_TOP_RULES.md", "GLSL_ERROR_SOLUTIONS.md"}
    for sub in ("references", "rules", "docs_internal"):
        d = kb(sub)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".md") or fn in skip:
                continue
            rel = f"{sub}/{fn}"
            if rel not in seen_rel:
                seen_rel.add(rel)
                targets.append((rel, os.path.splitext(fn)[0].lower()))
    return targets


def t_discovery(a: dict) -> dict:
    targets = _discovery_targets()
    if arg_bool(a.get("list_sources")):
        return {"count": len(targets), "sources": [{"source": tag, "file": rel} for rel, tag in targets]}
    q = (a.get("query") or a.get("topic") or "").strip().lower()
    src_filter = str(a.get("source") or "").strip().lower()
    terms = [t for t in re.findall(r"[\w]+", q) if len(t) > 1]
    items = []
    for rel, tag in targets:
        if src_filter and src_filter not in tag.lower() and src_filter not in rel.lower():
            continue
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
    return {"query": q, "count": len(items), "sources_scanned": len(targets),
            "findings": items[: arg_int(a, "limit", 6, 1, 50)],
            "nota": "Descubrimientos empíricos, cheatsheets, reglas POP, contratos y notas de rendimiento en TouchDesigner."}


def t_master_prompts(a: dict) -> dict:
    pr_dir = kb("prompts", "master")
    if not os.path.isdir(pr_dir):
        return {"error": "no se encontró prompts/master en kb/"}
    files = [f for f in sorted(os.listdir(pr_dir)) if f.endswith(".md")]
    stems = [f[:-3] for f in files]
    action = str(a.get("action") or "list").strip().lower()
    if _bad_action(action):
        return _bad_action(action)
    if action == "list":
        return {"count": len(files), "prompts": stems}
    name = str(a.get("name") or "").strip()
    if not name:
        return {"error": "falta 'name' para action=get", "disponibles": stems}
    best, otros = pick(stems, name)
    if best is None:
        return {"error": f"master prompt '{name}' no encontrado", "disponibles": stems}
    return {"name": best, "otras_coincidencias": otros, "content": _read_text(os.path.join(pr_dir, best + ".md"))}


TOOLS = [
    ("kb_info", "Provenance de esta KB offline: ruta, tamaño, origen, conteos de docs y de la matriz POP. Llamala primero si dudás de la frescura.", {}, t_kb_info),
    ("kb_taxonomy", "Qué hay en la KB: conteos por familia/trustTier/sourceType. Con list_docs=true y family='POP' lista los nombres.", {"family": "string (case-insensitive)", "list_docs": "boolean"}, t_kb_taxonomy),
    ("kb_search", "Búsqueda full-text (BM25) sobre ~1.2k documentos curados: ops, POPs, patrones, GLSL, workflows, tutoriales. Filtros case-insensitive por familia/trustTier/sourceType (avisa si el valor no existe). NO necesita TouchDesigner.", {"query": "string (requerido)", "family": "POP|TOP|CHOP|SOP|DAT|MAT|GLSL|GENERAL", "trust_tier": "official|live-verified|empirical|community", "source_type": "ops|pops|pop-pattern|pop-live|pop-glsl|workflow|tutorial|glsl-solution|empirical|master-prompt", "limit": "int 1-25 (default 8)"}, t_kb_search),
    ("kb_get", "Devuelve el documento completo (cuerpo paginado) por nombre de operador o slug de página (case-insensitive).", {"name_or_slug": "string (requerido)", "max_chars": "int 400-40000 (default 6000)"}, t_kb_get),
    ("pop_matrix", "Matriz POP medida en vivo (97 tipos): qué se crea, qué cocina, qué acepta input. Sin args = resumen; type='particlePOP' (o 'particle') = registro completo; category='ok_con_input' = miembros.", {"type": "string", "category": "ok_con_input|error_con_input|sin_geometria_con_input|no_creable"}, t_pop_matrix),
    ("ops_doc", "Doc curado de un operador (cualquier familia) enriquecido con topología de cableado (topology.json) y creation_defaults: summary, inputs, useCases, combinaciones, troubleshooting. Secciones: inputs/useCases/commonCombinations/troubleshooting/localNotes/examples/parameters/topology.", {"op_type": "string (requerido)", "section": "string"}, t_ops_doc),
    ("ops_params", "Parámetros documentados de un tipo de operador (offline). Con TD abierto preferí get_help del MCP oficial: lee del build vivo.", {"op_type": "string (requerido)"}, t_ops_params),
    ("validate_pop_pars", "Valida pre-flight una lista de nombres de parámetros para CUALQUIER familia de operador (POP, TOP, CHOP, SOP, DAT, MAT, COMP) contra pop_matrix (97 POPs), ops_doc y python_api. Detecta parámetros inexistentes, propiedades OP pasadas como par (display, render, bypass, lock), prefijos de tupla (sizex/y/z), bloques de secuencia (numBlocks) y advertencias de co-dependencia (outputresolution='custom', globforcemult, timeintegration, triangulatequads).", {"op_type": "string (requerido, ej. 'noisePOP', 'renderTOP', 'pointspriteMAT')", "params": "string (nombres separados por coma o espacio; vacío = lista todos)"}, t_validate_pop_pars),
    ("pop_knowledge", "Datos POP y topología empírica: 'patterns', 'wiki_params', 'pop_inventory', 'validation', 'glsl_library', 'glsl_pops_reference', 'glsl_curriculum', 'pop_chains', 'pop_networks', 'pop_parameters', 'real_world_topology', 'pop_rules', 'attribute_rules', 'bridges', 'pop_style'.", {"kind": "patterns|wiki_params|pop_inventory|validation|glsl_library|glsl_pops_reference|glsl_curriculum|pop_chains|pop_networks|pop_parameters|real_world_topology|pop_rules|attribute_rules|bridges|pop_style (requerido)", "query": "string"}, t_pop_knowledge),
    ("resolve_operator", "Traduce lenguaje natural (ES/EN, con o sin tildes) a tipo de operador canónico + conceptos arquitectónicos, alias de parámetros/atributos y plantillas sugeridas.", {"text": "string (requerido)", "limit": "int 1-25 (default 6)"}, t_resolve_operator),
    ("templates", "Plantillas de red (NETWORK_TEMPLATES + POP_NETWORK_TEMPLATES + pop-chains) y specs arquitectónicas (boids, SPH, field volumes, DMX…): action=list|get.", {"action": "list|get", "name": "string (requerido para get)", "query": "string", "max_chars": "int 500-60000"}, t_templates),
    ("recipes", "Recetas builder verificadas (feedback, partículas POP, GLSL TOP, audio-reactivo, render 3D) + recetas glslTOP (Book of Shaders) con gotchas y código: action=list|get.", {"action": "list|get", "name": "string (requerido para get)", "query": "string"}, t_recipes),
    ("workflows", "Workflows de producción completos (.md) + grafos JSON (workflows/graphs/*.json: alpha blend, audio viz, feedback trails, fluid solver, gaussian splatting, pathtracer…): action=list|get.", {"action": "list|get", "name": "string (requerido para get)", "query": "string", "max_chars": "int 500-60000"}, t_workflows),
    ("tutorials", "Tutoriales paso a paso de TouchDesigner avanzado + suite completa 'pop_tutorial' (INDEX, TUTORIAL_KNOWLEDGE y lecciones 01..06): action=list|get.", {"action": "list|get", "name": "string (requerido para get)", "query": "string", "max_chars": "int 500-60000"}, t_tutorials),
    ("glsl_solutions", "Catálogo de soluciones y fixes a errores frecuentes del compilador GLSL en TouchDesigner.", {"error_query": "string", "limit": "int 1-50 (default 6)"}, t_glsl_solutions),
    ("python_api", "Referencia offline de la API Python de las clases de operador (TOP/CHOP/SOP/DAT/POP): parámetros, métodos y docstrings sin TD abierto. Nombres ambiguos devuelven candidatos.", {"class_name": "string", "member_or_method": "string", "search": "string", "limit": "int 1-50"}, t_python_api),
    ("discovery", "Bitácora empírica y cheatsheets de TouchDesigner (discovery-log, pop-parameter-mapping, TD_PARAMETER_CHEATSHEET, POPs_KNOWLEDGE, POPs_CORRECTIONS, PERFORMANCE, etc.). list_sources=true lista los documentos.", {"query": "string", "source": "string", "list_sources": "boolean", "limit": "int 1-50 (default 6)"}, t_discovery),
    ("master_prompts", "Directivas maestras para orquestación de sistemas complejos (feedback sim, pathtracing, validación): action=list|get.", {"action": "list|get", "name": "string (requerido para get)"}, t_master_prompts),
    ("glsl_rules", "Reglas GLSL verificadas en vivo, por familia: POP (write-only, TDIndex, Create Attributes, outputaccess…) y TOP. rule='4' o 'R4' = regla exacta.", {"family": "pop|top", "rule": "número ('4', 'R4') o texto del título", "query": "texto en el cuerpo"}, t_glsl_rules),
    ("glsl_analyze", "Análisis ESTÁTICO (sin TD) de un shader o snippet Python contra las reglas verificadas: POP R1-R4/F1/F4/multi-input, TOP R1-R4/T4/T10, Python R6/f-string/math. Devuelve errores con el fix y los parámetros exactos de Create Attributes / outputattrs.", {"code": "string (requerido)", "family": "pop|top|python"}, t_glsl_analyze),
    ("glsl_curriculum", "Currículum estructurado GLSL POP (glsl_curriculum.json) + librería de ejemplos + shaders sueltos. entry='<id>' devuelve una lección con shader y params; learning_path=true devuelve la progresión por prerrequisitos.", {"query": "string", "entry": "string (id o título del curriculum)", "shader": "string", "list_shaders": "boolean", "learning_path": "boolean"}, t_glsl_curriculum),
    ("contracts", "Contratos verificados EN VIVO contra TD 2025.32460 + TDMCP 1.1.55 (cook lag, render POP, pointspriteMAT, API Python, verificación). list=true = índice; section='C2' (exacta) / 'cook_lag' para filtrar; query= texto libre.", {"query": "string", "section": "string", "list": "boolean", "max_chars": "int 1000-40000"}, t_contracts),
]
OFFLINE_NAMES = [n for n, _d, _s, _f in TOOLS]
# ── tools que necesitan TouchDesigner: hablan MCP contra el server OFICIAL (13316) ──
try:
    from live import LIVE_TOOLS, LIVE_READONLY
    TOOLS = TOOLS + LIVE_TOOLS
except Exception as _e:  # el server sigue arrancando aunque no esté TD
    LIVE_READONLY = set()
    print(f"[{SERVER_NAME}] tools live no cargadas: {_e}", file=sys.stderr)

TOOL_MAP = {name: (desc, schema, fn) for name, desc, schema, fn in TOOLS}

SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
INSTRUCTIONS = (
    "td-knowledge: capa de conocimiento OFFLINE (22 tools) + herramientas LIVE de alto nivel (41 tools) para TouchDesigner. "
    "Antes de construir: resolve_operator / kb_search / ops_doc para elegir operadores, pop_matrix y validate_pop_pars "
    "(soporta todas las familias POP/TOP/CHOP/SOP/DAT/MAT/COMP + co-dependencias) para verificar nombres de parámetros reales, "
    "contracts y glsl_rules para las reglas verificadas en vivo. Antes de compilar GLSL: glsl_analyze o td_glsl_apply. "
    "Las tools live (td_status, find_in_ops, auto_layout, smart_connect, tdn_export, tdn_diff, tdxn_export, tdxn_build, "
    "eval_render_frame, get_op_errors_deep, td_measure, td_glsl_apply, td_explore_project, td_compare_networks, "
    "td_spatial_context, td_build_pop_render, td_instantiate_template, td_verify_network, td_profile_network, "
    "td_scaffold_component, td_wire_reactive, td_frame_camera_to_geo, td_visual_diff, td_control_simulation, "
    "td_harvest_pattern, td_build_control_panel, td_render_contact_sheet, td_setup_audio_analyzer, "
    "td_setup_scene_switcher, td_preset_manager, td_setup_gpu_instancing, td_setup_postfx_chain, "
    "td_setup_io_bridge, td_record_movie, td_heal_network, td_setup_display_canvas, td_setup_pbr_stage, "
    "td_sync_external_tox, td_setup_ai_stream, td_benchmark_longevity, td_network_tidy) hablan con el MCP oficial TDMCP (127.0.0.1:13316) y requieren TouchDesigner con el .tox activo."
)


def _schema(props: dict) -> dict:
    out = {"type": "object", "properties": {}, "required": []}
    for k, v in props.items():
        t = "string"
        if isinstance(v, str) and v.startswith("int"):
            t = "integer"
        elif isinstance(v, str) and v.startswith("bool"):  # 'boolean' y 'bool (default …)' de live.py
            t = "boolean"
        out["properties"][k] = {"type": t, "description": v}
        if isinstance(v, str) and "requerido" in v and "requerido para" not in v:
            out["required"].append(k)
    return out


def _annotations(name: str) -> dict:
    ro = name in OFFLINE_NAMES or name in LIVE_READONLY
    return {"readOnlyHint": ro, "openWorldHint": name not in OFFLINE_NAMES}


def _rpc_error(mid, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def handle(msg):
    if not isinstance(msg, dict):
        # JSON-RPC batch fue removido en MCP 2025-06-18; cualquier no-objeto es Invalid Request
        return _rpc_error(None, -32600, "invalid request: se espera un objeto JSON-RPC")
    method = msg.get("method")
    mid = msg.get("id")
    if not isinstance(method, str):
        return None if mid is None else _rpc_error(mid, -32600, "invalid request: falta 'method'")
    if method == "initialize":
        asked = (msg.get("params") or {}).get("protocolVersion")
        proto = asked if asked in SUPPORTED_PROTOCOLS else PROTOCOL
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": proto,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION,
                           "title": "td-knowledge — capa de conocimiento offline de TouchDesigner"},
            "instructions": INSTRUCTIONS}}
    if method.startswith("notifications/"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": [
            {"name": n, "description": d, "inputSchema": _schema(s), "annotations": _annotations(n)}
            for n, d, s, _ in TOOLS]}}
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        args = params.get("arguments")
        if args is None:
            args = {}
        if not isinstance(args, dict):
            return _rpc_error(mid, -32602, "invalid params: 'arguments' tiene que ser un objeto")
        if name not in TOOL_MAP:
            return {"jsonrpc": "2.0", "id": mid, "result": {"content": [
                {"type": "text", "text": json.dumps({"error": f"tool desconocida '{name}'", "tools": list(TOOL_MAP)}, ensure_ascii=False)}],
                "isError": True}}
        try:
            res = TOOL_MAP[name][2](args)
            is_err = isinstance(res, dict) and "error" in res
            return {"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False, indent=1)}], "isError": bool(is_err)}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": json.dumps(
                {"error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()[-1200:]}, ensure_ascii=False)}],
                "isError": True}}
    if mid is None:
        return None
    return _rpc_error(mid, -32601, f"method not found: {method}")


# args por tool para --selftest: cada una con una consulta que TIENE que responder sin error
SELFTEST_ARGS = {
    "kb_info": {}, "kb_taxonomy": {}, "kb_search": {"query": "noise"},
    "kb_get": {"name_or_slug": "particlePOP", "max_chars": 500}, "pop_matrix": {"type": "particlePOP"},
    "ops_doc": {"op_type": "noiseTOP"}, "ops_params": {"op_type": "noiseTOP"},
    "validate_pop_pars": {"op_type": "noisePOP", "params": "seed, amp"},
    "pop_knowledge": {"kind": "patterns", "query": "noise"}, "resolve_operator": {"text": "webcam"},
    "templates": {"action": "list"}, "recipes": {"action": "list"}, "workflows": {"action": "list"},
    "tutorials": {"action": "list"}, "glsl_solutions": {"error_query": "undeclared"},
    "python_api": {"class_name": "noiseTOP"}, "discovery": {"query": "cook lag"},
    "master_prompts": {"action": "list"}, "glsl_rules": {"family": "pop"},
    "glsl_analyze": {"family": "pop", "code": "void main(){ const uint id = TDIndex(); if (id >= TDNumElements()) return; P[id] = TDIn_P(0, id); }"},
    "glsl_curriculum": {"query": "noise"}, "contracts": {"list": True},
}


def _selftest() -> int:
    try:
        from live import LIVE_NAMES
    except Exception:
        LIVE_NAMES = []
    fails = 0
    for n, _d, _s, fn in TOOLS:
        if n in LIVE_NAMES:
            print(f"  {n:<22} live (probar con test_live.py)")
            continue
        try:
            r = fn(dict(SELFTEST_ARGS.get(n, {})))
            ok = isinstance(r, dict) and "error" not in r
            print(f"  {n:<22} ok={ok}" + ("" if ok else f"  -> {str(r)[:160]}"))
        except Exception as e:
            ok = False
            print(f"  {n:<22} EXC {type(e).__name__}: {e}")
        fails += not ok
    missing = [n for n in OFFLINE_NAMES if n not in SELFTEST_ARGS]
    if missing:
        print(f"  tools offline sin args de selftest: {missing}")
        fails += len(missing)
    print(f"selftest: {len(OFFLINE_NAMES) - fails}/{len(OFFLINE_NAMES)} offline ok")
    return 1 if fails else 0


def _utf8_stdio() -> None:
    """MCP habla UTF-8. En Windows el stdio por defecto es cp1252: la entrada con tildes llega
    corrupta y la salida con '→' (está en los contratos) levantaba UnicodeEncodeError y mataba
    el server. newline='\\n' evita el CRLF en el framing."""
    for stream, kw in ((sys.stdin, {}), (sys.stdout, {"newline": "\n"})):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace", **kw)  # type: ignore[union-attr]
        except Exception:
            pass


def main() -> int:
    global KB_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", default=KB_DIR)
    ap.add_argument("--selftest", action="store_true", help="corre todas las tools offline con args de prueba; exit 1 si alguna falla")
    a = ap.parse_args()
    KB_DIR = a.kb
    os.environ["TD_KNOWLEDGE_KB"] = KB_DIR
    _utf8_stdio()
    print(f"[{SERVER_NAME}] kb={KB_DIR}", file=sys.stderr, flush=True)
    if a.selftest:
        return _selftest()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            print(f"[{SERVER_NAME}] JSON inválido: {e}", file=sys.stderr, flush=True)
            reply = _rpc_error(None, -32700, f"parse error: {e}")
        else:
            reply = handle(msg)
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())

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


def t_ops_doc(a: dict) -> dict:
    key = str(a.get("op_type") or a.get("slug") or "").strip()
    if not key:
        return {"error": "falta 'op_type' (ej. 'noiseTOP' o 'Noise_TOP')"}
    doc, all_ops = _load_op(key)
    if doc is None:
        close = [s for s in all_ops if norm(key) in norm(s)][:10]
        return {"error": f"sin doc para '{key}'", "quizas": close or all_ops[:10]}
    sec = str(a.get("section") or "").strip()
    base = {"family": doc.get("family"), "page": doc.get("pageTitle"), "slug": doc.get("pageSlug"),
            "url": doc.get("url"), "summary": clip(doc.get("summary"), 900)}
    if sec:
        real = next((k for k in doc if k.lower() == sec.lower()), None)
        if real is not None:
            return {**base, "section": real, "content": clip(json.dumps(doc[real], ensure_ascii=False, indent=1), 8000)}
        base["aviso"] = f"la sección '{sec}' no existe en este doc; devuelvo el resumen"
    for k in ("inputs", "useCases", "commonCombinations", "troubleshooting", "localNotes", "examples"):
        if doc.get(k):
            base[k] = clip(json.dumps(doc[k], ensure_ascii=False, indent=1), 1500)
    base["secciones_disponibles"] = [k for k in doc if k not in base]
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
    files = {"patterns": "pops/patterns.json", "wiki_params": "pops/wiki_params.json",
             "pop_inventory": "pops/pop_inventory.json", "validation": "pops/validation.json",
             "glsl_library": "pops/glsl_library.json"}
    if not kind:
        return {"error": "falta 'kind'", "kinds_disponibles": list(files)}
    if kind not in files or not os.path.exists(kb(files[kind])):
        return {"error": f"kind inválido '{kind}'", "kinds_disponibles": [k for k, v in files.items() if os.path.exists(kb(v))]}
    d = load_json(files[kind])
    q = str(a.get("query") or "").strip().lower()
    if q and isinstance(d, dict):
        hit = {}
        for k, v in d.items():
            if q in k.lower() or q in json.dumps(v, ensure_ascii=False).lower():
                hit[k] = clip(json.dumps(v, ensure_ascii=False, indent=1), 3000)
        return {"kind": kind, "query": q, "keys": list(hit), "content": hit}
    return {"kind": kind, "keys": list(d.keys()) if isinstance(d, dict) else f"lista({len(d)})",
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
    out = {"texto": raw, "familia_sugerida": fam[:4], "candidatos": cands, "origen": origen,
           "tipos_indexados": len(syn)}
    if trad:
        out["traduccion"] = trad
    return out


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _bad_action(action: str):
    if action not in ("list", "get"):
        return {"error": f"action inválida '{action}'", "acciones": ["list", "get"]}
    return None


def t_templates(a: dict) -> dict:
    tl = ts("templates", "NETWORK_TEMPLATES") or []
    action = str(a.get("action") or "list").strip().lower()
    if _bad_action(action):
        return _bad_action(action)
    specs_dir = kb("templates", "specs")
    spec_files = [f for f in sorted(os.listdir(specs_dir)) if f.endswith(".md")] if os.path.isdir(specs_dir) else []
    if action == "list":
        q = str(a.get("query") or "").lower()
        items = [{"name": t["name"], "type": "network_template", "description": clip(t.get("description"), 200), "tags": t.get("tags"),
                  "complexity": t.get("complexity"), "operadores": len(t.get("operators") or [])} for t in tl
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


# --- analyzer: puerto fiel de las reglas verificadas (POP R1-R4, TOP R1-R2, Python R6)
COMPONENTS = {"cd": 4, "n": 3, "uv": 2, "p": 3, "v": 3, "alpha": 1, "mass": 1, "masa": 1}
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
        mo = re.search(r"\bout\s+vec4\s+(\w+)", code)
        if mo and not re.search(rf"\b{mo.group(1)}\s*(?:\.\s*\w+)?\s*=(?!=)", code):
            warns.append({"regla": "TOP R1", "mensaje": f"la salida '{mo.group(1)}' se declara pero nunca se asigna",
                          "fix": f"{mo.group(1)} = TDOutputSwizzle(...);"})
        if re.search(r"\bTDOutputSwizzle\b", code):
            notes.append("TDOutputSwizzle detectado: es el idiom correcto para el canal de salida.")
        return {"family": "top", "ok": not errors, "errores": errors, "warnings": warns, "notas": notes}

    # ---- POP
    out_attrs = sorted(writes)
    if "TDIndex" not in code:
        errors.append({"regla": "POP R2", "mensaje": "no usa TDIndex() para iterar los puntos",
                       "fix": "const uint id = TDIndex();"})
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


def t_glsl_curriculum(a: dict) -> dict:
    sh_dir = kb("shaders")
    shaders = sorted(f for f in os.listdir(sh_dir) if f.endswith((".glsl", ".txt"))) if os.path.isdir(sh_dir) else []
    sh_name = str(a.get("shader") or "").strip()
    if sh_name:
        best, otros = pick(shaders, sh_name)
        if best is None:
            return {"error": f"shader '{sh_name}' no encontrado", "ejemplos": shaders[:12],
                    "hint": "list_shaders=true para el índice completo"}
        return {"shader": best, "otras_coincidencias": otros, "content": _read_text(os.path.join(sh_dir, best))}
    if arg_bool(a.get("list_shaders")):
        return {"count": len(shaders), "shaders": shaders}
    q = str(a.get("query") or "").strip().lower()
    out: dict = {}
    if q:  # también busca en los shaders sueltos (antes sólo en glsl_library.json)
        hits = []
        for fn in shaders:
            txt = _read_text(os.path.join(sh_dir, fn))
            if q in fn.lower() or q in txt.lower():
                hits.append(fn)
        out["shaders"] = hits[:20]
    p = kb("pops", "glsl_library.json")
    if not os.path.exists(p):
        if q:
            return {"query": q, **out}
        return {"error": "falta pops/glsl_library.json"}
    d = load_json("pops/glsl_library.json")
    if isinstance(d, dict):
        if q:
            sel = {k: v for k, v in d.items() if q in json.dumps(v, ensure_ascii=False).lower()}
            return {"query": q, "keys": list(sel)[:12], **out,
                    "content": clip(json.dumps(sel, ensure_ascii=False, indent=1), 8000),
                    "hint": "shader='<nombre>' devuelve el código completo de un shader"}
        return {"keys": list(d.keys())[:30], "content": clip(json.dumps(d, ensure_ascii=False, indent=1), 8000)}
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
        if name.lower() == alias and os.path.exists(kb(folder, rel)):
            return {"name": alias, "file": rel, "content": clip(_read_text(kb(folder, rel)), maxc)}
    best, otros = pick(stems, name)
    if best is None:
        return {"error": f"{label[:-1]} '{name}' no encontrado",
                "quizas": [s for s in stems if any(t in s.lower() for t in re.findall(r"\w{3,}", name.lower()))][:8]}
    return {"name": best, "file": best + ".md", "otras_coincidencias": otros,
            "content": clip(_read_text(os.path.join(d, best + ".md")), maxc)}


def t_workflows(a: dict) -> dict:
    return _md_collection(a, "workflows", "workflows")


def t_tutorials(a: dict) -> dict:
    alias = {k: os.path.join("pop_tutorial", "INDEX.md") for k in ("pop_tutorial", "pop_index", "pop-tutorial")}
    out = _md_collection(a, "tutorials", "tutorials", alias)
    if str(a.get("action") or "list").strip().lower() == "list" and "error" not in out:
        out["pop_tutorial_suite"] = os.path.exists(kb("tutorials", "pop_tutorial", "INDEX.md"))
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
    return {"query": q, "count": len(items), "findings": items[: arg_int(a, "limit", 6, 1, 50)],
            "nota": "Descubrimientos empíricos, notas de hardware, contratos y quirks de parámetros en TouchDesigner."}


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
    ("ops_doc", "Doc curado de un operador (cualquier familia): summary, inputs, useCases, combinaciones, troubleshooting. Secciones: inputs/useCases/commonCombinations/troubleshooting/localNotes/examples/parameters.", {"op_type": "string (requerido)", "section": "string"}, t_ops_doc),
    ("ops_params", "Parámetros documentados de un tipo de operador (offline). Con TD abierto preferí get_help del MCP oficial: lee del build vivo.", {"op_type": "string (requerido)"}, t_ops_params),
    ("pop_knowledge", "Datos POP no-oficiales: 'patterns' (mapas de red reales), 'wiki_params', 'pop_inventory', 'validation', 'glsl_library'.", {"kind": "patterns|wiki_params|pop_inventory|validation|glsl_library (requerido)", "query": "string"}, t_pop_knowledge),
    ("resolve_operator", "Traduce lenguaje natural (ES/EN, con o sin tildes) a tipo de operador canónico: 'cámara web' -> videodeviceinTOP, 'ruido' -> noise*. Si no hay sinónimo directo cae a búsqueda en los docs de operadores.", {"text": "string (requerido)", "limit": "int 1-25 (default 6)"}, t_resolve_operator),
    ("templates", "Plantillas de red (wiring, parámetros y builder Python) + specs arquitectónicas (boids, SPH, field volumes, DMX…): action=list|get.", {"action": "list|get", "name": "string (requerido para get)", "query": "string", "max_chars": "int 500-60000"}, t_templates),
    ("recipes", "Recetas builder verificadas (feedback, partículas POP, GLSL TOP, audio-reactivo, render 3D) + recetas glslTOP (Book of Shaders) con gotchas y código: action=list|get.", {"action": "list|get", "name": "string (requerido para get)", "query": "string"}, t_recipes),
    ("workflows", "Workflows de producción completos (alpha blend, audio viz, feedback trails, fluid solver, gaussian splatting, pathtracer…): action=list|get.", {"action": "list|get", "name": "string (requerido para get)", "query": "string", "max_chars": "int 500-60000"}, t_workflows),
    ("tutorials", "Tutoriales paso a paso de TouchDesigner avanzado (audio-reactivo, boids, god rays, fluid solver, instancing) + suite 'pop_tutorial': action=list|get.", {"action": "list|get", "name": "string (requerido para get)", "query": "string", "max_chars": "int 500-60000"}, t_tutorials),
    ("glsl_solutions", "Catálogo de soluciones y fixes a errores frecuentes del compilador GLSL en TouchDesigner.", {"error_query": "string", "limit": "int 1-50 (default 6)"}, t_glsl_solutions),
    ("python_api", "Referencia offline de la API Python de las clases de operador (TOP/CHOP/SOP/DAT/POP): parámetros, métodos y docstrings sin TD abierto. Nombres ambiguos devuelven candidatos.", {"class_name": "string", "member_or_method": "string", "search": "string", "limit": "int 1-50"}, t_python_api),
    ("discovery", "Bitácora empírica de TouchDesigner: quirks de parámetros, límites medidos, cook lag y lecciones de hardware.", {"query": "string", "limit": "int 1-50 (default 6)"}, t_discovery),
    ("master_prompts", "Directivas maestras para orquestación de sistemas complejos (feedback sim, pathtracing, validación): action=list|get.", {"action": "list|get", "name": "string (requerido para get)"}, t_master_prompts),
    ("glsl_rules", "Reglas GLSL verificadas en vivo, por familia: POP (write-only, TDIndex, Create Attributes, outputaccess…) y TOP. rule='4' o 'R4' = regla exacta.", {"family": "pop|top", "rule": "número ('4', 'R4') o texto del título", "query": "texto en el cuerpo"}, t_glsl_rules),
    ("glsl_analyze", "Análisis ESTÁTICO (sin TD) de un shader o snippet Python contra las reglas verificadas: POP R1/R2/R3/R4 (incluye +=, swizzles y comentarios), TOP R1/R2, Python R6. Devuelve errores con el fix y los parámetros exactos de Create Attributes / outputattrs.", {"code": "string (requerido)", "family": "pop|top|python"}, t_glsl_analyze),
    ("glsl_curriculum", "Ejemplos GLSL: corpus POP verificado + shaders sueltos (Book of Shaders, filtros, vertex). query busca en ambos; shader='<nombre>' devuelve el código; list_shaders=true = índice.", {"query": "string", "shader": "string", "list_shaders": "boolean"}, t_glsl_curriculum),
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
    "td-knowledge: capa de conocimiento OFFLINE de TouchDesigner (no necesita TD abierto). "
    "Antes de construir: resolve_operator / kb_search / ops_doc para elegir operadores, pop_matrix para saber si un POP "
    "necesita input, contracts y glsl_rules para las reglas verificadas en vivo. Antes de compilar GLSL: glsl_analyze. "
    "Las tools td_status, find_in_ops, auto_layout, smart_connect y tdn_export hablan con el MCP oficial TDMCP "
    "(127.0.0.1:13316) y requieren TouchDesigner con el .tox activo."
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

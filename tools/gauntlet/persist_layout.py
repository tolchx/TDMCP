#!/usr/bin/env python3
"""persist_layout.py — test opt-in: el layout /pop_* sobrevive a guardar + recargar.

Secuencia:
  1. Foto de posiciones (sin reacomodar nada) + huella SHA-256.
  2. `project.save()` y elección del `.toe` recién escrito.
  3. `project.load(<slot>)`; el MCP se cae mientras el componente vuelve a
     arrancar, así que se reintenta la conexión.
  4. Foto post-recarga: misma huella, mismas redes/nodos y 0 solapamientos.

No se usa un centinela en memoria como prueba de recarga: TD puede guardar el
estado actual antes de cargar, y entonces el centinela vuelve dentro del `.toe`.
La evidencia es el archivo guardado (hash), la caída del MCP y la huella.

Es OPT-IN porque recarga el proyecto y corta el MCP unos segundos. La batería
normal (`run_regression.py`) no lo corre salvo `--persist-layout`.

Uso:
    PYTHONIOENCODING=utf-8 python tools/gauntlet/persist_layout.py
    python tools/gauntlet/run_regression.py --persist-layout
    python tools/gauntlet/persist_layout.py --slot local/TDMCP.toe

Exit: 0 PASS · 1 FAIL · 2 entorno caído (MCP no responde / no hay archivo).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from gauntlet_client import Gauntlet  # noqa: E402
import td_layout  # noqa: E402

NUMBERED_TOE = re.compile(r"\.\d+\.toe$", re.I)


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _fresh_toe(folder: str, after: float, wait: float = 3.0) -> str | None:
    """El `.toe` que acaba de escribir save(); ignora backups viejos.

    TD rota versiones (`TDMCP.toe`, `TDMCP.2.toe`, …) con el mismo mtime. Si hay
    empate, prefiere el nombre canónico sin número, pero cualquiera de los dos
    tiene el mismo contenido (se verifica por hash).
    """
    deadline = time.time() + wait
    found: list[tuple[float, bool, int, str]] = []
    while time.time() < deadline:
        found = []
        try:
            for fn in os.listdir(folder):
                if not fn.lower().endswith(".toe"):
                    continue
                p = os.path.join(folder, fn)
                try:
                    mt = os.path.getmtime(p)
                    size = os.path.getsize(p)
                except OSError:
                    continue
                if mt >= after - 2.0 and size > 0:
                    found.append((mt, not NUMBERED_TOE.search(fn), size, p))
        except OSError:
            pass
        if found:
            return max(found)[3]
        time.sleep(0.1)
    return None


def _wait_stable(path: str, quiet: float = 0.5, timeout: float = 8.0) -> bool:
    """Espera a que tamaño+mtime no cambien durante `quiet` segundos.

    `project.save()` puede volver antes de que TD termine de escribir; hashear o
    recargar ese archivo intermedio daría una foto que no es la guardada.
    """
    last = None
    stable_since = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            st = (os.path.getsize(path), os.path.getmtime(path))
        except OSError:
            return False
        if st != last:
            last = st
            stable_since = time.time()
        elif stable_since is not None and time.time() - stable_since >= quiet:
            return True
        time.sleep(0.1)
    return False


def _project_state(g: Gauntlet) -> tuple[bool, dict]:
    code = r'''
import json
print('<<JSON>>' + json.dumps(dict(name=project.name, folder=project.folder,
                                   saveTime=project.saveTime)))
'''
    return g.exec_code(code)


def _save(g: Gauntlet) -> tuple[bool, dict]:
    code = r'''
import json
before = project.name
project.save()
print('<<JSON>>' + json.dumps(dict(before=before, after=project.name,
                                   folder=project.folder, saveTime=project.saveTime)))
'''
    return g.exec_code(code)


def _reconnect(g: Gauntlet, timeout: float) -> tuple[bool, float, str]:
    """Espera a que el componente MCP vuelva tras project.load()."""
    t0 = time.time()
    last = ""
    while time.time() - t0 < timeout:
        time.sleep(1.5)
        try:
            g.sid = None
            r = g.init()
            if isinstance(r, dict) and not g.is_err(r) and r.get("result"):
                return True, time.time() - t0, ""
            last = g.text_of(r)[:200]
        except Exception as e:  # URLError mientras el server está abajo
            last = f"{type(e).__name__}: {e}"[:200]
    return False, time.time() - t0, last


def main() -> int:
    ap = argparse.ArgumentParser(description="Persistencia del layout /pop_* (guardar + recargar)")
    ap.add_argument("--slot", default=None,
                    help="forzar el .toe a recargar (por defecto, el recién guardado)")
    ap.add_argument("--timeout", type=float, default=60.0,
                    help="segundos máximos esperando que el MCP vuelva (default 60)")
    args = ap.parse_args()

    g = Gauntlet(phase="persist-layout")
    try:
        r = g.init()
        if g.is_err(r) or not (r.get("result") or {}).get("serverInfo"):
            print("ENTORNO CAIDO — el MCP no responde en 13316")
            return 2
    except Exception as e:
        print(f"ENTORNO CAIDO — {type(e).__name__}: {e}")
        return 2

    print("== persistencia de layout /pop_* " + "=" * 40)
    ok, pre = td_layout.snapshot(g)
    if not ok:
        print("No pude leer el layout antes de guardar:", json.dumps(pre)[:300])
        return 2
    fp_pre, n_pre = td_layout.fingerprint(pre)
    nets_pre = len(pre.get("parents") or [])
    print(f"pre : {fp_pre[:16]}…  {nets_pre} redes / {n_pre} nodos / "
          f"{pre.get('total')} solapamientos")
    g.check("layout pre-save sin solapamientos", pre.get("total") == 0,
            f"total={pre.get('total')}")

    t_save = time.time()
    ok_save, saved = _save(g)
    if not ok_save:
        print("project.save() falló:", json.dumps(saved)[:300])
        g.check("project.save()", False, str(saved)[:200])
        g.summary()
        return 1
    time.sleep(0.2)
    folder = saved.get("folder") or ""
    slot = args.slot or _fresh_toe(folder, t_save)
    if not slot or not os.path.exists(slot):
        print("No encontré el .toe recién guardado en", folder)
        g.check("archivo .toe guardado", False, f"folder={folder}")
        g.summary()
        return 2
    slot = os.path.abspath(slot)
    if not _wait_stable(slot):
        print("El .toe no terminó de escribirse (tamaño/mtime inestables):", slot)
        g.check("archivo .toe estable tras save()", False, slot)
        g.summary()
        return 1
    file_hash = _sha256(slot)
    ok_state, state = _project_state(g)
    save_time = (state.get("saveTime") if ok_state else None) or saved.get("saveTime")
    print(f"save: {slot}")
    print(f"      sha256={file_hash[:16]}…  saveTime={save_time}")
    g.check("project.save()", os.path.getsize(slot) > 0, slot)

    load_fwd = slot.replace("\\", "/")
    print("recargando: project.load(...)")
    load_error = ""
    load_failed = False
    try:
        resp = g.call("execute_code", {"code": 'project.load(r"%s")' % load_fwd},
                      note="project.load", timeout=8)
        if g.is_err(resp):
            load_error = g.text_of(resp)[:300]
            load_failed = True
    except Exception as e:  # lo normal: el server muere con el proyecto
        load_error = f"{type(e).__name__}: {e}"[:300]
    if load_failed:
        print("project.load() devolvió error:", load_error)
        g.check("project.load()", False, load_error)
        g.meta = {"slot": slot, "file_sha256": file_hash, "saveTime": save_time}
        g.summary()
        return 1
    if load_error:
        print("  load cortó la conexión (evidencia de recarga):", load_error)
    else:
        print("  project.load devolvió sin cortar la conexión")
    g.sid = None
    reconnected, waited, last_err = _reconnect(g, args.timeout)
    print(f"reconexión: {'ok' if reconnected else 'FALLÓ'} en {waited:.1f}s"
          + (f" (último: {last_err})" if not reconnected else ""))
    if not reconnected:
        g.check("MCP vuelve tras project.load()", False, last_err or load_error)
        g.meta = {"slot": slot, "file_sha256": file_hash, "reconnected": False,
                  "saveTime": save_time}
        g.summary()
        return 1
    g.check("MCP vuelve tras project.load()", True, f"{waited:.1f}s")

    ok_post, post = td_layout.snapshot(g)
    if not ok_post:
        print("No pude leer el layout después de recargar:", json.dumps(post)[:300])
        g.check("layout post-reload legible", False, str(post)[:200])
        g.meta = {"slot": slot, "file_sha256": file_hash, "reconnected": True,
                  "saveTime": save_time}
        g.summary()
        return 1
    fp_post, n_post = td_layout.fingerprint(post)
    nets_post = len(post.get("parents") or [])
    print(f"post: {fp_post[:16]}…  {nets_post} redes / {n_post} nodos / "
          f"{post.get('total')} solapamientos")

    g.check("misma huella de posiciones", fp_post == fp_pre,
            f"{fp_pre} != {fp_post}")
    g.check("mismo número de redes", nets_post == nets_pre, f"{nets_pre} -> {nets_post}")
    g.check("mismo número de nodos", n_post == n_pre, f"{n_pre} -> {n_post}")
    g.check("layout post-reload sin solapamientos", post.get("total") == 0,
            f"total={post.get('total')}")

    g.meta = {"slot": slot, "file_sha256": file_hash, "saveTime": save_time,
              "fingerprint_pre": fp_pre, "fingerprint_post": fp_post,
              "networks": nets_post, "nodes": n_post,
              "overlaps": post.get("total"), "reconnected": True,
              "reconnect_s": round(waited, 1),
              "load_call_interrupted": bool(load_error), "load_error": load_error}
    report = dict(g.meta, ok=not g.failures, failures=g.failures)
    path = os.path.join(g.out_dir, "persist-layout-report.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    g.summary()
    print(f"Reporte: {path}")
    return 0 if not g.failures else 1


if __name__ == "__main__":
    sys.exit(main())

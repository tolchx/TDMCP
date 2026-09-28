r"""Restaura config.yaml = backup con comentarios + entrada tdmcp insertada.

`hermes config set` deja el YAML funcional pero borra TODOS los comentarios.
Este script parte del backup (que los tiene) e inserta SOLO el bloque nuevo,
sin re-dumpear el YAML: no cambia ni una línea existente.
"""
import shutil, sys, datetime

CFG = r"<user-home>\AppData\Local\hermes\config.yaml"
BAK = r"<user-home>\AppData\Local\hermes\config.yaml.bak-20260928-tdmcp"

BLOCK = """  tdmcp:
    # MCP oficial de Derivative (beta) corriendo DENTRO de TouchDesigner.
    # Requiere el .tox "TDMCP" activo en el root del proyecto (pagina MCP -> Active).
    url: http://127.0.0.1:13316/mcp
    timeout: 300
    connect_timeout: 60
    enabled: true
"""

src = open(BAK, encoding="utf-8").read()
if "  tdmcp:" in src:
    sys.exit("[!] el backup ya tiene tdmcp; nada que hacer")

# ancla: el bloque jev termina justo antes de 'platforms:' a nivel raiz
ANCHOR = "    connect_timeout: 60.0\n    enabled: true\nplatforms:\n"
if src.count(ANCHOR) != 1:
    sys.exit(f"[!] ancla no unica (matches={src.count(ANCHOR)})")

cur = open(CFG, encoding="utf-8").read()
shutil.copyfile(CFG, CFG + f".pre-comment-restore-{datetime.datetime.now():%Y%m%d-%H%M%S}")

new = src.replace(ANCHOR, "    connect_timeout: 60.0\n    enabled: true\n" + BLOCK + "platforms:\n")
open(CFG, "w", encoding="utf-8", newline="\n").write(new)

print(f"ok: {len(src)} -> {len(new)} bytes (+{len(new)-len(src)})")
print("comentarios:", new.count("#"), "| lineas:", new.count(chr(10)))

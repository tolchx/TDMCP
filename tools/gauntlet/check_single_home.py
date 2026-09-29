"""check_single_home.py — falla si un consumidor re-implementa la medición.

El asentamiento (`settle`), la lectura de píxeles (`px`) y la guardia de propiedad del
render (`render_is_ours`) tienen UN dueño: el programa inyectado `td_chain.py`, que se
manda con `td_probe.chain_source(root)`. Ya apareció una tercera copia del wrapper de log
una vez; este chequeo convierte la regla en algo ejecutable.

Uso: `python check_single_home.py` → exit 1 con cada violación listada.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OWNERS = {"td_chain.py", "td_probe.py"}
RE_DEF = re.compile(r"\s*def (settle|px|render_is_ours)\s*\(")


def violations() -> list:
    """[(archivo, línea, texto)] de los consumidores que redefinen la medición."""
    out = []
    for fn in sorted(os.listdir(HERE)):
        if not fn.endswith(".py") or fn in OWNERS:
            continue
        with open(os.path.join(HERE, fn), encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                if RE_DEF.match(line):
                    out.append((fn, i, line.strip()))
    return out


if __name__ == "__main__":
    bad = violations()
    for fn, i, line in bad:
        print("VIOLACION  %s:%d: %s" % (fn, i, line))
    print("check_single_home: %d violaciones (dueños: %s)"
          % (len(bad), ", ".join(sorted(OWNERS))))
    sys.exit(1 if bad else 0)

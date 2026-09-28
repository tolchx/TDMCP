r"""Adapta las 19 skills td-* de TDMCPSkills para Hermes y las instala.

Qué hace:
 1. Lee cada skills/td-*/SKILL.md del clone oficial.
 2. Adapta el frontmatter a la convención de Hermes: description que arranca
    con "Use when ..." (trigger autocontenido en los primeros 57 chars).
 3. Inyecta un banner de 4 líneas explicando el mapeo de nombres de tools en
    Hermes (mcp_tdmcp_<tool>) y el orden de carga (td-general primero).
 4. Escribe el resultado en Hermes skills/touchdesigner/<td-*>/SKILL.md
    y una copia en este repo: skills-hermes/.
"""
import os, re, shutil, json, sys

SRC = r"<legacy-repo>\tmp\skills_oficiales\TDMCPSkills\skills"
HERMES = r"<user-home>\AppData\Local\hermes\skills\touchdesigner"
EXTRA = r"<install>\extras\skills"

# descripciones reescritas: "Use when <trigger>. <comportamiento>."
DESCS = {
 "td-general": "Use when starting ANY TouchDesigner task. Mapa de skills y convenciones transversales — cargar primero.",
 "td-colab": "Use when sliding into auto-building a TD network. Recuerda el modo socio de pensamiento, no constructor.",
 "td-build-planning": "Use when a build needs more than one operator. Scout, elegir operadores, posiciones y fases antes de crear nada.",
 "td-working-mode": "Use when deciding how to attack a TD task. Rutea a las fortalezas del agente: código en disco + verificación empírica.",
 "td-top-family": "Use when building texture chains. TOPs: procesamiento de imagen, compositing, renders, feedback.",
 "td-chop-family": "Use when creating CHOPs or driving parameters from them. Audio, LFOs, animación, control por datos.",
 "td-sop-family": "Use when SOPS are needed (preferir POPs para GPU). Geometría procedural CPU.",
 "td-pop-family": "Use when building GPU point operations. Redes POP: partículas, geometryCOMP, feedback, fuerzas, instancing.",
 "td-dat-family": "Use when creating or populating any DAT. Tablas, callbacks Python, parameter/CHOP execute.",
 "td-mat-family": "Use when assigning or creating materials. constantMAT, pbrMAT, pointspriteMAT, glslMAT, lineMAT, blending.",
 "td-glsl-shaders": "Use when writing GLSL or creating glslTOP/glslMAT/glslPOP. Pixel, compute, vertex, uniforms, DATs dockeados.",
 "td-comp-architecture": "Use when creating COMPs or structuring a project. baseCOMPs, extensions, custom pars, parent shortcuts, modularidad.",
 "td-python-extension": "Use when building Python-driven COMPs. Extension classes, ext0object, parameter callbacks, ciclo de vida, estado.",
 "td-geometry-instancing": "Use when instancing geometry. geometryCOMP, fuentes de datos (CHOP/DAT/TOP/POP), transforms, texturas.",
 "td-lister-ui": "Use when building list-based interfaces. Lister y TreeLister: tablas, listas interactivas, browsers de datos.",
 "td-node-layout": "Use when placing operators. Convenciones de layout: espaciado, dirección de flujo, posicionamiento.",
 "td-network-cleanup": "Use after builds to organize a network. Alineación, espaciado, anotaciones y colores.",
 "td-review-network": "Use after builds to verify correctness. Chequear errores, verificar cableado, diagnosticar causa raíz.",
 "td-performance-check": "Use when cook cost matters. Cooking selectivo, GPU vs CPU, animación por operadores, evitar Python por frame.",
}

BANNER = """
> **Adaptación Hermes.** Estas skills son del repo oficial `TouchDesigner/TDMCPSkills`
> y asumen el MCP oficial corriendo en TD. En Hermes las 26 tools del oficial se
> llaman **`mcp_tdmcp_<tool>`** (ej. `get_help` → `mcp_tdmcp_get_help`,
> `list_operators` → `mcp_tdmcp_list_operators`); los nombres "pelados" que
> aparecen en el texto son de Claude Code/Codex: traducilos con ese prefijo.
> Cargá **`td-general` primero** en cualquier tarea de TouchDesigner.

---

"""

def adapt(name, text):
    # frontmatter: name + description (ya vienen, sólo reescribo description)
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n(.*)$", text, re.S)
    if not m:
        raise SystemExit(f"[!] {name}: sin frontmatter reconocible")
    fm, body = m.group(1), m.group(2)
    fm = re.sub(r"^description:.*$", "", fm, flags=re.M)
    fm = re.sub(r"\n{2,}", "\n", fm).strip()
    desc = DESCS[name]
    new_fm = f"---\n{fm}\ndescription: \"{desc}\"\n---\n"
    return new_fm + BANNER + body.lstrip("\n")

def main():
    names = sorted(d for d in os.listdir(SRC) if os.path.isdir(os.path.join(SRC, d)))
    missing = [n for n in names if n not in DESCS]
    if missing:
        raise SystemExit(f"[!] faltan descripciones para: {missing}")
    os.makedirs(EXTRA, exist_ok=True)
    report = []
    for n in names:
        src = os.path.join(SRC, n, "SKILL.md")
        new = adapt(n, open(src, encoding="utf-8").read())
        for base in (HERMES, EXTRA):
            d = os.path.join(base, n)
            os.makedirs(d, exist_ok=True)
            open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8", newline="\n").write(new)
        report.append((n, len(new), DESCS[n][:57]))
    print(f"OK: {len(report)} skills adaptadas e instaladas")
    for n, sz, d in report:
        print(f"  {n:<26} {sz:>5} b  | {d}")
    print(f"\nHermes: {HERMES}")
    print(f"Copia : {EXTRA}")

if __name__ == "__main__":
    main()

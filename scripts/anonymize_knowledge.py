#!/usr/bin/env python3
"""Anonymize external project names, artists, and community usernames in knowledge assets."""
from __future__ import annotations
import os, re, json

REPLACEMENTS = [
    # Proyectos y servidores externos
    (r"TWOZERO \(Discord\)", "Auditoría de MCPs Comunitarios"),
    (r"servidor Discord TWOZERO \(`1489238980942757908`\)", "servidor de comunidad técnica"),
    (r"servidor Discord TWOZERO", "servidor de comunidad técnica"),
    (r"discord-twozero", "community-feedback"),
    (r"03-twozero-evaluation\.md", "03-community-mcp-evaluation.md"),
    (r"inspiradas en TWOZERO", "inspiradas en toolkits comunitarios"),
    (r"TWOZERO se describe como", "El toolkit comunitario se describe como"),
    (r"sin depender de TWOZERO", "sin depender de toolkits externos"),
    (r"twozero_td", "community_td"),
    (r"twozero\.ai", "community-docs.local"),
    (r"twozero_chain_live", "community_chain_live"),
    (r"twozero_http_live", "community_http_live"),
    (r"twozero_measure_live", "community_measure_live"),
    (r"\bTWOZERO\b", "Community-MCP"),
    (r"\bTwoZero\b", "Community-MCP"),
    (r"\btwozero\b", "community_mcp"),
    
    # Nombres de artistas y desarrolladores externos
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

def anonymize_text(text: str) -> str:
    for pattern, repl in REPLACEMENTS:
        text = re.sub(pattern, repl, text)
    return text

def anonymize_directory(dir_path: str):
    count = 0
    for root, _, files in os.walk(dir_path):
        for f in files:
            if f.endswith(('.md', '.json', '.py', '.txt', '.html')):
                p = os.path.join(root, f)
                try:
                    with open(p, 'r', encoding='utf-8', errors='replace') as fh:
                        content = fh.read()
                    new_content = anonymize_text(content)
                    if new_content != content:
                        with open(p, 'w', encoding='utf-8') as fh:
                            fh.write(new_content)
                        count += 1
                except Exception as e:
                    print(f"Error procesando {p}: {e}")
    print(f"[anonymize] Modificados {count} archivos en {dir_path}")

if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.dirname(__file__)), "knowledge", "kb")
    anonymize_directory(target)

### `view_operator` returns no inline image with `Inline Images` off (the shipped default), while the description promises base64

**Environment**
- TDMCP **1.1.55** (`.tox` in project root, `Active`, page *MCP*: `Port=13316`, `Addressscope=localhost`, `Usehttps=0`, `Auth=0`)
- TouchDesigner **2025.32460** on Windows 11
- Client: plain HTTP client → `http://127.0.0.1:13316/mcp` (streamable-HTTP, `MCP-Protocol-Version: 2025-06-18`)
- All repros below were re-run on a clean sandbox `/hermes_i` created for this report (since deleted).

**Summary.** The description served in `tools/list` says:

> Capture an operator's visual output as a PNG image (returned inline as base64).

That is true only when **Inline Images** (page *Tune*) is ON. With the shipped default
(`Inlineimages=0`) the response carries **no image content block** — just a `file` path into the image
cache, which the description never mentions.

**Repro — default settings (`Inline Images` OFF)**
```json
{"path": "/hermes_i/lvl", "resolution": "tiny"}
```
**Actual** — content blocks: `['text']` only
```json
{"success": true,
 "path": "/hermes_i/lvl",
 "file": "C:/Users/…/TDMCP-1.1.55/.claude/cache/lvl.png",
 "resolution": {"width": 181, "height": 90}}
```

**Control — `Inline Images` ON** (flipped with `set_parameters` on `{"path": "/TDMCP", "values": {"Inlineimages": true}}`), same call:
content blocks `['text', 'image']` → a real PNG, 18 688 base64 chars → 14 014 bytes decoded
(verified visually: the levelTOP output).

**Why it matters for an agent**: an agent that trusts the description expects an image, gets none, and
has to decide on its own whether the capture failed, the operator is empty, or this is by design. Both
outcomes are useful — the fix is documentation, not behaviour, unless you prefer inline on by default:

> "…returned inline as base64 when *Inline Images* is enabled on the component; otherwise a path to the
> cached PNG is returned."

**Minor related nit**: the returned path is the one place an absolute path leaves the server
(`C:/Users/…`), with forward slashes from a Windows path. Fine for a localhost-only tool, just noting it.

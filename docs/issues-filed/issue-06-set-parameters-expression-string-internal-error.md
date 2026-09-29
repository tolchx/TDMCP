### `set_parameters` returns `internal_error` for an expression string in `values` instead of a structured argument error

**Environment**
- TDMCP **1.1.55** (`.tox` in project root, `Active`, page *MCP*: `Port=13316`, `Addressscope=localhost`, `Usehttps=0`, `Auth=0`)
- TouchDesigner **2025.32460** on Windows 11
- Client: plain HTTP client → `http://127.0.0.1:13316/mcp` (streamable-HTTP, `MCP-Protocol-Version: 2025-06-18`)
- Repro re-run for this report on a clean sandbox `/issue_probe` (since deleted).

**Summary.** Passing a Python expression *string* in a `values` entry is refused — correctly, since
`values` sets constant-mode values — but the refusal is tagged `internal_error` (unstructured code
with no fields). Meanwhile the prose message is genuinely helpful: *"Cannot cast value to a numeric
object. Set .expr member instead."* All the guidance an agent needs is already being produced; it is
just not in the machine-readable channel, so the agent cannot reliably branch on "switch to
`execute_code` and set `.expr`" and may instead retry or abort.

This is the highest-traffic trap in the whole API for cross-family wiring (CHOP → par of a TOP, etc.),
where setting an expression is the standard move. Every agent I have watched falls into it once, and
with the current error shape it cannot tell *how* it should have done it.

**Repro — expression string in `values`**
```json
{"path": "/issue_probe/c1", "values": {"colorr": "absTime.seconds % 1"}}
```
(`/issue_probe/c1` is a constantTOP; `colorr` is its RGB red component.)

**Actual**
```json
{
  "error": "Cannot cast value to a numeric object.  Set .expr member instead. Value:'absTime.seconds % 1' Type:<class 'str'>.",
  "details": {"code": "internal_error"}
}
```

**Control — a constant works, and the documented alternative works too**
```json
{"path": "/issue_probe/c1", "values": {"colorr": 0.5}}
→ {"success": true, "set": [{"name": "colorr", "value": 0.5}]}

execute_code {"code": "op('/issue_probe/c1').par.colorr.expr = 'absTime.seconds % 1'"}
→ {"success": true, ...}   // then colorr is in EXPRESSION mode and animates
```

**Expected**, following the pattern `set_parameters` already uses for its own missing arguments
(`"Provide 'values', 'sequences', or 'parent_path'+'batch' to set parameters"` with
`code: "invalid_argument"`):
```json
{"error": "String values set constants only; to set an expression use execute_code: par.<name>.expr = '...'",
 "details": {"code": "invalid_argument", "parameter": "colorr",
              "got": "string", "hint": "set .expr via execute_code, or send a numeric/bool/string constant"}}
```
Keeping the current prose (it is good) and adding the structured code + parameter name converts the
dead end into a one-step self-correction. Note a string *is* a valid constant for Str pars, so the
error only fires after the cast attempt — one more reason the code should say exactly which
parameter objected.

**How it came up**: an audio-reactive build wired a CHOP into a constantTOP by putting
`op('lvl')['chan1']...` into `values.colorr`; the level never animated and the response gave the
agent nothing to branch on.

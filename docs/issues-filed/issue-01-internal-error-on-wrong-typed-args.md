### Wrong-typed arguments return `internal_error` with a raw Python `AttributeError` instead of a structured error

**Environment**
- TDMCP **1.1.55** (`.tox` in project root, `Active`, page *MCP*: `Port=13316`, `Addressscope=localhost`, `Usehttps=0`, `Auth=0`)
- TouchDesigner **2025.32460** on Windows 11
- Client: plain HTTP client → `http://127.0.0.1:13316/mcp` (streamable-HTTP, `MCP-Protocol-Version: 2025-06-18`)
- All repros below were re-run on a clean sandbox `/hermes_i` created for this report (since deleted).

**Summary.** Two tools answer a Python-level `AttributeError` wrapped as `internal_error` when an
argument has the wrong JSON type. Every other failure mode I exercised returns a proper `details.code`
(`operator_not_found`, `wrong_operator_type`, `invalid_menu_value`, `capture_busy`, `invalid_argument`),
so this is the exception that leaks implementation detail instead of telling the agent what to fix.

I am **not** reporting that the arguments were rejected — the `inputSchema` declares both as objects,
so rejecting them is correct. What is missing is the shape of the rejection. Since the whole value of
TDMCP for an agent is "every tool returns structured errors so it can correct itself", these two are
the cases where it can't.

**Repro A — `get_parameters`, `search` passed as a string**
```json
{"path": "/hermes_i", "search": "res*"}
```
**Actual**
```json
{"error": "'str' object has no attribute 'get'", "details": {"code": "internal_error"}}
```

**Repro B — `reposition_operators`, `positions` passed as an array**
```json
{"parent_path": "/hermes_i",
 "positions": [{"path": "/hermes_i/src", "nodeX": -300, "nodeY": 250}]}
```
**Actual**
```json
{"error": "'list' object has no attribute 'keys'", "details": {"code": "internal_error"}}
```

**Controls — the correct shapes work**
```json
reposition_operators {"parent_path": "/hermes_i", "positions": {"src": [0, 0], "lvl": [175, 0]}}
→ {"success": true, "moved": 2}
```
And the reference for a good rejection, `set_parameters` (missing filter args):
```json
{"error": "Provide 'values', 'sequences', or 'parent_path'+'batch' to set parameters",
 "details": {"code": "invalid_argument"}}
```

**Expected**: `invalid_argument` (or `invalid_type`) carrying the offending field and the shape the tool
wants — e.g. `{"code": "invalid_argument", "argument": "positions", "expected": "object mapping operator name → [x, y]"}`.
That converts "the server is broken" into "retry with a dict", which is exactly the distinction the
structured-error design is for.

**Side note (same area, lower priority).** `get_parameters {"path": "/hermes_i", "search": {}}`
(empty search object) does not enter search mode: it falls back to the normal parameter fetch and
returns `{"parameters": {}, "count": 0}`. Reasonable behaviour, just not documented.

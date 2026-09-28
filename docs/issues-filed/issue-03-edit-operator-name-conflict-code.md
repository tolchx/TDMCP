### `edit_operator` reports a rename conflict as `internal_error` instead of a structured conflict code

**Environment**
- TDMCP **1.1.55** (`.tox` in project root, `Active`, page *MCP*: `Port=13316`, `Addressscope=localhost`, `Usehttps=0`, `Auth=0`)
- TouchDesigner **2025.32460** on Windows 11
- Client: plain HTTP client → `http://127.0.0.1:13316/mcp` (streamable-HTTP, `MCP-Protocol-Version: 2025-06-18`)
- All repros below were re-run on a clean sandbox `/hermes_i` created for this report (since deleted).

**Summary.** Renaming an operator to a name already used in the same parent is correctly refused, but
the refusal is tagged `internal_error` with no fields, so a caller cannot tell a name conflict from a
genuine server fault.

**Repro.** `/hermes_i` contains `a` (nullTOP) and `b` (nullTOP).
```json
{"path": "/hermes_i/a", "name": "b"}
```
**Actual**
```json
{"error": "Invalid or duplicate operator name.", "details": {"code": "internal_error"}}
```

**Control** — the same call with a free name:
```json
{"path": "/hermes_i/a", "name": "c"} → {"success": true, "path": "/hermes_i/c", "action": "renamed to c"}
```

**Expected**, following the pattern used elsewhere in TDMCP:
```json
{"error": "Operator name already in use: b",
 "details": {"code": "name_conflict", "path": "/hermes_i/a", "name": "b",
              "existing": "/hermes_i/b"}}
```
The prose is fine; what's missing is the machine-readable code plus the name/path in conflict, which is
what lets an agent pick another name and retry unattended. With `internal_error` a batch script has to
abort rather than continue.

**How it came up**: a batch that renamed operators and then re-queried `search_operators` — the script
couldn't distinguish "pick another name" from "the server is broken".

### `edit_custom_parameters` answers a wrong-schema call with `success: true` and an empty result instead of a structured error

**Environment**
- TDMCP **1.1.55** (`.tox` in project root, `Active`, page *MCP*: `Port=13316`, `Addressscope=localhost`, `Usehttps=0`, `Auth=0`)
- TouchDesigner **2025.32460** on Windows 11
- Client: plain HTTP client → `http://127.0.0.1:13316/mcp` (streamable-HTTP, `MCP-Protocol-Version: 2025-06-18`)
- Repro re-run for this report on a clean sandbox `/issue_probe` (baseCOMP, since deleted).

**Summary.** Calling `edit_custom_parameters` with a plausible-but-wrong argument shape is answered
with `success: true`, `added: []`, `failed: []` — nothing is created and nothing says why. The tool's
`inputSchema` wants `{ "page": "<page name>", "add": [ { "name", "type", "default", ... } ] }`, but
agents regularly arrive with other shapes that look equally legitimate (mine guessed an
`action`/`parameters` envelope, as documented below). Unlike the wrong-*type* cases already reported
in #1, here the types are all valid — the extra/unknown keys are simply ignored.

This is the one failure mode the structured-error design does not currently cover: **a silent no-op**.
A self-correcting agent (and a human) reads `success: true` and moves on; the custom parameters are
never there and the failure surfaces much later, downstream.

**Repro — plausible envelope, wrong keys**
```json
{"path": "/issue_probe", "action": "add",
 "parameters": [{"name": "Blur", "style": "Float", "defaultValue": 0.5, "page": "Module"}]}
```
**Actual** (HTTP 200, `isError` absent)
```json
{
  "path": "/issue_probe",
  "page": "",
  "added": [],
  "edited": [],
  "deleted": [],
  "validation_errors": [],
  "failed": [],
  "success": true
}
```
Zero parameters created (`/issue_probe` has no `Module` page afterwards), yet the response also
reports `"success": true` and `"failed": []` — the empty arrays are indistinguishable from "nothing
to do".

**Control — the schema's shape works**
```json
{"path": "/issue_probe", "page": "Module", "add": [{"name": "Blur", "type": "Float", "default": 0.5}]}
→ {"path": "/issue_probe", "page": "Module", "added": [{"name": "Blur", "type": "Float", "label": "Blur"}], "success": true}
```

**Expected**, one of the two (either fixes the failure mode):
1. Strict: reject unknown/meaningless payloads with the house pattern —
   `{"error": "No 'add', 'edit', 'delete' or 'sort' payload found", "details": {"code": "invalid_argument", "expected": "page + add[]/edit[]/delete[] (see inputSchema)"}}`; or
2. Honest bookkeeping: keep `success: true` for an empty batch but add `"ignored": ["action", "parameters"]` (unknown top-level keys) so a caller can tell "no-op by design" from "no-op by mistake".

**How it came up**: during an automated build gauntlet, a module level created custom parameters with
the wrong envelope, the response said success, and the subsequent graders failed two levels later —
an expensive detour that a structured rejection would have avoided on the spot.

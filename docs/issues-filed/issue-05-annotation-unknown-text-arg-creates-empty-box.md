### `annotation` create accepts an unknown `text` argument and silently creates an empty box

**Environment**
- TDMCP **1.1.55** (`.tox` in project root, `Active`, page *MCP*: `Port=13316`, `Addressscope=localhost`, `Usehttps=0`, `Auth=0`)
- TouchDesigner **2025.32460** on Windows 11
- Client: plain HTTP client → `http://127.0.0.1:13316/mcp` (streamable-HTTP, `MCP-Protocol-Version: 2025-06-18`)
- Repro re-run for this report on a clean sandbox `/issue_probe` (containerCOMP, since deleted).

**Summary.** The create mode of `annotation` documents the label as `comment` ("Text label for the
network box (required for create)"). Sending the more natural-sounding `text` instead — an argument
`annotation` does not declare — is not rejected: the box is created, `success: true` comes back with
`"comment": ""`, and the label is empty. Same family as the `edit_custom_parameters` case (#4 in this
series): unknown arguments are ignored rather than refused, so a small naming mistake produces a
successful-looking but wrong result.

It also compounds with a second, subtler trap: when `comment` *is* provided, a create against a
**wrong `parent_path`** fails cleanly (`wrong_operator_type`), but the error text says "Not an
annotation", which reads like the *tool* refused the op type rather than "the parent path you gave is
not a COMP". Minor, but it sends the agent hunting in the wrong direction.

**Repro — `text` instead of `comment`**
```json
{"parent_path": "/issue_probe", "text": "N2 reloj audio-reactivo (gauntlet)", "width": 300}
```
**Actual** (HTTP 200, `isError` absent)
```json
{"success": true, "parent_path": "/issue_probe", "name": "annotate1", "comment": ""}
```
The annotateCOMP exists with an empty label; the intended text is nowhere in the response, so nothing
hints that it was dropped.

**Control — the documented argument works**
```json
{"parent_path": "/issue_probe", "comment": "N2 reloj audio-reactivo (gauntlet)", "width": 320}
→ {"success": true, ..., "comment": "N2 reloj audio-reactivo (gauntlet)"}
```

**Expected**, either is fine:
1. Refuse unknown arguments on create: `{"error": "Unknown argument: text (did you mean 'comment'?)", "details": {"code": "invalid_argument", "argument": "text"}}` — the "did you mean" makes it self-correcting; or
2. Echo the created label in the response *and* warn when a non-empty text-like argument was ignored: `"warnings": ["ignored unknown argument 'text'"]`.

**Related observation.** `annotation {"path": "/gauntlet_n2", "comment": "..."}` against an existing
non-annotation op returns `{"error": "Not an annotation: /gauntlet_n2 (type: containerCOMP)",
"details": {"code": "wrong_operator_type", "expected": "annotation", "actual": "containerCOMP"}}`.
The code is right; consider wording the error as "path is not an annotation COMP — pass an
annotateCOMP path, or use parent_path to create one", since in an agent loop the usual cause is a
path mix-up, not a type mismatch.

**How it came up**: the same automated gauntlet annotated a finished build with `text`; the annotation
was created empty, and the missing label only became visible later in the network review pass.

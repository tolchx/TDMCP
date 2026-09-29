### `build_network`/`create_operator` reject a mistyped operator type without suggesting the closest known type

**Environment**
- TDMCP **1.1.55** (`.tox` in project root, `Active`, page *MCP*: `Port=13316`, `Addressscope=localhost`, `Usehttps=0`, `Auth=0`)
- TouchDesigner **2025.32460** on Windows 11
- Client: plain HTTP client → `http://127.0.0.1:13316/mcp` (streamable-HTTP, `MCP-Protocol-Version: 2025-06-18`)
- Repro re-run for this report on a clean sandbox `/issue_probe` (since deleted).

**Summary.** Operator type names in TD's own docs and in older MCP tooling are frequently written in
`audioDeviceInCHOP` style, while the live catalog is lowercase (`audiodeviceinCHOP`). A create with
the camel-cased name is refused — correctly — but the rejection carries no suggestion, and the
caller has no local way to discover the canonical spelling except a second tool round-trip to
`get_help`. In a batch `build_network` this is worse: the op is reported in `failed_ops`, the rest of
the batch proceeds, and every connection that referenced the failed name is also reported failed, so
one spelling mistake cascades into a partially built network that the agent must clean up (a trap
`td-build-planning` itself warns about).

The failure is correct; what would make it self-correcting is the same trick the server already uses
elsewhere: `invalid_menu_value` ships `valid_values`, and `wrong_operator_type` ships
`expected`/`actual`. Missing type names deserve the same treatment.

**Repro — camel-cased audio types**
```json
{"parent_path": "/issue_probe", "operators": [
  {"type": "audioDeviceInCHOP", "name": "audio"},
  {"type": "audioSpectrumCHOP", "name": "spectrum"}]}
```
**Actual** (`failed_ops` entries; the rest of the batch continues)
```json
{"failed_ops": [
  {"name": "audio", "error": "unknown operator type: audioDeviceInCHOP"},
  {"name": "spectrum", "error": "unknown operator type: audioSpectrumCHOP"}]}
```

**Control — the canonical lowercase form works**
```json
{"parent_path": "/issue_probe", "operators": [{"type": "audiodeviceinCHOP", "name": "audio2"}]}
→ {"success": true, "created": [{"name": "audio2", "path": "/issue_probe/audio2", "type": "audiodeviceinCHOP"}]}
```

**Expected** — a `details` payload in the same style as `invalid_menu_value`, e.g.:
```json
{"error": "unknown operator type: audioDeviceInCHOP (did you mean 'audiodeviceinCHOP'?)",
 "details": {"code": "unknown_operator_type", "op_type": "audioDeviceInCHOP",
              "suggestion": "audiodeviceinCHOP", "family": "CHOP"}}
```
Even a case-insensitive fold (the TD type string for `audiodeviceinCHOP` equals the lowercased
input) or a simple `difflib.get_close_matches` against the family catalog would fix the dominant
real-world cases (case variants and transposed prefixes). With a `suggestion` present, an agent can
retry the whole batch in one turn instead of interrogating `get_help`.

**How it came up**: the first audio-reactive level of the build gauntlet used the doc-style names;
both audio ops failed, their connections failed with them, and the level needed a cleanup pass —
exactly the partial-failure trap the official build-planning skill documents.

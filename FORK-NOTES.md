# Fork notes — tolchx/TDMCP

Personal working copy of **Derivative TDMCP** (the official TouchDesigner MCP server), used to
develop an **offline knowledge layer** that runs alongside it.

**Not affiliated with, reviewed by, or endorsed by Derivative Inc.** Upstream files
(`README.md`, `CHANGELOG.md`, `LICENSE.md`, `docs/`) are unmodified. The Shared Use License and
TDMCP Tool Terms of Use in `LICENSE.md` are retained as required; the additions below are
modifications of this software made for use with TouchDesigner.

## What this fork adds

| Path | What it is |
|---|---|
| `knowledge/` | **td-knowledge** — an offline MCP server (Python stdlib, stdio) with 14 tools: knowledge base search, the measured POP capability matrix, operator/parameter docs, natural-language → operator resolution, network templates and builder recipes, the live-verified GLSL rules, and a static GLSL analyzer. Needs no TouchDesigner running. |
| `skills-hermes/` | The 19 portable `td-*` skills from [TouchDesigner/TDMCPSkills](https://github.com/TouchDesigner/TDMCPSkills), adapted for the Hermes Agent skill format (`Use when …` descriptions + a header that maps the tool names to the host's `mcp_<server>_<tool>` convention). Original license retained in `LICENSE-TDMCPSkills.md`. |
| `docs/community-test-notes-2026-09-28.md` | Test notes from exercising TDMCP 1.1.55 against a live TouchDesigner project: what was verified (structured errors, undo-per-tool-call, security guards, grid captures, DAT file sync) and the three issues filed upstream. |
| `docs/issues-filed/` | Copy of the three bug reports opened on `TouchDesigner/TDMCP` (#1, #2, #3). |
| `component/` | The **official TDMCP 1.1.55 build** (`TDMCP.tox` + `TDMCP.json`), committed unmodified with its SHA-256 hashes so the binary travels with the fork instead of living only as a release asset. See `component/README.md`. |

## Division of labour

* **Live work** → the official `TDMCP.tox` (26 tools, in-process: create/wire/edit, read parameters,
  sample TOP/CHOP/POP values, capture the viewer, profile cook times, undo-per-call).
* **Knowledge, validation and planning** → `knowledge/` (works with TouchDesigner closed, so an
  agent can read the rules and validate code before the project is even open).

## Using it

```bash
# 1. build the knowledge assets (needs a local knowledge source; kb/ is not tracked)
python knowledge/build_assets.py --repo /path/to/knowledge/source

# 2. sanity-check, then register as a stdio MCP server
python knowledge/server.py --selftest
python knowledge/test_protocol.py
```

`kb/` is deliberately **not** in this repository: it is derived data (a SQLite index plus JSON
extracted from a local installation) and it embeds third-party documentation. Rebuild it locally.

## Provenance

Built and verified on Windows 11 with TouchDesigner 2025.32460 and TDMCP 1.1.55.

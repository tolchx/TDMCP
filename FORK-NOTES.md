# Fork notes — tolchx/TDMCP

Personal working copy of **Derivative TDMCP** (the official TouchDesigner MCP server), used to
develop an **offline knowledge layer** that runs alongside it.

**Not affiliated with, reviewed by, or endorsed by Derivative Inc.** Upstream files
(`CHANGELOG.md`, `LICENSE.md`, `docs/`) are unmodified; `README.md` is upstream plus a short fork-status section. The Shared Use License and
TDMCP Tool Terms of Use in `LICENSE.md` are retained as required; the additions below are
modifications of this software made for use with TouchDesigner.

## What this fork adds

| Path | What it is |
|---|---|
| `knowledge/` | **td-knowledge** — an offline MCP server (Python stdlib, stdio) with 14 tools: knowledge base search, the measured POP capability matrix, operator/parameter docs, natural-language → operator resolution, network templates and builder recipes, the live-verified GLSL rules, and a static GLSL analyzer. Needs no TouchDesigner running. |
| `skills-hermes/` | The portable `td-*` skills from [TouchDesigner/TDMCPSkills](https://github.com/TouchDesigner/TDMCPSkills) (**19** of them), adapted for the Hermes Agent skill format (`Use when …` descriptions + a header that maps the tool names to the host's `mcp_<server>_<tool>` convention). Original license retained in `LICENSE-TDMCPSkills.md`. **2026-09-28:** 5 carry verified live patches from the TDMCP build gauntlet (`td-general`, `td-chop-family`, `td-comp-architecture`, `td-mat-family`, `td-build-planning`) — lowercase op-type catalog, constants-only `set_parameters`, `annotation` takes `comment`, the real `edit_custom_parameters` schema, cloning via `edit_operator.copy_to`, and the render-rig coreography (`renderTOP`, no-input `environmentlightCOMP`). See `docs/tdmcp-gauntlet-2026-09-28.md`. **2026-09-29:** two **new** skills — `td-pop-render-pipeline` (how to make a POP effect actually draw: **point primitives via `convertPOP(topointprims)` — `deleteprims` renders black**, the auto-torus trap, render flags on the chain terminal, `pointspriteMAT` look, renderTOP bindings) and `td-live-verification` (measuring without fooling yourself: `settle()` for the cook lag, `poptoCHOP` as ground truth, pixel/PIL checks) — plus verified patches to `td-general`, `td-pop-family`, `td-mat-family`, `td-glsl-shaders`, `td-comp-architecture` and `td-review-network`. See `docs/td-lecciones-aprendidas-2026-09-29.md`. |
| `knowledge/contracts/` | **`VERIFIED_CONTRACTS.md`** — the live-verified contracts (cook lag, render cache vs POP data, stopped clock, POP→render, `pointspriteMAT`, POP Python API, TDMCP tool contracts, verification checklist), **tracked** in git (unlike `kb/`, which is derived). Served offline by the new `contracts` tool of `td-knowledge`. |
| `tools/gauntlet/` | Build + verification harness: `gauntlet_client.py` (MCP client with per-phase logs), the F1–F6 regression phases, `build_particle_fx.py` (builds and verifies `/particle_swirl`), `build_pop_curlfield.py` (a **second** POP network — `gridPOP` 3D + hand-written curl-noise GLSL — used to cold-run the POP→render recipe, with an A/B experiment `deleteprims` vs `topointprims` and a findings ledger), `verify_visual.py` / `make_preview.py` (PIL PNG metrics + HTML preview; `make_preview.py <run> swirl|curl`), **`td_chain.py`** — the program *injected* into TouchDesigner by `execute_code` (`settle()` / `px()` / `render_is_ours()`, with `ROOT` pinned by `td_probe.chain_source(root)`); importable code, so it is exercised off-TD with a fake `op`. **`td_probe.py`** is the single place to measure on the *host*: `chain_source(root)`, `set_and_verify()` writes-and-rereads, `stats_of`/`png_stats`/`grid_cells` are the PIL metrics, and `selftest_render_ownership()` proves the render-ownership guard can **fail** (it is what caught the auto-torus). **`check_single_home.py`** fails if a consumer re-defines `settle`/`px`/`render_is_ours` instead of importing them. |
| `docs/community-test-notes-2026-09-28.md` | Test notes from exercising TDMCP 1.1.55 against a live TouchDesigner project: what was verified (structured errors, undo-per-tool-call, security guards, grid captures, DAT file sync) and the three issues filed upstream. |
| `docs/td-lecciones-aprendidas-2026-09-29.md` | What two build sessions taught about constructing in TouchDesigner with TDMCP: the five costly lessons (cook lag, render cache vs POP data, surface vs point cloud, stopped clock, verification errors), the verified-contract index, the reusable tooling, and the **ritual** for turning each new finding into a contract + skill + tool. |
| `docs/particle-fx-2026-09-29.md` | Build report for `/particle_swirl` (POP GLSL particle swarm): network, shader, material look, run id `20260929-010805` and the environment limits on visual verification. ⚠️ **Corrected 2026-09-29 (pass 2):** its "35/35 verified" render was measuring the auto-created `torus1`, not the particles; see `docs/td-curl-field-2026-09-29.md`. |
| `docs/td-curl-field-2026-09-29.md` | **Pass 2** — cold-running the POP→render recipe against a brand-new network (`/curl_field`): the 7 findings (`deleteprims` renders black → `topointprims`; the auto-torus masking a broken render; `pointsize` vs `attensizenear`; `vec` `numBlocks`; lazy docked DATs; `set_parameters` silent no-apply), plus the fix applied to `/particle_swirl`. Runs `20260929-025128` (curl) and `20260929-025059` (swirl). |
| `docs/issues-filed/` | Copy of the three bug reports opened on `TouchDesigner/TDMCP` (#1, #2, #3). |
| `component/` | The **official TDMCP 1.1.55 build** (`TDMCP.tox` + `TDMCP.json`), committed unmodified with its SHA-256 hashes so the binary travels with the fork instead of living only as a release asset. See `component/README.md`. |

## Stage 3 — the bridge is gone

The original MCP used its own transport: a Web Server DAT bridge on `127.0.0.1:44444` plus a Node
MCP server with 107 tools. That transport is **retired**. The official `.tox` provides the live
side, and `knowledge/` provides the offline KB **plus 6 live wrappers** that speak MCP to the
official server: `find_in_ops` (search inside DATs and parameter expressions), `auto_layout`
(topological layering), `smart_connect` (family-aware input index), `tdn_export` / `tdn_diff`
(git-friendly network diffs) and `td_status`. `healthcheck.py` replaces the old bridge-based
watchdog (silent when healthy).

Tool split of the 107: **43 offline** kept, **30 mapped** 1:1 onto the official's 26, **20 needed a
wrapper** (the 4 above were worth building, the official covers the rest), **14 dropped**
(bridge undo/history, memory, watch, batch).

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

# TouchDesigner MCP

**An MCP server that runs inside TouchDesigner, so an AI coding agent can collaborate with you in a TouchDesigner environment.**

Drop one component into your project and your agent gets 26 tools for creating operators, wiring them, setting parameters, reading DATs, inspecting runtime values and looking up TD documentation.

Works with Claude Code, Codex, Antigravity (`agy`), OpenCode, and any other client that speaks streamable-HTTP MCP.

> **Beta.** The interface may still change and feedback is wanted. Found a bug?
> Open an [issue](https://github.com/TouchDesigner/TDMCP/issues); want to ask
> something, start a [discussion](https://github.com/TouchDesigner/TDMCP/discussions).
> Either way, include the **Version** and **.tox Save Build** from the component's
> About page.

## Requirements

- **TouchDesigner** — tested against build 2025.33070
- **An MCP client** — Claude Code needs nothing else and is the simplest starting point
- **Node.js 18+** — only for Claude Desktop, which needs a bridge. No other client requires it
- **mkcert** — only if you want HTTPS, which is optional

## Quick start

### 1. Add the component

1. Download `TDMCP.tox` from [Releases](https://github.com/TouchDesigner/TDMCP/releases).
2. Drag it into the root of your TouchDesigner project.
3. Turn on **Active** on the MCP page.

### 2. Connect your agent

Two things happen here: registering the server, so the agent gets the tools, and installing the skills, so it knows how TouchDesigner expects things to be done. Both live on the component's **MCP** page.

1. Pick your client in **Install For**. Defaults to Claude Code.
2. Pick an **Install Scope**. The menu rebuilds per client and offers only the scopes that client supports.
3. Copy **Add MCP** and run it in your project directory.
4. Pulse **Install Skills**.

For Claude Code that gives you:

```bash
claude mcp add --transport http --scope local touchdesigner http://127.0.0.1:13316/mcp
```

**Add MCP** and **Remove MCP** are generated, not typed. They rebuild from your live **Port**, **Server Name**, **Use HTTPS** and **Ask for authentication** settings, so the command always matches the server you are actually running.

### 3. Check it worked

```bash
claude mcp list
# touchdesigner: http://127.0.0.1:13316/mcp (HTTP) - ✔ Connected
```

Then ask your agent:

> What TouchDesigner project am I connected to?

A correct answer means the whole chain works: the server is running, the client found it, and a tool call round-tripped. If it does not, see [Troubleshooting](#troubleshooting).

Now try something real:

> Create a noise TOP, blur it, and end the chain in a null.

## What you get

**26 tools**, across operators (create, wire, move, delete, annotate), parameters (read, set, pulse, add custom pars, look up names), content and inspection (DAT text, CHOP channels, TOP pixels, geometry, screenshots, Python), query and navigation (browse, search, connections, TD docs), and project-level calls (info, save, errors, cook performance).

**Undo on edits.** Changes made through the editing tools are wrapped in undo blocks, so Ctrl+Z reverses them — one tool call is one undo step. Annotations are the current exception: creating one tears down the open undo block inside TouchDesigner.

**Visual feedback.** The network editor pans to whatever the agent is touching and flashes it: amber for edits, blue for inspections, violet for views.

**Skills.** A library of TouchDesigner conventions the agent loads on demand. See [Skills](#skills).

## The component's parameters

Five pages: **MCP**, **Skills**, **Tune**, **Docs**, **About**.

### MCP — server and agent setup

| Parameter | Notes |
| --- | --- |
| **Active** | Start and stop the server |
| **Port** | Default `13316` |
| **Server Name** | The name clients register the server under. Default `touchdesigner` |
| **Server Address Scope** | `Localhost only (127.0.0.1)` (default) or `All interfaces (LAN/remote)`. See [Security](#security) |
| **Use HTTPS** | Optional TLS. See [HTTPS](docs/setup-advanced.md#https) |
| **Certs Folder** | Optional override for where the cert lives |
| **Ask for authentication** | OAuth 2.1 with an in-TD consent popup. See [Security](#security) |
| **Auto-accept deletion** | Skip the confirmation dialog on `delete_operator`. That is the only tool that raises one. **On by default**; turn it off to be asked |
| **Install For** | Which agent to set up. Default Claude Code |
| **Install Scope** | Rebuilt per agent to the scopes it supports. Default `Local — this folder, private to you` |
| **Add MCP** / **Remove MCP** | Read-only, generated for the current selection |
| **Install Skills** | Install for the current Install For × Install Scope |
| **Skills Status** | Read-only. What is installed for that selection; the tooltip lists resolved directories |

**Running two TouchDesigner instances at once?** Give each component a different **Server Name**. Clients resolve one entry per name, so two servers both called `touchdesigner` means one silently shadows the other and your agent drives the wrong project.

### Skills — content, overrides and cleanup

| Parameter | Notes |
| --- | --- |
| **System prompt DAT** | The DAT served to clients as MCP `instructions`. Defaults to `./SystemPrompt` |
| **Skills Source (blank = latest release)** | Blank downloads the latest published release. A path is used only when it resolves to a TDMCPSkills checkout; a stale path falls back to the release with a note |
| **Skills Repo or Archive URL** / **Skills Version** | Override the repo (`owner/name`, a direct archive URL, or `file://`) and pin a release tag. Blank means `TouchDesigner/TDMCPSkills` at its latest release |
| **Host Override DAT** | A DAT of JSON host records layered over the shipped registry. See [Adding an agent](docs/setup-advanced.md#adding-an-agent) |
| **Installed Locations** | Read-only. Every registry destination currently holding skills. One directory serving two clients is listed once, with both named |
| **Uninstall Scope** | `Current selection only (MCP page)` · `All agents — this project` · `All agents — global` · `All agents — everywhere` |
| **Uninstall Skills** | Remove the skills this component installed, per the manifests it wrote |

> **Every Uninstall Scope except the first ignores Install For** and sweeps every agent at that scope. Read **Installed Locations** before a wide uninstall.

### Tune — rate limiting and visual feedback

**Rate limiting** (`Enable` on, `Slow Threshold` 5.0s, `Cooldown` 1.0s) throttles after a slow tool call. **Inline Images (base64)** (off), **Image Cache Path** (`.claude/cache`) and **Request Log** (off) control image return and logging. **Node following** (`Follow Active`, `Follow Time`, `Highlight Nodes`, `Color Time`, `Color Delay`) drives the pan and highlight behaviour.

### Docs — documentation source

**Docs Source** selects where `get_docs` reads from: `Auto (local if installed)` (default), `Web (docs.derivative.ca)`, or `Local only`. **Local Docs Path** points at an offline copy. **Status** is read-only.

### About

**Help** opens this repository. **Update** checks for a newer release and tells you whether you need it; if there is one it asks first, then replaces the component in place and keeps your settings. **Version** and **.tox Save Build** are what to quote in a bug report.

## Skills

Skills teach the agent how TouchDesigner expects things to be done: builder guides per operator family, layout and performance conventions, and workflow skills for planning, reviewing and cleanup. Without them an agent will guess at parameter names and produce networks that look plausible and are wrong.

They live in the separate [TDMCPSkills](https://github.com/TouchDesigner/TDMCPSkills) repo, which is content only. Installation lives here, in the component, and needs no clone: **Skills Source** blank downloads the latest published release.

Where they land depends on the client, because there is no shared directory:

| Client | User scope | Project scope |
| --- | --- | --- |
| Claude Code | `~/.claude/skills/` | `.claude/skills/` |
| Codex | `~/.codex/skills/` | `.agents/skills/` |
| Antigravity (`agy`) | `~/.gemini/config/skills/` | `.agents/skills/` |
| OpenCode v2 (beta, `opencode2`) | `~/.config/opencode/skills/` | `.agents/skills/` |

Codex, Antigravity and OpenCode v2 share `<project>/.agents/skills/`, so one project install serves all three.

> **Antigravity, scripted:** its workspace skills mount in the interactive TUI but **not** under headless `agy --print`. If you drive `agy` from a script, install at **user** scope.

Cursor and OpenCode v1 have no skills mechanism we have been able to establish, so they are connection-only. OpenCode v2, in beta, reads skills and is the most practical way to try a local model: see [docs/opencode.md](docs/opencode.md).

**The component owns the `td-` namespace.** Each install removes any `td-*` skill *it previously installed* that the current source no longer ships, so renames do not leave orphans. A `td-*` folder it did not install is left alone, as is anything without the prefix.

## Security

The server exposes `execute_code`. Treat reaching it as equivalent to a shell on your machine.

**Server Address Scope** controls who can:

- **Localhost only** (default) — any address outside loopback (`127.0.0.0/8`, `::1`) is refused `403 Forbidden` before routing, authentication or any tool runs. On TD 2025.33060+ the socket is also bound to `127.0.0.1`, so a port scan from another host sees nothing.
- **All interfaces** — non-loopback clients are answered **only when Ask for authentication and Use HTTPS are both on**. Either one off and off-host requests are refused `403`. Unauthenticated LAN access would hand out `execute_code`; un-TLS'd LAN access would put bearer tokens on the wire in cleartext.

**Origin checking** is always on. A request carrying an `Origin` header that is neither loopback nor this server's own origin is refused `403`. This is what stops a web page you have open from reaching the server on your behalf.

**Auto-accept deletion** is on by default, so `delete_operator` does not raise a confirmation dialog — the only dialog TDMCP has. Turn it off on the MCP page if you want to be asked. `execute_code` is arbitrary Python: it is not path-restricted, and on the default localhost configuration it runs without a prompt.

**Authentication** is OAuth 2.1 with PKCE and an in-TD consent popup. Access tokens live in memory and last 24 hours or until TouchDesigner restarts, whichever comes first. Client registrations persist in `.tdmcp/` beside the project. Details in [OAuth](docs/setup-advanced.md#oauth).

## Fork status — tolchx

This fork integrates the complete **offline knowledge layer + high-level composite live tools** (`td-knowledge`) from our previous TouchDesigner MCP (`tolchx/touchdesigner-MCP`, now retired) alongside the official in-process server (`TDMCP.tox` 1.1.55, compatible with TouchDesigner `2025.32460` and earlier).

Full inventory in [FORK-NOTES.md](FORK-NOTES.md); live state, runs and the verification ledger in [docs/BACKLOG.md](docs/BACKLOG.md).

### Dual-Server Architecture (78 Tools Total)

```
┌────────────────────────────────────────────────────────────────────────┐
│                               AI AGENT                                 │
│          (Claude Code / Cursor / Antigravity / OpenCode / Codex)       │
└───────────────────┬────────────────────────────────┬───────────────────┘
                    │ stdio (JSON-RPC)               │ SSE / HTTP (:13316)
                    ▼                                ▼
┌──────────────────────────────────────┐  ┌──────────────────────────────┐
│     td-knowledge (52 Tools)          │  │     TDMCP.tox (26 Tools)     │
│   • 22 Offline Tools (0% TD overhead)│  │   • 26 In-Process Live Tools │
│   • 30 High-Level Live Tools         │  │   • Direct TD Python engine  │
│   • 1,302 FTS5 BM25 Indexed Docs     │  │   • Viewport grab & cook eval│
│   • 79 GLSL Shaders + 15 Lessons     │  │   • Undo-per-call & stats    │
│   • 625-Op Topology + 97-POP Matrix  │  │   • Compatible w/ 2025.32460 │
└──────────────────────────────────────┘  └──────────────────────────────┘
```

---

### `td-knowledge` Tool Reference (52 Tools: 22 Offline + 30 Live)

The `td-knowledge` MCP server (`knowledge/server.py` + `knowledge/live.py`) runs in pure Python stdlib (zero external dependencies). All **22 offline tools** work with TouchDesigner closed; the **30 live tools** orchestrate composite workflows against `http://127.0.0.1:13316/mcp`:

| Category | Tool | Description |
|---|---|---|
| **Knowledge Base (Offline)** | `kb_info` | Provenance, document counts, extracted TS modules, and SQLite FTS5 index stats (1,302 docs, 41 MB). |
| | `kb_taxonomy` | Counts by family (`TOP`, `CHOP`, `SOP`, `POP`, `MAT`, `DAT`, `COMP`), trust tier, and source type. |
| | `kb_search` | Full-text BM25 search across 1,302 curated documents with family, trust-tier, and source filters. |
| | `kb_get` | Retrieve the full paginated content of any indexed document by name or slug. |
| **Operators, Params & API (Offline)** | `ops_doc` | Curated operator docs enriched with **625-operator wiring topology** (`topology.json`) and creation defaults. |
| | `ops_params` | Documented parameter list per operator (names, labels, types, defaults, pages). |
| | `validate_pop_pars` | **Multi-family pre-flight parameter validator** (`POP`, `TOP`, `CHOP`, `SOP`, `DAT`, `MAT`, `COMP`) against `pop_matrix` (97 POPs), `ops_doc`, and `python_api`. Detects OP properties passed as pars (`display`, `render`, `bypass`, `lock`), tuple prefixes (`sizex/y/z`), sequence `numBlocks`, and **co-dependency warnings** (`outputresolution='custom'`, `globforcemult`, `timeintegration`, `triangulatequads`). |
| | `python_api` | 10 MB offline reference for TouchDesigner Python operator classes, methods, members, and docstrings. |
| | `resolve_operator` | Bilingual (ES/EN) natural-language → canonical operator resolver with architectural concepts, parameter/attribute aliases, and suggested templates. |
| **POP System (Offline)** | `pop_matrix` | Live-measured capability matrix of **97 POP types** (creatable, input requirements, measured parameters, errors). |
| | `pop_knowledge` | 15 empirical POP datasets: `patterns`, `wiki_params`, `pop_inventory`, `validation`, `glsl_library`, `glsl_pops_reference`, `glsl_curriculum`, `pop_chains`, `pop_networks`, `pop_parameters`, `real_world_topology`, `pop_rules`, `attribute_rules`, `bridges`, `pop_style`. |
| **Workflows, Templates & Tutorials (Offline)** | `workflows` | 43 end-to-end production pipelines (`.md`) + **43 JSON workflow graphs** (`workflows/graphs/*.json`). |
| | `tutorials` | 28 deep-dive tutorials + the complete **`pop_tutorial` suite** (`INDEX`, `TUTORIAL_KNOWLEDGE`, and lessons `01`–`06`). |
| | `templates` | 35 parameterized network/POP templates (`NETWORK_TEMPLATES`, `POP_NETWORK_TEMPLATES`, `pop-chains`) + 17 architectural specs (`boids`, `SPH`, `field volumes`, `DMX`). |
| | `recipes` | Multi-operator builder recipes + **30 Book of Shaders `glslTOP` recipes** with shader code and gotchas. |
| | `master_prompts` | System-level prompt directives for complex simulation, pathtracing, and validation workflows. |
| **GLSL & Contracts (Offline)** | `glsl_solutions` | Diagnostic catalog of verified fixes for TouchDesigner GLSL compiler errors. |
| | `glsl_rules` | Live-verified syntax and safety rules for GLSL POP compute shaders and TOP pixel shaders. |
| | `glsl_analyze` | Static analyzer for **POP** (`R1–R4`, `F1 void main`, `F4 TDNumElements(k)`, multi-input `TDIn_*`), **TOP** (`R1–R4`, `T4 uniform0name`, `T10 sTD2DInputs`), and **Python** (`R6 .numPoints()`, f-string backslashes, bare math). |
| | `glsl_curriculum` | 15 structured GLSL POP/TOP lessons (`entry='<id>'`, `learning_path=true`) + 79 standalone `.glsl` shaders. |
| | `contracts` | Live-verified operational contracts **C1–C20** (cook lag, render ownership, stopped clock, `pointspriteMAT`, `rayPOP`, `copyPOP`, `mathcombinePOP`). |
| | `discovery` | Empirical bitácora across 27 sources (`discovery-log`, `TD_PARAMETER_CHEATSHEET`, `POPs_KNOWLEDGE`, `POPs_CORRECTIONS`, `PERFORMANCE`, `docs_internal`). |
| **Live Inspection & Layout (Require TD)** | `td_status` | Live health check returning project, build (`runningBuild` + `buildMismatch`), FPS, and **cooking clock diagnosis** (`power`, `timelinePlay`, `realTime`, `cookingVerdict`). |
| | `find_in_ops` | Single-call deep search across DAT text/tables, parameter expressions, parameter names, comments, and operator names (with `max_nodes`/`max_sec` budget). |
| | `auto_layout` | Topological layer layout engine (zero wire crossings), with `dry_run` preview. |
| | `smart_connect` | Intelligent connector selecting the right input index from `topology.json`, KB, and live build docs. |
| | `td_measure` | Live signal & geometry meter: CHOP channel range (`min`, `max`, `mean`, `is_constant`, `is_normalized_01`, `suggested_scale`/`suggested_offset`), POP/SOP `numPoints`/`numPrims`/`bounds`/attributes, TOP dimensions, or DAT rows/text. |
| | `td_explore_project` | Single-call container/project X-ray: counts by family/type, child COMPs, GLSL shaders, `customPars`, active errors, and heaviest operators by `cookTime`. |
| | `td_compare_networks` | Live structural diff between two COMP containers (`only_in_a`, `only_in_b`, `type_mismatches`, non-default `param_diffs`, `connection_diffs`). |
| | `td_spatial_context` | Active UI context: current Network Editor pane, open container path, `currentChild`, `selectedChildren`, and timeline state. |
| **Live Builders & Serialization (Require TD)** | `td_glsl_apply` | Atomic GLSL pipeline: static `glsl_analyze` check → creates `textDAT` + `glslPOP`/`glslcopyPOP`/`glslTOP` → auto-expands `attr` (`Create Attributes`) and `vec` (`uniforms` + `vec0type`) sequence blocks → wires inputs → verifies `_info` compilation. |
| | `td_build_pop_render` | Atomic POP 3D render builder in 1 call: creates `geometryCOMP` (**destroys default `torus1`**), wires `source_pop` (or `spherePOP`) → `convertPOP(topointprims)` → `nullPOP(display=True, render=True)`, plus `cameraCOMP`, `pointspriteMAT`/`constantMAT`/`pbrMAT`, `renderTOP`, and `nullTOP`, runs 4 cook settle passes, and evaluates the rendered frame. |
| | `td_instantiate_template` | Materializes any template or recipe (`templates` / `recipes` / `custom_templates`) live in 1 call: creates container + operators, expands sequence `numBlocks`, sets parameters/expressions and deferred references, wires connections, and runs `auto_layout`. |
| | `td_scaffold_component` | **Pilar 6 — Component & Extension Builder**: creates Custom Parameter pages (`Float`, `Int`, `RGB`, `Toggle`, `Pulse`, `Menu`, `OP`), links them via expression or `bindMaster` to child operators, attaches and initializes a **Python Extension** (`reinitextensions`), and optionally saves a `.tox`. |
| | `td_wire_reactive` | **Pilar 7 — Auto-Calibrated Reactive Bridge**: measures the real `[min, max]` of a live CHOP channel, builds `selectCHOP` → `mathCHOP` (mapped to `[target_min, target_max]`) → `lagCHOP` → `nullCHOP`, and binds the target parameter or uniform via expression. |
| | `td_harvest_pattern` | **Pilar 10 — Pattern Harvester**: extracts a live verified COMP container into `knowledge/custom_templates/<name>.json` + `.tdxn`, making it immediately available in `templates` and `td_instantiate_template`. |
| | `td_build_control_panel` | **Pilar 11 — Perform UI Control Panel Generator**: builds a `containerCOMP` with header, live `opviewerCOMP` viewport connected to the output TOP, interactive `parameterCOMP` inspector dock bound to target COMPs, and optional `windowCOMP`. |
| | `td_setup_audio_analyzer` | **Pilar 13 — Turnkey Multi-Band Audio Reactivity Engine**: builds an `audio_analyzer` `baseCOMP` (`test_oscillator`/`file`/`device`/`op` → `audiofilterCHOP` lowpass/bandpass/highpass → `analyzeCHOP` RMS → `mathCHOP` gain → `lagCHOP` → `nullCHOP` exposing `bass`, `mid`, `high`, `rms`, `kick`) and wires optional reactive bindings. |
| | `td_setup_scene_switcher` | **Pilar 14 — Master Scene Switcher with Smart Cooking**: connects 2+ scene COMPs/TOPs into a master switcher (`switchTOP` `blend=True` + `filterCHOP`) with a `chopexecuteDAT` that disables `allowCooking` on inactive scenes outside the active crossfade. |
| | `td_preset_manager` | **Pilar 15 — Preset & State Morphing Engine**: captures (`capture`), lists (`list`), applies (`apply`), deletes (`delete`), or linearly blends (`blend` with `alpha` `0.0..1.0`) parameter presets persisted in `<comp>/_mcp_presets` and optional JSON files. |
| | `tdn_export` / `tdn_diff` | Export a live network to **TDN v1.4 JSON** and diff two `.tdn` files offline. |
| | `tdxn_export` / `tdxn_build` | Export or build a complete network from **TDXN v2.1 YAML** (`=expr`, `~bind`, DATs, flags) in a single call. |
| **Live Verification, Camera & Profiling (Require TD)** | `td_verify_network` | **Single-call Gauntlet verifier**: runs 4 settle cook passes, audits `geometryCOMP` ownership (`torus1` deleted, `display`/`render` flags, `numPoints`/`numPrims > 0`), checks POPs/CHOPs for `NaN`/`Inf`, runs `get_op_errors_deep` and `eval_render_frame`, and returns `PASS`/`FAIL` with `actionable_fixes`. |
| | `td_frame_camera_to_geo` | **Pilar 8a — Mathematical 3D Auto-Framing**: computes the combined world AABB of all active POPs/SOPs across `geometryCOMP`s and frames the `cameraCOMP` (`tx, ty, tz, near, far`) using camera FOV and render aspect ratio. |
| | `td_visual_diff` | **Pilar 8b — Quantitative Pixel Diff**: compares two TOPs or PNGs pixel-by-pixel, returning `mean_abs_diff`, `changed_pixels_pct`, `psnr_db`, and verdict (`SIGNIFICANT_CHANGE` / `SUBTLE_CHANGE` / `IDENTICAL_NO_OP`). |
| | `td_render_contact_sheet` | **Pilar 12 — Multi-Frame Temporal Vision**: steps a simulation/network across $N$ samples spaced by `step_frames`, composites an $R \times C$ contact sheet PNG with progress bars, and computes inter-frame motion metrics (`ANIMATING` / `STATIC` / `BLANK`). |
| | `td_control_simulation` | **Pilar 9 — Simulation & Temporal Loop Controller**: detects all stateful operators (`feedbackPOP`, `particlePOP`, `feedbackTOP`, `trailPOP`, `cachePOP`, `speedCHOP`), pulses all resets atomically, runs $N$ pre-roll steps, and diagnoses `STABLE_DYNAMIC`, `STABLE_STATIC`, `EMPTY`, `EXPLODING`, or `NAN_CORRUPTED`. |
| | `td_profile_network` | **Live CPU/GPU profiler & anti-pattern detector**: measures CPU `cookTime`, `gpuCookTime`, and memory per node, computes % of frame budget (`16.67ms` at 60fps), and flags `PERFORMANCE.md` anti-patterns (`copyPOP` >50k pts without instancing, CPU SOPs inside POP `geometryCOMP`, >4K TOPs, heavy `poptoCHOP`/`toptoCHOP` readbacks). |
| | `eval_render_frame` | Evaluates TOP or image visual quality (`PASS`/`FAIL` for black, flat, or transparent frames with luminance/contrast metrics). |
| | `get_op_errors_deep` | Recursive error, warning, and docked GLSL `_info` compiler error scanner (with `max_nodes`/`max_sec` budget). |

---

### Sanitized Knowledge & Zero Hallucinations

During migration, all legacy assets were processed through [`scripts/sanitize_legacy_knowledge.py`](file:///c:/Users/Tolch/Documents/AI_Code/TDMCP/tolchx-TDMCP/scripts/sanitize_legacy_knowledge.py) (integrated into `knowledge/build_assets.py`) to purge obsolete paradigms and hallucinations:
- **Hallucinated Operators Removed**: `renderPOP` (does not exist in TouchDesigner) was systematically replaced with `poptoTOP` (data texture) and the standard rendering pipeline (`geometryCOMP` + `cameraCOMP` + `renderTOP` with `pointspriteMAT` per Contract C2).
- **Corrected Operator Names**: `pointgenPOP` → `pointgeneratorPOP`, `colorPOP` → `attributePOP`/`glslPOP`, `forcePOP`/`dragPOP` → `noisePOP`/`windPOP`/`particlePOP`, `lookupPOP` → `lookuptablePOP`, `spritePOP` → `pointspriteMAT`, `panelCOMP` → `containerCOMP`.
- **Render Blackout Bug (`deleteprims`) Fixed**: Workflows and template specs using `deleteprims` (which eliminated 100% of primitives leaving empty renders) were updated to `convertPOP(topointprims)` and `gridPOP.par.surftype = 'points'`.
- **Auto-Torus Trap Documented**: Explicit cleanup routines destroy default `torus1` geometry inside new `geometryCOMP` operators to avoid false positive renders.

---

### Client Configuration

Add both servers to your agent configuration to enable full offline knowledge and live execution.

#### Claude Code
```bash
# Add official live server (when TouchDesigner is running)
claude mcp add touchdesigner -- http://127.0.0.1:13316/mcp

# Add offline + high-level live knowledge server
claude mcp add td-knowledge -- python "C:/Users/Tolch/Documents/AI_Code/TDMCP/tolchx-TDMCP/knowledge/server.py"
```

#### Cursor (`.cursor/mcp.json`)
```json
{
  "mcpServers": {
    "touchdesigner": {
      "url": "http://127.0.0.1:13316/mcp"
    },
    "td-knowledge": {
      "command": "python",
      "args": ["C:/Users/Tolch/Documents/AI_Code/TDMCP/tolchx-TDMCP/knowledge/server.py"]
    }
  }
}
```

#### Antigravity / Gemini
In your workspace or user MCP configuration:
```json
{
  "mcpServers": {
    "td-knowledge": {
      "command": "python",
      "args": ["C:/Users/Tolch/Documents/AI_Code/TDMCP/tolchx-TDMCP/knowledge/server.py"]
    }
  }
}
```

---

### Building, Archiving, and Testing the Knowledge Base

`knowledge/build_assets.py` supports **standalone mode** (re-indexing existing `knowledge/kb/` even after the legacy repo is deleted) as well as portable `.zip` export/import:

```bash
# 1. Re-index in standalone mode (or pass --repo if syncing from legacy checkout)
python knowledge/build_assets.py

# 2. Export / import a portable ZIP backup of knowledge/kb/
python knowledge/build_assets.py --export-archive td-knowledge-kb.zip
python knowledge/build_assets.py --import-archive td-knowledge-kb.zip

# 3. Run internal tool self-tests (verifies all 22 offline tools)
python knowledge/server.py --selftest

# 4. Run JSON-RPC protocol test suite (verifies all 52 tools via stdio JSON-RPC 2.0)
python knowledge/test_protocol.py

# 5. Run end-to-end live test suite against TouchDesigner (32 stages across Pillars 1-15)
python knowledge/test_live.py
```

### Pruebas POP en vivo (35 builds)

La cobertura POP no se afirma de memoria: cada tipo se mide contra TD vivo con un build
versionado y checks con número. La batería completa son **35 builds / 473 chequeos** y corre
por el MCP oficial:

```bash
# TD abierto + componente TDMCP Active en 127.0.0.1:13316
GAUNTLET_RUN_ID=reg-20261029-2135 python tools/gauntlet/regression_pop.py

# un solo tipo, p. ej. los tres del tramo 2026-10-29
python tools/gauntlet/build_pop_ray.py          # 24 checks
python tools/gauntlet/build_pop_copy.py         # 20 checks
python tools/gauntlet/build_pop_mathcombine.py  # 20 checks
```

Exit 0 = todos verdes; exit 2 = entorno (TD/MCP caído), no rojo. Cada build deja
`tools/gauntlet/results/<run_id>/` (ignorado por git) con el `.jsonl` de tool calls, el
reporte numérico y un PNG del render. La batería cierra con un audit de layout:
`td_layout.py` separa los nodos por profundidad de conexiones y falla si dos se solapan
(hoy: **114 redes, 0 pares**).

Para comprobar que ese layout **persiste en el `.toe`**, hay un test opt-in que guarda,
recarga el proyecto y compara la huella de las 631 posiciones: `python
tools/gauntlet/persist_layout.py` (o `run_regression.py --persist-layout`). Corta el MCP
unos segundos mientras TD recarga, así que no forma parte de la batería normal.

El tramo del **2026-10-29** cerró tres tipos del ítem 5d y la deuda #1 del ítem 10:

- **`rayPOP`** — el rayo reescribe `P`/`N` al impacto aun con los toggles apagados;
  `RayDistance`/`RayNumHits`/`RayPrimIndex`/`RayInside`, centinelas de miss
  (`1e8` / `2^32`), `limitraylength` que recorta `P` pero no la distancia reportada,
  `numbounces` que exige `N` en la colisión y HW tracing que sólo reporta el primer hit.
- **`copyPOP`** — `puntos = fuente × template × ncy`, `dotemplatetranslate` OFF por default,
  `CopyId` por scope (y sólo con `ncy>1`), transform pars inertes para `P`.
- **`mathcombinePOP`** — gating 0/1 de `rayPOP`: `gt` es estricto (4 > 4 falla, 4 > 3 pasa),
  `mix` es un lerp (`C=0.5` → `0.55`), los bloques encadenan y `comb*result` auto-crea el
  atributo con la página `attr` default vacía; `mathmixPOP` da el mismo resultado y no tiene
  página `attr`. El build deja los nodos separados y verifica 0 solapamientos.

Los contratos medidos están en **C19** y **C20** de
[VERIFIED_CONTRACTS.md](knowledge/contracts/VERIFIED_CONTRACTS.md); C18 quedó corregido
(`RayHitNormal` no existe en 2025.32460). El detalle del pase, las tablas de números y el
hallazgo del rate limiter están en
[docs/pop-coverage-2026-10-29.md](docs/pop-coverage-2026-10-29.md).

**Regresión verde ≠ operador verificado en todas las versiones.** Los números codifican el
comportamiento de TD 2025.32460 + TDMCP 1.1.55; un build nuevo que los cambie es un hallazgo,
no un test a relajar.

## Other clients and advanced setup

[**docs/setup-advanced.md**](docs/setup-advanced.md) covers:

- [Per-client registration commands and config file shapes](docs/setup-advanced.md#other-clients) for Codex, Antigravity, Cursor and OpenCode, including the three traps: Antigravity needs `serverUrl` not `url`, OpenCode nests under `mcp` (v2: `mcp.servers`) not `mcpServers`, Codex uses a TOML table
- [HTTPS setup](docs/setup-advanced.md#https) with mkcert, per platform
- [Claude Desktop](docs/setup-advanced.md#claude-desktop), which needs the `mcp-remote` bridge
- [Multiple projects and side-by-side instances](docs/setup-advanced.md#multiple-instances)
- [OAuth internals](docs/setup-advanced.md#oauth): state, endpoints, the event log
- [Adding an agent](docs/setup-advanced.md#adding-an-agent) as a JSON record

[**docs/opencode.md**](docs/opencode.md) covers OpenCode v1 and the v2 beta, running a local model with Ollama, Code Mode, and what has been learned so far about local agents driving TDMCP.

## Troubleshooting

### The agent has no TouchDesigner tools

1. Check **Active** is on.
2. Test the server directly. A JSON reply means it is up; `401` means it is up with authentication on, which is also success:
   ```bash
   curl -X POST http://127.0.0.1:13316/mcp -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'
   ```
3. Confirm the port in **Add MCP** matches what your client registered.
4. Restart the client. Most only read MCP config at startup.

### Connection refused

- **Use `127.0.0.1`, never `localhost`.** The socket is IPv4-only. `localhost` resolves to `::1` first on many systems, and a client that does not retry the next address reports a refusal.
- Check nothing else holds the port.
- If you changed **Port**, re-register: **Remove MCP** then **Add MCP**.

### Install Skills reported an error

- **`CERTIFICATE_VERIFY_FAILED`** — TouchDesigner's bundled OpenSSL ships cert paths that do not exist on your machine, so HTTPS from inside TD has no trust anchors. TDMCP falls back to the `certifi` bundle that ships with TD. If you see this, your TD build has no `certifi`; set **Skills Source** to a local TDMCPSkills checkout as a workaround and file an issue.
- **`404 ... no such repo, or it is private`** — check **Skills Repo**. Blank means `TouchDesigner/TDMCPSkills`.
- Anything else — the message carries the underlying reason. Nothing is touched on failure; an existing install stays intact.

### Skills installed but the agent ignores them

- Read **Installed Locations** and confirm the directory matches the client you are actually running.
- Scope matters: a project install only applies to sessions started in that directory.
- Restart the agent. Most discover skills at startup.
- For scripted Antigravity, install at **user** scope — see [Skills](#skills).

### OAuth: 401, or "does not match expected", after a restart or a URL change

Clear the client's stored authentication and reconnect. In Claude Code: `/mcp` → `touchdesigner` → *Clear authentication* → *Reconnect*, then approve the TouchDesigner popup. Other clients: remove and re-add the server.

Tokens live in memory, so a TD restart invalidates all of them. The server also advertises itself exactly as you addressed it, so switching between `localhost` and `127.0.0.1` invalidates the client's cached identifier.

Restarting TouchDesigner does not help. The stale state is in the client.

### Stuck in a re-authentication loop

The consent page opens but never completes. The client is replaying a `client_id` this server does not have, and re-authenticating preserves registrations while clearing only tokens, so it fails identically every time.

Confirm with `grep authorize_reject .tdmcp/oauth_events.log` — `reason=unknown_client_id` is this failure. Fix by clearing the *registration*: `claude mcp logout touchdesigner`, or remove and re-add for other clients.

### Claude Desktop problems

See [docs/setup-advanced.md#claude-desktop](docs/setup-advanced.md#claude-desktop). Note that Desktop's **Add Custom Connector** cannot reach a local server at all; use the bridge.

## Changes

See [CHANGELOG.md](CHANGELOG.md). Each release is tagged with the bare version
baked into that build, so a `.tox` can always be traced to its release: read
**Version** on the component's About page and find the matching tag.

This repository carries the documentation and the published builds. Development
happens in a separate repository. Use
[Issues](https://github.com/TouchDesigner/TDMCP/issues) for bugs and
[Discussions](https://github.com/TouchDesigner/TDMCP/discussions) for questions
and requests.

## License

Shared Use License — see [LICENSE.md](LICENSE.md). It permits use and modification for your own projects and prohibits redistributing TDMCP itself as a product. Read it before shipping anything built on it commercially.

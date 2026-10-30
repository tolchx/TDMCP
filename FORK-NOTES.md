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
| `knowledge/` | **td-knowledge** — an offline + live MCP server (Python stdlib, stdio) with **22 offline tools + 40 live tools (62 tools total)**: full-text BM25 search across 1,302 documents, 43 production workflows (+ 43 JSON workflow graphs), 28 advanced tutorials (+ the complete `pop_tutorial` suite), 17 network template specs, 35 network/POP templates and chains, 79 GLSL shaders + 15 structured `glsl_curriculum` lessons, 10 MB TouchDesigner Python API reference, GLSL Error Solutions catalog, empirical discovery log across 27 markdown sources, the measured POP capability matrix (97 POPs) with multi-family parameter & co-dependency validator (`validate_pop_pars`), operator/parameter docs enriched with 625-operator topology (`topology.json`) and creation defaults, natural-language → operator resolution with architectural concepts and parameter/attribute aliases, live-verified GLSL rules, static analyzer (POP/TOP/Python), live-verified contracts C1–C20, and 40 high-level live tools (`td_status`, `find_in_ops`, `auto_layout`, `smart_connect`, `tdn_export`, `tdn_diff`, `tdxn_export`, `tdxn_build`, `eval_render_frame`, `get_op_errors_deep`, `td_measure`, `td_glsl_apply`, `td_explore_project`, `td_compare_networks`, `td_spatial_context`, `td_build_pop_render`, `td_instantiate_template`, `td_verify_network`, `td_profile_network`, `td_scaffold_component`, `td_wire_reactive`, `td_frame_camera_to_geo`, `td_visual_diff`, `td_control_simulation`, `td_harvest_pattern`, `td_build_control_panel`, `td_render_contact_sheet`, `td_setup_audio_analyzer`, `td_setup_scene_switcher`, `td_preset_manager`, `td_setup_gpu_instancing`, `td_setup_postfx_chain`, `td_setup_io_bridge`, `td_record_movie`, `td_heal_network`, `td_setup_display_canvas`, `td_setup_pbr_stage`, `td_sync_external_tox`, `td_setup_ai_stream`, `td_benchmark_longevity`). |
| `skills-hermes/` | The portable `td-*` skills (**28** of them, synced with `TDMCPSkills 1.4.1` companion references/examples), adapted for the Hermes Agent skill format (`Use when …` descriptions + a header that maps the tool names to the host's `mcp_<server>_<tool>` convention). Includes `td-glslpop-create`, `td-glslpop-debug`, `td-glslpop-shaders` ported from the previous MCP, plus verified live patches from the TDMCP gauntlet, plus `td-pop-particle-systems` and `td-pop-neighbors-and-rays` distilled from 2026 POP tutorials (not live-verified: see `docs/pop-tutorials-2026-10-07.md`). Original license retained in `LICENSE-TDMCPSkills.md`. |
| `knowledge/contracts/` | **`VERIFIED_CONTRACTS.md`** — the live-verified contracts (cook lag, render cache vs POP data, stopped clock, POP→render, `pointspriteMAT`, POP Python API, TDMCP tool contracts, verification checklist), **tracked** in git (unlike `kb/`, which is derived). Served offline by the `contracts` tool of `td-knowledge`. |
| `tools/gauntlet/` | Build + verification harness: `gauntlet_client.py` (MCP client with per-phase logs), the F1–F6 regression phases, `build_particle_fx.py` (builds and verifies `/particle_swirl`), `build_pop_curlfield.py` (a **second** POP network — `gridPOP` 3D + hand-written curl-noise GLSL — used to cold-run the POP→render recipe, with an A/B experiment `deleteprims` vs `topointprims` and a findings ledger), `verify_visual.py` / `make_preview.py` (PIL PNG metrics + HTML preview; `make_preview.py <run> swirl|curl`), **`td_chain.py`** — the program *injected* into TouchDesigner by `execute_code` (`settle()` / `px()` / `render_is_ours()`, with `ROOT` pinned by `td_probe.chain_source(root)`); importable code, so it is exercised off-TD with a fake `op`. **`td_probe.py`** is the single place to measure on the *host*: `chain_source(root)`, `set_and_verify()` writes-and-rereads, `stats_of`/`png_stats`/`grid_cells` are the PIL metrics, and `selftest_render_ownership()` proves the render-ownership guard can **fail** (it is what caught the auto-torus). **`check_single_home.py`** fails if a consumer re-defines `settle`/`px`/`render_is_ours` instead of importing them. |
| `docs/community-test-notes-2026-09-28.md` | Test notes from exercising TDMCP 1.1.55 against a live TouchDesigner project: what was verified (structured errors, undo-per-tool-call, security guards, grid captures, DAT file sync) and the three issues filed upstream. |
| `docs/td-lecciones-aprendidas-2026-09-29.md` | What two build sessions taught about constructing in TouchDesigner with TDMCP: the five costly lessons (cook lag, render cache vs POP data, surface vs point cloud, stopped clock, verification errors), the verified-contract index, the reusable tooling, and the **ritual** for turning each new finding into a contract + skill + tool. |
| `docs/particle-fx-2026-09-29.md` | Build report for `/particle_swirl` (POP GLSL particle swarm): network, shader, material look, run id `20260929-010805` and the environment limits on visual verification. ⚠️ **Corrected 2026-09-29 (pass 2):** its "35/35 verified" render was measuring the auto-created `torus1`, not the particles; see `docs/td-curl-field-2026-09-29.md`. |
| `docs/td-curl-field-2026-09-29.md` | **Pass 2** — cold-running the POP→render recipe against a brand-new network (`/curl_field`): the 7 findings (`deleteprims` renders black → `topointprims`; the auto-torus masking a broken render; `pointsize` vs `attensizenear`; `vec` `numBlocks`; lazy docked DATs; `set_parameters` silent no-apply), plus the fix applied to `/particle_swirl`. Runs `20260929-025128` (curl) and `20260929-025059` (swirl). |
| `docs/issues-filed/` | Copy of the three bug reports opened on `TouchDesigner/TDMCP` (#1, #2, #3). |
| `component/` | The **official TDMCP 1.1.55 build** (`TDMCP.tox` + `TDMCP.json`), committed unmodified with its SHA-256 hashes so the binary travels with the fork instead of living only as a release asset. See `component/README.md`. |

## Stage 3 — the bridge is gone (100% legacy integration)

The original MCP (`tolchx/touchdesigner-MCP`) used its own transport: a Web Server DAT bridge on
`127.0.0.1:44444` plus a Node MCP server with 107 tools. That transport and repository are **retired**.
The official `.tox` provides the low-level live side (`127.0.0.1:13316/mcp`, 26 tools), and
`knowledge/` provides the complete offline KB (**22 tools**) **plus 40 high-level live tools** that
speak MCP to the official server:
- `td_status` (includes `runningBuild`, `buildMismatch`, `power`, `timelinePlay`, `realTime`, `cookingVerdict`)
- `find_in_ops`, `auto_layout`, `smart_connect`, `tdn_export`, `tdn_diff`
- `tdxn_export`, `tdxn_build`, `eval_render_frame`, `get_op_errors_deep`
- `td_measure` (live CHOP signal range/scale/offset calculator, POP/SOP bounds & attributes, TOP/DAT stats)
- `td_glsl_apply` (end-to-end GLSL POP/TOP validator + textDAT + operator + auto `Create Attributes` / `vec` uniforms + `infoDAT` compiler check)
- `td_explore_project` (single-call container/project audit with family counts, shaders, issues, and top `cookTime` operators)
- `td_compare_networks` (live diff between two COMP containers)
- `td_spatial_context` (active Network Editor pane, current/selected operators, and timeline state)
- `td_build_pop_render` (atomic POP render pipeline builder: `geometryCOMP` without `torus1` + `convertPOP(topointprims)` + `nullPOP(display/render)` + `cameraCOMP` + `MAT` + `renderTOP` + `nullTOP` + 4-pass settle + frame evaluation)
- `td_instantiate_template` (materializes any network template or recipe in 1 call with sequence `numBlocks` expansion and auto-layout)
- `td_verify_network` (single-call physical, temporal, error, and visual Gauntlet verifier with `actionable_fixes`)
- `td_profile_network` (live CPU/GPU cook-time & memory profiler with frame-budget % and `PERFORMANCE.md` anti-pattern detector)
- `td_scaffold_component` (Pilar 6: encapsulates a COMP with typed Custom Parameters, child bindings/expressions, initialized Python Extension, and `.tox` export)
- `td_wire_reactive` (Pilar 7: measures live CHOP signal range and builds an auto-calibrated `selectCHOP` → `mathCHOP` → `lagCHOP` → `nullCHOP` chain wired to the target parameter)
- `td_frame_camera_to_geo` (Pilar 8a: computes combined 3D world bounds across active POPs/SOPs and auto-frames `cameraCOMP` via FOV & aspect ratio)
- `td_visual_diff` (Pilar 8b: quantitative pixel-level diff between two TOPs or PNGs with MAE, changed-pixel %, and PSNR)
- `td_control_simulation` (Pilar 9: atomic reset + pre-roll of stateful simulation nodes with inter-frame motion & explosion/NaN diagnosis)
- `td_harvest_pattern` (Pilar 10: harvests a live COMP network into `knowledge/custom_templates/<name>.json` + `.tdxn` for instant reuse)
- `td_build_control_panel` (Pilar 11: builds a Perform-ready UI `containerCOMP` with header, live `opviewerCOMP`, `parameterCOMP` inspector dock, and optional `windowCOMP`)
- `td_render_contact_sheet` (Pilar 12: multi-frame temporal vision; steps the network $N$ samples, composites an $R \times C$ contact sheet PNG with progress bars, and diagnoses `ANIMATING` / `STATIC` / `BLANK`)
- `td_setup_audio_analyzer` (Pilar 13: builds a turnkey multi-band audio analyzer `baseCOMP` outputting normalized `bass`, `mid`, `high`, `rms`, and `kick` channels + optional parameter bindings)
- `td_setup_scene_switcher` (Pilar 14: builds a master scene switcher with `switchTOP` `blend=True` + `filterCHOP` and `chopexecuteDAT` Smart Cooking that turns off `allowCooking` on inactive scenes)
- `td_preset_manager` (Pilar 15: captures, lists, applies, deletes, or linearly blends `alpha = 0.0..1.0` parameter presets stored in `<comp>/_mcp_presets` and optional JSON files)
- `td_setup_gpu_instancing` (Pilar 16: GPU hardware instancing on `geometryCOMP` with position/color/scale/normal mappings from POP/CHOP/TOP/SOP sources)
- `td_setup_postfx_chain` (Pilar 17: modular GPU post-processing and LookDev rack `baseCOMP` with bloom, feedback trail, color grading, and exposed Custom Parameters)
- `td_setup_io_bridge` (Pilar 18: universal show I/O bridge for OSC, MIDI, DMX/Art-Net, UDP with integrated loopback test signal generators)
- `td_record_movie` (Pilar 19: deterministic frame-by-frame animation/loop recorder cooking at exact target FPS with animated GIF encoding and verification)
- `td_heal_network` (Pilar 20: autonomous network doctor repairing torus1 traps, missing display/render flags, unconfigured custom resolutions, detached cameras, and simulation NaNs with dry_run and verification)
- `td_setup_display_canvas` (Pilar 21: multi-display & projector canvas generator with edge-blending overlap, per-display crop TOPs, test pattern overlays, and span windowCOMP)
- `td_setup_pbr_stage` (Pilar 22: 3D cinematic lighting studio with Key/Fill/Rim lights, environmentlightCOMP, shadow catcher ground plane, subject PBR material, and renderTOP)
- `td_sync_external_tox` (Pilar 23: external TOX hot-reload and drift auditor with atomic disk export and re-init)
- `td_setup_ai_stream` (Pilar 24: turnkey GenAI & ComfyUI streaming baseCOMP with webclientDAT/websocketDAT, prompt queue, telemetry CHOP, and outTOP)
- `td_benchmark_longevity` (Pilar 25: 24/7 longevity & soak benchmark measuring live VRAM/CPU memory slopes and auditing unbounded buffers)

## Division of labour

* **Live primitives** → the official `TDMCP.tox` (26 tools, in-process: create/wire/edit, read parameters,
  sample TOP/CHOP/POP values, capture the viewer, profile cook times, undo-per-call).
* **Knowledge, validation, planning & composite live workflows** → `knowledge/` (22 offline tools work with
  TouchDesigner closed; 40 live tools orchestrate multi-step building, component scaffolding, reactive wiring, audio analysis, scene switching, preset morphing, UI generation, temporal contact sheets, camera framing, simulation control, GPU instancing, postfx racks, show I/O bridges, movie recording, self-healing, multi-display edge blending, PBR staging, external TOX hot-reload, GenAI streaming, 24/7 longevity soak testing, verification, profiling, inspection, layout, measurement, and GLSL compilation over `:13316`).

## Using it

```bash
# 1. build or reindex the knowledge assets (standalone mode works even after deleting the old repo)
python knowledge/build_assets.py

# Optional: export/import a portable zip backup of kb/
python knowledge/build_assets.py --export-archive td-knowledge-kb.zip
python knowledge/build_assets.py --import-archive td-knowledge-kb.zip

# 2. sanity-check offline & live, then register as a stdio MCP server
python knowledge/server.py --selftest
python knowledge/test_protocol.py
python knowledge/test_live.py
```

`kb/` is deliberately **not** in this repository: it is derived data (a SQLite index plus JSON
extracted from a local installation) and it embeds third-party documentation. Rebuild it locally.

## Sanitization of Legacy MCP Hallucinations & Alignment with TD 2025+

During the migration of the legacy MCP knowledge base, an automated audit (`scripts/sanitize_legacy_knowledge.py`, integrated into `knowledge/build_assets.py`) purged legacy hallucinations and obsolete patterns:
- **Non-existent operators eliminated:**
  - `renderPOP` → replaced with `poptoTOP` (data texture) and the standard geometry pipeline (`geometryCOMP` + `cameraCOMP` + `renderTOP` with `pointspriteMAT`, per Contract C2).
  - `colorPOP` → replaced with `attributePOP` / `glslPOP` (Contract C11).
  - `forcePOP` / `dragPOP` → replaced with `noisePOP` / `windPOP` / `particlePOP`.
  - `lookupPOP`, `lookupattPOP`, `lookuptexPOP` → replaced with real operator names (`lookuptablePOP`, `lookuptexturePOP`).
  - `spritePOP` → replaced with `pointspriteMAT`.
  - `panelCOMP` → replaced with `containerCOMP`.
  - `pointgenPOP` → replaced with `pointgeneratorPOP`.
  - `pointfileselectPOP` → replaced with `pointfileinPOP`.
- **POP-to-Render Recipes Fixed:** Eliminated the `deleteprims` pitfall (which produces 0 point primitives and renders 100% black) in favor of `convertPOP(topointprims)` / `gridPOP.par.surftype = 'points'`, and enforced destroying default auto-created geometry (`torus1`) inside new `geometryCOMP` instances.
- **Parametric Alignment:** Replaced invalid parameters like `attensizenear` with `pointspriteMAT.par.pointsize`.

## Provenance

Built and verified on Windows 11 with TouchDesigner 2025.32460 and TDMCP 1.1.55.

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

This fork integrates the complete **offline knowledge layer** from our previous TouchDesigner MCP alongside the official in-process server (`TDMCP.tox`).

Full inventory in [FORK-NOTES.md](FORK-NOTES.md); live state, runs and the verification ledger in [docs/BACKLOG.md](docs/BACKLOG.md).

### Dual-Server Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                               AI AGENT                                 │
│          (Claude Code / Cursor / Antigravity / OpenCode / Codex)       │
└───────────────────┬────────────────────────────────┬───────────────────┘
                    │ stdio (JSON-RPC)               │ SSE / HTTP (:13316)
                    ▼                                ▼
┌──────────────────────────────────────┐  ┌──────────────────────────────┐
│       td-knowledge (Offline MCP)     │  │       TDMCP.tox (Official)   │
│   • 21 Offline Tools                 │  │   • 26 In-Process Live Tools │
│   • 6 Live Wrappers                  │  │   • Direct TD Python engine  │
│   • 1,128 FTS5 BM25 Indexed Docs     │  │   • Viewport grab & cook eval│
│   • Runs with TD closed (0% overhead)│  │   • Requires TD running      │
└──────────────────────────────────────┘  └──────────────────────────────┘
```

---

### `td-knowledge` Tool Reference (27 Tools)

The offline MCP server (`knowledge/server.py`) operates via standard I/O and requires no running instance of TouchDesigner:

| Category | Tool | Description |
|---|---|---|
| **Knowledge Base** | `kb_info` | Metadata, document counts, and SQLite FTS5 index stats. |
| | `kb_taxonomy` | High-level taxonomy of TouchDesigner families (TOP, CHOP, SOP, POP, MAT, DAT, COMP). |
| | `kb_search` | Full-text BM25 search across 1,128 curated documents with category filters and snippets. |
| | `kb_get` | Retrieve the full content of any indexed document by its unique URI. |
| **Operators & API** | `ops_doc` | Official documentation, parameter overviews, inputs, and common gotchas for any operator. |
| | `ops_params` | Exhaustive parameter inspection per operator (types, defaults, min/max, menus). |
| | `python_api` | 10 MB offline AST reference for TouchDesigner Python classes, methods, members, and docstrings. |
| | `resolve_operator` | Natural language query to matching TouchDesigner operator names with confidence scoring. |
| **POP System** | `pop_matrix` | Verified capability matrix of all 101 POP families (inputs, outputs, stability, context). |
| | `pop_knowledge` | Rules, known bugs, caveats, and recommended topologies for the POP system. |
| **Workflows & Guides**| `workflows` | 42 end-to-end production pipelines (pathtracer, gaussian splatting, audio-reactive, fluid solver, etc.). |
| | `tutorials` | 28 deep-dive tutorials including step-by-step POP simulations and creative feedback loops. |
| | `templates` | Parameterized network templates (audio reactive, particle systems, feedback loops). |
| | `recipes` | Granular multi-operator wiring recipes with verified Python generation code. |
| | `master_prompts` | System-level prompt directives for autonomous agent orchestration. |
| **GLSL & Verification**| `glsl_solutions`| Diagnostic catalog for GLSL errors (`undeclared identifier`, `swizzling`, `SSBO binding`, etc.). |
| | `glsl_rules` | Static syntax and safety rules for GLSL POP compute shaders and TOP pixel shaders. |
| | `glsl_analyze` | Static shader analyzer detecting missing `outputattrs`, incorrect types, and Vulkan TDR risks. |
| | `glsl_curriculum`| Progressive curriculum of 62 verified GLSL POP shader implementations. |
| | `contracts` | 16 live-verified operational contracts C1–C16 (cook lag, render ownership, stopped clock, etc.). |
| | `discovery` | Bitácora of empirical limits, hardware quirks, and measured edge-cases. |
| **Live Wrappers** | `td_status` | Fast health check and status query to the live `TDMCP.tox` server. |
| *(Require TD)* | `find_in_ops` | Deep search inside live DAT code, table contents, and operator parameter expressions. |
| | `auto_layout` | Automatic topological layout engine positioning operators neatly on the canvas. |
| | `smart_connect` | Intelligent port connector resolving appropriate input/output indices between operators. |
| | `tdn_export` | Export TouchDesigner network structure into clean, human-readable JSON. |
| | `tdn_diff` | Structural diffing tool comparing two network graphs for change audits. |

---

### Sanitized Knowledge & Zero Hallucinations

During migration, all legacy assets were processed through [`scripts/sanitize_legacy_knowledge.py`](file:///c:/Users/Tolch/Documents/AI_Code/TDMCP/tolchx-TDMCP/scripts/sanitize_legacy_knowledge.py) (integrated into `knowledge/build_assets.py`) to purge obsolete paradigms and hallucinations:
- **Hallucinated Operators Removed**: `renderPOP` (does not exist in TouchDesigner) was systematically replaced with `poptoTOP` (data texture) and the standard rendering pipeline (`geometryCOMP` + `cameraCOMP` + `renderTOP` with `pointspriteMAT` per Contract C2).
- **Corrected Operator Names**: `pointgenPOP` → `pointgeneratorPOP`, `colorPOP` → `attributePOP`/`glslPOP`, `forcePOP`/`dragPOP` → `noisePOP`/`windPOP`/`particlePOP`, `lookupPOP` → `lookuptablePOP`, `spritePOP` → `pointspriteMAT`, `panelCOMP` → `containerCOMP`.
- **Render Blackout Bug (`deleteprims`) Fixed**: Workflows using `deleteprims` (which eliminated 100% of primitives leaving empty renders) were updated to `convertPOP(topointprims)` and `gridPOP.par.surftype = 'points'`.
- **Auto-Torus Trap Documented**: Explicit cleanup routines destroy default `torus1` geometry inside new `geometryCOMP` operators to avoid false positive renders.

---

### Client Configuration

Add both servers to your agent configuration to enable full offline knowledge and live execution.

#### Claude Code
```bash
# Add official live server (when TouchDesigner is running)
claude mcp add touchdesigner -- http://127.0.0.1:13316/mcp

# Add offline knowledge server (always available)
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

### Building and Testing the Knowledge Base

```bash
# Rebuild assets and SQLite index from local knowledge sources
python knowledge/build_assets.py --repo "C:/Users/Tolch/Documents/AI_Code/Touchdesigner_MCP/Main"

# Run internal tool self-tests (verifies all 21 offline tools)
python knowledge/server.py --selftest

# Run JSON-RPC protocol test suite (verifies JSON-RPC 2.0 framing and responses)
python knowledge/test_protocol.py
```

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

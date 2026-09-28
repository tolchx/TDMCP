# component/ — TDMCP 1.1.55 (unmodified official build)

`TDMCP.tox` is the **official Derivative TDMCP component**, taken as-is from the
[`1.1.55` release](https://github.com/TouchDesigner/TDMCP/releases/tag/1.1.55) and committed here so the
binary travels with the fork instead of living only as a release asset.

| File | SHA-256 | Bytes |
|---|---|---|
| `TDMCP.tox` | `12e1c270171cd35f3b91377ee9c4e833ff42d4e6fa298b9269ed24d5f321c9d4` | 245630 |
| `TDMCP.json` | `a387eae5b59970d2db5e9509c1d79fd50d963aa38311469eddcb4401f03fd4cd` | 135 |

Both hashes match the upstream release-asset digests exactly — the files are untampered. Verify with:

```bash
sha256sum component/TDMCP.tox component/TDMCP.json
```

## Provenance and license

* Source: `TouchDesigner/TDMCP` release **1.1.55** ("Lighter logo, no browser process"), published 2026-09-28.
* **Unmodified.** The Shared Use License and the TDMCP Tool Terms of Use in the repository's
  [`LICENSE.md`](../LICENSE.md) apply to it, retained as required. Nothing here is endorsed by,
  reviewed by, or affiliated with Derivative Inc.
* `TDMCP.json` is upstream's release manifest (used by the component's **Update** button); it is kept
  next to the `.tox` so the pair can be verified together.

## How to use

1. Drop `TDMCP.tox` into the **root** of a TouchDesigner project.
2. On the component's **MCP** page, set **Active** on. Default endpoint: `http://127.0.0.1:13316/mcp`.
3. Point any MCP client at that endpoint — see [`docs/setup-advanced.md`](../docs/setup-advanced.md).

Requires TouchDesigner 2025.33070 or later per upstream; it also runs on 2025.32460 (with a
`menuDataStale` warning on `get_help`, since the menu catalog is extracted per release).

## Adding a newer version

Download the new asset, replace the two files, update the table above, and keep the commit message
carrying the new tag — that keeps the tree auditable against the release assets.

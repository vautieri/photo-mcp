# photo-mcp

Production MCP server bridging an MCP client (Claude Desktop, ChatGPT Desktop,
or any MCP-aware tool) to OpenAI's `gpt-image-1`, `gpt-image-1-mini`,
`gpt-image-1.5`, and `gpt-image-2` image-generation/editing models — with
photographer-grade quality preservation:

- Source files **never** modified, moved, or deleted
- EXIF / IPTC / XMP metadata captured and re-attached to outputs
- Source ICC color profile preserved on output
- Per-output provenance sidecar (`<output>.photo-mcp.json`) with SHA-256 of
  every source, the prompt, the model, every parameter, the SSIM score, and
  the cost
- 1–16 input images for compositing / style reference / "put this dress on
  this person" workflows
- All four model versions selectable per call; capability matrix exposed via
  the `list_models` tool

**Status**: in development. See `docs/00-executive-summary.md` for the
sponsor-facing overview, `docs/02-requirements.md` for the full requirements,
and `docs/10-process-flow.md` for the binding process.

## Install (development)

```bash
git clone <this-repo>
cd photo-mcp
pip install -e '.[test,dev]'
```

## Run (stdio mode)

```bash
export OPENAI_API_KEY=sk-...
python -m photo_mcp
```

The server reads MCP JSON-RPC frames from stdin and writes them to stdout.

## Cross-platform support

- **Linux**: tested on `ubuntu-latest` (CI)
- **Windows**: tested on `windows-latest` (CI)
- **macOS**: not yet (post-v1.0)

## Tools exposed

| Tool | Purpose |
|---|---|
| `generate` | Prompt-only image generation |
| `edit` | Edit / composite / style-reference 1–16 source images with optional alpha mask |
| `list_models` | Capability matrix per model version |
| `estimate_cost` | Cost estimate for a planned call |
| `attach_metadata` | Copy EXIF/IPTC/XMP from one file to another |

Full per-tool documentation: `docs/tools.md` (generated post-v1.0).

## Development

- `make lint` — ruff + black + mypy
- `make test` — pytest with coverage gate
- `make build` — wheel + standalone binary

See `docs/10-process-flow.md` for gate criteria and the binding process.

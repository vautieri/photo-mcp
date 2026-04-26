# Using photo-mcp from MICHAEL

photo-mcp speaks the standard Model Context Protocol over stdio, so any
MCP-aware client can use it. MICHAEL ships an MCP client (the
`services_mcp.hpp` subsystem) so registering photo-mcp is one config
entry — no MICHAEL code changes required.

The result: when the photographer chats with MICHAEL, MICHAEL has
`generate`, `edit`, `list_models`, `estimate_cost`, and `attach_metadata`
in its tool catalog right next to its built-in `Bash`, `Read`, `Write`,
etc. She types "compose the dress from `dress.png` onto the model in
`portrait.cr3`, output to `~/edits/`" and MICHAEL routes the call to
photo-mcp transparently.

## 1. Install photo-mcp

```bash
pip install -e /mnt/f/cl/mcp/photo-mcp        # from local repo
# or once published:
# pip install photo-mcp
```

Verify the binary works in isolation:

```bash
export OPENAI_API_KEY=sk-...
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{}}}' | python -m photo_mcp
```

You should see a JSON-RPC `initialize` response on stdout with
`serverInfo.name="photo-mcp"`.

## 2. Register photo-mcp in MICHAEL's settings

Add to `~/.config/michael/settings.json` (Linux/macOS) or
`%APPDATA%\michael\settings.json` (Windows):

```json
{
  "mcpServers": {
    "photo-mcp": {
      "transport": "stdio",
      "command": "python",
      "args": ["-m", "photo_mcp"],
      "env": {
        "OPENAI_API_KEY": "sk-...",
        "PHOTO_MCP_LOG_LEVEL": "info",
        "PHOTO_MCP_COST_CEILING_USD": "10.0",
        "PHOTO_MCP_ALLOWED_INPUT_ROOTS": "/home/photographer/Photos:/home/photographer/Edits",
        "PHOTO_MCP_ALLOWED_OUTPUT_ROOTS": "/home/photographer/Edits"
      },
      "filter": {
        "include": ["generate", "edit", "list_models", "estimate_cost", "attach_metadata"]
      }
    }
  }
}
```

Notes:

- The OpenAI key lives in the `env` block of MICHAEL's MCP server entry —
  not in MICHAEL's main env. This keeps photo-mcp's key scoped to its
  subprocess; MICHAEL's logs never see it (also: photo-mcp's
  `logging.redact` strips it from any log line that might carry it).
- `PHOTO_MCP_ALLOWED_*_ROOTS` is the security boundary. Restrict to the
  photographer's photo / output directories so MICHAEL cannot ask
  photo-mcp to read or write anywhere else.
- `filter.include` is optional but recommended — pins the tool set so a
  future photo-mcp release that adds new tools doesn't surface them
  until you opt in.

## 3. Restart MICHAEL

MICHAEL discovers MCP servers at startup. Restart it; in the status
banner you should see `mcp: photo-mcp (5 tools)` confirming the
connection. If the banner shows an error, run MICHAEL with
`--verbose` and check stderr for the photo-mcp startup line — most
issues are a missing `OPENAI_API_KEY` or a typo in `command`.

## 4. Use it

In MICHAEL's prompt, ask in natural language. MICHAEL will pick the
right photo-mcp tool. Example chats:

> **You**: take `~/photos/landscape_001.cr3` and replace the gray sky
> with golden-hour cumulus. Output to `~/edits/landscape_001-edited.png`.
> Keep the foreground exactly as-is.

MICHAEL will call `photo-mcp.edit` with `image=["~/photos/landscape_001.cr3"]`,
`output_dir=~/edits/`, `output_basename=landscape_001-edited.png`,
`prompt="replace gray sky with golden-hour cumulus..."`. The RAW gets
auto-decoded via rawpy with photographer-controlled de-bayer params,
EXIF + ICC profile travel through, the SSIM score lands in the result,
and a `landscape_001-edited.png.photo-mcp.json` sidecar lands next to
the output for provenance.

> **You**: how much would it cost to generate 4 portraits at 1024x1536
> high quality on gpt-image-2?

MICHAEL will call `photo-mcp.estimate_cost` and report back without
making any API calls.

## 5. Quality preservation in chat workflows

Every `edit` result includes a structured object MICHAEL displays:

- `files`: the output paths (you can copy them in chat)
- `ssim_to_image_0`: how much the AI changed pixels (1.00 = identical)
- `metadata_preserved`: whether EXIF/IPTC/XMP came through
- `color_profile_preserved`: whether your ICC profile is in the output
- `cost_usd_estimate`: this call's cost
- `session_total_usd`: running session cost

Plus the sidecar JSON with SHA-256 of every source file — your
authenticity guarantee.

## 6. Verifying authenticity later

If anyone questions whether one of your AI-edited photos is real, you
hand them:

1. The output PNG
2. The `.photo-mcp.json` sidecar next to it
3. The original source file the sidecar references

They run `sha256sum source.cr3` (or its equivalent) and compare to the
SHA-256 in the sidecar. Match → that exact file was the source. Plus
the sidecar contains the prompt, model, and every parameter the AI
saw, so the lineage is fully reproducible.

## 7. Coordinator-mode workflows

If you run MICHAEL in coordinator mode (`MICHAEL_COORDINATOR_MODE=1`),
MICHAEL spawns sub-agents that ALSO have access to photo-mcp. So you
can ask MICHAEL to "process my entire shoot folder, edit each photo
per the brief in `~/brief.md`, and write outputs to `~/edits/`." MICHAEL
spawns a sub-agent per photo, each one calls `photo-mcp.edit`, each
sub-agent's progress shows in the live agent panel (via the
AgentProgress system we built in MICHAEL today).

That's the full loop: human → MICHAEL → sub-agents → photo-mcp →
OpenAI → photographer's authenticated outputs back on disk.

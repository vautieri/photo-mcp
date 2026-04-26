# System Design Document — photo-mcp

**Version**: 0.1.0
**Date**: 2026-04-25
**Status**: Draft pending sponsor approval

---

## 1. Architecture overview

```
                        ┌─────────────────────────────────────────────────┐
   MCP client           │                   photo-mcp server              │
  (Claude Desktop,      │                                                  │
   custom CLI, etc.)    │   ┌─────────────┐                                │
        │               │   │ transport_  │  stdio (default)               │
        │  JSON-RPC     │   │   stdio.py  │  HTTP+SSE (optional)           │
   ─────┼──────────────►│◄──┤  / _http.py │                                │
        │               │   └──────┬──────┘                                │
        │               │          │                                        │
        │               │          ▼                                        │
        │               │     ┌─────────┐                                   │
        │               │     │server.py│   dispatch + tool registry        │
        │               │     └────┬────┘                                   │
        │               │          │                                        │
        │               │     tools/{generate, edit,                         │
        │               │            list_models, estimate_cost,            │
        │               │            attach_metadata}                        │
        │               │          │                                        │
        │               │          ▼                                        │
        │               │   ┌──────────────────────────────────────────┐    │
        │               │   │ openai_client.py  (wraps openai SDK)     │    │
        │               │   │  ↑ retry.py (NFR-2.1)                    │    │
        │               │   │  ↑ cost.py (FR-7.*)                      │    │
        │               │   │  ↑ models.py (capability matrix)         │    │
        │               │   └────────────────┬─────────────────────────┘    │
        │               │                    │                               │
        │               │                    ▼                               │
        │               │          ┌─────────────────────┐                  │
        │               │          │ pre/post processing │                  │
        │               │          │  metadata.py        │                  │
        │               │          │  color.py           │                  │
        │               │          │  raw.py             │                  │
        │               │          │  output.py          │                  │
        │               │          │  paths.py           │                  │
        │               │          └─────────────────────┘                  │
        │               │                                                    │
        │               │   logging.py (NFR-6.*) ─► stderr (JSON-line)      │
        │               │                                                    │
        │               └─────────────────────────────────────────────────┘
        │                                  │
        │                                  ▼ HTTPS
        │                        api.openai.com (TLS)
```

---

## 2. Language and runtime

### 2.1 Decision

**Python 3.12+** for both the MCP server core and image processing.

### 2.2 Rationale

- **Image library ecosystem**: Pillow, rawpy (LibRaw), piexif, ExifRead, scikit-image (SSIM), numpy — all mature, all cross-platform. No equivalent in TypeScript or Rust covers RAW, EXIF/IPTC/XMP round-trip, ICC profile manipulation, and SSIM with the same maturity.
- **OpenAI SDK**: official `openai` Python SDK is the most actively maintained client, with first-class streaming support and `Stream[T]` typing.
- **MCP SDK**: Anthropic's reference MCP Python SDK is stable and protocol-compliant; same code path serves stdio and HTTP+SSE transports.
- **Type checking**: `mypy --strict` covers full codebase; `pydantic` v2 for tool input/output schemas (auto-generates JSON Schema for MCP tool registration).
- **Cross-platform**: Python 3.12 ships standard on `windows-latest` and `ubuntu-latest` GitHub runners; PyInstaller produces single-file binaries for both.

### 2.3 Trade-offs accepted

- ~50–150 ms baseline interpreter startup (mitigated by long-running daemon mode)
- GIL prevents true CPU parallelism (acceptable: workload is HTTP-IO-bound; image processing per-call is single-threaded by design)
- Larger distributable than Rust/Go (offset: PyInstaller produces single-file ~50 MB; user does not need to manage a venv)

### 2.4 Pinned dependencies (top-level)

```toml
[project.dependencies]
mcp                 = ">=1.0,<2.0"      # Anthropic MCP SDK
openai              = ">=1.50,<2.0"     # OpenAI SDK
pydantic            = ">=2.5,<3.0"      # tool schemas
Pillow              = ">=10.4,<12.0"    # PNG/JPEG/WebP I/O, ICC
piexif              = ">=1.1.3,<2.0"    # EXIF read/write
xmp-toolkit         = ">=1.0,<2.0"      # XMP read/write
iptcinfo3           = ">=2.1,<3.0"      # IPTC read/write
rawpy               = ">=0.21,<1.0"     # RAW (.cr2/.cr3/.nef/.arw/.dng) decode
scikit-image        = ">=0.22,<1.0"     # SSIM / PSNR
numpy               = ">=1.26,<3.0"
httpx               = ">=0.27,<1.0"     # transitive via openai; pinned for retry control
tomli               = ">=2.0,<3.0"      # config reader (3.11+ has tomllib stdlib)
```

Test-only:
```toml
pytest              = ">=8.0,<9.0"
pytest-asyncio      = ">=0.24,<1.0"
pytest-cov          = ">=5.0,<7.0"
vcrpy               = ">=6.0,<7.0"      # HTTP cassette recording
mypy                = ">=1.10,<2.0"
ruff                = ">=0.6,<1.0"
black               = ">=24.0,<26.0"
```

All pins are tested at v1.0 release; CI matrix includes the lower bounds and the latest patch within the pin range.

---

## 3. Module dependency graph

```
            paths.py ◄─────── config.py ◄─── (env vars + TOML)
              ▲                  ▲
              │                  │
              │                  │
   metadata.py│   color.py       │   raw.py
       │      │      │           │      │
       └──────┼──────┴───────────┼──────┘
              │                  │
              ▼                  ▼
           output.py          models.py ──► (capability matrix)
              ▲                  ▲
              │                  │
              │                  │
              │            cost.py ──► retry.py ──► openai_client.py
              │                  ▲           ▲              ▲
              └──────────────────┼───────────┼──────────────┘
                                 │           │
                              tools/{generate, edit, compose, ...}
                                 ▲           ▲
                                 │           │
                              server.py
                                 ▲           ▲
                                 │           │
                  transport_stdio.py     transport_http.py
                                 ▲           ▲
                                 │           │
                                 └─── main.py (entry point)
```

The graph is acyclic. No module imports from `tools/` except `server.py`. No
module under `photo_mcp/` imports from `tests/`.

---

## 4. File layout

```
photo-mcp/
├── pyproject.toml
├── README.md
├── Makefile                       # cross-platform make targets via uv/pip
├── docs/                          # CDRL-001..016
├── src/photo_mcp/
│   ├── __init__.py                # version + public API surface
│   ├── __main__.py                # `python -m photo_mcp` entry point
│   ├── main.py                    # CLI parsing, transport selection
│   ├── config.py                  # FR-8.*
│   ├── models.py                  # FR-3.*; capability matrix
│   ├── cost.py                    # FR-7.*
│   ├── retry.py                   # NFR-2.1
│   ├── openai_client.py           # IR-2.*
│   ├── metadata.py                # FR-6.1, 6.2; QR-2..4
│   ├── color.py                   # FR-6.3, 6.4; QR-5
│   ├── raw.py                     # FR-6.6
│   ├── output.py                  # FR-5.*, IR-3.2
│   ├── paths.py                   # NFR-3.3..6
│   ├── logging.py                 # NFR-6.*
│   ├── transport_stdio.py         # FR-1.2
│   ├── transport_http.py          # FR-1.3
│   ├── server.py                  # FR-1.1, dispatch
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── generate.py            # FR-2.1
│   │   ├── edit.py                # FR-2.2 (single + multi-image; mask only when single)
│   │   ├── info.py                # FR-2.3, 2.4
│   │   └── utility.py             # FR-2.5
│   └── prices.json                # cost table; versioned
├── tests/
│   ├── unit/                      # one file per src module
│   ├── integration/
│   │   ├── cassettes/             # 12 vcr.py cassettes
│   │   └── test_*.py
│   ├── quality/
│   │   ├── test_ssim_round_trip.py
│   │   ├── test_metadata_round_trip.py
│   │   └── test_color_profile.py
│   ├── perf/
│   │   └── test_dispatch_overhead.py
│   ├── security/
│   │   ├── test_path_traversal.py
│   │   ├── test_ssrf.py
│   │   └── test_key_redaction.py
│   └── fixtures/
│       ├── photos/                # 10 reference photos
│       ├── masks/                 # alpha PNG masks
│       └── icc/                   # AdobeRGB.icc, ProPhotoRGB.icc, sRGB.icc
└── .github/workflows/ci.yml
```

---

## 5. Tool input/output schemas (illustrative)

### 5.1 `generate`

Input (via Pydantic; schema auto-emitted to MCP):
```python
class GenerateInput(BaseModel):
    prompt: str
    model: ModelId = "gpt-image-1.5"
    n: int = Field(default=1, ge=1, le=10)
    size: SizeStr = "auto"
    quality: Literal["low", "medium", "high", "auto"] = "auto"
    output_format: Literal["png", "jpeg", "webp"] = "png"
    output_compression: int | None = None  # 0..100; jpeg/webp only
    background: Literal["opaque", "auto", "transparent"] = "auto"
    response_format: Literal["b64_json", "url"] = "b64_json"
    moderation: Literal["auto", "low"] = "auto"
    stream: bool = False
    partial_images: int = 0  # 0..3
    output_dir: Path
    output_basename: str
    overwrite: bool = False
    save_partial_images: bool = False
```

Output:
```python
class GenerateOutput(BaseModel):
    files: list[Path]                           # one entry per image (n)
    model: ModelId
    revised_prompts: list[str] | None           # if API returned revisions
    usage: ApiUsage
    cost_usd_estimate: float
    request_ms: int
```

### 5.2 `edit`

Single tool covers the full edit endpoint surface: 1 image (with optional
mask) up through 16-image compositing / style reference / "put this dress
on this person" workflows.

Input:
```python
class EditInput(BaseModel):
    prompt: str = Field(max_length=32_000)
    image: list[Path] = Field(min_length=1, max_length=16)  # 1..16 source images
    mask: Path | None = None                                # only valid with len(image)==1
    model: ModelId = "gpt-image-2"                          # default to highest fidelity
    n: int = Field(default=1, ge=1, le=4)
    size: SizeStr = "auto"
    quality: Literal["low", "medium", "high", "auto"] = "high"
    output_format: Literal["png", "jpeg", "webp"] = "png"
    output_compression: int | None = None
    input_fidelity: Literal["high", "low"] = "high"         # ignored on gpt-image-2
    response_format: Literal["b64_json", "url"] = "b64_json"
    moderation: Literal["auto", "low"] = "auto"
    stream: bool = False
    partial_images: int = 0
    preserve_metadata: bool = True                          # attached from image[0]
    preserve_color_profile: bool = True                     # attached from image[0]
    raw_params: RawParams | None = None                     # applied to any RAW inputs
    pre_resize_to: SizeStr | None = None                    # opt-in; applied per-input
    output_dir: Path
    output_basename: str
    overwrite: bool = False

    @model_validator(mode="after")
    def _check_mask(self) -> "EditInput":
        if self.mask is not None and len(self.image) != 1:
            raise ValueError(
                "mask requires exactly one source image; "
                "for compositing/style-reference workflows omit the mask"
            )
        return self
```

For multi-image calls (len(image)>1), the photographer's primary source image
is **image[0]** by convention — its EXIF/IPTC/XMP and ICC profile are the
source-of-truth that gets re-attached to the output when `preserve_metadata`
or `preserve_color_profile` is true. The remaining images (`image[1..]`) are
treated as references / style donors / composite elements; their metadata is
not preserved (no obvious mapping when 16 sources collapse to one output).

Output:
```python
class EditOutput(BaseModel):
    files: list[Path]
    model: ModelId
    ssim_to_image_0: float | None               # SSIM vs image[0]; meaningful for single-image high-fidelity edits
    metadata_preserved: bool
    metadata_source: Path | None                # which image's metadata was preserved (image[0] or None)
    color_profile_preserved: bool
    warnings: list[str]                         # color-space drift, multi-image limits, etc.
    usage: ApiUsage
    cost_usd_estimate: float
    request_ms: int
```

`attach_metadata` takes `source: Path, target: Path, fields: list[str]`.

### 5.3 Provenance sidecar (QR-10..12)

For every output the server writes, it ALSO writes a sibling JSON file at
`<output_path>.photo-mcp.json`. This is the provable audit trail that
underwrites the photographer's "you could pull the original and see it's
not fake" requirement.

Schema (v0.1.0):

```json
{
  "$schema": "https://photo-mcp.example/schemas/sidecar/v0.1.0",
  "version": "0.1.0",
  "created_at": "2026-04-25T14:32:01.234Z",
  "tool": "edit",
  "model": "gpt-image-2",
  "endpoint": "edits",
  "prompt": "replace the cloudy sky with golden-hour cumulus, preserve the foreground",
  "parameters": {
    "n": 1,
    "size": "auto",
    "quality": "high",
    "output_format": "png",
    "input_fidelity": "high",
    "moderation": "auto",
    "preserve_metadata": true,
    "preserve_color_profile": true
  },
  "sources": [
    {
      "path": "/Users/photographer/exports/landscape_001.tif",
      "sha256": "a3f9c7e2…",
      "size_bytes": 24193847,
      "mime": "image/tiff"
    },
    {
      "path": "/Users/photographer/refs/skies/golden_005.png",
      "sha256": "b8d4f1c9…",
      "size_bytes": 8421044,
      "mime": "image/png"
    }
  ],
  "mask": null,
  "output": {
    "path": "/Users/photographer/exports/landscape_001-edited.png",
    "sha256": "c2e7a8f1…",
    "size_bytes": 11203942
  },
  "ssim_to_image_0": 0.9742,
  "metadata_preserved_from": "/Users/photographer/exports/landscape_001.tif",
  "color_profile_preserved_from": "/Users/photographer/exports/landscape_001.tif",
  "color_profile_name": "AdobeRGB1998",
  "warnings": [],
  "cost_usd_estimate": 0.0418,
  "request_ms": 4127
}
```

Sidecar guarantees:

1. **Atomic with the output**: written via tmp+rename to the same
   directory; if the write fails after the output is renamed, the
   server unlinks the output to avoid an output-without-sidecar
   orphan. Tested in `tests/quality/test_sidecar_atomicity.py`.

2. **SHA-256 of every source**: lets the photographer years later run
   `sha256sum landscape_001.tif` and verify against the sidecar — proof
   the AI didn't fabricate from nothing, that exact file was the source.

3. **Parameters captured verbatim**: every knob that was set is recorded.
   No "we used some defaults" — defaults are recorded as their concrete
   values.

4. **Distinct from EXIF**: an EXIF `Software` tag is also written into the
   output (QR-12), but the sidecar carries the full audit trail because
   EXIF cannot fit `prompt` reliably and is brittle across format
   conversions.

The sidecar is forward-compatible: future versions add fields without
breaking older readers (v0.2.0 readers ignore unknown keys; consumers
should check `version` and degrade gracefully).

---

## 6. State machines

### 6.1 Retry / backoff (NFR-2.1, 2.2)

```
     [Idle]
        │ tool call
        ▼
   [Sending request]
        │           ┌─ HTTP 2xx ──► [Success] ──► return
        │
        ├─ HTTP 401/403/404/422 ──► [Permanent error] ──► raise structured ER-*
        │
        ├─ HTTP 429/500/502/503/504 ──► [Backoff]
        │                                   │
        │                                   │ wait = min(60s, 1s × 2^attempt × jitter)
        │                                   │ attempt += 1; max 5
        │                                   │
        │                                   ▼
        │                              [Sending request] ──► (loop)
        │
        └─ network error ──► [Backoff] (same)
```

Jitter is uniform ±25% to avoid thundering-herd retries when many calls fire
in parallel against a rate-limited account.

### 6.2 Streaming progress

```
   [Open stream]
        │
        ▼
   [Receive event]
        │
        ├─ event=image.partial: emit MCP tools/progress with partial b64
        │       │ (and write to disk if save_partial_images=true)
        │       ▼
        │   [Receive event]  (loop)
        │
        ├─ event=image.completed: write final image, emit final tool result
        │
        └─ event=error: map to ER-*, abort stream, emit isError=true
```

### 6.3 Cost ceiling (FR-7.4)

```
   [Tool call]
        │
        ▼
   [Estimate cost(call)]
        │
        ▼
   [Read session_total]
        │
        ▼
   [Would exceed ceiling?]
        │
        ├─ No  ──► [Send to OpenAI] ──► add billed cost to session_total ──► return
        │
        └─ Yes ──► [Refuse] ──► return ER-7 cost_ceiling
```

`session_total` is in-memory; persisted to a per-session JSONL audit log if
`--cost-audit` is enabled.

---

## 7. Threading model

The server is **single-threaded** for tool dispatch (no concurrent tool calls
inside one request), with one execution context per MCP transport channel:

- **stdio mode**: a single async event loop processes one tool call at a time
  (MCP protocol allows concurrent calls but the photographer use case is
  inherently sequential, and we want determinism for cost ceiling math)
- **HTTP+SSE mode**: one async coroutine per active SSE client; each
  coroutine has its own session_total counter

Streaming is async (`AsyncOpenAI` client + `async for event in stream`); no
threading for SSE consumption.

Image preprocessing (RAW decode, ICC extraction, SSIM compute) is CPU-bound
but bounded — runs synchronously on the dispatch coroutine. If a call's
preprocessing exceeds 5 s, the operation is logged for performance review.

---

## 8. Error handling strategy

All exceptions inside a tool call are caught at the dispatch boundary
(`server.dispatch_tool_call`). The catch ladder:

1. Pydantic ValidationError on input → ER-3 unsupported_parameter or
   structured-error mapping
2. `paths.PathNotAllowed` / `paths.PathOutsideRoot` → ER (path safety)
3. `openai.AuthenticationError` → ER-6 auth_error (no key in message)
4. `openai.APIStatusError` → mapped via `retry.classify(...)` to either
   retry loop or ER (permanent)
5. `openai.APIConnectionError` / `httpx.NetworkError` → retry loop
6. `cost.CeilingExceeded` → ER-7 cost_ceiling
7. `Exception` (uncaught) → ER-8 internal_error; full traceback to stderr
   via structured logger; never to MCP client

---

## 9. Configuration loading order

1. Built-in defaults (in `config.py`)
2. TOML file at `$XDG_CONFIG_HOME/photo-mcp/config.toml` or
   `%APPDATA%\photo-mcp\config.toml`
3. Environment variables (`OPENAI_API_KEY`, `PHOTO_MCP_*`)
4. CLI flags (`--allowed-roots`, `--log-level`, etc.)
5. Per-tool-call arguments (highest precedence)

Each later layer can override the previous; config file path is itself
configurable via `PHOTO_MCP_CONFIG`.

---

## 10. Logging

### 10.1 Format

One JSON object per line on stderr:
```json
{"ts":"2026-04-25T14:32:01.234Z","level":"info","call_id":"c-12","event":"openai_request","model":"gpt-image-1.5","endpoint":"edits","input_bytes":2418293,"latency_ms":4127,"output_bytes":1204932,"cost_usd_estimate":0.0418}
```

Mandatory fields: `ts`, `level`, `event`. All other fields are event-specific.

### 10.2 Redaction

Every log emission goes through `logging.redact()` which strips:
- Any string starting with `sk-` (OpenAI key prefix) — replaced with `sk-***`
- Any field named `api_key`, `Authorization`, `auth`, `token`, `secret`

Tested in `tests/security/test_key_redaction.py`.

---

## 11. Cassette strategy (for CI without API key)

Production code paths use `httpx.AsyncClient` via the OpenAI SDK. Tests use
`vcrpy` to record real interactions on the developer's machine (with
sponsor's key) and replay them in CI.

Cassette naming: `tests/integration/cassettes/<endpoint>_<model>_<scenario>.yaml`
(e.g., `edits_gpt-image-1.5_preserve_high.yaml`).

Recorded with `record_mode="once"`. Re-record requires deleting the cassette
file. Cassettes are checked into the repo; key is filtered out via vcr's
`filter_headers=["authorization"]`.

12 minimum cassettes (3 endpoints × 4 models). Additional cassettes for:
- `input_fidelity=low` on each 1.x model (3)
- transparent background on each 1.x model (3)
- Streaming partial_images=2 on each model (4)

Total target: 22 cassettes.

---

## 12. Cross-platform considerations

| Concern | Linux | Windows | macOS (post-v1.0) |
|---|---|---|---|
| Path separators | `/` | `\` (handled via `pathlib`) | `/` |
| EOL in JSON-RPC frames | `\n` | `\n` (explicit; not `\r\n`) | `\n` |
| Config dir | `~/.config/photo-mcp/` | `%APPDATA%\photo-mcp\` | `~/Library/Application Support/photo-mcp/` |
| `OPENAI_API_KEY` | env | env | env |
| RAW decoding via rawpy | LibRaw via wheel | LibRaw via wheel | LibRaw via wheel (post-v1.0 verify) |
| Standalone binary | PyInstaller ELF | PyInstaller PE | PyInstaller Mach-O (post-v1.0) |
| Signal handling | SIGTERM, SIGINT | SIGINT (Ctrl+C); WM_CLOSE in console | SIGTERM, SIGINT |

---

## 13. Backward / forward compatibility

The server pins the OpenAI SDK to `>=1.50,<2.0`. When OpenAI bumps the SDK
major or adds a new image model:

1. CI fails on cassette mismatch (existing tests catch the drift)
2. Engineer rev's the SDK pin in a feature branch
3. Re-records cassettes against the new SDK
4. Expands the capability matrix in `models.py`
5. Releases as `0.X+1.0`

The MCP protocol version is also pinned (2024-11-05). Any breaking MCP
protocol change is a major-version bump for photo-mcp.

---

## 14. Out-of-scope confirmations

These are explicitly NOT designed in this v1.0:

- Multi-user accounts / per-user API keys
- Image upload to cloud storage
- Auto-tone / auto-sharpen / denoise
- Other providers (Google Imagen, Stability, Adobe Firefly)
- Mobile clients
- macOS at v1.0 (deferred to +30 days)

These are tracked in the Risk Register as items to revisit if scope expands.

---

## 15. Sponsor approval block

| Field | Value |
|---|---|
| Approver | _pending_ |
| Date | |
| Notes | |

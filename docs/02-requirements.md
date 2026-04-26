# Requirements Document — photo-mcp

**Version**: 0.1.0
**Date**: 2026-04-25
**Status**: Draft pending sponsor approval

---

## Conventions

- Priority levels follow RFC 2119: **MUST** (hard requirement), **SHOULD** (strong recommendation, deviation requires logged rationale), **MAY** (optional)
- Verification methods (per IEEE 1012):
  - **T**est — automated test asserts the requirement
  - **I**nspection — visual / manual inspection of code or artifact
  - **D**emonstration — observed live operation
  - **A**nalysis — derived from other artifacts or measurements
- Each requirement traces to a verification activity in the V&V Plan (doc 06)
- Each requirement traces to one or more WBS work packages (doc 03)

---

## 1. Functional Requirements (FR)

### 1.1 MCP server lifecycle

| ID | Priority | Description | Verification | Source |
|---|---|---|---|---|
| FR-1.1 | MUST | The server SHALL implement MCP protocol version 2024-11-05, including `initialize`, `initialized`, `tools/list`, `tools/call`, `ping`, `shutdown` methods | T | MCP spec |
| FR-1.2 | MUST | The server SHALL support stdio transport (read JSON-RPC frames from stdin, write to stdout) for desktop-client integration | T, D | Charter §4 |
| FR-1.3 | SHOULD | The server SHALL support HTTP+SSE transport bound to a configurable address for multi-client / remote access | T | Charter §4 |
| FR-1.4 | MUST | The server SHALL exit cleanly on stdin EOF (stdio mode) within 5 seconds, releasing all resources | T | Operational |
| FR-1.5 | MUST | The server SHALL handle SIGTERM/SIGINT (POSIX) and Ctrl+C / `WM_CLOSE` (Windows) by initiating graceful shutdown | T | Cross-platform |

### 1.2 Tool catalog

The server SHALL expose at minimum the following tools, each implementing the
named OpenAI endpoint with full parameter coverage:

| ID | Priority | Tool name | Maps to | Description |
|---|---|---|---|---|
| FR-2.1 | MUST | `generate` | `POST /v1/images/generations` | Prompt-only image generation |
| FR-2.2 | MUST | `edit` | `POST /v1/images/edits` | Edit / composite / style-reference 1–16 source images with a prompt; optional alpha mask (single-image case only) defines edit region. Multi-image use cases include "put this dress on this person", style reference from one image applied to another, and gift-basket-style compositions |
| FR-2.3 | MUST | `list_models` | n/a | Returns the static list of supported models with their capability matrix |
| FR-2.4 | MUST | `estimate_cost` | n/a | Computes a dollar-cost estimate for a given (model, parameters) tuple before the user calls `generate`/`edit` |
| FR-2.5 | SHOULD | `attach_metadata` | n/a | Re-attach EXIF/IPTC/XMP metadata from a source file to a target file (used internally; exposed for explicit user invocation) |

### 1.3 Model parameter coverage

For every tool that maps to an OpenAI endpoint, the server SHALL expose every
parameter documented for the selected model with no silent dropping. Missing
optional parameters are filled with the model's documented default; passing
an unsupported parameter for a given model SHALL return a structured error
naming the unsupported parameter and the model that doesn't support it
(see ER-3.x).

| ID | Priority | Parameter | Models supporting | Notes |
|---|---|---|---|---|
| FR-3.1 | MUST | `model` | all | Enum: `gpt-image-1`, `gpt-image-1-mini`, `gpt-image-1.5`, `gpt-image-2` |
| FR-3.2 | MUST | `prompt` | all | UTF-8 string up to 32,000 characters per OpenAI; the server SHALL refuse longer prompts with a structured error naming the limit |
| FR-3.3 | MUST | `n` | all | Integer ≥ 1 |
| FR-3.4 | MUST | `size` | all (gpt-image-2 supports more values) | Enum varies per model — see `list_models` matrix |
| FR-3.5 | MUST | `quality` | all | Enum: `low`, `medium`, `high`, `auto` |
| FR-3.6 | MUST | `output_format` | all | Enum: `png`, `jpeg`, `webp` |
| FR-3.7 | MUST | `output_compression` | gpt-image-2 (jpeg/webp only) | Integer 0–100 |
| FR-3.8 | MUST | `background` | gpt-image-1.x only | Enum: `opaque`, `auto`, `transparent` (1.x); `opaque`, `auto` (2). Server SHALL reject `transparent` for gpt-image-2 with a clear error |
| FR-3.9 | MUST | `response_format` | all | Enum: `b64_json` (default), `url` |
| FR-3.10 | MUST | `moderation` | all | Enum: `auto`, `low` |
| FR-3.11 | MUST | `stream` | all | Boolean |
| FR-3.12 | MUST | `partial_images` | all (only meaningful with stream=true) | Integer 0–3 |
| FR-3.13 | MUST | `input_fidelity` | gpt-image-1, gpt-image-1-mini, gpt-image-1.5; **NOT** gpt-image-2 (always high) | Enum: `high`, `low`. Server SHALL reject for gpt-image-2 with a message naming the limitation |
| FR-3.14 | MUST | `image` (edit only) | all | 1–16 local file paths or base64-encoded image data; PNG / WebP / JPG accepted; ≤50 MB per file. The server SHALL refuse calls with `>16` images naming the limit |
| FR-3.15 | MUST | `mask` (edit only) | all | Local file path to a PNG-with-alpha or base64-encoded PNG; same size and format as the source image. Mask is meaningful only when there is exactly one source `image` — the server SHALL refuse `mask` together with multiple `image` entries since masking only applies to a single base image |

### 1.4 Streaming

| ID | Priority | Description | Verification |
|---|---|---|---|
| FR-4.1 | MUST | When `stream=true`, the server SHALL return progress events to the MCP client as they arrive from the OpenAI stream, preserving partial-image frames in `partial_images` mode | T |
| FR-4.2 | MUST | Streaming events MUST be delivered to the MCP client as `tools/progress` notifications (or as multi-content-block tool result if the client doesn't support progress events) | T |
| FR-4.3 | SHOULD | Partial frames SHOULD be persisted to disk under a user-specified `output_dir` only when the user explicitly requests it (`save_partial_images=true`); otherwise they are discarded | T |

### 1.5 Workflow ergonomics

| ID | Priority | Description | Verification |
|---|---|---|---|
| FR-5.1 | MUST | The user SHALL specify the output directory and base filename per call. The server SHALL NOT pick a directory or invent a filename | T |
| FR-5.2 | MUST | When `n>1`, the server SHALL append a deterministic suffix (`-001`, `-002`, …) to the user-specified base filename, zero-padded to the width of `n` | T |
| FR-5.3 | MUST | If a target output path already exists, the server SHALL fail with a clear error listing the conflicting path, UNLESS the user has set `overwrite=true` | T |
| FR-5.4 | SHOULD | The server SHOULD return per-output paths in the tool result so the parent agent can reference them downstream | T |

### 1.6 Quality-preservation features

| ID | Priority | Description | Verification |
|---|---|---|---|
| FR-6.1 | MUST | Prior to upload, the server SHALL extract EXIF, IPTC, and XMP metadata from the source image and retain it in memory for re-attachment | T |
| FR-6.2 | MUST | After a successful edit/compose, the server SHALL re-attach the captured metadata to the output file IF the user requested `preserve_metadata=true` (default: true for `edit`/`compose`, false for `generate` since there's no source) | T |
| FR-6.3 | MUST | The server SHALL detect and record the source ICC color profile and embed it into PNG/JPEG outputs IF the user requested `preserve_color_profile=true` (default: true for `edit`/`compose`) | T |
| FR-6.4 | MUST | The server SHALL log a warning in the tool result if the source color space is not sRGB and the user did not request `preserve_color_profile=true`, because OpenAI returns sRGB regardless | T |
| FR-6.5 | MUST | The server SHALL refuse to silently downscale a source image that is already ≤50 MB. If `>50 MB`, the server SHALL return a structured error and offer a recommended downscale path the user can opt into via `pre_resize_to=…` | T |
| FR-6.6 | SHOULD | For RAW input formats (`.cr2`, `.cr3`, `.nef`, `.arw`, `.dng`, etc.), the server SHALL pre-convert via rawpy with photographer-controlled de-bayer parameters (camera-matrix, no_auto_bright, output_bps=16) and warn that lossless RAW capture is converted | T |
| FR-6.7 | MUST | For PNG output, the server SHALL verify the file by re-decoding it after write and asserting byte length matches the OpenAI response payload | T |
| FR-6.8 | SHOULD | For round-trip identity-preserving edits (`input_fidelity=high` on 1.x, or any edit on gpt-image-2), the server SHALL compute SSIM between source and output and include it in the tool result so the photographer can see how much the model changed pixels | T |

### 1.7 Cost transparency

| ID | Priority | Description | Verification |
|---|---|---|---|
| FR-7.1 | MUST | Every tool result SHALL include `usage` (token counts) and `cost_usd_estimate` fields | T |
| FR-7.2 | MUST | `estimate_cost` tool SHALL return the same dollar estimate the server would produce for an actual call with the given parameters | T |
| FR-7.3 | MUST | Cost estimation SHALL be sourced from a versioned price table (file: `prices.json`) so updates are a one-line config change | I |
| FR-7.4 | SHOULD | If a user-configured `session_cost_ceiling_usd` is set and the next call would push cumulative session cost over it, the server SHALL refuse the call and return a structured error with the running total | T |

### 1.8 Configuration

| ID | Priority | Description | Verification |
|---|---|---|---|
| FR-8.1 | MUST | API key SHALL be read from `OPENAI_API_KEY` env var (no other location) | I |
| FR-8.2 | MUST | The server SHALL fail-fast on startup if `OPENAI_API_KEY` is missing or empty | T |
| FR-8.3 | MUST | The server SHALL never log the API key in any form (full or prefix beyond first 4 chars) | I, T |
| FR-8.4 | SHOULD | A startup config block SHALL be loaded from `$XDG_CONFIG_HOME/photo-mcp/config.toml` (Linux/Mac) or `%APPDATA%\photo-mcp\config.toml` (Windows) with default `model`, `quality`, `output_format`, `session_cost_ceiling_usd` | T |
| FR-8.5 | SHOULD | All config values SHOULD be overridable per tool call via the tool's `arguments` object | T |

---

## 2. Non-Functional Requirements (NFR)

### 2.1 Performance

| ID | Priority | Description | Verification |
|---|---|---|---|
| NFR-1.1 | MUST | Tool dispatch overhead (MCP request received → first OpenAI HTTP byte sent) SHALL be ≤ 250 ms at the 95th percentile on a reference machine (4-core x86_64, 8 GB RAM, Linux) | T |
| NFR-1.2 | MUST | Output write + integrity verification SHALL complete in ≤ 1 s for a 4096×4096 PNG on the reference machine | T |
| NFR-1.3 | SHOULD | Streaming partial frames SHOULD be delivered to the MCP client within 100 ms of arrival from the OpenAI stream | T |

### 2.2 Reliability

| ID | Priority | Description | Verification |
|---|---|---|---|
| NFR-2.1 | MUST | Transient HTTP 429/500/502/503/504 errors from OpenAI SHALL be retried with exponential backoff (initial 1s, factor 2, jitter ±25%, max 5 retries, max total wait 60s) | T |
| NFR-2.2 | MUST | Permanent errors (HTTP 400, 401, 403, 404, 413, 422) SHALL NOT be retried; SHALL be returned immediately as a structured error | T |
| NFR-2.3 | MUST | A single failed tool call SHALL NOT crash the server process. Worker-thread exceptions SHALL be caught and returned as a structured error response | T |
| NFR-2.4 | MUST | The server SHALL operate correctly when stdout is line-buffered or fully-buffered (handled by explicit flush after every JSON-RPC frame) | T |

### 2.3 Security

| ID | Priority | Description | Verification |
|---|---|---|---|
| NFR-3.1 | MUST | The OpenAI API key SHALL be transmitted only over HTTPS to `api.openai.com` (TLS verification enabled) | I, T |
| NFR-3.2 | MUST | The server SHALL NOT include the API key in any error message, log line, or tool result | T |
| NFR-3.3 | MUST | Local file paths supplied by the MCP client SHALL be canonicalized and rejected if they traverse outside the user's home directory OR a configured `allowed_input_roots` list | T |
| NFR-3.4 | SHOULD | The server SHOULD support reading paths from a `--allowed-roots` CLI flag (list of dirs) so untrusted clients cannot read arbitrary files | T |
| NFR-3.5 | MUST | Output paths SHALL be similarly restricted to a configured `allowed_output_roots` list (defaults to user's home directory) | T |
| NFR-3.6 | MUST | The server SHALL refuse to follow symlinks for input files unless `--follow-symlinks` is set explicitly | T |
| NFR-3.7 | MUST | Any HTTP requests other than to `api.openai.com` SHALL be refused (no SSRF risk to internal networks) | T |

### 2.4 Portability

| ID | Priority | Description | Verification |
|---|---|---|---|
| NFR-4.1 | MUST | The full test suite SHALL pass on `windows-latest` and `ubuntu-latest` GitHub-hosted runners | T |
| NFR-4.2 | MUST | All file paths SHALL use `pathlib.Path` (or equivalent) — no hard-coded `/` or `\` | I |
| NFR-4.3 | MUST | Newlines in JSON-RPC framing SHALL use `\n` regardless of platform (per MCP spec) | I, T |
| NFR-4.4 | SHOULD | macOS support SHALL be added within 30 days of v1.0 release; the test matrix SHALL extend to `macos-latest` at that point | T |

### 2.5 Maintainability

| ID | Priority | Description | Verification |
|---|---|---|---|
| NFR-5.1 | MUST | Production code coverage (lines) SHALL be ≥ 90% across modules under `photo_mcp/` | T |
| NFR-5.2 | MUST | All public functions and classes SHALL have type annotations checked by `mypy --strict` | T |
| NFR-5.3 | MUST | Lint and format checks (`ruff`, `black`) SHALL be clean (zero warnings) | T |
| NFR-5.4 | MUST | The server SHALL be packaged as a `pip`-installable wheel and as a PyInstaller-built single-file executable for Windows + Linux | I, D |

### 2.6 Observability

| ID | Priority | Description | Verification |
|---|---|---|---|
| NFR-6.1 | MUST | The server SHALL emit structured JSON logs to stderr (one JSON object per line), keyed by call_id, model, endpoint, latency_ms, output_bytes, cost_usd_estimate | T |
| NFR-6.2 | SHOULD | A `--log-level` CLI flag SHOULD select among `debug`, `info`, `warning`, `error` | I |
| NFR-6.3 | MUST | The server SHALL never write to stdout outside of MCP JSON-RPC frames (stdout is the protocol channel; logs go to stderr) | T |

---

## 3. Interface Requirements (IR)

### 3.1 MCP interface

| ID | Priority | Description | Verification |
|---|---|---|---|
| IR-1.1 | MUST | All tool input schemas SHALL be valid JSON Schema Draft 2020-12 | T |
| IR-1.2 | MUST | Tool descriptions SHALL state, in plain English, which models support which parameters and link to the relevant OpenAI doc URL | I |
| IR-1.3 | MUST | Tool results SHALL be MCP `text` or `image` content blocks; errors SHALL set `isError: true` and include a structured error payload | T |
| IR-1.4 | SHOULD | When the user calls a tool with a parameter unsupported by the chosen model, the error message SHALL name the parameter and the model | T |

### 3.2 OpenAI interface

| ID | Priority | Description | Verification |
|---|---|---|---|
| IR-2.1 | MUST | The server SHALL use the official `openai` Python SDK ≥ 1.x for all API calls | I |
| IR-2.2 | MUST | The server SHALL pin the SDK to a specific minor version in `pyproject.toml` to avoid silent API drift | I |
| IR-2.3 | MUST | When the SDK signature changes (parameter added/removed), the test cassettes SHALL re-record and the parameter matrix SHALL be re-verified before release | I |

### 3.3 Filesystem interface

| ID | Priority | Description | Verification |
|---|---|---|---|
| IR-3.1 | MUST | The server SHALL accept input paths as absolute paths or relative-to-CWD paths, canonicalized via `Path.resolve(strict=True)` | T |
| IR-3.2 | MUST | Output writes SHALL use the tmp+rename atomic pattern (write to `<dest>.tmp`, fsync, rename to `<dest>`) | T |
| IR-3.3 | SHOULD | For RAW input handling, the server SHOULD use `rawpy` (LibRaw bindings) with parameters specified via the tool's `raw_params` object | T |

---

## 4. Quality Preservation Requirements (QR)

These are photographer-specific and the principal differentiator of this server.

The sponsor's stated aesthetic principle:

> "Make it seem almost unreal — but you could pull the original and see it's not fake."

That is operationalized as: **the original is never altered, never moved, never overwritten; every output ships with provable provenance back to its source(s); the photographer can always reach into the file system and find the un-AI'd source.**

| ID | Priority | Description | Verification |
|---|---|---|---|
| QR-1 | MUST | For `edit` calls with `input_fidelity=high` on gpt-image-1.x, source-vs-output SSIM SHALL average ≥ 0.95 across a curated set of 10 reference photos in a controlled re-render-only test (no transformative prompt) | T |
| QR-2 | MUST | EXIF DateTime, Make, Model, LensModel, FocalLength, FNumber, ExposureTime, ISO, GPSLatitude, GPSLongitude, Copyright, Artist SHALL round-trip through `edit`/`compose` when `preserve_metadata=true` | T |
| QR-3 | MUST | XMP `dc:rights`, `dc:creator`, `dc:title`, `dc:description` SHALL round-trip when `preserve_metadata=true` | T |
| QR-4 | SHOULD | IPTC `By-line`, `By-line Title`, `Caption-Abstract`, `Copyright Notice` SHOULD round-trip when `preserve_metadata=true` | T |
| QR-5 | MUST | A non-sRGB source SHALL trigger a warning unless `preserve_color_profile=true` is set; with that flag, the output SHALL embed the source ICC profile | T |
| QR-6 | MUST | The server SHALL NOT auto-recompress, auto-resize, or auto-color-correct any source image | T, I |
| QR-7 | MUST | When `output_format=png`, the output PNG SHALL pass `pngcheck`-equivalent integrity verification (or `Pillow`'s `verify()` method) | T |
| QR-8 | SHOULD | The server SHOULD warn the user if they pass `output_format=jpeg` (lossy) on an `edit` operation, since iterative edits will accumulate JPEG artifacts (matches the public complaint about iterative degradation) | T |
| QR-9 | MUST | The server SHALL NEVER modify, move, rename, or delete a source image file. Every operation reads the source; outputs go to a new path. If the user passes a source path equal to a target path, the server SHALL refuse with ER-5 output_exists | T |
| QR-10 | MUST | For each output file the server SHALL write a sibling provenance sidecar `<output>.photo-mcp.json` containing: `version`, `created_at` (ISO-8601 UTC), `model`, `endpoint`, `prompt`, `parameters` (full record of the call args), `sources` (list of `{path, sha256, size_bytes}` for every input image), `mask` (path + sha256, if any), `ssim_to_image_0` (when computed), `metadata_preserved_from`, `color_profile_preserved_from`, `warnings`, and `cost_usd_estimate`. The sidecar makes "pull the original and prove it's not fake" literally true on disk | T |
| QR-11 | MUST | The provenance sidecar SHALL be written atomically (tmp + rename) to the same directory as the output file, so a sidecar without an output (or vice versa) cannot persist after a crash | T |
| QR-12 | SHOULD | When `output_format=png|jpeg|webp`, the server SHOULD embed a `Software` EXIF tag identifying `photo-mcp <version>` and the model used (e.g. `gpt-image-2`), so AI provenance is visible to any standard EXIF reader without opening the sidecar | T |
| QR-13 | SHOULD | The server SHOULD support a future-state C2PA (Content Provenance and Authenticity) manifest as a v1.1+ enhancement; v1.0 sidecar carries the same information in JSON form, ready to be re-emitted as a C2PA manifest when the dependency stack supports it | I |

---

## 4a. Capability Acceptance Scenarios (WS)

These are **capability proof-points**, not a workflow menu. They are named
end-to-end examples the server is verified to handle so we have evidence
the underlying capabilities work. The photographer is free to ask the
server for anything that uses any combination of these capabilities (or
extends them with novel prompts) — the WS-* set is illustrative, not
prescriptive. If a capability passes its WS test, then any prompt that
exercises that capability is supported, not just the example used in
the test.

Each WS gets at least one cassette + assertion in the test suite. They
are how we prove "the design serves the photographer's actual job"
beyond per-feature unit tests.

| ID | Priority | Workflow | Acceptance criteria |
|---|---|---|---|
| WS-1 | MUST | **Sky replacement (single image, prompt-driven)** — Photographer hands a landscape with a flat / overcast sky and a prompt like "replace the sky with golden-hour cumulus, keep the foreground exactly as-is, match the warm light onto the existing scene." | Output preserves the foreground (SSIM on the lower 60% of the frame ≥ 0.97 against source), sky region clearly transformed, EXIF + ICC carried, sidecar written |
| WS-2 | MUST | **Two-photo merge (sky from photo A, foreground from photo B)** — Photographer hands two images and a prompt like "use the sky from image 1, the foreground from image 2, blend the lighting so the merge looks like a single capture." | `edit` accepts both, `image[0]`'s metadata preserved, output convincing, sidecar lists both sources with their SHA-256s |
| WS-3 | MUST | **Three-photo merge (e.g., two model shots + one location plate)** — Photographer wants the model from one shot, the pose from another, dropped into the location of the third. | `edit` with 3 images succeeds; result is a single coherent frame; sidecar carries all three sources |
| WS-4 | MUST | **Atmospheric addition (rainbow, sun rays, snow, fog)** — Photographer hands an existing photo with prompt "add a rainbow arching from the left tree to the lake," with original detail untouched elsewhere. | Foreground SSIM ≥ 0.95, addition visible, no other unintended changes; warnings list any drift |
| WS-5 | MUST | **"Put this dress on this person"** — Two images: a person and a clothing reference. Prompt directs the model to replace the person's clothing with the reference garment, matching lighting and pose. | `edit` with 2 images; output preserves identity (face SSIM in face-detected region ≥ 0.92 vs source person) and clothing visually matches reference |
| WS-6 | SHOULD | **Color/mood reinterpretation while preserving structure** — Photographer asks for "twilight mood, slightly cooler shadows, warmer highlights" without compositional change. | Output dimensions identical, no objects added/removed, color palette shifted per prompt, sidecar shows the shift |
| WS-7 | MUST | **Authenticity audit** — Given any output produced by this server, the photographer can read the sidecar JSON and recover (a) every source path, (b) the prompt used, (c) the model, and (d) verify each source by comparing its SHA-256 to the file currently at the recorded path. | Sidecar JSON is complete, parsable, and the SHA-256s match the unchanged source files |

Capability proof-points WS-1 through WS-5 are gated on Phase 1.4 sponsor
acceptance. Failure on any MUST proof-point blocks v1.0 release.

These are deliberately distinct from the unit / cassette tests (which
prove the API surface works). They prove the *capabilities the
photographer needs* work end-to-end with the originals untouched and
the output clearly attributable. The photographer's actual day-to-day
calls will be open-ended natural-language prompts — these tests just
confirm the building blocks are in place.

---

## 5. Error Requirements (ER)

| ID | Priority | Description | Verification |
|---|---|---|---|
| ER-1 | MUST | All errors returned to the MCP client SHALL be structured: `{type, message, retriable, hint?}` | T |
| ER-2 | MUST | OpenAI HTTP error responses SHALL be mapped to ER-1 form, preserving the OpenAI `code` and `message` fields | T |
| ER-3 | MUST | Unsupported parameter for a chosen model: `{type: "unsupported_parameter", parameter, model, supported_models}` | T |
| ER-4 | MUST | Source file too large: `{type: "input_too_large", path, size_bytes, max_bytes: 52428800}` | T |
| ER-5 | MUST | Output path collision: `{type: "output_exists", path}` (unless `overwrite=true`) | T |
| ER-6 | MUST | API key missing/invalid: `{type: "auth_error", message}` (no key contents in message) | T |
| ER-7 | MUST | Cost ceiling exceeded: `{type: "cost_ceiling", session_total_usd, ceiling_usd, would_have_added_usd}` | T |
| ER-8 | MUST | Unknown / unexpected exceptions in worker code SHALL be caught and returned as `{type: "internal_error", message}` (full traceback to stderr log; not to MCP client) | T |

---

## 6. Capability Matrix (informational)

Generated from the API research; the canonical matrix lives in code (`photo_mcp/models.py`) and is exposed via `list_models`.

| Parameter | gpt-image-1 | gpt-image-1-mini | gpt-image-1.5 | gpt-image-2 |
|---|---|---|---|---|
| `prompt` | ✓ | ✓ | ✓ | ✓ |
| `n` | ✓ | ✓ | ✓ | ✓ |
| `size 1024×1024` | ✓ | ✓ | ✓ | ✓ |
| `size 1024×1536` / `1536×1024` | ✓ | ✓ | ✓ | ✓ |
| `size 2048×2048` / `2048×1152` | — | — | — | ✓ |
| `size 3840×2160` / `2160×3840` | — | — | — | ✓ |
| `size auto` | ✓ | ✓ | ✓ | ✓ |
| `quality low/medium/high/auto` | ✓ | ✓ | ✓ | ✓ |
| `output_format png/jpeg/webp` | ✓ | ✓ | ✓ | ✓ |
| `output_compression 0–100` | ✓ (jpeg/webp) | ✓ | ✓ | ✓ (jpeg/webp) |
| `background opaque/auto` | ✓ | ✓ | ✓ | ✓ |
| `background transparent` | ✓ | ✓ | ✓ | ✗ |
| `response_format b64/url` | ✓ | ✓ | ✓ | ✓ |
| `moderation auto/low` | ✓ | ✓ | ✓ | ✓ |
| `stream` + `partial_images 0–3` | ✓ | ✓ | ✓ | ✓ |
| `input_fidelity high/low` | ✓ | ✓ | ✓ | ✗ (always high) |
| Edit `image` count | 1–16 | 1–16 | 1–16 | 1–16 |
| Mask (PNG with alpha) | ✓ (single-image edits only) | ✓ | ✓ | ✓ |
| Max prompt length | 32,000 chars | 32,000 chars | 32,000 chars | 32,000 chars |
| Max input file size | 50 MB | 50 MB | 50 MB | 50 MB |
| Accepted input formats | PNG, WebP, JPG | PNG, WebP, JPG | PNG, WebP, JPG | PNG, WebP, JPG |

---

## 7. Traceability matrix (placeholder)

To be filled in once WBS is finalized:

| Requirement | WBS package | Test ID(s) |
|---|---|---|
| FR-1.1 | WP-3.1 | T-MCP-001..010 |
| FR-3.1 | WP-3.2 | T-PARAM-001..050 |
| QR-1 | WP-4.3 | T-QUAL-SSIM-001 |
| QR-2 | WP-4.2 | T-EXIF-001..020 |
| (… etc.) | | |

---

## Sources

Research that established this requirement set:

- [OpenAI image generation guide](https://developers.openai.com/api/docs/guides/image-generation)
- [gpt-image-1 model](https://developers.openai.com/api/docs/models/gpt-image-1)
- [gpt-image-1.5 model](https://developers.openai.com/api/docs/models/gpt-image-1.5)
- [gpt-image-1.5 prompting guide](https://developers.openai.com/cookbook/examples/multimodal/image-gen-1.5-prompting_guide)
- [gpt-image-1.5 quality regression thread](https://community.openai.com/t/gpt-image-1-5-decreased-image-render-quality/1371885)
- [gpt-image-2 issues collection](https://community.openai.com/t/collection-of-gpt-image-generator-2-0-issues-bugs-and-work-around-tips-check-first-post/1379535)
- [input_fidelity Microsoft Q&A](https://learn.microsoft.com/en-us/answers/questions/5752784/changing-input-fidelity-on-gpt-image-1-5-to-low)
- [GPT Image 2 review — CrePal](https://crepal.ai/blog/aiimage/image-gpt-image-2-review/)

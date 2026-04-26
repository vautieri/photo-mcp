# Project Charter — photo-mcp

**Project name**: photo-mcp
**Version**: 0.1.0 (charter)
**Date**: 2026-04-25
**Status**: Design phase — no code until charter + requirements + system design are approved

---

## 1. Purpose

Build a production-grade Model Context Protocol (MCP) server that exposes
OpenAI's GPT-Image family (`gpt-image-1`, `gpt-image-1-mini`, `gpt-image-1.5`,
`gpt-image-2`) to a single user — a professional photographer — via
standard MCP transports (stdio for desktop client integration; HTTP+SSE
for remote use).

The server is **not a wrapper that flattens the API**. It exposes every
capability of every selected model, names the model versions explicitly,
preserves source quality at every stage where the photographer's
control matters (input fidelity, color space, EXIF, output format,
output compression), and surfaces the trade-offs honestly so the user
can decide.

## 2. Background

OpenAI's image-generation lineage in production order:
- `gpt-image-1` (2025-04) — first multimodal-aware image gen on the API
- `gpt-image-1-mini` — cost-optimized variant of 1
- `gpt-image-1.5` (2025-12-16) — quality + speed iteration; documentation
  gap on `input_fidelity` caused public complaints from photographers
  about edit-fidelity regression
- `gpt-image-2` (2026-04-21) — latest; supports up to 3840×2160 and
  always uses `high` input fidelity, but does not support transparent
  background and cannot be commanded to use low fidelity

A working photographer benefits from all four because:
- 1.5 with `input_fidelity=high` is currently the cheapest path for
  identity-preserving edits at 1024×1536
- 2 is the only path for 4K output and is the strongest overall but
  loses transparent-background and low-fidelity reinterpretation
- 1 and 1-mini remain the cost floor for prompt-only generation
  during ideation passes

This server lets the user pick per-call, exposes all parameters
verbatim, and preserves the parts of the photographer's source
material that the OpenAI API discards by default.

## 3. Objectives

| ID | Objective | Measurement |
|---|---|---|
| OBJ-1 | Expose every documented parameter of every selected model version | 100% parameter coverage verified by parameter-matrix test |
| OBJ-2 | Preserve source-image quality where the API permits | SSIM ≥ 0.95 against source on identity-preserving edits at `input_fidelity=high` (1.x); zero unsolicited resize, recompress, color-convert |
| OBJ-3 | Re-attach source EXIF/IPTC/XMP to outputs when the photographer requests it | Round-trip metadata preserved for fields the photographer marks critical (DateTime, Camera, Lens, Copyright, GPS) |
| OBJ-4 | Cross-platform: Windows + Linux at v1.0; macOS within +30 days | Same test suite passes on all targets |
| OBJ-5 | Real test coverage — every endpoint exercised against the real OpenAI API in a recorded-cassette integration suite | ≥90% line coverage on production code; ≥1 cassette per (endpoint × model) pair |
| OBJ-6 | Cost transparency — every tool result includes the model, parameters, billed image-token count, and dollar cost estimate | All responses contain `cost_usd_estimate` and `usage` fields |

## 4. Scope

### In scope

- MCP server (stdio + HTTP+SSE transports) implementing standard MCP 2024-11-05 spec
- Tools that map 1:1 to OpenAI image endpoints with full parameter exposure:
  - `generate` → `/v1/images/generations`
  - `edit` → `/v1/images/edits` (single image, with optional mask)
  - `compose` → `/v1/images/edits` (multi-image compositing)
- Quality-preservation utilities:
  - Source-EXIF/IPTC/XMP capture before upload, re-attach after download
  - Source color-profile capture, output ICC tagging
  - RAW pre-conversion to PNG with photographer-controlled de-bayer settings (rawpy)
  - PNG output integrity verification (CRC + decode round-trip)
- Workflow ergonomics:
  - Streaming partial-image previews (`partial_images=0..3`)
  - Idempotent retries on transient errors with exponential backoff
  - Deterministic input file hashing for cassette replay
  - Cost ceiling enforcement per session (configurable, default unlimited)
- Cross-platform packaging: PyPI wheel + standalone binary (PyInstaller) for Windows and Linux
- Configuration via environment variables (API key, model defaults, cost ceiling) and per-call overrides

### Out of scope (explicit)

- Image upload to cloud storage (S3, GCS) — out of scope; user manages their own storage
- Pre/post-processing beyond color-space and EXIF (no auto-sharpen, auto-tone, no denoise)
- Authentication beyond OpenAI API key (no per-user accounts)
- macOS at v1.0 (target +30 days post-v1.0)
- Mobile clients
- Other image providers (Google Imagen, Stability, Adobe Firefly)
- Anything not documented as supported by the OpenAI image API

### Hard constraints

- The server MUST NOT silently downsize, recompress, or convert the source image's color space
- The server MUST NOT make a request whose total billed cost exceeds the per-session ceiling without explicit confirmation in the tool output
- The server MUST NOT proceed with an `image` parameter exceeding 50 MB (API hard limit) — return a structured error with the file size

## 5. Stakeholders

| Stakeholder | Role | Interest |
|---|---|---|
| Sponsor (the user / photographer) | Funds project, approves design, supplies API key | End-to-end product fitness |
| Lead engineer (Claude / me) | Designs, implements, tests, packages | Bar = port-quality directive: line-by-line correctness, no shortcuts, real tests |
| OpenAI Platform | API provider | Up to date with latest published parameters |

## 6. Success criteria

The project is **delivered** when ALL of the following are true:

1. Charter, Requirements (SDD-001..NN), WBS, CDRL list, System Design, V&V Plan, EVM Baseline, and Risk Register are written, internally consistent, and approved by the sponsor
2. All functional requirements (FR-*) and non-functional requirements (NFR-*) marked Priority=MUST are implemented and verified by automated tests
3. ≥90% line coverage on production code
4. ≥1 recorded-cassette integration test per (endpoint × model) cell — 12 cells minimum: 3 endpoints × 4 models
5. Round-trip image quality tests pass: SSIM ≥ 0.95 for `input_fidelity=high` edit operations on a curated set of 10 reference photos
6. EXIF round-trip tests pass: critical EXIF fields preserved on PNG output
7. Cost estimation accuracy within ±2% of OpenAI's billed cost on a 50-call sampled session
8. Cross-platform CI green on `windows-latest` and `ubuntu-latest` GitHub runners
9. Sponsor performs an acceptance run with a live API key, no MUST-defects logged
10. All known bugs are either fixed or explicitly accepted by sponsor in a deviation log

## 7. High-level schedule

(Detailed in EVM Baseline doc — placeholder summary here.)

| Phase | Duration | Gate |
|---|---|---|
| Design | as long as needed | Sponsor approves all 8 docs |
| Implementation | est. 5–8 working days | All FR-MUST + NFR-MUST passing |
| Verification | est. 2–3 days | All V&V tests passing on Windows + Linux |
| Acceptance | 1 day | Sponsor sign-off |

No code begins until design is approved.

## 8. Budget

Tracked in EVM. Budget is engineering time + an allowance for live-API verification calls (estimated ≤ $50 USD across the full V&V cycle).

## 9. Approval

| Role | Name | Date | Signature |
|---|---|---|---|
| Sponsor | the photographer | 2026-04-25 | Approved via husband on 2026-04-25 ("my wife approved"); logged in process-ledger.md as G1 pass |
| Lead engineer | Claude | 2026-04-25 | committed via this document |

---

## Sources

Research that grounded this charter:

- [Image generation — OpenAI Developer Platform](https://developers.openai.com/api/docs/guides/image-generation)
- [GPT Image 1 model spec](https://developers.openai.com/api/docs/models/gpt-image-1)
- [GPT Image 1.5 model spec](https://developers.openai.com/api/docs/models/gpt-image-1.5)
- [GPT Image 1.5 prompting guide (OpenAI Cookbook)](https://developers.openai.com/cookbook/examples/multimodal/image-gen-1.5-prompting_guide)
- [GPT-Image-1.5 decreased image render quality? — OpenAI Developer Community thread](https://community.openai.com/t/gpt-image-1-5-decreased-image-render-quality/1371885)
- [Collection of GPT-image-generator 2.0 issues, bugs, and work-arounds — OpenAI Developer Community](https://community.openai.com/t/collection-of-gpt-image-generator-2-0-issues-bugs-and-work-around-tips-check-first-post/1379535)
- [Changing input_fidelity on GPT-Image-1.5 to "low" — Microsoft Q&A](https://learn.microsoft.com/en-us/answers/questions/5752784/changing-input-fidelity-on-gpt-image-1-5-to-low)
- [GPT Image 1.5 prompt guide — fal.ai](https://fal.ai/learn/devs/gpt-image-1-5-prompt-guide)
- [GPT Image 2 review — CrePal](https://crepal.ai/blog/aiimage/image-gpt-image-2-review/)

# Risk Register — photo-mcp v1.0

**Version**: 0.1.0
**Date**: 2026-04-25
**Status**: Living document — updated on event

---

## Conventions

| Field | Values / Notes |
|---|---|
| ID | `R-` prefix, sequential |
| Likelihood | Low (1) / Medium (2) / High (3) |
| Impact | Low (1) / Medium (2) / High (3) — based on schedule + scope effect |
| Score | Likelihood × Impact (1–9) |
| Owner | who tracks the mitigation |
| Status | Open / Mitigating / Closed / Accepted |
| Mitigation | concrete plan; "accept" only with sponsor approval |

---

## Risks

### R-001 — OpenAI API drift mid-build

| Field | Value |
|---|---|
| Likelihood | High (3) |
| Impact | Medium (2) |
| Score | 6 |
| Owner | Engineer |
| Status | Mitigating |
| Description | The image-generation API is iterating quickly (gpt-image-2 released 2026-04-21, days before this project). New models / parameters / breaking changes can appear during the build. |
| Mitigation | (a) SDK pinned to `>=1.50,<2.0` in pyproject; (b) cassettes capture exact responses; (c) capability matrix in `models.py` is the single source of truth and easy to extend; (d) Phase 1.3.10 live-API smoke run within 7 days of release validates against current API. |

### R-002 — `input_fidelity` documentation ambiguity for gpt-image-1.5

| Field | Value |
|---|---|
| Likelihood | Medium (2) |
| Impact | High (3) |
| Score | 6 |
| Owner | Engineer |
| Status | Mitigating |
| Description | Sources disagree on whether `input_fidelity` is settable on gpt-image-1.5 vs always-defaulted-to-high. Wrong assumption → either rejection (false 400s) or unexpected token costs. |
| Mitigation | (a) Live-API verification on each 1.x model in WBS 1.3.10; (b) `models.py` capability matrix tracks the truth and is updated post-verification; (c) when client passes `input_fidelity` for a model that doesn't support it, server returns ER-3 unsupported_parameter naming the model — never silent dropping. |

### R-003 — Iterative quality degradation in user workflows

| Field | Value |
|---|---|
| Likelihood | High (3) |
| Impact | Medium (2) |
| Score | 6 |
| Owner | Sponsor + Engineer |
| Status | Mitigating |
| Description | Public complaints document that re-feeding model outputs as inputs causes "blotchy mess of globs" cumulative degradation. The photographer might iterate 3–5 times on one image and not realize fidelity has dropped. |
| Mitigation | (a) FR-6.8 SSIM-against-source returned in every edit response so degradation is measurable; (b) tool description in `edit` warns about iterative re-edits; (c) post-v1.0: optional `iteration_count` parameter that aggregates SSIM across rounds and warns when cumulative loss exceeds a threshold. |

### R-004 — Color space drift (sRGB output vs AdobeRGB/ProPhoto sources)

| Field | Value |
|---|---|
| Likelihood | High (3) |
| Impact | Medium (2) |
| Score | 6 |
| Owner | Engineer |
| Status | Mitigating |
| Description | OpenAI returns sRGB regardless of input. Photographer working in AdobeRGB or ProPhoto loses gamut silently if not warned. |
| Mitigation | FR-6.4 explicit warning in tool result; FR-6.3 + QR-5 ICC profile preservation when user opts in via `preserve_color_profile=true`; default ON for `edit` so the photographer sees their profile retained. |

### R-005 — EXIF/IPTC/XMP loss on edit

| Field | Value |
|---|---|
| Likelihood | High (3) |
| Impact | High (3) |
| Score | 9 |
| Owner | Engineer |
| Status | Mitigating |
| Description | OpenAI strips all metadata on output. Photographer's copyright, GPS, lens, license fields disappear. Critical for professional workflow. |
| Mitigation | QR-2..4: explicit re-attachment of critical fields after download; default ON; tested by `tests/quality/test_metadata_round_trip.py` against 10-photo set. |

### R-006 — File size limit (≤ 50 MB) against high-res / RAW workflows

| Field | Value |
|---|---|
| Likelihood | Medium (2) |
| Impact | Medium (2) |
| Score | 4 |
| Owner | Engineer |
| Status | Mitigating |
| Description | Modern RAW files (Canon CR3 from R5, Nikon NEF from Z9) often exceed 50 MB pre-decode; high-res TIFF outputs from photo workflow can exceed 50 MB even after 8-bit downconvert. |
| Mitigation | (a) FR-6.6: rawpy pre-decode RAW to PNG; rawpy output is typically 30–60 MB at 16-bit, so server defaults to 8-bit decode for upload (and warns); (b) FR-6.5: explicit `pre_resize_to` opt-in for the photographer to choose downscale rather than refuse; (c) refuse silently is forbidden — server always returns ER-4 input_too_large with the specific size and recommendation. |

### R-007 — RAW format compatibility (older / odd cameras)

| Field | Value |
|---|---|
| Likelihood | Low (1) |
| Impact | Medium (2) |
| Score | 2 |
| Owner | Engineer |
| Status | Accept (mitigation prepared) |
| Description | rawpy/LibRaw supports most modern bodies but lags on very new (e.g. just-released cameras' DCRAW patches) or very old formats. Photographer's specific camera body may not decode. |
| Mitigation | (a) `tests/quality/test_raw_pipeline.py` exercises Sony A7 IV / Canon R5 / Nikon Z9 / Fujifilm GFX / iPhone Pro RAW; (b) when rawpy fails, server returns a structured error suggesting the photographer pre-convert to TIFF/PNG via Lightroom/Capture One. Accept the gap rather than ship with broken decoding. |

### R-008 — Cost ceiling miscount on streaming partial frames

| Field | Value |
|---|---|
| Likelihood | Medium (2) |
| Impact | Low (1) |
| Score | 2 |
| Owner | Engineer |
| Status | Mitigating |
| Description | When `partial_images > 0`, OpenAI bills only the final image (per current docs), but estimate logic must not double-count partials. |
| Mitigation | Cost estimator in `cost.py` reads `usage.total_tokens` from the final completion event only; partial events do NOT contribute to the running session_total. Tested in `tests/integration/test_cost_accuracy.py`. |

### R-009 — Path traversal via tool input

| Field | Value |
|---|---|
| Likelihood | Medium (2) |
| Impact | High (3) |
| Score | 6 |
| Owner | Engineer |
| Status | Mitigating |
| Description | A malicious or buggy MCP client could pass `../../etc/shadow` as `image` and the server might read or upload it. Even though "the user controls their MCP client", the server SHOULD defend in depth. |
| Mitigation | NFR-3.3..3.7: canonicalize, allow-list roots, refuse symlinks by default; tested in `tests/security/test_path_traversal.py`. |

### R-010 — API key leak in logs / error messages

| Field | Value |
|---|---|
| Likelihood | Low (1) |
| Impact | High (3) |
| Score | 3 |
| Owner | Engineer |
| Status | Mitigating |
| Description | A traceback or error response that includes the request's `Authorization` header could leak the key into logs the user shares for debugging. |
| Mitigation | NFR-3.2 + `logging.redact()` strips any `sk-…` string and any field named `api_key`/`Authorization`/`auth`/`token`/`secret` before emit; tested in `tests/security/test_key_redaction.py`; OpenAI SDK error path is exercised explicitly. |

### R-011 — Cross-platform path / EOL bugs

| Field | Value |
|---|---|
| Likelihood | Medium (2) |
| Impact | Medium (2) |
| Score | 4 |
| Owner | Engineer |
| Status | Mitigating |
| Description | Windows (`\` separators, `\r\n`-default text mode) vs Linux (`/`, `\n`). Common source of "works on my machine" bugs in transport framing and file paths. |
| Mitigation | NFR-4.1 CI matrix runs full suite on `windows-latest` + `ubuntu-latest`; explicit `\n` in JSON-RPC framing; pathlib everywhere. macOS is post-v1.0 risk. |

### R-012 — PyInstaller standalone binary fails to load on user's Windows

| Field | Value |
|---|---|
| Likelihood | Medium (2) |
| Impact | Medium (2) |
| Score | 4 |
| Owner | Engineer |
| Status | Mitigating |
| Description | PyInstaller bundles an embedded Python interpreter and DLL set; some Windows hosts (older builds, locked-down enterprise) trigger antivirus or DLL-load failures. |
| Mitigation | (a) Provide both wheel (pip install) and standalone binary; (b) sign the Windows binary if sponsor wants — out of v1.0 scope but documented as v1.1 enhancement; (c) include rich error output on startup so DLL-load issues are diagnosable. |

### R-013 — MCP protocol version drift

| Field | Value |
|---|---|
| Likelihood | Low (1) |
| Impact | Medium (2) |
| Score | 2 |
| Owner | Engineer |
| Status | Accept |
| Description | MCP protocol could revise in a backward-incompatible way before v1.0 ships, requiring a server rev to maintain client compatibility. |
| Mitigation | Pin to MCP protocol version 2024-11-05; declare it in handshake; re-evaluate on each MCP SDK minor bump. Accepted because MCP has been stable since release. |

### R-014 — Sponsor unavailable to approve CDRLs

| Field | Value |
|---|---|
| Likelihood | Low (1) |
| Impact | High (3) |
| Score | 3 |
| Owner | Engineer |
| Status | Accept |
| Description | Sponsor (the photographer-wife) is the sole approval authority. If unavailable for >5 working days, design phase stalls. |
| Mitigation | Engineer keeps producing the next deliverable in parallel where dependencies allow; project halts only if Phase 1.1 gate fails. Acceptance requires sponsor; no surrogate. |

### R-015 — Reference-photo set too narrow

| Field | Value |
|---|---|
| Likelihood | Medium (2) |
| Impact | Medium (2) |
| Score | 4 |
| Owner | Sponsor |
| Status | Open |
| Description | If the sponsor's actual photography style isn't represented in the 10-photo fixture set, SSIM/EXIF tests pass but real-world workflows still fail. |
| Mitigation | Sponsor reviews and curates the photo set during Phase 1.1.9. Sponsor may swap out reference photos at any time during V&V; tests re-run automatically. The set is data, not code. |

### R-016 — Cost overrun on live-API verification

| Field | Value |
|---|---|
| Likelihood | Medium (2) |
| Impact | Low (1) |
| Score | 2 |
| Owner | Engineer |
| Status | Mitigating |
| Description | Live-API smoke run plus cassette recording could blow past the project's $50 verification allowance if mis-managed. |
| Mitigation | (a) Run smallest sizes (1024×1024 except for the 4K verify); (b) `quality=low` for all initial cassette recordings unless a test specifically validates `high`; (c) cap session_cost_ceiling for the recording session; (d) log every call's cost. |

### R-017 — Multi-image edit (16-image) memory pressure

| Field | Value |
|---|---|
| Likelihood | Low (1) |
| Impact | Medium (2) |
| Score | 2 |
| Owner | Engineer |
| Status | Mitigating |
| Description | Encoding 16 images at 50 MB each in memory before upload = 800 MB peak RSS. A workstation with 8 GB RAM may struggle if other apps are running. |
| Mitigation | Stream-encode each image to base64 lazily; never hold all 16 decoded simultaneously; document RAM headroom in README. |

---

## Summary scores

| Score band | Count |
|---|---|
| 9 (red) | 1 (R-005 EXIF loss) |
| 6 (amber) | 5 |
| 4 (yellow) | 4 |
| 2–3 (green) | 7 |

Top item is R-005 — EXIF loss is the most photographer-critical risk and is
fully mitigated in the design (QR-2..4 + tested round-trip). All amber items
have mitigations in design or tests.

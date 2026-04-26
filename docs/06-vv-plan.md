# Verification & Validation Plan — photo-mcp

**Version**: 0.1.0
**Date**: 2026-04-25

---

## 1. Purpose

This plan defines how every requirement in `docs/02-requirements.md` is
verified before v1.0 release. It maps each requirement (FR/NFR/IR/QR/ER) to
one or more named test artifacts, defines the test environment, and sets
acceptance gates.

The plan distinguishes **verification** (does it meet the spec?) from
**validation** (does it solve the photographer's actual problem?). The
SSIM benchmarks, EXIF round-trip, and reference-photo set are validation
activities; the rest are verification.

---

## 2. Test types

| Tier | Purpose | Run frequency | Where |
|---|---|---|---|
| Unit | Single module / function correctness with deps mocked | Every commit | dev + CI |
| Integration (cassette) | Multi-module flows replayed against recorded OpenAI responses | Every commit | dev + CI |
| Quality / validation | Reference-photo SSIM, metadata round-trip, color round-trip | Every PR | dev + CI |
| Performance | Dispatch overhead, streaming latency, write+verify time | Nightly | CI |
| Security | Path traversal, SSRF, key redaction | Every commit | dev + CI |
| Live API | Real-money calls against api.openai.com | On-demand + before each release | dev (sponsor's key) |

---

## 3. Environment

### 3.1 Reference machine (perf NFR-1.*)

- 4-core x86_64 (e.g., GitHub `ubuntu-latest`, ~Intel Xeon 8370C)
- 8 GB RAM
- Linux 6.x
- Python 3.12.x

### 3.2 CI matrix

| OS | Python | Notes |
|---|---|---|
| ubuntu-latest | 3.12 | Primary |
| ubuntu-latest | 3.13 | Forward compat |
| windows-latest | 3.12 | Cross-platform |
| macos-latest | 3.12 | Post-v1.0 only |

### 3.3 Cassette policy

- Cassettes live under `tests/integration/cassettes/`
- Recording is opt-in via `RECORD_CASSETTES=1` env var
- Cassettes filter `Authorization` header to `<REDACTED>` before commit
- CI runs in `replay` mode (cassette must exist; recording is forbidden)
- Cassettes are refreshed when the OpenAI SDK rev'd in `pyproject.toml` minor-bumps

---

## 4. Requirement-to-test traceability

| Req ID | Description (short) | Verification | Test ID(s) |
|---|---|---|---|
| FR-1.1 | MCP protocol 2024-11-05 conformance | T | `tests/unit/test_server_protocol.py::test_initialize_handshake` |
| FR-1.2 | stdio transport | T | `tests/unit/test_transport_stdio.py::*` |
| FR-1.3 | HTTP+SSE transport | T | `tests/unit/test_transport_http.py::*` |
| FR-1.4 | EOF clean shutdown ≤5s | T | `tests/unit/test_transport_stdio.py::test_eof_shutdown_under_5s` |
| FR-1.5 | Signal handling SIGTERM/SIGINT/Ctrl+C | T (per-OS) | `tests/unit/test_signals.py::*` |
| FR-2.1 | `generate` tool | T | `tests/integration/test_generate_*.py` |
| FR-2.2 | `edit` tool (1..16 images) | T | `tests/integration/test_edit_*.py` |
| FR-2.3 | `list_models` | T | `tests/unit/test_info_tools.py::test_list_models` |
| FR-2.4 | `estimate_cost` | T | `tests/unit/test_info_tools.py::test_estimate_cost_*` |
| FR-2.5 | `attach_metadata` | T | `tests/unit/test_utility_tools.py::test_attach_metadata` |
| FR-3.1..3.15 | Parameter coverage | T | `tests/integration/test_parameter_matrix.py` (parameterized; one row per cell) |
| FR-4.1..4.3 | Streaming | T | `tests/integration/test_stream.py::*` |
| FR-5.1..5.4 | Output paths and `n>1` suffix | T | `tests/unit/test_output.py::*` |
| FR-6.1..6.2 | Metadata capture/re-attach | T | `tests/quality/test_metadata_round_trip.py` |
| FR-6.3..6.4 | Color profile capture/embed/warn | T | `tests/quality/test_color_profile.py` |
| FR-6.5 | Refuse silent downscale on >50MB | T | `tests/unit/test_size_limits.py::test_refuse_oversize` |
| FR-6.6 | RAW pre-conversion via rawpy | T | `tests/quality/test_raw_pipeline.py::*` |
| FR-6.7 | PNG integrity verify | T | `tests/unit/test_output.py::test_png_verify_after_write` |
| FR-6.8 | SSIM in tool result | T | `tests/quality/test_ssim_round_trip.py` |
| FR-7.1..7.4 | Cost estimate, table, ceiling | T | `tests/unit/test_cost.py::*`; `tests/integration/test_cost_accuracy.py` |
| FR-8.1..8.5 | Config: env, fail-fast, no-log-key, TOML, per-call override | T+I | `tests/unit/test_config.py::*`; `tests/security/test_key_redaction.py` |
| NFR-1.1..1.3 | Performance | T | `tests/perf/test_dispatch_overhead.py::*`; `test_stream_latency.py` |
| NFR-2.1..2.4 | Reliability / retries / buffering | T | `tests/unit/test_retry.py::*`; `tests/unit/test_dispatch_robustness.py::*` |
| NFR-3.1..3.7 | Security | T+I | `tests/security/*.py` |
| NFR-4.1..4.4 | Cross-platform | T | matrix-driven CI runs the full suite per OS |
| NFR-5.1 | ≥90% coverage | A | `pytest --cov` gate in CI |
| NFR-5.2 | mypy --strict clean | T | CI step |
| NFR-5.3 | ruff + black clean | T | CI step |
| NFR-5.4 | Wheel + standalone bin produced | I+D | CI artifacts; sponsor downloads |
| NFR-6.1..6.3 | JSON logs, levels, no stdout pollution | T | `tests/unit/test_logging.py::*` |
| IR-1.1..1.4 | MCP schema conformance | T | `tests/unit/test_schema.py::*` (validates each tool's schema as draft-2020-12) |
| IR-2.1..2.3 | OpenAI SDK pinning | I | release checklist |
| IR-3.1..3.3 | Filesystem | T | `tests/unit/test_paths.py`; `test_output_atomic.py` |
| QR-1 | SSIM ≥ 0.95 on identity edits | T (validation) | `tests/quality/test_ssim_round_trip.py` |
| QR-2..4 | EXIF/XMP/IPTC round-trip | T (validation) | `tests/quality/test_metadata_round_trip.py` |
| QR-5 | Color profile + warn | T | `tests/quality/test_color_profile.py` |
| QR-6 | No silent transformation | I+T | code-review checklist; `test_no_silent_resize.py` |
| QR-7 | PNG integrity | T | `tests/unit/test_output.py::test_png_verify_after_write` |
| QR-8 | JPEG-on-edit warning | T | `tests/quality/test_format_warnings.py` |
| QR-9 | Source never modified | T | `tests/quality/test_source_immutable.py` (snapshot source SHA-256 before call, compare after) |
| QR-10 | Provenance sidecar written and complete | T | `tests/quality/test_sidecar.py::test_sidecar_fields_complete`, `::test_sidecar_sha256_matches_sources` |
| QR-11 | Sidecar atomicity | T | `tests/quality/test_sidecar_atomicity.py` (simulate crash mid-write; assert no orphaned output or sidecar) |
| QR-12 | Software EXIF tag identifies photo-mcp + model | T | `tests/quality/test_exif_software_tag.py` |
| WS-1 | Sky replacement preserves foreground | T (validation) | `tests/quality/test_workflow_sky_replace.py` (foreground-region SSIM check) |
| WS-2 | Two-photo merge (sky from A, foreground from B) | T (validation) | `tests/quality/test_workflow_two_photo_merge.py` |
| WS-3 | Three-photo merge | T (validation) | `tests/quality/test_workflow_three_photo_merge.py` |
| WS-4 | Atmospheric addition (rainbow / sun rays) preserves elsewhere | T (validation) | `tests/quality/test_workflow_atmosphere.py` |
| WS-5 | Dress-on-person identity preservation | T (validation) | `tests/quality/test_workflow_garment_swap.py` (face-region SSIM via face-detect) |
| WS-6 | Mood reinterpretation, no composition change | T (validation) | `tests/quality/test_workflow_mood_shift.py` (dimension equality, content delta in expected band) |
| WS-7 | Authenticity audit replays correctly | T (validation) | `tests/quality/test_workflow_audit_trail.py` (parse sidecar, verify each source SHA, confirm completeness) |
| ER-1..ER-8 | Structured errors | T | `tests/unit/test_errors.py::*` |

---

## 5. Cassette inventory

Minimum required cassettes (file names under `tests/integration/cassettes/`):

| # | Cassette | Endpoint | Model | Scenario |
|---|---|---|---|---|
| 1 | `gen_gpt-image-1_basic.yaml` | generations | gpt-image-1 | size=1024×1024, quality=auto |
| 2 | `gen_gpt-image-1-mini_basic.yaml` | generations | gpt-image-1-mini | same |
| 3 | `gen_gpt-image-1.5_basic.yaml` | generations | gpt-image-1.5 | same |
| 4 | `gen_gpt-image-2_basic.yaml` | generations | gpt-image-2 | same |
| 5 | `gen_gpt-image-2_4k.yaml` | generations | gpt-image-2 | size=3840×2160 (validates 4K path) |
| 6 | `edit_gpt-image-1_high_fidelity.yaml` | edits | gpt-image-1 | 1 image, mask, input_fidelity=high |
| 7 | `edit_gpt-image-1_low_fidelity.yaml` | edits | gpt-image-1 | 1 image, no mask, input_fidelity=low |
| 8 | `edit_gpt-image-1-mini_high.yaml` | edits | gpt-image-1-mini | 1 image, high |
| 9 | `edit_gpt-image-1.5_high.yaml` | edits | gpt-image-1.5 | 1 image, high |
| 10 | `edit_gpt-image-1.5_4images.yaml` | edits | gpt-image-1.5 | 4 reference images, no mask, high |
| 11 | `edit_gpt-image-1.5_16images.yaml` | edits | gpt-image-1.5 | 16 images (max), validates the cap |
| 12 | `edit_gpt-image-2_8images.yaml` | edits | gpt-image-2 | 8 images, no mask |
| 13 | `edit_gpt-image-2_dress_on_person.yaml` | edits | gpt-image-2 | 2 images: person + clothing — primary multi-image use case |
| 14 | `edit_gpt-image-1.5_transparent_bg.yaml` | edits | gpt-image-1.5 | background=transparent (1.x feature) |
| 15 | `gen_gpt-image-2_stream_p3.yaml` | generations | gpt-image-2 | stream=true, partial_images=3 |
| 16 | `edit_gpt-image-1.5_stream_p2.yaml` | edits | gpt-image-1.5 | stream=true, partial_images=2 |
| 17 | `gen_gpt-image-2_jpeg.yaml` | generations | gpt-image-2 | output_format=jpeg, output_compression=92 |
| 18 | `gen_gpt-image-2_webp.yaml` | generations | gpt-image-2 | output_format=webp, output_compression=85 |
| 19 | `gen_gpt-image-2_url_response.yaml` | generations | gpt-image-2 | response_format=url |
| 20 | `gen_gpt-image-1.5_moderation_low.yaml` | generations | gpt-image-1.5 | moderation=low |
| 21 | `error_gpt-image-2_invalid_size.yaml` | generations | gpt-image-2 | bad size → 400 |
| 22 | `error_429_retry.yaml` | generations | gpt-image-2 | one 429 then 200 — exercises retry/backoff |

22 cassettes, sized to give one cell per important behavior. `RECORD_CASSETTES=1`
operator generates them once against the live API; CI replays.

---

## 6. Reference photo set (validation fixtures)

Located at `tests/fixtures/photos/`. Curated to cover the photographer's
realistic input variety:

| File | Camera | Color profile | EXIF richness | Use |
|---|---|---|---|---|
| `portrait_studio.jpg` | Sony A7 IV | sRGB | full | SSIM identity-edit test, EXIF round-trip |
| `portrait_natural.cr3` | Canon R5 | AdobeRGB (RAW) | full | RAW pipeline, AdobeRGB warn |
| `landscape_golden.nef` | Nikon Z9 | ProPhoto (RAW) | full | RAW + ProPhoto, color profile preserve |
| `landscape_blue_hour.tif` | Fujifilm GFX | AdobeRGB | full | non-PNG/JPG handling (TIFF path: convert + warn) |
| `low_light_iso6400.arw` | Sony A1 | sRGB (RAW) | full | high ISO grain preservation in edits |
| `product_white_bg.png` | Canon R6 | sRGB | minimal | transparent-background edit |
| `with_gps_copyright.jpg` | iPhone 17 Pro | sRGB | GPS + Copyright + Artist | GPS / IPTC round-trip |
| `large_50mb.png` | rendered | sRGB | none | 50MB boundary test |
| `large_60mb.png` | rendered | sRGB | none | over-50MB rejection test (FR-6.5) |
| `four_corners_text.png` | rendered | sRGB | none | tests the dimensional-distortion complaint regression |

License + provenance for the curated photos goes in `tests/fixtures/photos/PROVENANCE.md`. Photos that can't be redistributed publicly
are excluded from the public repo and substituted with rendered equivalents
that exercise the same code paths.

---

## 7. SSIM benchmark methodology (QR-1)

Goal: detect quality regression in `edit` operations between releases.

Procedure:

1. For each model in `{gpt-image-1, gpt-image-1.5, gpt-image-2}` and each
   reference photo in the set's identity-suitable subset (portrait_studio,
   portrait_natural, landscape_golden, with_gps_copyright):
2. Submit `edit` with prompt = "preserve all details exactly, no changes"
   and `input_fidelity=high` (when supported).
3. Compute SSIM between source (decoded to numpy uint8 RGB) and output.
4. Record per-(model, photo) SSIM in a JSON results file.
5. Assert mean SSIM ≥ 0.95 across the subset for each model.
6. Per-photo results plotted to `tests/quality/results/ssim_history.json`
   over time so degradation trend is visible PR-to-PR.

This is a **regression** test — it does not assert SSIM matches the original
sponsor expectation (the sponsor accepts whatever current floor is). It
asserts SSIM does not drop ≥ 0.02 from the floor recorded at v1.0 baseline.

---

## 8. EXIF / XMP / IPTC round-trip methodology (QR-2..4)

For each photo with rich metadata, the test:

1. Extracts the metadata snapshot pre-call.
2. Submits `edit` with `preserve_metadata=true`.
3. Reads metadata from the output file.
4. Diffs critical fields (DateTime, Make, Model, LensModel, FocalLength, FNumber,
   ExposureTime, ISO, GPSLatitude/Longitude, Copyright, Artist, dc:rights,
   dc:creator, dc:title, dc:description, IPTC By-line, Caption-Abstract).
5. Asserts each critical field is byte-identical.

Non-critical fields (thumbnail, MakerNote) are not asserted and may differ
because Pillow doesn't always preserve them.

---

## 9. Color profile round-trip methodology (QR-5)

Each AdobeRGB / ProPhoto reference photo is run through `edit` with both
`preserve_color_profile=true` and `=false`:

- With `=true`: output PNG/JPEG must contain an embedded ICC profile that
  matches the source's profile bytes (or a known sRGB→AdobeRGB conversion
  marker if the user opted into conversion).
- With `=false`: a warning entry SHALL appear in `EditOutput.warnings`
  naming the source profile.

ICC bytes compared via SHA-256 (Pillow's `info["icc_profile"]`).

---

## 10. Performance methodology (NFR-1.*)

`pytest-benchmark` runs:

1. Dispatch overhead: time from MCP `tools/call` received to first byte sent
   to OpenAI (with cassette short-circuit, but measure pre-cassette path).
2. Output write+verify: 4096×4096 PNG generated (synthesized in test) and
   written through `output.py` atomic path.
3. Streaming latency: simulated stream events through the partial-image
   relay, measure event-receipt-to-MCP-emit delta.

Each metric has a documented ceiling (NFR-1.1 ≤ 250 ms p95, NFR-1.2 ≤ 1 s,
NFR-1.3 ≤ 100 ms). CI fails if any metric breaches.

---

## 10a. Workflow acceptance methodology (WS-1..7)

Each named workflow runs as an end-to-end acceptance test against recorded
cassettes plus reference photos. The procedure for the multi-image workflows
(WS-2, WS-3, WS-5):

1. **Inputs**: select reference photos from the curated set that match the
   workflow's intent (e.g., for WS-2: a photo with poor sky + a photo with
   good sky).
2. **Pre-call snapshot**: record SHA-256 of every source file.
3. **Call**: dispatch through the real `edit` tool path with cassette
   playback.
4. **Post-call assertions**:
   - Every source's SHA-256 still matches → QR-9 passes
   - Sidecar exists at `<output>.photo-mcp.json` → QR-10 passes
   - Sidecar's `sources` list has every source with matching SHA → WS-7 passes
   - For workflows that preserve a region (WS-1 foreground, WS-5 face):
     run face-detect or sky-detect, compute SSIM only on the preserve-region,
     assert ≥ threshold
   - Output dimensions match expectation (WS-6 dimension equality)

Workflow tests are slower than unit tests (cassette I/O + SSIM compute);
they run in the `quality` test directory and are gated on every PR but not
on every commit.

---

## 11. Security methodology (NFR-3.*)

| Test | Method |
|---|---|
| Path traversal (input) | Submit `image="../../etc/passwd"` → expect ER (PathOutsideRoot) |
| Path traversal (output) | Submit `output_dir="../../tmp"` outside allowed_output_roots → expect ER |
| Symlink follow | Place a symlink that points outside allowed roots, attempt to read → expect ER unless `--follow-symlinks` |
| SSRF | Mock the OpenAI client with a hostname injection attempt; verify no request goes anywhere except api.openai.com |
| Key redaction | Trigger a code path that includes the API key (intentional, for the test); read stderr; assert key never appears |
| TLS verify | Force a self-signed cert via env override; verify the call fails with TLS error |

---

## 12. Live API run (release gate only)

Once per release candidate, the engineer (with sponsor approval and key)
runs the full live-call suite — same scenarios as the cassette inventory,
but recording cost actually billed. The result file
`tests/live/results_<date>.json` documents:

- Per-call latency, billed tokens, billed cost
- Estimate accuracy: `|estimate - billed| / billed` per call; mean ±2% required
- Any drift from cassettes (refresh cassettes if observed)

This run is opt-in via `RUN_LIVE_API=1` and never executes in CI.

---

## 13. Coverage gate

`pytest --cov=photo_mcp --cov-report=term --cov-fail-under=90` in CI.
Uncovered lines are exempt only with explicit `# pragma: no cover` and a
linked rationale comment.

---

## 14. Release checklist (V&V close-out)

Before tagging v1.0:

- [ ] All MUST requirements pass (FR/NFR/IR/QR/ER)
- [ ] Coverage ≥ 90%
- [ ] Cassettes refreshed against current OpenAI SDK
- [ ] Live API run within last 7 days, estimate accuracy ≤ 2%
- [ ] CI green on Windows + Linux (macOS deferred to post-v1.0)
- [ ] Wheel + standalone binary built, smoke-tested
- [ ] Sponsor acceptance log signed
- [ ] V&V Report (CDRL-012) generated and submitted

---

## 15. Out of scope for v1.0 V&V

- macOS test matrix (deferred +30 days)
- Fuzz testing (acknowledged risk; tracked in Risk Register)
- Long-running session stress (>1000 calls in one process) — sponsor confirmed not a primary use case

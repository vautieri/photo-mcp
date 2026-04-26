# Work Breakdown Structure — photo-mcp v1.0

**Date**: 2026-04-25
**Format**: 3-level WBS — Project → Phase → Work Package
**Effort unit**: engineering-hours (eh). Hours are estimates, not commitments;
EVM tracks earned value in % weight, not hours.

---

## Numbering

`1.0`         project
`1.X`         phase
`1.X.Y`       work package (deliverable)
`1.X.Y.Z`     activity (one-line task within a work package)

---

## 1.0 photo-mcp v1.0

### 1.1 Design phase (must complete and be sponsor-approved before any code)

| WBS | Work Package | Effort (eh) | Dependencies | Deliverable | % weight |
|---|---|---|---|---|---|
| 1.1.1 | Project Charter | 4 | — | `docs/01-project-charter.md` | 1.5% |
| 1.1.2 | Requirements Document | 8 | 1.1.1 | `docs/02-requirements.md` (FR/NFR/IR/QR/ER + traceability matrix) | 3.0% |
| 1.1.3 | WBS (this document) | 3 | 1.1.2 | `docs/03-wbs.md` | 1.0% |
| 1.1.4 | CDRL list | 2 | 1.1.2 | `docs/04-cdrls.md` (DID-style deliverable definitions) | 1.0% |
| 1.1.5 | System Design Document | 12 | 1.1.2 | `docs/05-system-design.md` (architecture, file layout, module dependency graph, error taxonomy, state machines for streaming + retry + cost ceiling) | 4.5% |
| 1.1.6 | V&V Plan | 8 | 1.1.2, 1.1.5 | `docs/06-vv-plan.md` (test approach, cassette strategy, SSIM benchmarks, EXIF round-trip, parameter matrix, coverage gates) | 3.0% |
| 1.1.7 | EVM Baseline | 4 | 1.1.3 | `docs/07-evm-baseline.md` (planned-value curve, BCWS, BCWP measurement) | 1.5% |
| 1.1.8 | Risk Register | 3 | 1.1.5 | `docs/08-risk-register.md` (risk × likelihood × impact × mitigation) | 1.0% |
| 1.1.9 | Reference photo set curation | 4 | 1.1.6 | `tests/fixtures/photos/` — 10 photos covering portrait, landscape, low-light, RAW, AdobeRGB, ProPhoto, large-EXIF, transparent-mask source | 1.0% |
| 1.1.10 | Process Flow document (binding) | 3 | 1.1.4 | `docs/10-process-flow.md` — gates, parallelism rules, deviation discipline, audit trail, final attestation template | 1.0% |

**Phase 1.1 total**: 51 eh, 18.5% project weight. (+1.0% for 1.1.10 binding Process Flow.)

**Phase 1.1 gate**: Sponsor signs off on all 8 docs (review log appended to each doc as a "Sponsor Approval" section). No work in 1.2 begins until this gate passes.

### 1.2 Implementation phase

| WBS | Work Package | Effort (eh) | Dependencies | Deliverable | % weight |
|---|---|---|---|---|---|
| 1.2.1 | Project scaffold + tooling | 4 | 1.1.5 | `pyproject.toml`, `.github/workflows/ci.yml`, `Makefile`, lint/format/type configs, `tox.ini` | 2.0% |
| 1.2.2 | Model capability matrix module | 6 | 1.1.5, 1.2.1 | `photo_mcp/models.py` — enum of models, capability table, parameter validators | 2.5% |
| 1.2.3 | Configuration + secrets | 4 | 1.2.1 | `photo_mcp/config.py` — env vars, TOML config, allowed-roots, log level, cost ceiling | 1.5% |
| 1.2.4 | Cost estimator | 6 | 1.2.2 | `photo_mcp/cost.py` — price table, per-call estimate, session aggregator, ceiling guard | 2.5% |
| 1.2.5 | Retry / error mapping | 4 | 1.2.1 | `photo_mcp/retry.py` — exponential backoff, error taxonomy mapping (NFR-2.1, ER-*) | 1.5% |
| 1.2.6 | OpenAI client adapter | 8 | 1.2.2, 1.2.5 | `photo_mcp/openai_client.py` — wraps `openai` SDK, handles streaming, propagates partial_images events | 3.0% |
| 1.2.7 | EXIF/IPTC/XMP capture + re-attach | 8 | 1.2.1 | `photo_mcp/metadata.py` — Pillow + piexif + iptcinfo3 + xmp_toolkit; round-trip preservation | 3.0% |
| 1.2.8 | Color profile capture + ICC tagging | 6 | 1.2.1 | `photo_mcp/color.py` — extract ICC, embed in PNG/JPEG/WebP, sRGB warning logic | 2.0% |
| 1.2.9 | RAW pre-conversion | 6 | 1.2.1 | `photo_mcp/raw.py` — rawpy wrapper, photographer-controlled de-bayer params | 2.0% |
| 1.2.10 | Output writer (atomic + integrity verify) | 4 | 1.2.1 | `photo_mcp/output.py` — tmp+rename, PNG verify, suffix generation for n>1 | 1.5% |
| 1.2.10b | Provenance sidecar writer (QR-10..12) | 3 | 1.2.10 | `photo_mcp/sidecar.py` — JSON sidecar at `<output>.photo-mcp.json` with SHA-256 of every source, atomic write, software EXIF tag injection | 1.5% |
| 1.2.11 | Path safety / allowed roots | 4 | 1.2.3 | `photo_mcp/paths.py` — canonicalize, allow-list check, symlink policy | 1.5% |
| 1.2.12 | MCP transport (stdio) | 6 | 1.2.1 | `photo_mcp/transport_stdio.py` — JSON-RPC framing, EOF handling, signal handlers | 2.0% |
| 1.2.13 | MCP transport (HTTP+SSE) | 6 | 1.2.12 | `photo_mcp/transport_http.py` — uvicorn + sse-starlette, same dispatch path as stdio | 2.0% |
| 1.2.14 | MCP server core (dispatch + tool registry) | 6 | 1.2.12 | `photo_mcp/server.py` — JSON-RPC method routing, tool registration | 2.0% |
| 1.2.15 | Tool: `generate` | 4 | 1.2.6, 1.2.10, 1.2.4 | `photo_mcp/tools/generate.py` | 1.5% |
| 1.2.16 | Tool: `edit` (single image + 1..16-image multi-input compositing/style-reference, optional mask only for single-image) | 8 | 1.2.6, 1.2.7, 1.2.8, 1.2.9, 1.2.10 | `photo_mcp/tools/edit.py` | 4.0% |
| 1.2.17 | Tool: `list_models`, `estimate_cost`, `attach_metadata` | 4 | 1.2.2, 1.2.4, 1.2.7 | `photo_mcp/tools/info.py`, `tools/utility.py` | 1.5% |
| 1.2.18 | Streaming progress relay | 4 | 1.2.6, 1.2.14 | progress events through MCP `tools/progress` notifications | 1.5% |
| 1.2.19 | Structured logging | 2 | 1.2.1 | `photo_mcp/logging.py` — JSON-line logger to stderr | 1.0% |

**Phase 1.2 total**: 105 eh, 39.5% project weight. (Renumbered after folding `compose` into `edit`; multi-image edit at 1.2.16 absorbs the prior compose package effort. Added 1.2.10b sidecar writer at 3 eh / 1.5%.)

**Phase 1.2 gate**: All MUST-priority FR + NFR have passing unit tests. Code coverage ≥ 90%. Lint, format, type checks clean. Cross-platform CI green.

### 1.3 Verification phase

| WBS | Work Package | Effort (eh) | Dependencies | Deliverable | % weight |
|---|---|---|---|---|---|
| 1.3.1 | Unit test build-out (FR/NFR/IR/ER coverage) | runs in parallel with 1.2.* | runs with each WP | `tests/unit/` | folded into 1.2 weights |
| 1.3.2 | Cassette-based integration tests (live API recordings) | 12 | 1.2.6, 1.2.15–17 | `tests/integration/cassettes/*.yaml` — 12 cassettes (3 endpoints × 4 models); replay-only suite for CI | 4.5% |
| 1.3.3 | Reference-photo SSIM benchmark | 6 | 1.1.9, 1.2.16 | `tests/quality/test_ssim_round_trip.py` (QR-1) | 2.5% |
| 1.3.4 | EXIF/IPTC/XMP round-trip suite | 6 | 1.1.9, 1.2.7 | `tests/quality/test_metadata_round_trip.py` (QR-2..4) | 2.5% |
| 1.3.5 | Color profile round-trip suite | 4 | 1.1.9, 1.2.8 | `tests/quality/test_color_profile.py` (QR-5) | 1.5% |
| 1.3.6 | Cost estimate accuracy validation | 4 | 1.2.4, 1.3.2 | `tests/integration/test_cost_accuracy.py` — computes estimate vs `usage.total_tokens × price` | 1.5% |
| 1.3.7 | Cross-platform CI matrix | 6 | all 1.2.* | `.github/workflows/ci.yml` runs on `windows-latest` + `ubuntu-latest`; Linux ARM64 cross-test if cycles allow | 2.5% |
| 1.3.8 | Performance benchmark | 4 | 1.2.10, 1.2.14 | `tests/perf/test_dispatch_overhead.py` (NFR-1.1, 1.2) | 1.5% |
| 1.3.9 | Security review (path traversal, SSRF, key leakage) | 4 | 1.2.11, 1.2.20 | `tests/security/test_path_traversal.py`, `test_ssrf.py`, `test_key_redaction.py` | 1.5% |
| 1.3.10 | Live-API smoke run + cassette refresh | 4 | API key from sponsor | `cassettes/` updated against latest API; sample call log | 1.5% |
| 1.3.11 | Workflow acceptance tests (WS-1..7) | 8 | 1.1.9, 1.2.10b, 1.2.16 | `tests/quality/test_workflow_*.py` — sky replace, two-photo merge, three-photo merge, atmosphere addition, garment swap, mood shift, audit-trail replay | 3.0% |

**Phase 1.3 total**: 58 eh, 22.5% project weight. (Increased by 8 eh / 3.0% to add workflow acceptance suite WS-1..7 in 1.3.11.)

**Phase 1.3 gate**: All V&V tests in V&V Plan (doc 06) pass. Sponsor reviews V&V report.

### 1.4 Packaging & Acceptance phase

| WBS | Work Package | Effort (eh) | Dependencies | Deliverable | % weight |
|---|---|---|---|---|---|
| 1.4.1 | PyPI wheel build + version pinning | 3 | 1.2.1 | `dist/photo_mcp-0.1.0-py3-none-any.whl` | 1.0% |
| 1.4.2 | PyInstaller standalone binary (Windows + Linux) | 4 | 1.4.1 | `dist/photo-mcp-0.1.0-win-x86_64.exe`, `photo-mcp-0.1.0-linux-x86_64` | 1.5% |
| 1.4.3 | User-facing README + tool reference | 4 | all | `README.md`, `docs/tools.md` (per-tool params, examples, photographer guide) | 1.5% |
| 1.4.4 | Sponsor acceptance run + sign-off log | 4 | 1.4.1, 1.4.2 | `docs/09-acceptance-log.md` | 1.5% |
| 1.4.5 | Final Process Compliance Attestation (CDRL-019) | 3 | all phases | `docs/13-process-compliance-attestation.md` — engineer signs, sponsor verifies and counter-signs per `10-process-flow.md` §7 | 1.0% |

**Phase 1.4 total**: 18 eh, 6.5% project weight. (+1.0% for 1.4.5 final attestation.)

**Phase 1.4 gate**: Sponsor signs the acceptance log. Project closes.

---

## Roll-up

| Phase | eh | % weight |
|---|---|---|
| 1.1 Design | 51 | 18.5% |
| 1.2 Implementation | 105 | 39.5% |
| 1.3 Verification | 58 | 22.5% |
| 1.4 Packaging & Acceptance | 18 | 6.5% |
| Total tracked | 232 | 87.0% |

The remaining 13% is reserved for:
- Issue triage during implementation (7%)
- Cassette re-recording when OpenAI rev's the API mid-build (2%)
- macOS port window (post-v1.0; not counted in v1.0 EVM but reserved): 2%
- Documentation refinement during sponsor review (2%)
- Continuous process ledger maintenance (CDRL-018): folded into respective phase weights, not separately reserved

---

## Critical path

```
1.1.1  Charter
   └─> 1.1.2  Requirements
          └─> 1.1.5  System Design
                 ├─> 1.1.6 V&V Plan
                 │      └─> 1.3.* Verification suite
                 └─> 1.2.1  Scaffold
                        └─> 1.2.2 Models matrix
                               └─> 1.2.6 OpenAI adapter
                                      └─> 1.2.16 edit tool
                                             └─> 1.3.3 SSIM benchmark
                                                    └─> 1.4.4 Acceptance
```

Identity-preserving edits (`edit` + SSIM benchmark + EXIF round-trip) are the
critical path because they're the most photographer-visible features. They
gate sponsor acceptance.

---

## Parallelism

Within Phase 1.2, the following packages can run in parallel (no shared files):
- 1.2.7 (metadata) || 1.2.8 (color) || 1.2.9 (raw) || 1.2.20 (logging)
- 1.2.12 (stdio transport) || 1.2.13 (HTTP transport) — share transport interface defined in 1.2.14
- Tool packages 1.2.15, 1.2.16, 1.2.17, 1.2.18 — all depend on adapters but are independent of each other

A single engineer with full context can complete Phase 1.2 in 5–7 working days
at sustainable pace. Multi-engineer parallelism is possible but introduces
coordination overhead not modeled here.

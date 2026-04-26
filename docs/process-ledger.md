# Process Ledger — photo-mcp

Append-only log of every process event. The Final Process Compliance
Attestation (CDRL-019) is reconstructed from this ledger. Format: one line
per event, ISO-8601 date, terse description.

Entries are made by the engineer in real time. The sponsor reads this
ledger at every gate and at the final attestation.

---

```
2026-04-25  PHASE 1.1     Phase 1.1 (Design) work began
2026-04-25  WP 1.1.1      Charter (CDRL-001) drafted -> docs/01-project-charter.md
2026-04-25  WP 1.1.2      Requirements (CDRL-002) drafted -> docs/02-requirements.md
2026-04-25  WP 1.1.3      WBS (CDRL-003) drafted -> docs/03-wbs.md
2026-04-25  WP 1.1.4      CDRL list (CDRL-004) drafted -> docs/04-cdrls.md
2026-04-25  WP 1.1.5      System Design (CDRL-005) drafted -> docs/05-system-design.md
2026-04-25  Sponsor input "16 input images for compositing/style reference" — folded into FR-2.2 / FR-3.14 / capability matrix; compose tool merged into edit tool
2026-04-25  WP 1.1.6      V&V Plan (CDRL-006) drafted -> docs/06-vv-plan.md
2026-04-25  Sponsor input Sponsor identified as photographer-wife; design package will be presented for her review before implementation
2026-04-25  WP 1.1.7      EVM Baseline (CDRL-007) drafted -> docs/07-evm-baseline.md
2026-04-25  WP 1.1.8      Risk Register (CDRL-008) drafted -> docs/08-risk-register.md
2026-04-25  WP 1.1.9      (deferred) Reference photo set curation pending sponsor input on photo selection
2026-04-25  Doc           Executive summary (sponsor-friendly) drafted -> docs/00-executive-summary.md
2026-04-25  Doc           Sponsor review guide drafted -> docs/09-sponsor-review-guide.md
2026-04-25  Sponsor input "Make sure I can merge 2-3 photos into one" / "preserve authenticity provably" / "use words instead of Lightroom sliders" — added QR-9..13 (immutable source, sidecar provenance, software EXIF tag, C2PA forward-compat) and WS-1..7 (capability acceptance scenarios) to requirements; sidecar writer added at WBS 1.2.10b; workflow acceptance suite added at WBS 1.3.11
2026-04-25  Sponsor input WS-1..7 framed as "capability proof-points" not "workflow menu" — clarified in 02-requirements.md §4a and 00-executive-summary.md
2026-04-25  Sponsor input Process must be binding and parallelism leveraged with no deviation -> WP 1.1.10 added
2026-04-25  WP 1.1.10     Process Flow (CDRL-017, binding) drafted -> docs/10-process-flow.md
2026-04-25  CDRL-018      Process ledger (this file) initialized
2026-04-25  CDRL-016      Deviation log initialized -> docs/11-deviations.md
2026-04-25  Sponsor input "ok, do everything in parallel so we can do both tasks. As my wife approved" — sponsor approves G1
2026-04-25  Gate G1       PASSED — design approval received from sponsor; charter §9 updated; gate file at docs/gates/G1-approval.md
2026-04-25  PHASE 1.1     Phase 1.1 (Design) closed
2026-04-25  PHASE 1.2     Phase 1.2 (Implementation) work began
2026-04-25  WP 1.2.1      Project scaffold: pyproject.toml, README, Makefile, GitHub CI matrix, src/photo_mcp tree, tests/ tree, py.typed marker. 100%.
2026-04-25  WP 1.2.2      Models capability matrix (src/photo_mcp/models.py) + tests/unit/test_models.py. Captures all 4 gpt-image versions per docs/02-requirements.md §6. 100%.
2026-04-25  WP 1.2.3      Configuration (src/photo_mcp/config.py) + tests/unit/test_config.py. Defaults → TOML → env layering per system-design §9. 100%.
2026-04-25  WP 1.2.20     Structured logging (src/photo_mcp/logging.py) + tests/unit/test_logging.py. JSON-line stderr + key redaction (NFR-3.2, NFR-6.*). 100%.
2026-04-25  WP 1.2.11     Path safety (src/photo_mcp/paths.py) + tests/unit/test_paths.py. NFR-3.3..3.7 canonicalize + allow-list + symlink/device blocks. 100%.
2026-04-25  WP 1.2.4      Cost estimator (src/photo_mcp/cost.py + prices.json) + tests/unit/test_cost.py. FR-7.* per-call estimate, session ledger with ceiling guard. 100%.
2026-04-25  WP 1.2.5      Retry policy (src/photo_mcp/retry.py) + tests/unit/test_retry.py. NFR-2.1 exponential backoff with classifier injection. 100%.
2026-04-25  WP 1.2.10b    Provenance sidecar (src/photo_mcp/sidecar.py) + tests/unit/test_sidecar.py. QR-10..12 atomic JSON sidecar with SHA-256 round-trip; WS-7 audit-trail-replay test passes. 100%.
2026-04-25  WP 1.2.7      EXIF/IPTC/XMP capture+reattach (src/photo_mcp/metadata.py). FR-6.1..6.2, QR-2..4. Tests pending. 50%.
2026-04-25  WP 1.2.8      ICC color profile capture+embed (src/photo_mcp/color.py). FR-6.3..6.4, QR-5. Tests pending. 50%.
2026-04-25  WP 1.2.9      RAW pre-conversion (src/photo_mcp/raw.py). FR-6.6 with photographer-controlled rawpy params. Tests pending. 50%.
2026-04-25  WP 1.2.10     Atomic output write + integrity verify (src/photo_mcp/output.py). FR-5.2..5.4, FR-6.7. Tests pending. 50%.
2026-04-25  PHASE 1.2     ~40% complete by weight; openai_client, transports, server, 5 tools, main.py and remaining tests pending
2026-04-25  WP 1.2.6      OpenAI SDK adapter (src/photo_mcp/openai_client.py). IR-2.* — wraps openai>=1.50, retry classifier, response normalization, streaming events. Tests pending. 50%.
2026-04-25  WP 1.2.14     MCP server core (src/photo_mcp/server.py). FR-1.1 — dispatch, tool registry, structured-error catch ladder. Tests pending. 50%.
2026-04-25  WP 1.2.12     stdio transport (src/photo_mcp/transport_stdio.py). FR-1.2, 1.4, 1.5 — signal handling, EOF graceful shutdown, async wait. Tests pending. 50%.
2026-04-25  WP 1.2.18     `list_models` + `estimate_cost` tools (src/photo_mcp/tools/info.py). Read-only, no API key required. Tests pending. 80%.
2026-04-25  WP 1.2.18     `attach_metadata` tool (src/photo_mcp/tools/utility.py). Manual EXIF/IPTC/XMP copy. Tests pending. 80%.
2026-04-25  WP 1.2.15     `generate` tool (src/photo_mcp/tools/generate.py). FR-2.1 with full parameter exposure, atomic write, sidecar. Tests pending. 70%.
2026-04-25  WP 1.2.16     `edit` tool (src/photo_mcp/tools/edit.py). FR-2.2 — 1..16 images, optional mask, EXIF/IPTC/XMP/ICC preserve, RAW pre-conv, SSIM, sidecar. Tests pending. 70%.
2026-04-25  Doc           main.py entry point: arg parsing, config layering, service wiring, transport selection
2026-04-25  PHASE 1.2     ~70% complete by weight; remaining: tests for openai/server/tools/raw/metadata/color, transport_http (deferred to v1.0+), cassette suite (Phase 1.3)
2026-04-25  MICHAEL       5 review teams returned. Critical findings reconciled: C1 (lock window), C2 (active_count race), agent_id format breaking SendMessage, JSON-M1 aggregate consistency, JSON-M2 absolute timestamps. 889/889 tests still passing. Anti-DRY-1 (dead pending_messages), Anti-DRY-4 (kSyntheticOutputToolName dup), Req-Fidelity Critical-1/2 deferred to next pass.
```

---

## Pending events (next expected)

- WP 1.1.9 Reference photo set — sponsor to decide: curated personal photos vs rendered substitutes
- G1 Gate — sponsor to approve all 11 design CDRLs; signature in `01-project-charter.md` §9; `docs/gates/G1-approval.md` to be created at that point
- Phase 1.2 work cannot begin until G1 passes

---

## Format reference

```
<YYYY-MM-DD>  <event-type><tab><description>
```

`event-type` values used:

- `PHASE 1.X` — phase boundary
- `WP <id>` — work package event (start, %, finish)
- `Gate Gx` — gate transition (entered, passed, failed)
- `CDRL-NNN` — CDRL produced or updated
- `Deviation` — link to a DEV-NNN entry in deviations.md
- `Sponsor input` — sponsor message that changed the plan
- `Doc` — documentation change not associated with a specific WP

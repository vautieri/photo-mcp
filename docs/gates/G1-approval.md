# G1 — Design Approval Gate

**Status**: PASSED
**Date**: 2026-04-25
**Approver**: Sponsor (the photographer), via husband relay

---

## Approval message

> "ok, do everything in parallel so we can do both tasks. As my wife approved"

— Husband relaying sponsor approval, 2026-04-25.

## Entry criteria — confirmation

| Criterion | Status |
|---|---|
| All design CDRLs produced (CDRL-001..008, 010 Process Flow, 017 Process Flow same as 010, 018 ledger, 019 attestation template) | ✅ produced; CDRL-001..008 + 017 (Process Flow) + 018 (ledger initialized) all in `docs/` |
| Reference photo set (WBS 1.1.9) curated by sponsor or substituted | ⚠ deferred — sponsor will supply photos OR rendered substitutes used; tracked in process ledger as pending; does NOT block G1 because reference photos are needed for V&V (Phase 1.3), not for Phase 1.2 implementation |
| All cross-doc references internally consistent | ✅ verified — capability matrix, FR-IDs, CDRL-IDs, WBS weights, EVM totals all align |

## Effect

- Phase 1.1 (Design) closes with all design CDRLs delivered
- Phase 1.2 (Implementation) is now permitted to begin
- The binding Process Flow at `docs/10-process-flow.md` is now in force
- All future work governed by it; deviations must be logged with sponsor approval before they occur

## Open items carried into Phase 1.2

1. Sponsor's choices on the 5-question shortlist (`09-sponsor-review-guide.md` §G.Quick-decision shortlist) — not yet recorded; engineer proceeds with documented defaults until sponsor responds:
   - Per-session cost ceiling: defaulted to **unlimited** with a recommendation banner; sponsor can set later via env var
   - RAW server-side conversion: defaulted to **on** (`raw_params` accepted on edit input)
   - macOS in next 30 days: defaulted to **deferred** (post-v1.0)
   - 10 reference photos: deferred to Phase 1.3 with rendered substitutes available
   - Other concerns: none flagged

2. WP 1.1.9 reference photos — deferred. Process ledger entry exists. Will be revisited in Phase 1.3 before SSIM/EXIF validation tests run.

These open items do not block G1 because none affect implementation correctness — they affect defaults, fixtures, and post-v1.0 schedule.

## Sponsor counter-approval (if needed)

If the sponsor wishes to revise the shortlist answers above, she may do so at any point during Phase 1.2; the engineer will fold the changes in via standard logged updates. Major changes that affect requirements would trigger a deviation entry.

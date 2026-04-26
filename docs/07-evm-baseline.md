# Earned Value Management Baseline — photo-mcp v1.0

**Version**: 0.1.0
**Date**: 2026-04-25

---

## 1. Purpose

Establish the planned-value (PV) curve, work-package weights, and earned-value
(EV) measurement method so progress is tracked against a baseline rather than
guessed. EVM here is lightweight — appropriate for a single-engineer project
with one sponsor — but follows standard PMI/DoD definitions.

---

## 2. Definitions

| Acronym | Meaning |
|---|---|
| **BAC** | Budget at Completion — total project weight (100%) |
| **PV** | Planned Value — % weight scheduled to be complete by date |
| **EV** | Earned Value — % weight actually complete by date (binary or 0/50/100 per WP) |
| **AC** | Actual Cost — engineering hours actually expended |
| **CV** | Cost Variance = EV − AC (in % weight terms; AC normalized) |
| **SV** | Schedule Variance = EV − PV |
| **CPI** | Cost Performance Index = EV / AC |
| **SPI** | Schedule Performance Index = EV / PV |

Healthy: SPI ≥ 0.9, CPI ≥ 0.9. Watch: 0.8 ≤ SPI < 0.9. Action required:
SPI < 0.8.

---

## 3. Work-package weights (rolled up from WBS doc 03)

| Phase | % weight | Cumulative |
|---|---|---|
| 1.1 Design (10 docs incl. binding Process Flow) | 18.5% | 18.5% |
| 1.2 Implementation (20 packages, incl. sidecar writer 1.2.10b) | 39.5% | 58.0% |
| 1.3 Verification (11 packages, incl. workflow acceptance 1.3.11) | 22.5% | 80.5% |
| 1.4 Packaging & Acceptance (5 packages, incl. final compliance attestation 1.4.5) | 6.5% | 87.0% |
| Reserve (issue triage, cassette refresh, doc refinement, macOS port window) | 13.0% | 100.0% |

Reserve is held separately; EVM tracks the 87.0% of explicit work. BAC for
EVM purposes = 100% (reserve consumed only against documented overrun).

---

## 4. Earned-value rule per work package

Each WP earns value via **0/50/100 rule**:
- 0% — not started
- 50% — started, deliverable in draft
- 100% — deliverable accepted (CDRL approved by sponsor or test passes)

Tracked at the work-package granularity, not activity granularity.

---

## 5. Planned schedule

(Calendar dates depend on sponsor approval timing. Schedule below is
relative to "Day 0 = sponsor approves the design package".)

### 5.1 Phase 1.1 — Design (in progress, this package)

Engineer is producing the 8 design docs in the order CDRL-001..008.
Phase 1.1 is **already at 50% EV** (charter, requirements, WBS, CDRL,
system design, V&V plan written; EVM baseline + Risk Register pending;
none yet sponsor-approved). When sponsor signs off, all 8 reach 100%.

### 5.2 Phase 1.2 — Implementation

Estimated 102 engineering-hours = ~13 working days at 8 eh/day, but
sustainable pace targets 5–7 calendar days with overlap to 1.3 build-out.

| Day (rel) | PV cumulative | Work delivered |
|---|---|---|
| 0 | 17.5% | Phase 1.1 complete + approved |
| 1 | 22% | 1.2.1 scaffold, 1.2.3 config, 1.2.20 logging |
| 2 | 28% | 1.2.2 models, 1.2.4 cost, 1.2.5 retry |
| 3 | 35% | 1.2.6 OpenAI adapter, 1.2.11 paths |
| 4 | 42% | 1.2.7 metadata, 1.2.8 color, 1.2.9 raw, 1.2.10 output |
| 5 | 48% | 1.2.12 stdio transport, 1.2.14 server core |
| 6 | 53% | 1.2.13 HTTP transport, 1.2.18 streaming relay |
| 7 | 55.5% | 1.2.15 generate, 1.2.16 edit, 1.2.17 info+utility tools |

### 5.3 Phase 1.3 — Verification

| Day (rel) | PV cumulative | Work delivered |
|---|---|---|
| 8 | 60% | 1.3.2 cassette suite, 1.3.6 cost accuracy |
| 9 | 66% | 1.3.3 SSIM, 1.3.4 EXIF, 1.3.5 color round-trip |
| 10 | 71% | 1.3.7 cross-platform CI, 1.3.8 perf, 1.3.9 security |
| 11 | 75% | 1.3.10 live-API smoke + cassette refresh |

### 5.4 Phase 1.4 — Packaging & Acceptance

| Day (rel) | PV cumulative | Work delivered |
|---|---|---|
| 12 | 78% | 1.4.1 wheel, 1.4.2 standalone binaries |
| 13 | 80% | 1.4.3 user docs |
| 14 | 80.5% | 1.4.4 sponsor acceptance run + sign-off |

---

## 6. Tracking

A single tracking table (`docs/evm-status.md`, generated weekly) shows:

| WP | Weight | Status (0/50/100) | EV | PV at this date | EV − PV |
|---|---|---|---|---|---|
| 1.1.1 Charter | 1.5% | 100% | 1.5% | 1.5% | 0 |
| 1.1.2 Requirements | 3.0% | 100% | 3.0% | 3.0% | 0 |
| 1.1.3 WBS | 1.0% | 100% | 1.0% | 1.0% | 0 |
| 1.1.4 CDRL | 1.0% | 100% | 1.0% | 1.0% | 0 |
| 1.1.5 System Design | 4.5% | 100% | 4.5% | 4.5% | 0 |
| 1.1.6 V&V Plan | 3.0% | 100% | 3.0% | 3.0% | 0 |
| 1.1.7 EVM (this) | 1.5% | 100% | 1.5% | 1.5% | 0 |
| 1.1.8 Risk Register | 1.0% | 0% | 0% | 1.0% | -1.0% |
| 1.1.9 Reference photos | 1.0% | 0% | 0% | 1.0% | -1.0% (post-approval) |
| Phase 1.2 (rolled) | 38.0% | 0% | 0% | 0% | 0 |
| Phase 1.3 (rolled) | 19.5% | 0% | 0% | 0% | 0 |
| Phase 1.4 (rolled) | 5.5% | 0% | 0% | 0% | 0 |
| **Totals** | **80.5%** | | **15.5%** | **17.5%** | **-2.0%** |

(Snapshot as of 2026-04-25, before Risk Register and reference photo
curation are complete. Once those land and sponsor approves, EV catches up
to PV at 17.5%.)

---

## 7. Reporting cadence

- **Daily** (during Phase 1.2 / 1.3): one-line status in commit messages —
  "WP 1.2.6 → 100% (cassette tests passing)"
- **Weekly**: regenerate `docs/evm-status.md` and post to sponsor with SPI/CPI,
  notable variances, and any reserve consumption
- **Phase gate**: full status report; sponsor reviews variance and approves
  next phase

---

## 8. Reserve consumption rules

Reserve (19.5%) may be drawn against only when:

1. A risk in the Risk Register materializes and triggers its mitigation budget, OR
2. A defect found in V&V requires un-budgeted rework, OR
3. OpenAI API drift requires cassette refresh + parameter-matrix re-verification mid-build

Each reserve draw is logged in `docs/11-deviations.md` (CDRL-016) with
sponsor approval. Reserve is depleted, not re-budgeted, when consumed.

---

## 9. Termination criteria

The engineer SHALL halt and escalate to sponsor if any of the following:

- Total EV − PV ≤ −15% (project is significantly behind)
- Reserve is fully consumed before Phase 1.4 begins
- A MUST requirement is found unfeasible given the OpenAI API surface
- Sponsor declines to approve a CDRL twice (indicating a design impasse)

In any of these conditions, the project is not delivered until the sponsor
re-baselines or re-scopes.

---

## 10. Approval

| Role | Signature | Date |
|---|---|---|
| Sponsor | _pending_ | |
| Lead engineer | committed via this document | 2026-04-25 |

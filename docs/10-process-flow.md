# Process Flow — photo-mcp

**Status**: BINDING — this document is a MUST-FOLLOW process specification
for the entire project. Deviations are forbidden unless explicitly logged
in `docs/11-deviations.md` (CDRL-016) and approved by the sponsor.

**Version**: 0.1.0
**Date**: 2026-04-25

---

## 0. Why this document is binding

The sponsor has set the bar: design first, no shortcuts, real tests, no
silent deviations. This Process Flow is how that bar is enforced. Every
phase has a gate, every gate has an approval, every approval is recorded.
At delivery the engineer attests — and the sponsor verifies — that the
process was followed without any unlogged deviation.

If this document and any other doc in the package conflict, **this document
wins** for process matters; the conflicting doc is updated to align.

---

## 1. Phase model — sequential, gated

The project moves through four phases. Phases run **sequentially**: a phase
cannot begin until its predecessor's gate has passed. Within a phase, work
packages may run in parallel where their dependencies allow (see §3).

```
        ┌──────────────────────────┐
        │ Phase 1.1 — Design        │
        │ docs 00..09 produced      │
        └────────────┬──────────────┘
                     │
                ◆ Gate G1: Design Approval ◆
                     │
        ┌────────────▼──────────────┐
        │ Phase 1.2 — Implementation │
        │ src/photo_mcp/** built     │
        │ unit tests pass            │
        └────────────┬──────────────┘
                     │
                ◆ Gate G2: Implementation Complete ◆
                     │
        ┌────────────▼──────────────┐
        │ Phase 1.3 — Verification   │
        │ V&V Plan executed          │
        │ all MUST reqs verified     │
        └────────────┬──────────────┘
                     │
                ◆ Gate G3: V&V Pass ◆
                     │
        ┌────────────▼──────────────┐
        │ Phase 1.4 — Packaging +    │
        │  Sponsor Acceptance        │
        └────────────┬──────────────┘
                     │
                ◆ Gate G4: Sponsor Sign-Off ◆
                     │
                  Delivery
                     │
        ┌────────────▼──────────────┐
        │ Final Process Compliance  │
        │ Attestation + sponsor      │
        │ verification (§7)          │
        └────────────────────────────┘
```

**No phase may begin work until its preceding gate has passed.** No work
package may be started, even speculatively, before the gate clears.

---

## 2. Gate definitions

### G1 — Design Approval

**Entry criteria** (all MUST be true):
- All design CDRLs produced: `docs/00-executive-summary.md`,
  `01-project-charter.md`, `02-requirements.md`, `03-wbs.md`,
  `04-cdrls.md`, `05-system-design.md`, `06-vv-plan.md`,
  `07-evm-baseline.md`, `08-risk-register.md`, `09-sponsor-review-guide.md`,
  `10-process-flow.md` (this doc)
- Reference photo set (WBS 1.1.9) curated by sponsor or substituted
- All cross-doc references are internally consistent (no FR-X cited that
  doesn't exist; WBS weights sum correctly; CDRLs reference real work
  packages)

**Approval action**: sponsor records approval in
`01-project-charter.md` §9 (signature block) — date + brief affirmation.
Engineer countersigns.

**Exit artifact**: `docs/gates/G1-approval.md` — copy of the signed
charter §9 + a one-line statement "G1 passed on `<date>`."

**Forbidden until G1 passes**: any work in `src/`, any code commit, any
test fixture beyond reference photos, any cassette recording.

### G2 — Implementation Complete

**Entry criteria**:
- All MUST-priority FR/NFR/IR/QR requirements have at least one passing
  unit test
- All Phase 1.2 work packages reach 100% EV (per WBS doc 03)
- `pytest --cov=photo_mcp --cov-fail-under=90` passes locally
- `mypy --strict` clean on `src/photo_mcp/`
- `ruff` + `black` clean
- CI green on `windows-latest` and `ubuntu-latest`

**Approval action**: engineer self-attests in `docs/gates/G2-attestation.md`
listing the satisfied entry criteria with evidence pointers (commit
SHAs, CI run IDs, coverage report path). Sponsor reviews; if any criterion
unmet or evidence inadequate, gate is **not** passed and engineer returns
to Phase 1.2 work.

**Exit artifact**: `docs/gates/G2-attestation.md` signed by both.

**Forbidden until G2 passes**: V&V execution beyond unit tests; Phase 1.4
packaging.

### G3 — V&V Pass

**Entry criteria**:
- Every requirement traceability row in `06-vv-plan.md` §4 has a
  passing test ID
- All cassettes from §5 (22 minimum) recorded and replaying clean
- All workflow acceptance scenarios (WS-1..7) pass per §10a methodology
- Live-API smoke run executed within 7 days, estimate accuracy ≤ 2%
- Performance benchmarks within NFR-1.* thresholds
- Security suite passes (path traversal, SSRF, key redaction)

**Approval action**: engineer produces `docs/12-vv-report.md` (CDRL-012)
that maps every requirement to its evidence; sponsor reviews.

**Exit artifact**: `docs/gates/G3-pass.md` referencing the V&V Report.

**Forbidden until G3 passes**: any release tag, distributable build for
sponsor delivery.

### G4 — Sponsor Sign-Off

**Entry criteria**:
- Wheel + standalone binary built and smoke-tested
- User docs (README, tools.md) complete
- Sponsor performs an acceptance run with the live API key
- All MUST defects from acceptance run fixed; all SHOULD defects either
  fixed or accepted in `docs/11-deviations.md`

**Approval action**: sponsor signs `docs/09-acceptance-log.md` (CDRL-015).

**Exit artifact**: `docs/gates/G4-signoff.md` referencing the acceptance
log.

**Forbidden until G4 passes**: declaring v1.0 delivered.

---

## 3. Parallelism rules

The principle: **parallelize where dependencies allow; never short-circuit
a sequence the dependencies require.**

### 3.1 Phase 1.1 (Design) parallelism

After charter (1.1.1) and requirements (1.1.2) are written, the following
docs may be drafted in parallel:

```
1.1.1 charter
   └─► 1.1.2 requirements
            ├─► 1.1.3 WBS ────► 1.1.4 CDRL list
            │                  │
            │                  └─► 1.1.7 EVM Baseline
            └─► 1.1.5 System Design ──► 1.1.6 V&V Plan
                                    └─► 1.1.8 Risk Register
                                    └─► 1.1.9 Reference photos
```

Subagents may be tasked with drafting independent docs, but the engineer
remains the integrator and is responsible for cross-consistency. The
final design package is reviewed for consistency before G1.

### 3.2 Phase 1.2 (Implementation) parallelism

Work packages with no shared file may run in parallel. From WBS doc 03 §
Parallelism:

- 1.2.7 metadata || 1.2.8 color || 1.2.9 raw || 1.2.20 logging
- 1.2.12 stdio transport || 1.2.13 HTTP transport (share the interface
  defined by 1.2.14, which is sequential first)
- Tool packages 1.2.15 generate, 1.2.16 edit, 1.2.17 info+utility — all
  depend on adapters but are independent of each other once adapters land

Subagents performing parallel work get strict file-ownership briefs to
prevent merge conflicts.

### 3.3 Phase 1.3 (Verification) parallelism

- Cassette suite (1.3.2) || quality benchmarks (1.3.3, 1.3.4, 1.3.5) ||
  performance (1.3.8) || security (1.3.9)
- Workflow acceptance (1.3.11) runs after the implementation package each
  workflow needs; multiple workflows can be tested in parallel runs

### 3.4 Phase 1.4 parallelism

- Wheel build (1.4.1) || PyInstaller binary builds (1.4.2 — Win + Linux
  in parallel via CI matrix)
- User docs (1.4.3) can draft during 1.3 since they depend on the API
  surface, not on test results

### 3.5 Hard constraints on parallelism

- Cross-phase parallelism is **forbidden**. No Phase 1.2 work begins before
  G1; no Phase 1.3 work begins before G2; etc.
- Sponsor approval activities are **never parallelized with engineering**
  work that depends on them. If the sponsor is reviewing the design,
  engineering does not begin coding.
- Two work packages that share a file are **never parallelized** — the
  one with earlier start time finishes first; the second begins only
  after.

---

## 4. Deliverable discipline

Every CDRL listed in `04-cdrls.md` MUST be produced before the gate that
references it. Missing a CDRL is a gate failure, regardless of how complete
the rest of the work appears.

The CDRL → gate mapping:

| Gate | CDRLs that MUST be complete |
|---|---|
| G1 | CDRL-001..008 + 010-Process-Flow |
| G2 | CDRL-009 (source repo at the milestone tag); evidence for entry criteria |
| G3 | CDRL-010 (test artifacts), CDRL-011 (coverage), CDRL-012 (V&V report) |
| G4 | CDRL-013 (distributables), CDRL-014 (user docs), CDRL-015 (acceptance log) |

CDRL-016 (deviation log) is continuous — it is reviewed at every gate and
may be empty.

---

## 5. Deviation discipline

A deviation is **any** action that:

- Skips a CDRL
- Begins work before its gate
- Ships with a MUST requirement unverified or marked accepted-as-deferred
- Introduces a behavior not described in the requirements (e.g., a
  background service the user did not ask for)
- Modifies the process described in this document

**No deviation is permitted without a logged entry in
`docs/11-deviations.md` (CDRL-016) approved by the sponsor before the
deviation occurs (or, if discovered post-hoc, before the next gate).**

Every deviation log entry MUST contain:
- Date
- What rule was deviated from (section reference)
- Why
- Sponsor approval (signature / message reference)
- Scope (one-time / persistent until v1.X)
- Impact on requirements / weights / schedule

---

## 6. Audit trail

The engineer maintains a running ledger of process events at
`docs/process-ledger.md`. Each entry is one line, append-only, dated:

```
2026-04-25  G1 entered   Charter approved by sponsor; commit a1b2c3d
2026-04-26  WP 1.2.1     Started by engineer
2026-04-26  WP 1.2.1     100% — scaffold tests passing; commit d4e5f6g
2026-04-27  Deviation    1.2.10b sidecar atomicity changed from tmp+rename
                         to write-lock; logged in deviations.md DEV-002;
                         sponsor approved 2026-04-27
2026-04-28  G2 entered   Implementation complete; coverage 92%; commit ...
…
```

The ledger is the source of truth at delivery — the final attestation
(§7) is generated from it.

---

## 7. Final Process Compliance Attestation (delivery)

At Phase 1.4 close, the engineer produces
`docs/13-process-compliance-attestation.md`. It contains:

1. **Phase summary** — for each phase, the start date, end date, gate
   passed, gate approver, and a list of CDRLs delivered
2. **Parallelism log** — which packages ran in parallel, how concurrency
   was controlled, any contention resolved
3. **Deviation summary** — total count of logged deviations, link to each,
   sponsor approval reference for each
4. **Process audit** — a per-clause compliance check against this Process
   Flow document. For each clause (G1, G2, G3, G4, parallelism rules,
   deliverable discipline, deviation discipline, audit trail), the
   engineer asserts "Followed" with evidence pointer, OR "Deviated" with
   reference to the deviation log entry

5. **Engineer's attestation**:

   > "I attest that the process described in `docs/10-process-flow.md`
   > version 0.1.0 was followed for the entirety of photo-mcp v1.0.
   > No undeclared deviations occurred. Every deviation declared in
   > `docs/11-deviations.md` was approved by the sponsor prior to or
   > immediately upon discovery, and is reconciled in this attestation.
   > Signed: <engineer>, <date>."

6. **Sponsor verification** — sponsor reviews the attestation against
   their own records (commit history, message logs, deviation log) and
   signs:

   > "I have reviewed the process compliance attestation and verified
   > the audit trail in `docs/process-ledger.md`. The process was
   > followed; deviations are accounted for. Signed: <sponsor>, <date>."

7. **Discrepancy resolution** — if the sponsor finds an undeclared
   deviation in their review, the project does **not** close. The
   engineer files a retrospective deviation entry and the gate is
   re-evaluated.

---

## 8. Process changes

This Process Flow document may be revised mid-project, but only via:

1. Engineer drafts the proposed change as `docs/10-process-flow.md@v0.X+1`
2. Sponsor approves
3. Old version is preserved at `docs/archive/10-process-flow.v0.X.md`
4. The change itself is logged as a deviation entry referencing the
   old → new version

A process change is **never silent**. The audit trail and final
attestation reference whichever version was in force at each moment.

---

## 9. Failure modes

If the engineer cannot achieve a gate, the engineer:

1. Halts further work
2. Notifies the sponsor with the unmet criterion(a)
3. Proposes either a deviation, a re-baseline (revise WBS / EVM), or a
   scope reduction (deferred-to-v1.1 list)
4. Resumes only after sponsor decision is logged

The engineer does **not** unilaterally lower the bar to claim a gate.

---

## 10. Sponsor's role

The sponsor's process role is approval authority for:
- All CDRLs requiring sponsor approval (per `04-cdrls.md`)
- Each gate (G1..G4)
- Every deviation
- The final compliance attestation

The sponsor is not expected to write code, draft requirements, or run
tests. The sponsor IS expected to:
- Read and approve (or revise) design docs
- Run the acceptance test (Phase 1.4) on a real workstation
- Verify the final attestation against their own observation of the
  project's progress

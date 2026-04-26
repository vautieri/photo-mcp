# CDRL List — Contract Data Requirements List

**Project**: photo-mcp v1.0
**Date**: 2026-04-25
**Format**: DID-style entries — each row is a delivered artifact with format, due date, distribution, approval authority, and acceptance criteria. Adapted from MIL-STD-963 conventions for a software project of this size.

---

## Conventions

- **CDRL #** sequential identifier
- **Title** human-readable name
- **Source WBS** the work package that produces it (doc 03)
- **DID ref** the Data Item Description analog — the spec document this artifact must conform to
- **Format** delivered artifact format (file type)
- **Frequency** one-time / per-release / monthly / on-event
- **Due date** absolute or relative to a milestone
- **Distribution** sponsor / internal / public
- **Approval authority** who signs off
- **Acceptance criteria** what makes the artifact "delivered"

---

## CDRL List

### CDRL-001 — Project Charter

| Field | Value |
|---|---|
| Source WBS | 1.1.1 |
| DID ref | docs/01-project-charter.md |
| Format | Markdown, GitHub-flavored |
| Frequency | One-time, revisable |
| Due | End of Phase 1.1, before any code |
| Distribution | Sponsor + project repo |
| Approval | Sponsor |
| Acceptance | Sponsor signature in §9 of the charter |

### CDRL-002 — Requirements Document

| Field | Value |
|---|---|
| Source WBS | 1.1.2 |
| DID ref | docs/02-requirements.md |
| Format | Markdown with traceability matrix |
| Frequency | One-time, revisable on requirement change |
| Due | End of Phase 1.1, before any code |
| Distribution | Sponsor + project repo |
| Approval | Sponsor |
| Acceptance | Every FR/NFR/IR/QR/ER has a Priority, Description, Verification method; capability matrix matches the published OpenAI API for the four supported models |

### CDRL-003 — Work Breakdown Structure

| Field | Value |
|---|---|
| Source WBS | 1.1.3 |
| DID ref | docs/03-wbs.md |
| Format | Markdown |
| Frequency | One-time, revisable on scope change |
| Due | End of Phase 1.1 |
| Distribution | Sponsor + project repo |
| Approval | Sponsor |
| Acceptance | All work packages have effort estimate, dependencies, deliverable, and weight; weights sum to ≤100% |

### CDRL-004 — CDRL List (this document)

| Field | Value |
|---|---|
| Source WBS | 1.1.4 |
| DID ref | docs/04-cdrls.md |
| Format | Markdown |
| Frequency | One-time, revisable |
| Due | End of Phase 1.1 |
| Distribution | Sponsor + project repo |
| Approval | Sponsor |
| Acceptance | Every project deliverable in WBS has a CDRL entry |

### CDRL-005 — System Design Document (SDD)

| Field | Value |
|---|---|
| Source WBS | 1.1.5 |
| DID ref | docs/05-system-design.md |
| Format | Markdown with embedded diagrams (ASCII or PlantUML source) |
| Frequency | One-time, revisable |
| Due | End of Phase 1.1, gate to Phase 1.2 |
| Distribution | Sponsor + project repo |
| Approval | Sponsor |
| Acceptance | Architecture covers all FR/NFR; module dependency graph is acyclic; every requirement traces to one or more design components |

### CDRL-006 — Verification & Validation Plan

| Field | Value |
|---|---|
| Source WBS | 1.1.6 |
| DID ref | docs/06-vv-plan.md |
| Format | Markdown |
| Frequency | One-time, revisable on requirement change |
| Due | End of Phase 1.1 |
| Distribution | Sponsor + project repo |
| Approval | Sponsor |
| Acceptance | Every requirement with verification=T (Test) is mapped to one or more named test IDs; cassette strategy documented; SSIM benchmark methodology documented |

### CDRL-007 — EVM Baseline

| Field | Value |
|---|---|
| Source WBS | 1.1.7 |
| DID ref | docs/07-evm-baseline.md |
| Format | Markdown with planned-value curve table |
| Frequency | One-time at design phase end; updated weekly during execution |
| Due | End of Phase 1.1; updates every Friday |
| Distribution | Sponsor |
| Approval | Sponsor (initial); engineer logs subsequent updates |
| Acceptance | All WBS work packages have % weight assigned; weights sum to ≤ 100%; PV curve published |

### CDRL-008 — Risk Register

| Field | Value |
|---|---|
| Source WBS | 1.1.8 |
| DID ref | docs/08-risk-register.md |
| Format | Markdown table |
| Frequency | Updated on event (new risk identified, mitigation closed) |
| Due | Initial at end of Phase 1.1; updated on event |
| Distribution | Sponsor + project repo |
| Approval | Engineer (no sponsor approval needed for additions); sponsor consulted on accepting any risk with impact ≥ High |
| Acceptance | Each risk has Likelihood × Impact, owner, status, and either mitigation or explicit acceptance |

### CDRL-009 — Source code repository

| Field | Value |
|---|---|
| Source WBS | 1.2.* |
| DID ref | Repository at the project location, branch `main` |
| Format | Git repository, public commit history, signed tags for releases |
| Frequency | Continuous during Phase 1.2; tagged at v1.0 |
| Due | Phase 1.2 gate; v1.0 tag at Phase 1.4 close |
| Distribution | Sponsor (read access) + project repo |
| Approval | Engineer (commits); sponsor (release tag) |
| Acceptance | Lint/format/type checks pass; unit tests pass; coverage ≥90%; no TODOs in production paths |

### CDRL-010 — Test artifacts

| Field | Value |
|---|---|
| Source WBS | 1.3.* |
| DID ref | `tests/` directory, including unit, integration cassettes, quality benchmarks |
| Format | Python test files, YAML cassettes (vcr.py format), reference photos in `tests/fixtures/` |
| Frequency | Continuous during 1.3 |
| Due | Phase 1.3 gate |
| Distribution | Sponsor + project repo |
| Approval | Sponsor |
| Acceptance | All tests in V&V Plan pass on Windows + Linux CI; cassette files committed; reference photos curated and licensed for project use |

### CDRL-011 — Coverage report

| Field | Value |
|---|---|
| Source WBS | 1.3.7 |
| DID ref | `coverage.xml` + HTML report |
| Format | coverage.py output, HTML report directory |
| Frequency | Per CI run; final at Phase 1.3 gate |
| Due | Phase 1.3 gate |
| Distribution | Sponsor |
| Approval | Sponsor reviews; engineer attests ≥90% |
| Acceptance | Lines coverage ≥ 90% on `photo_mcp/` modules |

### CDRL-012 — V&V report

| Field | Value |
|---|---|
| Source WBS | 1.3 close-out |
| DID ref | `docs/10-vv-report.md` (generated) |
| Format | Markdown summary with pass/fail per requirement, traceability filled in |
| Frequency | One-time at Phase 1.3 gate |
| Due | Phase 1.3 gate |
| Distribution | Sponsor |
| Approval | Sponsor |
| Acceptance | Every MUST requirement is marked Pass with link to evidence; SHOULD requirements are Pass or have logged deviation |

### CDRL-013 — Distributable artifacts

| Field | Value |
|---|---|
| Source WBS | 1.4.1, 1.4.2 |
| DID ref | wheel + standalone binaries |
| Format | `.whl` (PyPI), `.exe` (Windows), `linux-x86_64` (ELF) |
| Frequency | Per release |
| Due | Phase 1.4 gate |
| Distribution | Sponsor (initially); PyPI public after sponsor sign-off if desired |
| Approval | Sponsor |
| Acceptance | Sponsor installs via wheel and runs against live API key without errors |

### CDRL-014 — User documentation

| Field | Value |
|---|---|
| Source WBS | 1.4.3 |
| DID ref | `README.md` + `docs/tools.md` |
| Format | Markdown |
| Frequency | One-time at v1.0; updated per release |
| Due | Phase 1.4 gate |
| Distribution | Public (or sponsor-only if private) |
| Approval | Sponsor |
| Acceptance | Each tool documented with parameters, defaults, examples, photographer-relevant tips; README has install + run instructions for Windows + Linux |

### CDRL-015 — Acceptance log

| Field | Value |
|---|---|
| Source WBS | 1.4.4 |
| DID ref | `docs/09-acceptance-log.md` |
| Format | Markdown — sponsor's acceptance run notes, defects found, sign-off |
| Frequency | One-time at v1.0 |
| Due | Phase 1.4 gate |
| Distribution | Sponsor + project repo |
| Approval | Sponsor signature |
| Acceptance | Sponsor signs; defects either fixed in v1.0.1 patch or accepted in deviation log |

### CDRL-017 — Process Flow (binding)

| Field | Value |
|---|---|
| Source WBS | 1.1.10 (added) |
| DID ref | docs/10-process-flow.md |
| Format | Markdown |
| Frequency | One-time, revisable per its own §8 only |
| Due | End of Phase 1.1 |
| Distribution | Sponsor + project repo |
| Approval | Sponsor |
| Acceptance | Process is internally consistent; gate criteria, parallelism rules, deviation rules, and final attestation procedure all documented; conflicts with other docs are resolved in this doc's favor per §0 |

### CDRL-018 — Process ledger (continuous audit trail)

| Field | Value |
|---|---|
| Source WBS | (continuous, no specific WP) |
| DID ref | docs/process-ledger.md |
| Format | Markdown, append-only one-line entries |
| Frequency | Continuous (every gate transition, every WP start/finish, every deviation) |
| Due | Continuous; final entry at delivery |
| Distribution | Sponsor + project repo |
| Approval | Engineer maintains; sponsor verifies at final attestation |
| Acceptance | Final attestation can be reconstructed from the ledger; no gaps between WP starts and finishes |

### CDRL-019 — Final Process Compliance Attestation

| Field | Value |
|---|---|
| Source WBS | (Phase 1.4 close) |
| DID ref | docs/13-process-compliance-attestation.md |
| Format | Markdown per `10-process-flow.md` §7 template |
| Frequency | One-time at v1.0 delivery |
| Due | Phase 1.4 gate (G4) |
| Distribution | Sponsor |
| Approval | Engineer signs; sponsor verifies and counter-signs |
| Acceptance | Every clause of `10-process-flow.md` checked off "Followed" with evidence, or accounted for in the deviation log; sponsor's verification confirms no undeclared deviation |

### CDRL-016 — Deviation log

| Field | Value |
|---|---|
| Source WBS | (event-driven) |
| DID ref | `docs/11-deviations.md` |
| Format | Markdown table |
| Frequency | On event (any time a SHOULD requirement is not met or a MUST requirement is partially deferred) |
| Due | Continuous |
| Distribution | Sponsor + project repo |
| Approval | Sponsor (each deviation requires sponsor approval) |
| Acceptance | Each deviation has rationale, scope, expected resolution date or "permanent" tag |

---

## Summary table

| CDRL | Title | Due | Approver |
|---|---|---|---|
| 001 | Project Charter | end of design | Sponsor |
| 002 | Requirements | end of design | Sponsor |
| 003 | WBS | end of design | Sponsor |
| 004 | CDRLs (this doc) | end of design | Sponsor |
| 005 | System Design | end of design | Sponsor |
| 006 | V&V Plan | end of design | Sponsor |
| 007 | EVM Baseline | end of design | Sponsor |
| 008 | Risk Register | end of design + on event | Engineer / Sponsor |
| 009 | Source code repo | continuous | Engineer |
| 010 | Test artifacts | end of V&V | Sponsor |
| 011 | Coverage report | end of V&V | Sponsor |
| 012 | V&V Report | end of V&V | Sponsor |
| 013 | Distributables | end of acceptance | Sponsor |
| 014 | User docs | end of acceptance | Sponsor |
| 015 | Acceptance log | end of acceptance | Sponsor |
| 016 | Deviation log | on event | Sponsor |
| 017 | Process Flow (binding) | end of design | Sponsor |
| 018 | Process ledger (continuous) | continuous | Engineer (Sponsor verifies) |
| 019 | Final Compliance Attestation | end of acceptance | Both sign |

---

## Notes

- All CDRLs that require sponsor approval block their dependent phase until approved
- The Risk Register and Deviation Log are "living" — they are reviewed at each phase gate even though they are continuously updated
- No sponsor approval is currently in place; the engineer (Claude) is producing the design package now and will request approval when all 8 design CDRLs are complete

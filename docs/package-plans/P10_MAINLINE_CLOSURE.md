# P10 Package Plan: Mainline Closure

## Package Ralplan

P10 closes the P0-P9 mainline by reconciling the repository's planning docs,
status docs, and verification expectations with the actual shipped CLI and
package records.

P10 does not add new runtime behavior, new workers, new adapters, live
OpenClaw integration, MCP servers, subject commands, or additional doctor
subcommands.

## Reality Check

- P0 is represented by `docs/P0_CONTRACT_REALITY_PASS.md` and
  `tests/test_p0_contracts.py`, not by a package unfreeze record.
- P1-P9 are represented by package unfreeze records under
  `docs/package-reviews/`.
- P1 does not currently have a tracked `docs/package-plans/` plan file; its
  planning evidence was local OMX plan artifacts. P10 must create a tracked P1
  plan summary instead of linking untracked local files.
- The original implementation plan still contains aspirational command surfaces
  such as subject commands and multiple doctor subcommands that are not
  implemented.
- P8 deliberately did not add Codex MCP config, even though earlier strategy
  language mentioned it after CLI stability.
- P9 deliberately shipped a structured-only OpenClaw projection, not rich
  natural-language runtime context, live OpenClaw workspace writes, or
  memory-wiki apply integration.
- Mainline closure is a documentation/status package. It should not mutate
  canonical topology records or generated projection outputs.

## Construction Table

| Small Package | Purpose | Files / Surfaces | Fixtures / Tests | Acceptance Criteria | Stop Condition |
| --- | --- | --- | --- | --- | --- |
| P10.1 P1 plan shim | Add tracked P1 plan summary so every package has public evidence | `docs/package-plans/P1_ENGINE_SKELETON.md` | docs-content test | P1 status links only tracked artifacts | linking untracked `.omx/plans` as public evidence |
| P10.2 Status matrix | Record P0-P9 package status, commits, reviews, and artifacts | `docs/MAINLINE_STATUS.md` | docs-content test | P0 is marked contract reality pass; P1-P9 have tracked plan/review links and final states | inventing unverified evidence |
| P10.3 Plan reality alignment | Mark shipped vs deferred surfaces in the implementation plan | `docs/IMPLEMENTATION_PLAN.md` | docs-content and CLI reality tests | shipped command list matches CLI; deferred surfaces are explicit | changing architecture instead of status |
| P10.4 Closure verification | Add tests that guard status/docs/CLI reality | `tests/test_p10_mainline_closure.py` | unittest + CLI help inspection | docs mention P0-P9 complete, deferred surfaces, shipped CLI, and no live OpenClaw/MCP claim | testing generated local outputs |
| P10.5 Unfreeze record | Record P10 package review and final decision | `docs/package-reviews/P10_UNFREEZE.md` | docs-content test | P10 follows the same package gate it documents | closing without an unfreeze record |

## Team Decision

Do not use `$team` for P10 implementation. The work is a small documentation
and status reconciliation package; one owner is less error-prone.

## Gemini Requirement

Not required by default.

Reason: P10 does not change architecture or adapter behavior; it records final
status and deferrals. Gemini remains not required only if P10 does not change
`SCHEMA.md`, `POLICY.md`, `STORAGE.md`, `QUEUES.md`, adapter behavior, command
contracts, or architecture boundaries, and `docs/IMPLEMENTATION_PLAN.md` edits
are status/deferred annotations. If Reviewer and Critic disagree, Gemini is
required.

## Acceptance Criteria

- `docs/MAINLINE_STATUS.md` exists and states that P0-P9 mainline is complete.
- `docs/MAINLINE_STATUS.md` states that P0 is a contract reality pass, while
  P1-P9 are package-gated unfreeze records.
- `docs/package-plans/P1_ENGINE_SKELETON.md` exists as a tracked P1 plan
  summary.
- `docs/IMPLEMENTATION_PLAN.md` clearly distinguishes shipped mainline commands
  from deferred surfaces.
- Deferred surfaces include:
  - subject commands
  - `doctor queues`
  - `doctor public-safe`
  - `doctor projections`
  - `doctor canonical-parity`
  - audio/video transcript resolver
  - deep social thread expansion resolver
  - Codex topology MCP registration
  - Claude changed-file lint/writeback hooks
  - live OpenClaw adapter/workspace writes
  - OpenClaw queue leases around external writes
  - OpenClaw memory-wiki/QMD import or live validation
  - OpenClaw natural-language runtime context sanitizer
  - OpenClaw file-ref projection with subject-file index
- Tests verify status docs, deferral docs, tracked package links, and CLI
  reality:
  - shipped top-level commands: `init`, `ingest`, `digest`, `reconcile`,
    `apply`, `compose`, `lint`, `doctor`, `writeback`, `agent-guard`
  - shipped compose subcommands: `builder`, `openclaw`
  - shipped doctor subcommand: `stale-anchors`
  - deferred commands are not claimed as shipped: `subject`, `doctor queues`,
    `doctor public-safe`, `doctor projections`, `doctor canonical-parity`
- `docs/package-reviews/P10_UNFREEZE.md` exists before P10 is final.
- Full suite, compile check, lint, Reviewer, and Critic pass before any next
  package starts.

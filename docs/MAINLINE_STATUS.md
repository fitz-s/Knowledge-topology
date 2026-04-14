# Mainline Status

The P0-P9 mainline is complete.

This file records what is shipped, what is deliberately deferred, and what
evidence supports the claim. It is a status document, not a new architecture
contract.

## Evidence Model

- P0 is a contract reality pass, represented by
  `docs/P0_CONTRACT_REALITY_PASS.md` and `tests/test_p0_contracts.py`.
- P1-P9 are package-gated implementation packages, represented by tracked
  package plans and unfreeze records.
- P10 is the mainline closure package.

## Package Matrix

| Package | Status | Plan / Evidence | Review |
| --- | --- | --- | --- |
| P0 Contract Reality Pass | complete | `docs/P0_CONTRACT_REALITY_PASS.md` | `tests/test_p0_contracts.py` |
| P1 Engine Skeleton | approved | `docs/package-plans/P1_ENGINE_SKELETON.md` | `docs/package-reviews/P1_UNFREEZE.md` |
| P2 Source Packet and Fetch V1 | approved | `docs/package-plans/P2_SOURCE_PACKET_FETCH.md` | `docs/package-reviews/P2_UNFREEZE.md` |
| P3 Digest Contract | approved | `docs/package-plans/P3_DIGEST_CONTRACT.md` | `docs/package-reviews/P3_UNFREEZE.md` |
| P4 Reconcile and Mutation | approved | `docs/package-plans/P4_RECONCILE_MUTATION.md` | `docs/package-reviews/P4_UNFREEZE.md` |
| P5 Apply Gate | approved | `docs/package-plans/P5_APPLY_GATE.md` | `docs/package-reviews/P5_UNFREEZE.md` |
| P6 Builder Compose | approved | `docs/package-plans/P6_BUILDER_COMPOSE.md` | `docs/package-reviews/P6_UNFREEZE.md` |
| P7 Writeback, Lint, Doctor | approved | `docs/package-plans/P7_WRITEBACK_LINT_DOCTOR.md` | `docs/package-reviews/P7_UNFREEZE.md` |
| P8 Codex and Claude Integration | approved | `docs/package-plans/P8_CODEX_CLAUDE_INTEGRATION.md` | `docs/package-reviews/P8_UNFREEZE.md` |
| P9 OpenClaw Runtime Projection | approved | `docs/package-plans/P9_OPENCLAW_INTEGRATION.md` | `docs/package-reviews/P9_UNFREEZE.md` |
| P10 Mainline Closure | approved | `docs/package-plans/P10_MAINLINE_CLOSURE.md` | `docs/package-reviews/P10_UNFREEZE.md` |

## Shipped CLI Reality

Top-level shipped commands:

- `topology init`
- `topology ingest`
- `topology digest`
- `topology reconcile`
- `topology apply`
- `topology subject`
- `topology compose`
- `topology lint`
- `topology doctor`
- `topology writeback`
- `topology agent-guard`
- `topology openclaw`

Shipped compose subcommands:

- `topology compose builder`
- `topology compose openclaw`

Shipped doctor subcommands:

- `topology doctor stale-anchors`
- `topology doctor queues`
- `topology doctor public-safe`
- `topology doctor projections`
- `topology doctor canonical-parity`

Shipped subject subcommands:

- `topology subject add`
- `topology subject refresh`
- `topology subject show`
- `topology subject resolve`

Shipped OpenClaw bridge subcommands:

- `topology openclaw capture-source`
- `topology openclaw issue-lease`
- `topology openclaw lease`
- `topology openclaw run-writeback`

## Deferred Surfaces

The following items are intentionally not shipped in the P0-P9 mainline:

- audio/video transcript resolver
- deep social thread expansion resolver
- Codex topology MCP registration
- Claude changed-file lint/writeback hooks
- live OpenClaw adapter
- OpenClaw private workspace writes
- queue leases around external OpenClaw writes
- OpenClaw memory-wiki import or live validation
- OpenClaw QMD live indexing validation
- OpenClaw natural-language runtime context sanitizer

## Mainline Boundary

P0-P9 delivered the repo-root canonical substrate, builder-first loop pieces,
Codex/Claude routing, and a conservative OpenClaw runtime projection.

Post-mainline operational closure packages shipped the runtime doctor split,
subject registry command surface, and the controlled OpenClaw file-index
projection. Remaining deferred work is limited to the items listed above.

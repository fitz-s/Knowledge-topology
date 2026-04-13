# P1 Package Plan: Engine Skeleton

## Package Ralplan

P1 established the first executable topology engine skeleton. It made the repo
initializable, added durable opaque ID helpers, path safety, schema loading,
filesystem transactions, and local spool queue mechanics.

This tracked summary mirrors the original local OMX planning artifacts cited
by `docs/package-reviews/P1_UNFREEZE.md` so public checkouts have complete
package-plan evidence.

## Reality Check

- P1 did not implement ingest, digest, reconcile, apply, compose, lint, doctor,
  writeback, adapters, MCP, or runtime projection behavior.
- Queue semantics are local single-filesystem spool semantics, not a
  distributed broker.
- Path helpers reject production nested `.topology/` roots.
- Later packages own public-source, canonical-write, projection, and adapter
  behavior.

## Construction Table

| Small Package | Purpose | Files / Surfaces | Fixtures / Tests | Acceptance Criteria | Stop Condition |
| --- | --- | --- | --- | --- | --- |
| P1.1 Init command | Initialize repo-root topology directories and registries | `workers/init.py`, `cli.py`, `paths.py` | `tests/test_p1_engine_skeleton.py` | `topology init` is idempotent | init creates nested production `.topology/` |
| P1.2 Opaque IDs | Generate and validate ULID-prefixed durable IDs | `ids.py` | ID tests | known prefixes validate; unknown prefixes reject | slug becomes stable reference |
| P1.3 Path safety | Keep all topology paths under repo root | `paths.py` | path escape tests | absolute/traversal/nested `.topology` paths reject | tests need destructive path behavior |
| P1.4 Schema loader | Load JSON fixtures with clear failures | `schema/loader.py` | schema loader tests | invalid JSON fails deterministically | loader invents schema semantics |
| P1.5 Transactions | Atomic text writes for file-backed state | `storage/transaction.py` | transaction tests | parent dirs are created and content is complete | partial writes are accepted |
| P1.6 Spool queue | Create, lease, complete, fail, and requeue job files | `storage/spool.py` | queue tests | one job per file and state moves are atomic | shared JSONL queue returns |

## Team Decision

P1 was implemented as a single-owner package. The surface was foundational and
cross-cutting, so split implementation would have risked divergent contracts.

## Gemini Requirement

Required.

Reason: P1 touched path safety, storage mechanics, and queue contracts.

## Acceptance Criteria

- `topology init` initializes a new root and is idempotent.
- ID generation and validation cover all frozen prefixes.
- Path helper rejects root escape and nested production `.topology` paths.
- Schema loader reports malformed JSON deterministically.
- Atomic writer leaves complete file content.
- Spool queue can create, lease, complete, fail, and requeue fixture jobs.
- No worker business logic beyond engine skeleton is introduced.

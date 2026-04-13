# P6 Package Plan: Builder Compose

## Package Ralplan

P6 creates deterministic task-scoped builder packs from applied canonical state.
It must not read `mutations/pending/` or treat projections as canonical truth.

## Reality Check

- Builder packs are generated/local-only by default under `projections/tasks/`.
- P6 consumes applied registry/page state from P5.
- P6 load-bearing files must be deterministic compiler outputs.
- P6 must filter runtime/operator-only data and avoid unsafe raw content.
- P6 does not write canonical, mutation packs, or OpenClaw runtime projections.
- P6 changes projection mechanics, so Gemini is required before P7 unfreeze.

## Construction Table

| Small Package | Purpose | Files / Surfaces | Fixtures / Tests | Acceptance Criteria | Stop Condition |
| --- | --- | --- | --- | --- | --- |
| P6.1 Pack schema | Define fixed builder pack outputs | `workers/compose_builder.py` | pack fixture tests | writes all six files | output shape varies run to run |
| P6.2 Registry reader use | Read applied claims/edges/nodes/gaps only | compose worker | pending exclusion tests | ignores pending mutations | reads pending as truth |
| P6.3 Filters and bounds | Enforce audience/sensitivity/status and limits | compose worker | filter tests | excludes operator/runtime-only, bounded output | leaks runtime/operator data |
| P6.4 Relationship tests | Emit relationship-test specs for builder-critical invariants | compose worker | invariant fixture | relationship-tests.yaml created | missing output file |
| P6.5 CLI compose builder | Add `topology compose builder` | `cli.py` | CLI smoke | produces pack under task dir | CLI writes canonical/projections common |

## Team Decision

Do not use `$team` for P6 implementation. The deterministic compiler should be
implemented by one owner to avoid traversal-policy drift.

## Gemini Requirement

Required before unfreeze because P6 defines builder projection mechanics.

## Acceptance Criteria

- `topology compose builder` writes:
  - `metadata.json`
  - `brief.md`
  - `constraints.json`
  - `relationship-tests.yaml`
  - `source-bundle.json`
  - `writeback-targets.json`
- Pack metadata includes `canonical_rev`, `subject_repo_id`,
  `subject_head_sha`, and `generated_at`.
- Pack is stale when canonical or subject revision differs.
- Pending mutation packs are ignored.
- Runtime/operator-only records are excluded.
- Output is deterministic enough for same-input tests after ignoring timestamps.
- P0-P5 tests still pass.

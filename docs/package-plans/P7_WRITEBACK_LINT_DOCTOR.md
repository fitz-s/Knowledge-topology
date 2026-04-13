# P7 Package Plan: Writeback, Lint, Doctor

## Package Ralplan

P7 adds deterministic quality gates and session writeback. It does not perform
live agent integration, MCP, hooks, OpenClaw runtime projection, or canonical
apply beyond producing mutation proposals.

## Reality Check

- P7 must validate P6 builder packs without treating projections as canonical.
- P7 must produce writeback mutation proposals, not direct canonical writes.
- P7 must surface stale file refs and local-only projection leakage.
- P7 should remain deterministic and stdlib-only.
- P7 changes lint/doctor/writeback gates, so Gemini is required before P8
  unfreeze.

## Construction Table

| Small Package | Purpose | Files / Surfaces | Fixtures / Tests | Acceptance Criteria | Stop Condition |
| --- | --- | --- | --- | --- | --- |
| P7.1 Lint | Check public-safe packets, projection leakage, relationship-test schema, missing antibodies | `workers/lint.py` | lint fixtures | bad states fail with clear messages | lint mutates files |
| P7.2 Doctor | Report stale file refs and queue/projection diagnostics | `workers/doctor.py` | stale file ref fixtures | stale anchors reported | doctor writes canonical |
| P7.3 Writeback | Convert session summary into mutation proposal and relationship-test delta | `workers/writeback.py` | writeback fixtures | mutation pack and reltest delta emitted | writes canonical directly |
| P7.4 CLI | Add `topology lint`, `topology doctor stale-anchors`, `topology writeback` | `cli.py` | CLI smoke tests | nonzero on lint failures | CLI bypasses workers |

## Team Decision

Do not use `$team` for P7 implementation. The package spans related quality
gates and should be kept coherent by one owner.

## Gemini Requirement

Required before unfreeze because P7 defines package quality gates and
writeback semantics.

## Acceptance Criteria

- `topology lint` fails for:
  - unsafe public text source packets
  - generated projection files outside fixtures
  - malformed relationship-test outputs
  - builder-critical invariants without relationship-test specs
- `topology doctor stale-anchors` reports stale file refs.
- `topology writeback` writes a pending mutation proposal and relationship-test
  delta without canonical writes.
- P0-P6 tests still pass.

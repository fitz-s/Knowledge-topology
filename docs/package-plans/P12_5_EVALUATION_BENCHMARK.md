# P12.5 Package Plan: Evaluation / Benchmark

## Package Ralplan

P12.5 adds a minimal deterministic evaluation surface before claiming the
topology is operationally useful. The package measures observable continuity and
maintenance signals from existing artifacts; it does not ask an LLM to grade
itself and does not mutate canonical state.

## Reality Check

- P12.1-P12.4 now provide consumer bootstrap, video/media closure, OpenClaw
  consumer wiring, and a maintainer supervisor.
- The system still needs an operator-visible way to answer whether these
  surfaces are improving future work rather than only producing more files.
- Some desired metrics require manual or external experiment input. The first
  version should report deterministic metrics and mark unsupported metrics as
  `not_measured`, not invent scores.

## Construction Table

| Small Package | Purpose | Files / Surfaces | Tests | Acceptance | Stop Condition |
| --- | --- | --- | --- | --- | --- |
| P12.5a Eval worker | Produce deterministic metrics from topology artifacts | `workers/evaluation.py` | focused tests | local-only report with builder pack, writeback, mutation, video, OpenClaw, and context metrics | evaluator writes canonical or makes unsupported claims |
| P12.5b CLI surface | Add operator command | `cli.py` | CLI smoke | `topology eval run --root ...` writes/prints report | requires manual spreadsheet assembly |
| P12.5c Governance docs | Record eval status and metric limits | status/review/docs | P10 status test | shipped CLI reality includes eval; unsupported metrics explicit | status claims "proved effectiveness" |

## Gemini Requirement

Required before unfreeze: no.

Reason: P12.5 is deterministic local reporting and does not add new authority,
network, provider, or trust-boundary behavior.

## Acceptance Tests

- Eval report is written under ignored local-only `ops/reports/tmp/evaluations/`.
- Report includes:
  - builder pack count and stale pack rate
  - task pack size bytes
  - writeback proposal acceptance rate
  - stale mutation/precondition rate
  - conflict rate
  - video manual-intervention rate
  - OpenClaw runtime proposal acceptance rate
  - context relevance score status
- Metrics are path-sanitized and do not leak the local topology root.
- Unsupported/manual metrics are `not_measured`, not fabricated.

## Stop Conditions

- Eval writes `canonical/`, `digests/`, `mutations/`, or tracked reports.
- Eval uses LLM judgment without a captured artifact.
- Eval claims success-rate improvement without paired experiment inputs.

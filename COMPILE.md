# Compile Policy

Compile turns canonical records into audience-specific projections. It must be
deterministic and bounded.

## Builder Pack Inputs

Builder compile may use:

- active decisions
- active invariants
- active interfaces
- directly relevant file refs
- relevant contradictions
- relevant open gaps
- safe provenance summaries

Builder compile must exclude:

- operator-only directives
- runtime-only observations unless explicitly promoted
- low-confidence chatter
- unsafe raw text
- unrelated background reading

## Traversal Rules

Always eligible builder traversal edge types:

- `IMPLEMENTS`
- `DEPENDS_ON`
- `INVARIANT_FOR`
- `TESTS`
- `LOCATED_IN`

Eligible with confidence and scope checks:

- `SUPPORTS`
- `NARROWS`
- `SUPERSEDES`

Excluded by default from automatic builder traversal:

- `RELATED_TO`
- `EXAMPLE_OF`
- `CONTRADICTS`

Default bounds:

- max nodes: 40
- max sources: 20
- max file refs: 40
- max traversal depth: 2

If bounds are exceeded, prefer higher authority, active status, direct file
refs, direct evidence, and recent verification.

## Sensitivity Filtering

Builder projections must exclude records whose audience does not include
builders. Runtime-only and operator-only records may appear only in OpenClaw
runtime projections.

## Load-Bearing Outputs

These files are compiled from canonical records:

- `metadata.json`
- `constraints.json`
- `relationship-tests.yaml`
- `source-bundle.json`
- `writeback-targets.json`

`brief.md` may contain concise prose, but it must not introduce new authority.

## Staleness

A projection is stale when:

- `canonical_rev` changes
- `subject_head_sha` changes
- referenced file refs fail verification
- sensitivity/audience labels change

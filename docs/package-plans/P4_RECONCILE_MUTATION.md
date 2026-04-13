# P4 Package Plan: Reconcile and Mutation Proposal

## Package Ralplan

P4 maps validated digest JSON onto existing canonical registries and emits
mutation packs. It must never edit canonical pages or registries.

## Reality Check

- Reconcile consumes P3 digest JSON and P2 source IDs.
- Reconcile is a proposal layer. Apply owns canonical writes.
- Low-confidence or unknown targets must not silently merge.
- Human-gated edge types such as `CONTRADICTS` and `SUPERSEDES` must set
  `requires_human`.
- Mutation packs must carry `base_canonical_rev`, `subject_repo_id`, and
  `subject_head_sha`.
- P4 changes canonical proposal mechanics, so Gemini is required before P5
  unfreeze.

## Construction Table

| Small Package | Purpose | Files / Surfaces | Fixtures / Tests | Acceptance Criteria | Stop Condition |
| --- | --- | --- | --- | --- | --- |
| P4.1 Registry reader | Read canonical registry JSONL safely | `src/knowledge_topology/storage/registry.py` | registry fixtures | known node IDs are available to reconcile | invalid JSONL cannot fail clearly |
| P4.2 Mutation pack schema | Validate mutation pack payloads | `src/knowledge_topology/schema/mutation_pack.py` | mutation pack tests | missing preconditions/changes fail | schema allows non-opaque IDs |
| P4.3 Conservative reconcile | Convert digest claims/edges to proposal changes | `src/knowledge_topology/workers/reconcile.py` | digest fixtures | unknown/low confidence creates gaps, not edges | low confidence silently merges |
| P4.4 Human gate classification | Mark contradiction/supersession proposals human-gated | reconcile worker | human gate tests | required gate class is set | destructive edge bypasses gate |
| P4.5 CLI reconcile | Add `topology reconcile` | `cli.py` | CLI smoke tests | writes only `mutations/pending/*.json` | writes canonical/mutations applied |

## Team Decision

Do not use `$team` for P4 implementation. The package is tightly coupled around
mutation-pack shape and conservative reconcile semantics.

## Gemini Requirement

Required before unfreeze because P4 defines canonical proposal mechanics.

## Acceptance Criteria

- `topology reconcile` writes a mutation pack under `mutations/pending/`.
- Mutation pack includes preconditions and evidence refs.
- Claim changes are emitted for digest author claims.
- Known target and adequate confidence can emit `add_edge`.
- Unknown or low-confidence targets emit `open_gap`.
- `CONTRADICTS` and `SUPERSEDES` require human gates.
- Reconcile does not write `canonical/`, `mutations/approved`, `mutations/applied`,
  `mutations/rejected`, or `projections/`.
- P0-P3 tests still pass.

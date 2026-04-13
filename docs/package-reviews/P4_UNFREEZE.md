# P4 Unfreeze Review

## Package

P4 Reconcile and Mutation Proposal

## Package Plan

- `docs/package-plans/P4_RECONCILE_MUTATION.md`

## Implementation Commits

- `177bfb3` - Implement P4 conservative reconcile proposals
- `e21c998` - Harden P4 mutation proposal validation
- `62cefc2` - Prove P4 mutation evidence refs resolve

## Verification Evidence

Commands run:

```bash
python3 -m unittest discover -s tests
python3 -m compileall -q src tests
PYTHONPATH=src python3 -m knowledge_topology.cli reconcile <fixture smoke>
git diff --check
```

Result: all passed after hardening.

## Reviewer Verdict

Approved after hardening and evidence-ref regression.

Initial reviewer blockers:

- malformed registry JSONL did not fail with `RegistryError`
- P4-specific Gemini artifact was missing
- evidence refs were shape-checked but not independently proven to resolve

Fixes:

- malformed registry JSONL is wrapped in `RegistryError`
- non-opaque registry node IDs are rejected
- evidence refs are tested against existing source and digest artifacts

## Critic Verdict

Approved after blocker fixes.

Initial critic blockers:

- non-opaque registry IDs could become accepted `add_edge` proposals
- mutation pack validation checked operation names but not op-specific fields or opaque IDs

Fixes:

- registry known node IDs must be valid `nd_` IDs
- malformed digest target IDs are rejected before proposal creation
- mutation changes validate op-specific required fields and ID prefixes
- low-confidence or unknown targets still open gaps
- `CONTRADICTS` and `SUPERSEDES` set human gates

## Gemini Status

Required: yes.

Reason: P4 defines canonical proposal mechanics and the reconcile/apply boundary.

Artifacts:

- `.omx/artifacts/gemini-p4-reconcile-mutation-unfreeze-20260413T163918Z.md`

Gemini verdict: `APPROVE`.

Gemini residual risks:

- registry reader currently loads full `nodes.jsonl` into memory; streaming/indexed reads may be needed for large topologies
- human gates currently cover `CONTRADICTS` and `SUPERSEDES`; future high-impact operations may require broader gate classification

## Residual Risks

- P4 does not apply mutation packs; P5 must revalidate preconditions, evidence refs, and human gates before canonical writes.
- P4 does not implement escalation card UI or approval flows.

## Final Decision

`approved`

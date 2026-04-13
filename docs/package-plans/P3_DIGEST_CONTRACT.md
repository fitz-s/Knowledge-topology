# P3 Package Plan: Digest Contract

## Package Ralplan

P3 makes digest output executable and verifiable. It does not call a live model
by default; it defines the adapter boundary and validates model-produced JSON
before writing digest artifacts.

## Reality Check

- Digest is the first LLM-facing layer, so output must be treated as untrusted
  until validation passes.
- P3 must consume P2 source packet JSON and preserve `source_id`,
  `source_type`, `content_mode`, and source artifacts.
- P3 must not write canonical state, mutation packs, projections, or adapters
  for Codex/Claude/OpenClaw.
- Invalid digest output must fail before any digest artifact is written.
- P3 touches digest fidelity and LLM-output trust boundaries, so Gemini is
  required before unfreezing P4.

## Construction Table

| Small Package | Purpose | Files / Surfaces | Fixtures / Tests | Acceptance Criteria | Stop Condition |
| --- | --- | --- | --- | --- | --- |
| P3.1 Prompt contracts | Encode deep/standard digest requirements | `prompts/digest_deep.md`, `prompts/digest_standard.md` | prompt presence tests | prompts require fidelity fields and uncertainty separation | prompt asks model to write canonical |
| P3.2 Digest schema | Make digest JSON fields executable | `src/knowledge_topology/schema/digest.py` | valid/invalid digest fixtures | missing fields, bad IDs, bad fidelity flags fail | schema allows uncertainty collapse |
| P3.3 Adapter boundary | Load model output without embedding model calls | `src/knowledge_topology/adapters/digest_model.py` | JSON-file adapter tests | model output can be supplied as file | adapter performs business logic |
| P3.4 Digest writer | Write `digests/by_source/<src_id>/<dg_id>.json|md` | `src/knowledge_topology/workers/digest.py` | integration tests | valid digest writes md/json and no canonical files | invalid output creates partial digest |
| P3.5 CLI digest | Add `topology digest` | `cli.py` | CLI smoke tests | command validates and writes digest artifacts | CLI calls real model/network |

## Team Decision

Do not use `$team` for P3 implementation. The package is cohesive and the main
risk is schema/validation consistency, not parallel coding throughput.

## Gemini Requirement

Required before unfreeze because P3 defines LLM-output trust-boundary behavior
and digest fidelity contracts.

## Acceptance Criteria

- Valid fixture source + valid digest JSON produces `digest.json` and
  `digest.md`.
- Invalid digest JSON fails before writing artifacts.
- Mismatched `source_id` fails.
- Digest JSON separates author claims, direct evidence, model inferences,
  boundary conditions, alternative interpretations, contested points,
  unresolved ambiguity, open questions, candidate edges, and fidelity flags.
- Digest writer never writes `canonical/`, `mutations/`, or `projections/`.
- P0/P1/P2 tests still pass.

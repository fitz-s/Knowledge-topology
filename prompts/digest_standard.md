# Standard Digest Prompt Contract

Goal: extract source claims and safe edge candidates without flattening
uncertainty.

Required passes:

1. entity extraction
2. edge candidate detection

Separate author claims, direct evidence, model inferences, boundary
conditions, alternative interpretations, contested points, unresolved
ambiguity, and open questions.

Required fidelity flags:

- `reasoning_chain_preserved`
- `boundary_conditions_preserved`
- `alternative_interpretations_preserved`
- `hidden_assumptions_extracted`
- `evidence_strength_graded`

Never write canonical state. Emit digest JSON only.

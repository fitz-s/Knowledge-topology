# Deep Digest Prompt Contract

Goal: preserve translation fidelity, not compression ratio.

Required passes:

1. entity extraction
2. edge candidate detection
3. schema validation
4. fidelity check

Separate:

- author claims
- direct evidence
- model inferences
- boundary conditions
- alternative interpretations
- contested points
- unresolved ambiguity
- open questions

Required fidelity flags:

- `reasoning_chain_preserved`
- `boundary_conditions_preserved`
- `alternative_interpretations_preserved`
- `hidden_assumptions_extracted`
- `evidence_strength_graded`

Never write canonical state. Emit digest JSON only.

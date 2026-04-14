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

For `video_platform` sources, extract the argument structure instead of a short
topic list: misconception, thesis, segment flow, named concepts, conditions,
examples, implications, caveats, and open questions. If the video covers
mathematical or statistical ideas, preserve the mechanism that breaks common
intuition rather than only naming the theorem.

Never write canonical state. Emit one JSON object only, with no Markdown fence,
commentary, or extra text outside the JSON.

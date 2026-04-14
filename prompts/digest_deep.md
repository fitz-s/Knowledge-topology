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

For `video_platform` sources, do not summarize as shallow bullet points. Treat
the transcript, key-frame notes, audio summary, and landing metadata as evidence
for a long-form argument. Extract:

- the opening misconception or target intuition the speaker rejects
- the central thesis and why it matters
- the chapter or segment structure of the argument
- every named concept, framework, object, result, method, or claim that is
  load-bearing in the source's own domain
- the conditions, assumptions, scope limits, or prerequisites attached to each
  load-bearing concept or claim
- the mechanism by which the source says intuition, common practice, or a
  default assumption fails
- concrete implications for decisions, practice, modeling, design, research, or
  interpretation
- examples used by the speaker and what each example is evidence for
- caveats, missing assumptions, contested claims, and places where the model
  should not overgeneralize

Do not assume the video's domain. Let the attached transcript, key-frame notes,
audio summary, and landing metadata determine the domain vocabulary.

Never write canonical state. Emit one JSON object only, with no Markdown fence,
commentary, or extra text outside the JSON.

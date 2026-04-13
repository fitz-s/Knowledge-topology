# Escalation Cards

Escalation cards turn human gates into structured review, not open-ended chat.

## When to Escalate

Escalate only for authority-changing decisions:

- canonical source ambiguity
- high-impact contradiction
- `fitz_belief`
- `operator_directive`
- supersede or delete proposal
- cross-scope authority upgrade
- high-consequence weak-evidence merge
- reviewer/critic dialectic stalemate

## Card Schema

Minimum fields:

- `id`
- `gate_class`
- `question`
- `recommended_default`
- `options`
- `why_it_matters`
- `evidence_refs`
- `mutation_pack_id`
- `base_canonical_rev`
- `subject_repo_id`
- `subject_head_sha`
- `created_at`
- `expires_at`

## Default Actions

Safe defaults:

- ambiguity: keep current and mark contested
- contradiction: mark contested, do not supersede
- belief/directive: require explicit approval
- delete/supersede: reject unless explicitly approved
- scope upgrade: keep lower scope
- weak high-impact merge: create related node, do not merge

## Evidence Bundle

Each escalation card includes source IDs, digest IDs, claim IDs, mutation pack
ID, and a short explanation of the decision pressure.

## Timeouts

If a card expires without review, apply the safe default and keep the card in
`ops/escalations/` for audit.

## Dialectic Stalemate

When Reviewer and Critic disagree on package completion, create an escalation
card and run `$ask-gemini` when the disagreement touches architecture,
security, public/private leakage, OpenClaw, adapter boundaries, or canonical
authority. The package remains frozen until the conflict is resolved or waived
by the user.

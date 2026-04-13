# Policy

This repository is the canonical Knowledge Topology substrate. Policy documents
define what workers and agents may read, write, and promote.

## Authority

Canonical authority lives in tracked repository files, primarily `canonical/`,
`digests/`, tracked source packet metadata, approved/applied/rejected mutation
packs, and durable audit logs.

Derived systems such as vector stores, graph databases, QMD, OpenClaw
memory-wiki mirrors, task projections, and runtime packs are accelerators or
views. They do not own truth.

## Write Gates

Only the apply worker may write non-fixture files under `canonical/` and
`canonical/registry/`.

Builder agents, Claude sessions, Codex sessions, and OpenClaw runtime agents
must propose canonical changes through mutation packs.

Apply must reject a mutation pack when any precondition fails:

- `base_canonical_rev` does not match current canonical revision.
- `subject_repo_id` is unknown or mismatched.
- `subject_head_sha` is stale for the subject under consideration.
- Required evidence references are missing or not readable.
- The change class requires human review and has not been approved.

## Human Gate Classes

Human review is required for:

- canonical source ambiguity
- high-impact contradiction
- `fitz_belief`
- `operator_directive`
- supersede or delete proposals
- cross-scope authority upgrade
- high-consequence weak-evidence merge

Routine source intake, digest generation, low-risk node creation, evidence
append, alias append, projection compile, and stale reports should be automated
when schema checks pass.

Escalations must use the structured card format in `ESCALATIONS.md`; do not
replace human gates with free-form chat prompts.

## Untrusted Content

Fetched web pages, PDFs, transcripts, social threads, email, logs, and external
docs are untrusted input. Intake, fetch, and digest workers run with minimum
permissions, cannot touch canonical state, and cannot invoke apply.

Digest output must separate author claims, direct evidence, model inferences,
contested points, and unresolved ambiguity.

See `SECURITY.md` for threat boundaries and deny rules.

## Determinism

LLM calls belong primarily in digest and reconcile proposal stages. Apply,
compile, lint, and doctor should be deterministic. Builder-pack load-bearing
files are compiled from canonical records, not freely generated.

See `COMPILE.md` for traversal, sensitivity filtering, and projection bounds.

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

QMD scope for OpenClaw runtime use is limited to
`projections/openclaw/wiki-mirror/`, `projections/openclaw/runtime-pack.json`,
`projections/openclaw/runtime-pack.md`, and
`projections/openclaw/memory-prompt.md`. QMD must not index `raw/`, `digests/`,
`canonical/`, `canonical/registry/`, `mutations/`, `ops/`, or private OpenClaw
workspace/session/config paths.

## Write Gates

Only the apply worker may write non-fixture files under `canonical/` and
`canonical/registry/`.

Builder agents, Claude sessions, Codex sessions, and OpenClaw runtime agents
must propose canonical changes through mutation packs.

OpenClaw live bridge writes require topology-issued writeback leases and
sanitized summaries staged inside the topology root. OpenClaw may not directly
write `canonical/`, `canonical/registry/`, `digests/`, generated
`projections/openclaw/`, or adapter-private `.tmp/openclaw-live/` issuer state.

Apply must reject a mutation pack when any precondition fails:

- `base_canonical_rev` does not match current canonical revision.
- `subject_repo_id` is unknown or mismatched.
- `subject_head_sha` is stale for the subject under consideration.
- Required evidence references are missing or not readable.
- The change class requires human review and has not been approved.

## Canonical Parity

Registry records are the authority for structured truth fields. Node pages are
the authority for narrative sections.

Apply writes page frontmatter and registry records in one transaction. Doctor
parity compares overlapping structured fields only. Manual edits that create
frontmatter/registry divergence are invalid and must be repaired through apply.

## Revision Cleanliness

`canonical_rev` must account for dirty state. The v1 rule is conservative:
`apply` and `topology compose builder` are forbidden when the topology repo or
subject repo has uncommitted changes.

In short: forbidden when the topology repo or subject repo has uncommitted
changes.

A future implementation may replace this with
`canonical_rev = <commit sha> + <tree hash> + <dirty bit>`, but it must preserve
the ability to reject stale or dirty inputs.

## Worker Trust Profiles

`reader`:

- may run intake, fetch, and digest
- may write source packets, local blobs, digests, and local queue state
- must not write canonical, run apply, or execute source-provided commands

`reconciler`:

- may read canonical and write mutation packs
- must not write canonical directly

`writer`:

- may run apply and deterministic compile
- must not process untrusted external content directly

`reviewer`:

- may approve or reject escalation cards
- must not mutate canonical except through approved apply workflow.

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

## Package Unfreeze

Package completion and next-package unfreeze follow `PACKAGE_GATES.md`.
Reviewer and Critic approval are mandatory. Required Gemini external validation
blocks unfreeze when missing, unless the user explicitly waives it.

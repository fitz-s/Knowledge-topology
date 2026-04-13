# Schema Contract

Batch 0 freezes the core data model. JSON Schema or typed models can refine
validation later, but they must preserve these fields and semantics.

## IDs

All durable entities use immutable opaque IDs with ULID suffixes:

- `src_`: source packet
- `dg_`: digest
- `mut_`: mutation pack
- `job_`: worker job
- `evt_`: audit event
- `gap_`: gap
- `clm_`: claim
- `edg_`: edge
- `nd_`: node

Human-readable `slug` and `aliases` are mutable lookup aids. References use
opaque IDs.

## Source Packet

Minimum fields:

- `id`
- `source_type`
- `original_url`
- `canonical_url`
- `retrieved_at`
- `curator_note`
- `ingest_depth`: `deep`, `standard`, or `scan`
- `authority`
- `trust_scope`
- `content_status`
- `content_mode`: `public_text`, `excerpt_only`, or `local_blob`
- `redistributable`: `yes`, `no`, or `unknown`
- `hash_original`
- `hash_normalized`
- `artifacts`
- `fetch_chain`

## Digest

Every digest has markdown and JSON forms. The JSON separates:

- `author_claims`
- `direct_evidence`
- `model_inferences`
- `boundary_conditions`
- `alternative_interpretations`
- `contested_points`
- `unresolved_ambiguity`
- `open_questions`
- `candidate_edges`
- `fidelity_flags`

## Node

Minimum fields:

- `id`
- `slug`
- `type`
- `scope`
- `sensitivity`
- `authority`
- `status`
- `confidence`
- `audiences`
- `source_ids`
- `claim_ids`
- `aliases`
- `tags`
- `file_refs`
- `supersedes`
- `superseded_by`

## File Reference

Minimum fields:

- `repo_id`
- `commit_sha`
- `path`
- `line_range`
- `symbol`
- `verified_at`

File references are stale when the subject repo head moves and the reference is
not reverified.

## Mutation Pack

Minimum fields:

- `id`
- `proposal_type`
- `proposed_by`
- `base_canonical_rev`
- `subject_repo_id`
- `subject_head_sha`
- `changes`
- `evidence_refs`
- `requires_human`
- `human_gate_class`
- `merge_confidence`

Apply rejects mutation packs whose preconditions no longer hold.

## Builder Pack

Fixed outputs:

- `metadata.json`
- `brief.md`
- `constraints.json`
- `relationship-tests.yaml`
- `source-bundle.json`
- `writeback-targets.json`

`metadata.json` includes:

- `canonical_rev`
- `subject_repo_id`
- `subject_head_sha`
- `generated_at`

A builder pack is stale when `canonical_rev` or `subject_head_sha` no longer
matches the current context.

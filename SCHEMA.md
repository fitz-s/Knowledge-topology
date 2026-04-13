# Schema Contract

Batch 0.5 freezes the core data model, value domains, and load-bearing payload
shapes needed before worker implementation. JSON Schema or typed models can
refine validation later, but they must preserve these fields and semantics.

Schema evolution follows `SCHEMA_EVOLUTION.md`.

## IDs

All durable entities use immutable opaque IDs with ULID suffixes:

- `src_`: source packet
- `dg_`: digest
- `mut_`: mutation pack
- `job_`: worker job
- `evt_`: semantic audit event
- `gap_`: gap
- `clm_`: claim
- `edg_`: edge
- `nd_`: node
- `syn_`: synthesis
- `esc_`: escalation card
- `reltest_`: relationship test

Human-readable `slug` and `aliases` are mutable lookup aids. References use
opaque IDs.

## Enumerations

`node.type`:

- `finding`
- `method`
- `claim`
- `assumption`
- `question`
- `fitz_belief`
- `decision`
- `invariant`
- `interface`
- `component`
- `runtime_observation`
- `operator_directive`
- `artifact`
- `task_lesson`

`edge.type`:

- `SUPPORTS`
- `CONTRADICTS`
- `NARROWS`
- `SUPERSEDES`
- `RELATED_TO`
- `EXAMPLE_OF`
- `IMPLEMENTS`
- `DEPENDS_ON`
- `INVARIANT_FOR`
- `DIVERGES_FROM`
- `READS`
- `WRITES`
- `TESTS`
- `LOCATED_IN`

`scope`:

- `global`
- `repo`
- `operator`
- `runtime`

`authority`:

- `source_grounded`
- `repo_observed`
- `runtime_observed`
- `fitz_curated`
- `model_inferred`

`sensitivity`:

- `public`
- `internal`
- `operator_only`
- `runtime_only`

`status`:

- `draft`
- `active`
- `contested`
- `superseded`
- `rejected`

`human_gate_class`:

- `source_ambiguity`
- `high_impact_contradiction`
- `fitz_belief`
- `operator_directive`
- `supersede_delete`
- `cross_scope_upgrade`
- `weak_evidence_merge`

## Source Packet

Minimum fields:

- `schema_version`
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

Every digest has markdown and JSON forms. Minimum JSON fields:

- `schema_version`
- `id`
- `source_id`
- `digest_depth`
- `passes_completed`
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

## Claim

Minimum fields:

- `schema_version`
- `id`
- `statement`
- `source_ids`
- `evidence_refs`
- `evidence_strength`
- `authority`
- `status`
- `confidence`
- `inference_chain`

## Node

Minimum fields:

- `schema_version`
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

## Edge

Minimum fields:

- `schema_version`
- `id`
- `from_id`
- `to_id`
- `type`
- `status`
- `confidence`
- `basis_claim_ids`
- `source_ids`
- `updated_at`

## Synthesis

Minimum fields:

- `schema_version`
- `id`
- `slug`
- `type`
- `scope`
- `audiences`
- `source_node_ids`
- `summary`
- `open_questions`
- `updated_at`

## File Reference

Minimum fields:

- `repo_id`
- `commit_sha`
- `path`
- `path_at_capture`
- `line_range`
- `symbol`
- `anchor_kind`: `symbol`, `line`, or `excerpt`
- `excerpt_hash`
- `verified_at`
- optional `symbol_signature`

File references are stale when the subject repo head moves and the reference is
not reverified.

## Mutation Pack

Minimum fields:

- `schema_version`
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

## Audit Event

Tracked durable audit events are semantic events, not queue churn. Minimum
fields:

- `schema_version`
- `id`
- `event_type`
- `occurred_at`
- `actor`
- `summary`
- `refs`
- `canonical_rev`

Operational events such as job creation, lease, completion, failure, and
requeue belong in local-only runtime logs unless promoted to a semantic event.

## Gap

Minimum fields:

- `schema_version`
- `id`
- `status`
- `summary`
- `opened_at`
- `closed_at`
- `source_ids`
- `related_node_ids`
- `owner`

## Escalation Card

Minimum fields:

- `schema_version`
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

Escalation cards follow `ESCALATIONS.md`.

## Relationship Test

Minimum fields:

- `schema_version`
- `id`
- `invariant_node_id`
- `property`
- `evidence_refs`
- `suggested_test_shape`
- `failure_if`
- `status`

Relationship-test schema is frozen before builder compose, because
`relationship-tests.yaml` is a Batch 6 load-bearing output.

## Subject Record

Minimum fields:

- `schema_version`
- `subject_repo_id`
- `name`
- `kind`
- `location`
- `default_branch`
- `head_sha`
- `visibility`
- `sensitivity`
- `created_at`
- `updated_at`

Subject command surface:

- `topology subject add`
- `topology subject refresh`
- `topology subject show`
- `topology subject resolve`

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

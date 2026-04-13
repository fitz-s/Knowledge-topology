# P11.1 Package Plan: Builder Compose / Writeback Symmetry

## Package Ralplan

P11.1 closes the gap between builder packs and session writeback. Builder
packs must provide enough construction context for implementation, and
writeback must accept the corresponding session evidence instead of only
`decisions` and `invariants`.

P11.1 does not add provider/model runners, fetch v2, OpenClaw live bridge,
extra doctor subcommands, or subject/file-index commands.

## Reality Check

- Current `brief.md` is only counts plus goal; it is not a usable construction
  brief.
- Current `constraints.json` only lists invariants.
- Current writeback summary accepts only `decisions` and `invariants`.
- Mutation `propose_node` already carries extra fields through to apply, so
  P11.1 can add candidate node types without changing canonical apply behavior.
- Builder packs remain generated/local-only under `projections/tasks/**`.
- Writeback still emits mutation proposals and local relationship-test deltas;
  it does not write canonical state.
- P11.1 may project file refs only from `canonical/registry/file_refs.jsonl`
  when they match `subject_repo_id` and `subject_head_sha`; richer subject-file
  indexing remains P11.6.

## Construction Table

| Small Package | Purpose | Files / Surfaces | Fixtures / Tests | Acceptance Criteria | Stop Condition |
| --- | --- | --- | --- | --- | --- |
| P11.1a Builder brief | Upgrade `brief.md` into a construction brief | `workers/compose_builder.py` | P6 tests with section checks and leakage checks | brief includes fixed sections and bounded records, sorted by ID | brief embeds whole topology dump |
| P11.1b Constraints expansion | Add bounded interfaces, verified file refs, and contradiction pressure to `constraints.json` | `workers/compose_builder.py` | P6/P11 tests for safe refs, limits, sort order, operator/runtime/raw exclusion | constraints has exact keys and safe field allowlists | constraints includes unsafe/raw/operator data |
| P11.1c Writeback summary contract | Freeze expanded writeback summary schema | `SCHEMA.md`, skills | P7/P11 malformed input tests | summary accepts exact object shapes and fails before writing on malformed entries | schema remains list of names only |
| P11.1d Writeback proposals | Generate candidate nodes from expanded summary | `workers/writeback.py`, `schema/mutation_pack.py` | P7/P11 tests for each new type and conflict human gate | writeback emits `decision`, `invariant`, `interface`, `runtime_observation`, and `task_lesson`; conflicts require human gate | writeback only absorbs decisions/invariants |
| P11.1e Skill routing | Update Codex/Claude writeback skills | `.agents/skills/topology-writeback/SKILL.md`, `.claude/skills/topology-writeback/SKILL.md` | docs-content tests | skills show the expanded summary JSON fields and stale-precondition workflow | skills instruct direct canonical writes |

## Gemini Requirement

Required before unfreeze.

Reason: P11.1 changes `SCHEMA.md` and the writeback contract.

Acceptance:

- Save Gemini output under `.omx/artifacts/gemini-p11-1-*.md`.
- Summarize the artifact in `docs/package-reviews/P11_1_UNFREEZE.md`.
- Missing or rejected Gemini blocks P11.2.

## Builder Output Contract

`brief.md` sections, in order:

- title and task goal
- revision preconditions: `canonical_rev`, `subject_repo_id`,
  `subject_head_sha`
- key decisions: up to 10 visible `decision` nodes
- invariants: up to 10 visible `invariant` nodes
- interfaces: up to 10 visible `interface` nodes
- contradiction pressure: up to 10 visible `CONTRADICTS` or `DIVERGES_FROM`
  edges
- open gaps: up to 10 visible builder gaps
- writeback reminder: summarize required writeback fields

Brief row allowlist:

- `id`
- `type`
- `status`
- `authority`
- `source_ids`
- `title`: optional text derived from `summary`, `statement`, `reason`, or
  `contract`, capped at 160 characters and stripped of newlines

`constraints.json` exact top-level keys:

- `invariants`: list of `{id, type, status, source}`
- `interfaces`: list of `{id, status, source_ids}`
- `file_refs`: list of safe file refs
- `contradiction_pressure`: list of `{id, type, from_id, to_id, confidence,
  basis_claim_ids, source_ids}`
- `count`: legacy integer count of `invariants`, preserved for existing lint
- `counts`: object with counts for `invariants`, `interfaces`, `file_refs`,
  and `contradiction_pressure`

Builder file-ref projection is allowed only from
`canonical/registry/file_refs.jsonl` when:

- `repo_id == subject_repo_id`
- `commit_sha == subject_head_sha`
- `path` matches `[A-Za-z0-9_./@+-]+`, is relative, contains `/` or `.`, has no
  traversal, and does not contain canonical/projection/raw/local/private/blob
  path markers or any forbidden token below
- projected fields are only `repo_id`, `commit_sha`, `path`, `line_range`,
  `symbol`, `anchor_kind`, `excerpt_hash`, `verified_at`
- `line_range` is a two-item positive integer list
- `symbol` matches `[A-Za-z_][A-Za-z0-9_.:-]{0,120}`
- `anchor_kind` is `symbol`, `line`, or `excerpt`
- `excerpt_hash` is hex-shaped, 8 to 128 chars
- `verified_at` is UTC timestamp-shaped
- `path_at_capture` and unknown/extra fields are never projected in P11.1

Forbidden file-ref path tokens, matched after lowercasing and replacing
non-alphanumeric separators with `-`:

- `ignore`
- `read-only`
- `banner`
- `mutate`
- `bash`
- `append`
- `canonical`
- `registry`
- `disregard`
- `instructions`
- `override`
- `policy`
- `bypass`
- `apply`
- `gate`
- `write-directly`
- `delete`
- `execute`
- `shell`
- `command`

All builder outputs are sorted deterministically by opaque ID or path and use
bounded lists. Operator/runtime-only records, unsafe raw text, unknown whole
record fields, and local blob hints must not appear.

## Builder Visibility Matrix

Builder nodes:

- require `audiences` list containing `builders`
- require `status` of `active`, `draft`, or `contested`
- exclude `scope` of `operator` or `runtime`
- exclude `sensitivity` of `operator_only` or `runtime_only`
- exclude `type` of `operator_directive` or `runtime_observation`
- malformed `audiences`, `status`, `scope`, `sensitivity`, or `type` fail
  closed and exclude the node

Builder contradiction edges:

- include only `type` / `edge_type` of `CONTRADICTS` or `DIVERGES_FROM`
- require `status` of `active`, `draft`, or `contested`
- require `confidence` of `high`, `medium`, or `low`
- if `from_id` or `to_id` is an `nd_` ID, it must be in the visible builder
  node set
- `src_` endpoints are allowed as evidence anchors
- malformed schema-native edge fields, hidden endpoints, or unknown endpoint
  prefixes exclude the edge
- P11.1 does not require or invent `audiences`, `scope`, or `sensitivity` fields
  on edge records

Builder gaps:

- require `audiences` list containing `builders`
- require `status` of `active`, `draft`, or `contested`
- exclude `sensitivity=operator_only` when present
- malformed or missing `audiences` / `status` exclude the gap

Builder constraints bounds:

- `invariants`: max 10
- `interfaces`: max 10
- `file_refs`: max 20
- `contradiction_pressure`: max 10

Truncation is deterministic after sorting by opaque ID or path.

## Builder File-Ref Input Safety

`canonical/registry/file_refs.jsonl` is a new P11.1 input surface and must be
preflighted lexically before reading:

- every parent component must be a real directory, not a symlink
- the final JSONL path must be a regular non-symlink file
- missing file is treated as an empty file-ref list
- directory, FIFO/special file, symlink, parent symlink, and malformed JSONL
  fail with deterministic compose errors

Safe file refs require all per-field rules in the Builder Output Contract.
Adversarial tests must include command-like paths and scalar variants such as
`ignore-read-only-banner`, `use-bash`, `bypass-apply-gate`, `write-directly`,
and `override-policy`.

## Expanded Writeback Summary Schema

All top-level fields are optional except `source_id` and `digest_id`. At least
one proposal-producing field must be non-empty.

Legacy string arrays remain valid for `decisions` and `invariants`:

```json
{
  "source_id": "src_...",
  "digest_id": "dg_...",
  "decisions": ["decision statement"],
  "invariants": ["invariant statement"]
}
```

Object arrays use these shapes:

- `decisions[]`: `{ "statement": "...", "status": "draft|active|contested" }`
- `invariants[]`: `{ "statement": "...", "status": "draft|active|contested" }`
- `interfaces[]`: `{ "name": "...", "contract": "...", "file_refs": [] }`
- `runtime_assumptions[]`: `{ "statement": "...", "observed_in": "..." }`
- `task_lessons[]`: `{ "lesson": "...", "applies_to": "..." }`
- `tests_run[]`: `{ "command": "...", "result": "passed|failed|skipped", "notes": "..." }`
- `commands_run[]`: `{ "command": "...", "exit_code": 0, "notes": "..." }`
- `file_refs[]`: file ref objects using the safe builder file-ref projection
  fields
- `conflicts[]`: `{ "summary": "...", "expected": "...", "observed": "...",
  "severity": "low|medium|high", "refs": [] }`

Validation rules:

- malformed top-level JSON, scalar arrays, empty strings, invalid status/result
  enums, invalid opaque IDs, unsafe file refs, and over-limit arrays fail before
  any mutation or relationship-test file is written
- maximum 50 entries per array
- maximum 500 characters per free-text field
- `commands_run` and `tests_run` are captured in mutation metadata and also
  produce `task_lesson` candidates when no explicit `task_lessons` are present
- top-level `file_refs` are stored in mutation metadata under `file_refs`
- `interfaces[].file_refs` are stored on that interface `propose_node` change
  under `file_refs`

## Writeback Proposal Mapping

`MutationPack.proposal_type` becomes `session_writeback` for P11.1 writeback
packs.

Field-to-node mapping:

- `decisions` -> `propose_node` with `type=decision`
- `invariants` -> `propose_node` with `type=invariant`
- `interfaces` -> `propose_node` with `type=interface`
- `runtime_assumptions` -> `propose_node` with `type=runtime_observation`,
  `authority=runtime_observed`, `scope=runtime`, `sensitivity=runtime_only`
- `task_lessons` and synthesized lessons from `tests_run` / `commands_run` ->
  `propose_node` with `type=task_lesson`
- `conflicts` -> `propose_node` with `type=decision`, `status=contested`

If a summary contains any `conflicts`, the whole mutation pack must set:

- `requires_human=true`
- `human_gate_class=high_impact_contradiction`
- `merge_confidence=low`

Non-conflict writeback packs must set `requires_human=false`,
`human_gate_class=null`, and `merge_confidence=medium`.

P11.1 emits one mutation pack per writeback summary. It does not split mixed
conflict/non-conflict summaries; mixed summaries are human-gated as a whole.

## Relationship-Test Delta Rule

- Legacy string invariants and object-form invariants always generate local
  relationship-test delta entries.
- Non-invariant proposal types do not generate relationship-test deltas in
  P11.1.
- Mixed conflict plus invariant summaries may generate invariant relationship
  tests, but the mutation pack remains human-gated because conflicts are
  pack-level.
- Relationship-test deltas remain local under `.tmp/writeback/` and never imply
  auto-apply approval.

## Required Test Fixtures

P11.1 tests must cover:

- builder brief sections and deterministic ordering
- constraints keys and bounded counts
- safe file refs included only when subject/revision match
- unsafe file refs rejected from builder constraints
- file-ref registry input preflight covers missing, malformed JSONL, directory,
  FIFO/special file, final symlink, and parent symlink cases
- hidden endpoint contradiction edges are excluded
- malformed builder visibility labels fail closed
- operator/runtime/raw/private leakage absence
- legacy decisions/invariants writeback still works
- interfaces-only writeback produces mutation proposals
- runtime-assumptions-only writeback produces mutation proposals
- task-lessons-only writeback produces mutation proposals
- tests/commands-only writeback produces task lessons
- empty expanded summary fails with an error naming accepted fields
- stale preconditions fail before writes
- conflict summary produces contested, human-gated mutation pack
- invariant relationship-test deltas persist for legacy, object-form, and mixed
  conflict summaries
- non-invariant-only writeback produces no relationship-test delta
- skills show the expanded summary object schema

## Acceptance Criteria

- Builder `brief.md` is a real construction brief, not just counts.
- `constraints.json` includes `interfaces`, `file_refs`, and
  `contradiction_pressure`.
- `writeback.py` parses and validates:
  - `decisions`
  - `invariants`
  - `interfaces`
  - `runtime_assumptions`
  - `tests_run`
  - `commands_run`
  - `file_refs`
  - `conflicts`
  - `task_lessons`
- Writeback emits candidate `propose_node` changes for at least:
  - `decision`
  - `invariant`
  - `interface`
  - `runtime_observation`
  - `task_lesson`
- `conflicts` are carried as contested metadata/proposals, not silent
  overwrites.
- Existing P0-P10 tests still pass.
- Reviewer, Critic, and Gemini approve before P11.2 starts.

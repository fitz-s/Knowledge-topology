# P9 Package Plan: OpenClaw Runtime Projection

## Package Ralplan

P9 adds the first OpenClaw-facing runtime projection. It compiles topology
records into local-only OpenClaw runtime artifacts while preserving the topology
repo as canonical authority.

P9 does not configure a live OpenClaw gateway, write into an OpenClaw private
workspace, mutate OpenClaw memory-wiki via `openclaw wiki apply`, or add a
topology MCP server.

### Principles

- OpenClaw is a runtime consumer, not canonical owner.
- OpenClaw gets a runtime-scoped projection, not a whole topology dump.
- Runtime projection is deterministic and generated from canonical registries.
- Runtime observations remain lower authority and must return as mutation
  proposals before they can become canonical truth.
- Generated OpenClaw outputs stay local-only under `projections/openclaw/`.

### Decision Drivers

1. Preserve canonical authority and sensitivity boundaries.
2. Match OpenClaw's actual model: private workspace files, optional extra memory
   paths, QMD sidecar indexing, and memory-wiki as compiled vault.
3. Avoid a live adapter that cannot be tested without a configured OpenClaw
   gateway and workspace.

### Options Considered

- **A. Live OpenClaw adapter now:** write directly into an active OpenClaw
  workspace and run `openclaw wiki` commands.
  - Rejected because workspace selection, permissions, sandboxing, memory
    backend, and gateway state are host-local operational concerns.
- **B. Memory-wiki as canonical:** generate wiki pages and treat `openclaw wiki`
  as the topology source of truth.
  - Rejected because memory-wiki is a compiled vault and safe mutation surface,
    not the canonical topology substrate.
- **C. Deterministic runtime projection:** compile local-only runtime pack,
  memory prompt, and wiki mirror from canonical records.
  - Chosen because it gives OpenClaw consumable artifacts without changing
    authority ownership.

## Reality Check

- Filesystem/Git: `projections/openclaw/**` is ignored. Tests must use temp
  roots and fixtures; no generated runtime pack is committed. P9 verification
  must include `git check-ignore` for the generated output paths and a
  post-compose `git status --short` check that generated files stay unstaged.
- Public repository safety: projection compiler must filter `operator_only`,
  operator records, and non-OpenClaw audiences. It must use field allowlists,
  not whole-record serialization, and must strip unsafe raw text, local blob
  hints, and any unknown future fields.
- Untrusted-content handling: P9 only compiles records already accepted into
  canonical or tracked gap/event surfaces. It does not fetch external content.
- Concurrency/queue semantics: P9 does not add live external-root queue writers.
  It documents queue/lease expectations for later OpenClaw runtime writeback.
- Adapter/facade boundary: `topology compose openclaw` is the business-logic
  entry point. Any future OpenClaw adapter must call this command/library.
- Canonical authority: projection never writes `canonical/`; runtime writeback
  must later emit mutation packs with low authority.
- Current-runtime check: OpenClaw docs state the agent workspace is private
  memory and default cwd, not a hard sandbox; QMD can index extra paths; the
  `memory-wiki` CLI compiles and lints a provenance-rich vault. Therefore P9
  exports files that OpenClaw can read or index, but does not assume ownership
  of OpenClaw's workspace, config, credentials, sessions, QMD state, or wiki
  cache.

References checked:

- OpenClaw Agent Workspace:
  https://openclawlab.com/en/docs/concepts/agent-workspace/
- OpenClaw Memory and QMD:
  https://openclawlab.com/en/docs/concepts/memory/
- OpenClaw wiki CLI:
  https://docs.openclaw.ai/cli/wiki

## Construction Table

| Small Package | Purpose | Files / Surfaces | Fixtures / Tests | Acceptance Criteria | Stop Condition |
| --- | --- | --- | --- | --- | --- |
| P9.1 Runtime visibility policy | Define OpenClaw record filter, field whitelist, and runtime authority handling | `workers/compose_openclaw.py` | visibility fixtures for missing/scalar audience, unknown sensitivity, operator scope, operator directive, malformed authority/status | fail closed on malformed visibility labels; excludes `operator_only`, operator records, builder-only records, and `operator_directive`; includes `openclaw`/`all` audience records; runtime observations stay marked low-authority | projection leaks operator-only data |
| P9.2 OpenClaw compiler | Add `topology compose openclaw` | `workers/compose_openclaw.py`, `cli.py` | temp-root projection fixtures, stale/dirty subject fixtures, output symlink fixtures, nested-field strip fixtures | writes exact generated files under `projections/openclaw/`; rejects stale/dirty topology or verified subject state unless `--allow-dirty`; marks caller-asserted subject state when no `--subject-path`; denies symlink output escapes | compiler writes canonical or tracked projection examples |
| P9.3 Wiki mirror shape | Generate read-only mirror files and manifest | `projections/openclaw/wiki-mirror/` generated in temp tests | mirror manifest/page tests | mirror has stable IDs, source refs, sensitivity/audience metadata, owner/authority/write policy, and explicit read-only banner | mirror implies memory-wiki owns authority |
| P9.4 OpenClaw adapter notes | Document external-root mounting and future writeback constraints | `docs/OPENCLAW.md` | docs-content tests | docs state workspace remains private, config/secrets/sessions are not committed, memory-wiki mirror is derived/read-only, and runtime writeback must use mutation packs | docs instruct copying secrets or sessions into repo |

## Runtime Projection Contract

Command:

```bash
topology compose openclaw \
  --root <topology-root> \
  --project-id <runtime-project-id> \
  --canonical-rev <topology-head-sha> \
  --subject <subject-repo-id> \
  --subject-head-sha <subject-head-sha> \
  [--subject-path <subject-repo-path>] \
  [--allow-dirty]
```

Outputs, all local-only:

- `projections/openclaw/runtime-pack.json`
- `projections/openclaw/runtime-pack.md`
- `projections/openclaw/memory-prompt.md`
- `projections/openclaw/wiki-mirror/manifest.json`
- `projections/openclaw/wiki-mirror/pages/*.md`

`runtime-pack.json` minimum fields:

- `schema_version`
- `project_id`
- `canonical_rev`
- `subject_repo_id`
- `subject_head_sha`
- `subject_state_verified`
- `generated_at`
- `records`
- `open_gaps`
- `pending_escalations`
- `writeback_policy`

Runtime record field whitelist:

- `id`
- `kind`: `node` in P9; other kinds stay excluded unless they directly carry
  the full P9 visibility label set
- `type`
- `status`
- `authority`
- `scope`
- `sensitivity`
- `audiences`
- `confidence`
- `source_ids`
- `claim_ids`
- `basis_claim_ids`
- `file_refs`
- `tags`: safe slug tokens only
- `updated_at`

Nested field allowlists:

`file_refs` entries:

- `repo_id`
- `commit_sha`
- `path`: original tracked file anchor path from the canonical file reference
- `path_at_capture`
- `line_range`
- `symbol`
- `anchor_kind`
- `excerpt_hash`
- `verified_at`

`source_ids`, `claim_ids`, and `basis_claim_ids` are opaque ID string arrays
only.

`file_refs.path` is not a wiki mirror page path. Local, private, cache, or blob
paths are excluded from `file_refs`; allowed paths remain code/source anchors.
`file_refs.symbol` is not projected in P9. `anchor_kind` is an enum only, and
`verified_at`/`updated_at` must be timestamp-shaped strings.

`open_gaps` entries:

- `gap_id`
- `target_id`
- `reason`
- `digest_id`
- `status`
- `source_ids`
- `audiences`
- `sensitivity`

`pending_escalations` entries:

- `id`
- `summary`
- `reason`
- `status`
- `source_ids`
- `audiences`
- `sensitivity`
- `human_gate_class`

`manifest.pages` entries:

- `id`
- `kind`
- `path`
- `source_ids`
- `sensitivity`
- `audiences`

All nested objects drop unknown fields, raw-text fields, local/private paths,
cache paths, and blob hints. Tests must include unknown nested fields and prove
they are stripped.

Forbidden runtime record fields:

- raw or normalized source text
- `unsafe_raw_text`
- local blob paths, local blob hints, or private cache paths
- full packet artifacts
- unknown future fields not listed above

Wiki mirror manifest fields:

- `schema_version`
- `owner`: always `knowledge-topology`
- `authority`: always `derived`
- `write_policy`: always `read_only`
- `canonical_rev`
- `subject_repo_id`
- `subject_head_sha`
- `subject_state_verified`
- `generated_at`
- `pages`

Wiki mirror page frontmatter fields:

- `id`
- `kind`
- `owner`: always `knowledge-topology`
- `authority`: always `derived`
- `write_policy`: always `read_only`
- `source_ids`
- `sensitivity`
- `audiences`
- `canonical_rev`

Wiki mirror page body:

- starts with a read-only derived-artifact banner
- includes only record ID, type, authority, source IDs, and selected file refs
- never includes raw source text, local blob references, `.openclaw-wiki/`
  cache data, OpenClaw config/session paths, or unmanaged generated sections
- P9 does not project natural-language `summary` or `statement` fields into
  OpenClaw outputs. Natural-language runtime projection requires a later
  sanitizer package.

The mirror is not a memory-wiki vault root. P9 must not create `.openclaw-wiki/`
and must not call or recommend `openclaw wiki apply` as an authority path.

Wiki page path derivation:

- Page path is always `pages/<opaque-id>.md`.
- The opaque ID comes from the projected record ID.
- Record slugs, summaries, titles, source paths, and user-provided fields never
  become path segments.
- Path traversal, case variants, and symlink output escapes are denied by the
  output safety helper.

## Deterministic Output Contract

- Runtime records are sorted by `id`.
- Wiki mirror pages and `manifest.pages` entries are sorted by `id`.
- Opaque ID arrays are sorted lexicographically unless a field explicitly
  preserves canonical source order.
- JSON is emitted with stable key ordering and trailing newline.
- Markdown sections are emitted in the section order specified by this plan.
- `generated_at` is produced by an injectable clock in the compiler/library.
  Tests use a fixed timestamp. Production may use current UTC time, but byte
  stability tests must control the clock.
- Filesystem glob and JSONL read order must not determine final projection
  ordering without an explicit sort.

## Memory Prompt Contract

`memory-prompt.md` is a derived runtime prompt for OpenClaw context loading. It
uses the same field allowlists as `runtime-pack.json` and must contain only
these sections:

- read-only derived-artifact banner
- projection metadata: `project_id`, `canonical_rev`, `subject_repo_id`,
  `subject_head_sha`, `subject_state_verified`, `generated_at`
- runtime instructions: OpenClaw is a consumer, not canonical owner; writeback
  returns through mutation packs
- bounded records summary using `id`, `kind`, `type`, `status`, `authority`,
  and source IDs only
- open gaps summary using the `open_gaps` nested allowlist
- writeback policy summary using the concrete `writeback_policy` payload

`memory-prompt.md` must not contain:

- raw source text
- local blob hints or cache paths
- OpenClaw config/session/credential paths
- `.openclaw-wiki/` cache/vault instructions
- language saying OpenClaw owns canonical truth
- instructions to use `openclaw wiki apply` as a canonical authority path
- arbitrary natural-language record `summary` or `statement` text

## Runtime Visibility Matrix

Global fail-closed rules:

- Missing, scalar, or malformed `audiences` excludes the record.
- Unknown `sensitivity`, `scope`, `authority`, or `status` excludes the record.
- `audiences` must contain `openclaw` or `all`.
- `status` must be `active`, `draft`, or `contested`.
- `sensitivity=operator_only` excludes the record.
- `scope=operator` excludes the record.
- `type=operator_directive` is hard-denied in P9, even with `audiences=all`.
- Records are emitted only through the field whitelist above.

Per-surface rules:

- `nodes`: include allowed node records; include `runtime_observation` only with
  `authority=runtime_observed`; exclude `operator_directive`.
- `claims`: excluded in P9 unless a future schema adds the full P9 visibility
  label set directly to claim records. P9 does not inherit visibility from
  source packets or nodes.
- `edges`: excluded in P9 unless a future schema adds the full P9 visibility
  label set directly to edge records and both endpoints are visible in the same
  runtime projection. P9 has no unresolved-edge exception.
- `syntheses`: excluded in P9 unless the record directly carries the full P9
  visibility label set. P9 does not infer missing sensitivity, authority, or
  status.
- `open_gaps`: excluded in P9 unless the gap record directly carries the full
  P9 visibility label set and passes the global fail-closed rules. Absent
  visibility labels exclude the gap.
- `pending_escalations`: excluded in P9 unless the escalation record directly
  carries the full P9 visibility label set and passes the global fail-closed
  rules. Absent visibility labels exclude the escalation.

P9 never inherits `audiences`, `sensitivity`, `scope`, `authority`, or `status`
from related records. A surface without those labels is excluded rather than
default-included.

Runtime observations preserve `authority=runtime_observed`; projection never
promotes them to `repo_observed`, `source_grounded`, or `fitz_curated`.

## Writeback Policy Payload

`runtime-pack.json.writeback_policy` must include:

- `read_surfaces`: `projections/openclaw/runtime-pack.json`,
  `projections/openclaw/runtime-pack.md`,
  `projections/openclaw/memory-prompt.md`,
  `projections/openclaw/wiki-mirror/`
- `allowed_writeback_surfaces`: `raw/packets/`, `mutations/pending/`,
  `.tmp/writeback/`, `ops/queue/`, `ops/events/`, `ops/gaps/`,
  `ops/escalations/`
- `forbidden_surfaces`: `canonical/`, `canonical/registry/`, `digests/`,
  `projections/openclaw/`, `.openclaw-wiki/`, OpenClaw
  config/session/credential paths
- `ops_events_policy`: `semantic_events_only_no_queue_churn`
- `required_preconditions`: `canonical_rev`, `subject_repo_id`,
  `subject_head_sha`
- `runtime_observation_authority`: `runtime_observed`
- `canonical_write_path`: `mutation_pack_only`
- `queue_semantics`: `local_spool_single_filesystem`
- `wiki_policy`: `read_only_mirror_no_openclaw_wiki_apply_authority`

## Staleness And Dirty-State Contract

- `canonical_rev` must match the current clean topology `HEAD` unless
  `--allow-dirty` is set for tests.
- If the topology repo is dirty, reject unless `--allow-dirty` is set.
- If `--subject-path` is provided, the subject repo must be clean and its
  current `HEAD` must equal `--subject-head-sha` unless `--allow-dirty` is set.
- If `--subject-path` is omitted, metadata must set
  `subject_state_verified: false`; otherwise it is `true`. In this mode,
  `subject_head_sha` is caller-asserted and cannot be independently rejected by
  P9.
- Pack metadata records `canonical_rev`, `subject_repo_id`,
  `subject_head_sha`, `subject_state_verified`, and `generated_at`.
- Future OpenClaw writeback must compare these values before emitting mutation
  proposals.

## Output Safety Contract

- Generated files are limited to the exact paths listed in the output contract.
- `projections/`, `projections/openclaw/`, `wiki-mirror/`, and
  `wiki-mirror/pages/` must not be symlinks.
- Resolved generated output paths must remain inside `projections/openclaw/`.
- P9 tests must cover symlinked output directory denial.
- P9 verification must include:

```bash
git check-ignore projections/openclaw/runtime-pack.json \
  projections/openclaw/wiki-mirror/pages/example.md
git status --short
```

No generated projection output may be staged or tracked.

Visibility policy summary:

- Include records with `audiences` containing `openclaw` or `all`.
- Exclude records with `sensitivity` of `operator_only`.
- Exclude records with `scope` of `operator`.
- Include `runtime_only` only in OpenClaw runtime outputs, never builder packs.
- Include `runtime_observation` records with `authority` preserved as
  `runtime_observed`; do not promote them.

## Team Decision

Do not use `$team` for P9 implementation. The package is a coherent compiler
surface plus tests and should stay under one owner to avoid projection drift.
Use Reviewer and Critic after implementation.

## Gemini Requirement

Required before unfreeze.

Reason: P9 changes OpenClaw external-root behavior and runtime projection
boundaries.

## Acceptance Criteria

- `topology compose openclaw` writes only local-only projection files.
- OpenClaw projection never writes `canonical/`, `raw/`, `digests/`, or
  `mutations/`.
- Operator-only records do not appear in runtime packs or wiki mirror.
- Field allowlists prevent raw source text, local blob hints, and unknown
  future fields from entering runtime pack or wiki mirror outputs.
- Malformed visibility labels fail closed and are excluded deterministically.
- Runtime-only records may appear in OpenClaw outputs but remain excluded from
  builder packs.
- Runtime observations preserve low authority and are not promoted.
- Generated mirror pages state they are read-only derived artifacts.
- `memory-prompt.md` follows the explicit section contract and strips forbidden
  raw text, local paths, cache paths, and ownership language.
- Nested allowlists strip unknown fields from `file_refs`, gaps, escalations,
  manifest page entries, and source/ref arrays.
- Non-node surfaces without direct P9 visibility labels are excluded; P9 does
  not inherit visibility labels from related records.
- Edges are included only when both endpoints are visible; there is no
  unresolved-edge exception in P9.
- Dirty topology repo is rejected unless `--allow-dirty` is used in tests.
- Dirty subject repo and stale `subject_head_sha` are rejected before writing
  projection files when `--subject-path` is provided.
- When `--subject-path` is omitted, projection metadata sets
  `subject_state_verified: false` and tests assert that the subject head is
  caller-asserted rather than locally verified.
- Generated output path symlinks are denied.
- `git check-ignore` confirms OpenClaw projection outputs are ignored, and
  `git status --short` confirms they remain unstaged.
- `docs/OPENCLAW.md` describes external-root mounting, private workspace
  boundaries, QMD extra-path indexing, memory-wiki read-only consumption, and
  mutation-pack writeback.
- No OpenClaw config, credentials, sessions, or generated wiki/cache files are
  tracked.
- Full test suite, compile check, lint, reviewer, critic, and Gemini pass
  before any next package starts.

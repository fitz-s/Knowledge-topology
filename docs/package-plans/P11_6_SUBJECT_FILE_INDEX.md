# P11.6 Package Plan: Subject / File-Index

## Package Ralplan

P11.6 finishes the subject/file-index surface so the topology can track more
than one subject repository, refresh subject heads deterministically, and give
OpenClaw a controlled subject file-ref index instead of opaque archaeology.

P11.6 does not change canonical apply semantics, writeback schema, or OpenClaw
lease/auth boundaries beyond adding a projection-side file index.

## Reality Check

- `SUBJECTS.yaml` currently contains a single seed subject with `head_sha: null`.
- The CLI exposes no `topology subject ...` commands even though `SCHEMA.md` and
  `IMPLEMENTATION_PLAN.md` list them.
- `canonical/registry/file_refs.jsonl` may be present or absent; existing
  builder code already treats a missing registry as empty input.
- Existing builder/writeback safe file-ref helpers are intentionally stricter
  than the seed strong-anchor fixture. P11.6 needs a separate OpenClaw
  file-index normalizer instead of reusing those helpers.
- OpenClaw projection currently trusts caller-supplied `--subject` /
  `--subject-head-sha` metadata and does not read `SUBJECTS.yaml`.
- `compose_openclaw.py` can safely add a separate file-index output without
  reintroducing arbitrary file refs into node/runtime records.
- Runtime lint/doctor currently validate only `runtime-pack.json`,
  `runtime-pack.md`, `memory-prompt.md`, and `wiki-mirror/manifest.json`.
- Tests must remain deterministic and local. Git-backed subject refresh should
  use temp repos.

## Execution Mode Decision

`$team` is not appropriate for implementation.

Reason: subject registry, CLI routing, projection output, and their tests share
the same small set of files and contracts. Parallel code-writing would add
merge pressure without shortening the critical path. Use Reviewer/Critic
subagents for gate checks only.

## Construction Table

| Small Package | Purpose | Files / Surfaces | Fixtures / Tests | Acceptance Criteria | Stop Condition |
| --- | --- | --- | --- | --- | --- |
| P11.6a Subject registry helpers | Parse/update `SUBJECTS.yaml` with multiple subjects | new subject helper module or worker, `SUBJECTS.yaml` | temp registry tests | add/show/resolve/refresh work for multiple subjects; IDs remain stable | CLI still assumes one subject |
| P11.6b Subject CLI | Add `topology subject add|refresh|show|resolve` | `cli.py`, subject helper module | CLI smoke tests with temp git repos | commands update/show registry deterministically and refresh head SHA | subject commands mutate unrelated state |
| P11.6c Head refresh | Resolve current git HEAD for subject repos | subject helper module | dirty/missing repo tests | refresh updates `head_sha` and `updated_at`; missing/non-git subjects fail cleanly | head_sha remains stale/null after refresh |
| P11.6d Controlled OpenClaw file index | Project safe file refs for the active subject/head | `compose_openclaw.py`, `STORAGE.md`, `SCHEMA.md`, `.gitignore`, `docs/OPENCLAW.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/MAINLINE_STATUS.md` | OpenClaw projection tests | emits a separate controlled file index for current subject/head only | file refs leak into runtime records or private paths |
| P11.6e File-index safety and diagnostics | Lock path/schema constraints for projection and runtime checks | `compose_openclaw.py`, `workers/lint.py`, `workers/doctor.py` | safe path/subject/revision tests | index only includes safe relative paths and allowed fields from `file_refs.jsonl`; lint/doctor validate it | arbitrary file refs or stale refs enter projection |

## Gemini Requirement

Required before unfreeze: yes.

Reason: P11.6 changes OpenClaw projection behavior and adds a new projection
surface with public/private leakage risk. It also updates storage/projection
contracts. Gemini must review the final implementation before unfreeze.

## Subject Registry Contract

Implementation strategy:

- stdlib-only constrained parser/serializer for `SUBJECTS.yaml`
- no new dependency is introduced for YAML handling
- serializer rewrites the file deterministically in a fixed field order

Registry file:

- `SUBJECTS.yaml`
- top-level key `subjects`
- each subject keeps:
  `schema_version`, `subject_repo_id`, `name`, `kind`, `location`,
  `default_branch`, `head_sha`, `visibility`, `sensitivity`,
  `created_at`, `updated_at`

Rules:

- `subject_repo_id` is immutable and unique
- `location` may be relative to the topology root or absolute
- relative `location` resolves against the topology root
- relative `location` must not be absolute, must not contain `..`, and must not
  escape the topology root after lexical resolution
- `add`, `show`, `resolve`, and `refresh` use no-follow lexical path checks;
  symlinked final targets or symlinked parent components are rejected instead of
  being followed
- `refresh` updates only `head_sha` and `updated_at`
- `show` and `resolve` are read-only
- `add` fails on duplicate `subject_repo_id`
- `add` and `refresh` print the updated stored subject record as deterministic
  JSON
- `show` prints the stored subject record as deterministic JSON
- `resolve` prints deterministic JSON with the stored subject record plus
  `resolved_location`
- `compose openclaw` must load the subject from `SUBJECTS.yaml`
- `compose openclaw` must first reject any stored subject `location` whose
  lexical normalized path escapes, or whose parent/final path is symlinked
- `compose openclaw` rejects missing subjects, null stored `head_sha`, and any
  mismatch between caller-supplied `--subject-head-sha` and the stored
  `head_sha`
- if `--subject-path` is provided to compose, it must resolve to the same
  lexical normalized absolute path as the stored subject `location`; compose
  rejects a symlinked `--subject-path` or any symlinked parent before
  comparison, and mismatch is rejected
- `subject_state_verified` keeps its current meaning: it is `true` only when a
  subject repo path is actually verified against git state, and `false` when no
  local verification path is provided
- caller-supplied CLI subject values are preconditions only; `SUBJECTS.yaml`
  remains the authority for subject location and stored head binding

CLI commands:

- `topology subject add --root ... --id ... --name ... --kind git --location ... --default-branch ... --visibility ... --sensitivity ...`
- `topology subject refresh --root ... --subject ...`
- `topology subject show --root ... --subject ...`
- `topology subject resolve --root ... --subject ...`

Refresh rules:

- target location must exist and be a git repo
- refresh resolves `HEAD` SHA without modifying the repo
- dirty state does not block refresh; it only records current HEAD
- missing/non-git repos fail with clear errors

## Controlled File-Index Contract

OpenClaw projection adds:

- `projections/openclaw/file-index.json`

The file index is separate from `runtime-pack.json` records and does not attach
file refs to projected nodes.

Allowed file-index fields:

- `repo_id`
- `commit_sha`
- `path`
- `line_range`
- `symbol`
- `anchor_kind`
- `excerpt_hash`
- `verified_at`

Rules:

- only rows from `canonical/registry/file_refs.jsonl`
- only rows where `repo_id == subject_repo_id`
- only rows where `commit_sha == subject_head_sha`
- path must satisfy the P11.1 safe relative-path grammar
- no `path_at_capture`, private/cache/raw/local blob paths, absolute paths, or
  unknown fields
- use a dedicated OpenClaw file-index normalizer; do not reuse the stricter
  builder/writeback helper
- this compatibility is OpenClaw-only; P11.1 builder/writeback file-ref shapes
  stay unchanged
- deterministic sort uses normalized tuple:
  `path`, `symbol or ""`, normalized `line_range`, `anchor_kind or ""`,
  `excerpt_hash or ""`, `verified_at or ""`, then full JSON row string
- bounded count, max 200 entries
- `runtime-pack.json` includes only metadata:
  `file_index_path`, `file_index_count`, and `file_index_truncated`
- `file_index_path` is fixed as the repo-root-relative string
  `projections/openclaw/file-index.json`
- `file-index.json` is the source of truth for file-index metadata; runtime-pack
  metadata is derived from the emitted file-index rows, and lint/doctor must
  reject any non-exact path/count/truncation mismatch
- `runtime-pack.md`, `memory-prompt.md`, and wiki pages may mention the file
  index path/count, but must not inline file-ref rows
- output rows remain bound to the active `subject_repo_id` and
  `subject_head_sha`; the file index must not trust ad hoc CLI subject values
  over `SUBJECTS.yaml`
- `line_range` compatibility is explicit:
  preserve either a positive-two-int list or a legacy `"start-end"` string
- `excerpt_hash` compatibility is explicit:
  preserve safe digest-like strings such as `sha256:example` or hex-only values
- if `canonical/registry/file_refs.jsonl` is absent, emit `file-index.json` as
  an empty JSON array and set `file_index_count: 0`
- if safe rows exceed 200 entries, truncate after deterministic sort and mark
  `file_index_truncated: true`
- `lint runtime` and `doctor projections` must validate `file-index.json`
  presence, JSON shape, metadata parity, and no-follow path safety when an
  OpenClaw projection exists
- add `projections/openclaw/file-index.json` to the local-only storage and
  ignore contract
- add `projections/openclaw/file-index.json` to OpenClaw read-surface docs and
  QMD scope docs; QMD may index it, but runtime outputs must still not inline
  its rows
- add `projections/openclaw/file-index.json` to the machine-readable
  `writeback_policy.read_surfaces`, while writes to `projections/openclaw/`
  remain forbidden

`runtime-pack.json` may include only metadata about the file index, such as
`file_index_path` and `file_index_count`; it must not inline the whole file
index into every runtime record.

## Acceptance Tests

Required tests:

- `topology subject add` adds a second subject to a temp `SUBJECTS.yaml`.
- duplicate subject add fails.
- `topology subject show` and `resolve` return the requested subject.
- `topology subject add` and `refresh` print deterministic JSON for the stored
  record.
- `topology subject show` prints deterministic JSON for the stored record.
- `topology subject resolve` prints deterministic JSON including
  `resolved_location`.
- `topology subject refresh` updates `head_sha` for a temp git repo and updates
  `updated_at`.
- `topology subject refresh` fails cleanly for missing/non-git locations.
- relative subject locations that contain `..` or escape the topology root are
  rejected.
- subject add/show/resolve/refresh reject symlinked parent or final target
  paths.
- `compose openclaw` rejects missing subjects, null stored `head_sha`, and
  caller/registry subject-head mismatch.
- `compose openclaw` rejects stored subject locations whose lexical normalized
  path escapes or whose parent/final path is symlinked.
- `compose openclaw --subject-path` rejects symlinked paths, rejects lexical
  mismatch with stored subject location, keeps `subject_state_verified=false`
  when no local verification path is provided, and sets it `true` only after
  successful git verification.
- `compose_openclaw.py` emits `file-index.json` for the current subject/head.
- missing `canonical/registry/file_refs.jsonl` yields an empty `file-index.json`
  plus `file_index_count: 0`, not a failure.
- file index excludes stale refs for another subject or another commit.
- file index excludes unsafe/private/raw/local-blob paths and unknown fields.
- file index preserves safe legacy `line_range` / `excerpt_hash` shapes.
- file index sorts deterministically and marks truncation when over limit.
- OpenClaw runtime records still do not inline `file_refs`.
- `runtime-pack.json` metadata stays in parity with `file-index.json` path/count
  and truncation state.
- `lint runtime` and `doctor projections` recompute file-index count/truncation
  from the emitted `file-index.json` and reject any non-exact metadata mismatch.
- `runtime-pack.md`, `memory-prompt.md`, and wiki pages mention only file-index
  metadata and never inline file-index rows.
- `lint runtime` and `doctor projections` report missing, symlinked, malformed,
  or stale/leaky `file-index.json`.
- `writeback_policy.read_surfaces` includes
  `projections/openclaw/file-index.json`, while
  `projections/openclaw/` remains a forbidden write surface.
- `.gitignore`, `STORAGE.md`, and `docs/OPENCLAW.md` explicitly include the new
  local-only file-index surface and its QMD/read-scope boundary.
- `git check-ignore` proves `projections/openclaw/file-index.json` remains
  ignored.
- existing builder/writeback tests prove the OpenClaw-only normalizer does not
  relax P11.1 builder/writeback file-ref validation.
- existing P9/P11.4 OpenClaw tests continue to pass or are updated to the new
  separate `file-index.json` output.
- CLI smoke tests cover all four `subject` commands.

## Stop Conditions

- subject commands still assume a single subject or mutate unrelated state.
- `head_sha` refresh is not deterministic.
- OpenClaw projection inlines arbitrary file refs into runtime records.
- stale or unsafe file refs enter `file-index.json`.

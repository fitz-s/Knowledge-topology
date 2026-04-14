# P11.5 Package Plan: Lint / Doctor Split

## Package Ralplan

P11.5 separates deterministic repository lint from local runtime hygiene. The
current `topology lint` reports generated projection files under
`projections/`, which is useful for tracked repository cleanliness but conflicts
with local generated task packs. P11.5 introduces explicit lanes:

- `lint repo`: tracked/canonical cleanliness and public-safe source checks
- `lint runtime`: local-only projections and writeback deltas
- `doctor queues`
- `doctor projections`
- `doctor canonical-parity`
- `doctor public-safe`

P11.5 does not implement subject/file-index commands, OpenClaw live changes, or
new canonical apply behavior.

## Reality Check

- `run_lints()` currently combines source packet checks, projection leakage,
  relationship-test parsing, and missing-antibody checks in one default command.
- `lint_projection_leakage()` treats every generated projection file as a lint
  failure. This is correct for repo cleanliness but wrong for local runtime
  workflows after composing builder/OpenClaw packs.
- `doctor.py` currently only implements `stale_anchors`.
- CLI currently exposes only `topology lint` and `topology doctor stale-anchors`.
- Existing tests assert old behavior. P11.5 must preserve an equivalent strict
  repo-lint mode while adding runtime-aware commands and updating default CLI
  behavior deliberately.

## Construction Table

| Small Package | Purpose | Files / Surfaces | Fixtures / Tests | Acceptance Criteria | Stop Condition |
| --- | --- | --- | --- | --- | --- |
| P11.5a Lint lanes | Split lint into repo/runtime modes | `workers/lint.py`, `cli.py` | P7/P11.5 tests | `topology lint repo` catches projection leakage; `topology lint runtime` validates generated projection/writeback state without treating local projections as repo leakage | generated task pack still fails default local lint |
| P11.5b Default lint behavior | Make CLI defaults explicit | `cli.py`, docs | CLI smoke tests | `topology lint` aliases repo lint for backward compatibility or prints mode guidance; behavior documented | existing automation silently changes meaning |
| P11.5c Doctor queues | Diagnose leased/failed/pending queue state | `workers/doctor.py`, `cli.py` | queue fixture tests | reports expired leases, malformed jobs, unknown queue files, failed jobs, and stale leased jobs | doctor mutates queues or hides expired leases |
| P11.5d Doctor projections | Diagnose local projection freshness/safety | `workers/doctor.py`, `cli.py` | builder/OpenClaw fixture tests | reports stale/missing/malformed generated projections, symlinked projection files, and projection metadata mismatches | doctor treats generated projections as canonical |
| P11.5e Doctor canonical parity | Compare node pages and registry overlap | `workers/doctor.py`, `cli.py` | parity fixtures | reports missing pages, missing registry rows, and frontmatter/registry ID/type/status mismatches | doctor rewrites canonical state |
| P11.5f Doctor public-safe | Scan tracked-safe raw/source surfaces | `workers/doctor.py`, `cli.py`, `docs/IMPLEMENTATION_PLAN.md` | source fixture tests | reports public_text without redistributable=yes, local blob bytes in packet dirs, suspicious private/cache/OpenClaw paths in tracked artifacts | doctor reads local blobs or private workspaces |

## Gemini Requirement

Required before unfreeze: no.

Reason: P11.5 is deterministic command routing and diagnostics. It does not
change security/trust boundaries beyond enforcing already documented checks.
If implementation adds new policy semantics beyond this plan, Gemini becomes
required.

## Lint Contract

`topology lint repo`:

- checks source packet schema and public-safe `public_text`
- fails on generated projection files under `projections/**`
- checks relationship-test files under tracked/generated locations if present
- checks missing antibodies for builder task packs if present
- intended for clean repository gate before commits

`topology lint runtime`:

- validates builder task pack required files:
  `metadata.json`, `brief.md`, `constraints.json`, `relationship-tests.yaml`,
  `source-bundle.json`, and `writeback-targets.json`
- validates required builder pack JSON files parse to objects and core keys are
  present; deeper freshness checks belong to `doctor projections`
- checks relationship-test files under `projections/tasks/**` and
  `.tmp/writeback/**`
- checks missing antibodies for generated builder packs
- checks OpenClaw projection JSON/manifest shape when present
- does not fail merely because `projections/**` exists
- preflights runtime lint inputs lexically and refuses symlinked
  `relationship-tests.yaml`, task-pack files, projection files, and
  `.tmp/writeback` files instead of following them
- preflight walks every parent component under the topology root; symlinked
  parent directories such as `projections/tasks/task_x`,
  `projections/openclaw/wiki-mirror/pages`, or `.tmp/writeback/<id>` are
  reported without reading targets
- queue state is not part of runtime lint; use `topology doctor queues`
- intended after `topology compose builder/openclaw` and writeback work

`topology lint` default:

- remains equivalent to `topology lint repo` for backward compatibility
- CLI help documents `repo` and `runtime` modes

## Doctor Contract

`topology doctor queues`:

- read-only
- enumerates `ops/queue/` children first, validates queue kind directory names
  against known queue kinds, then validates each state directory name against
  `pending`, `leased`, `done`, and `failed`
- reports malformed JSON, invalid job IDs, mismatched file/job IDs, unknown
  queue kinds/states, expired leases, and failed jobs
- reports stray files at `ops/queue/`, queue-kind root, and queue-state root
- uses no-follow lexical preflight for queue kind directories, state
  directories, and job files; symlinked queue kind, symlinked state directory,
  and symlinked `job_*.json` are reported without reading targets
- does not requeue or mutate; repair remains a future explicit command

`topology doctor projections`:

- read-only
- accepts optional expected metadata inputs:
  `project_id`, `canonical_rev`, `subject_repo_id`, and `subject_head_sha`
- checks builder packs under `projections/tasks/**` for required files and
  matching metadata/constraints/relationship-tests
- checks OpenClaw projection files for required files, metadata consistency,
  non-symlink files, and manifest page path safety
- walks every projection parent component lexically; symlinked builder pack
  directories, OpenClaw projection directories, wiki `pages/` directories, and
  page files are reported without reading targets
- reports internal metadata mismatches always; when expected metadata inputs are
  provided, reports stale projection metadata against those values
- does not treat generated projections as canonical truth

`topology doctor canonical-parity`:

- read-only
- compares canonical registry rows and canonical node pages where both exist
- uses page-frontmatter `op` mapping:
  `create_claim -> canonical/registry/claims.jsonl`,
  `add_edge -> canonical/registry/edges.jsonl`, and
  `propose_node -> canonical/registry/nodes.jsonl`
- reports missing page, missing registry row, duplicate IDs, and mismatched
  overlapping fields such as `id`, `type`, and `status`
- compares only fields present on both page frontmatter and registry row
- does not rewrite pages or registries

`topology doctor public-safe`:

- read-only
- scans tracked source packet directories
- reports `public_text` without `redistributable=yes`
- reports `.pdf`/large binary-looking files in packet dirs
- reports raw/local blob bytes in `raw/packets/**`
- reports private/cache/OpenClaw path markers in tracked packet artifacts
- reports P11.3 external `public_text` `content.md` over 8,000 characters
- preflights packet files lexically and reports final symlink or parent symlink
  instead of following the target

## Acceptance Tests

Required tests:

- Existing P7 lint/doctor tests still pass or are updated to explicit
  `run_repo_lints()`.
- Existing `topology doctor stale-anchors` command remains available and keeps
  its CLI smoke test.
- `topology lint repo` fails on generated projection files.
- `topology lint runtime` accepts a generated builder task pack with valid
  relationship tests and does not report projection leakage.
- `topology lint runtime` still rejects malformed relationship-test deltas and
  missing antibodies.
- `topology lint runtime` rejects builder packs missing required files,
  malformed `metadata.json` / `constraints.json` / `writeback-targets.json`,
  and symlinked relationship-test or `.tmp/writeback` files.
- `topology lint runtime` does not perform queue diagnostics; `doctor queues`
  owns queue state.
- `topology doctor queues` reports expired leases, malformed jobs, filename/id
  mismatches, unknown queue kind, unknown queue state, stray queue files, and
  failed jobs without moving files.
- `topology doctor queues` reports symlinked queue kind directories, symlinked
  state directories, and symlinked job files without reading targets.
- `topology doctor projections` reports missing builder pack files, symlinked
  projection files, stale metadata when expected inputs are provided, internal
  metadata mismatch, and unsafe OpenClaw wiki manifest paths.
- `topology doctor projections` reports symlinked parent directories for
  builder packs, OpenClaw projection trees, wiki pages, and `.tmp/writeback`
  surfaces without reading targets.
- `topology doctor canonical-parity` reports registry/page mismatches and
  duplicate IDs using the explicit op-to-registry mapping.
- `topology doctor public-safe` reports unsafe public_text, packet-dir PDF
  bytes, local blob bytes, external `content.md` over 8,000 characters, final
  symlinks, parent symlinks, and private/OpenClaw path markers.
- CLI smoke tests cover `lint`, `lint repo`, `lint runtime`,
  `doctor queues`, `doctor projections`, `doctor canonical-parity`, and
  `doctor public-safe`, while preserving `doctor stale-anchors`.
- `docs/IMPLEMENTATION_PLAN.md` documents the split.

## Stop Conditions

- Generated task packs still make runtime lint fail solely because they exist.
- Repo lint no longer catches generated projection leakage.
- Doctor commands mutate queues, projections, or canonical files.
- Doctor public-safe reads or copies local blob/private workspace content.

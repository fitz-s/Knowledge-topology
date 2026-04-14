# P11.4 Package Plan: OpenClaw Live Bridge

## Package Ralplan

P11.4 adds the first live OpenClaw maintenance bridge. OpenClaw remains an
external runtime consumer of this topology root. It can read the OpenClaw
projection and propose runtime-observed writebacks, but it never receives
canonical write authority.

P11.4 does not add MCP as the primary integration, does not implement the
P11.5 lint/doctor split, and does not implement the P11.6 subject/file-index
package.

## Reality Check

- `compose_openclaw.py` already emits local-only `runtime-pack.json`,
  `runtime-pack.md`, `memory-prompt.md`, and `wiki-mirror/`.
- `docs/OPENCLAW.md`, `SECURITY.md`, and `POLICY.md` already state that
  OpenClaw is a runtime consumer and must not write canonical state.
- There is no live adapter path that reads projections and writes bounded
  runtime observations back into `mutations/pending/`.
- Existing `writeback.py` can emit `runtime_observation` proposals with
  runtime-only boundaries after P11.1.
- Existing spool queues support leases but not a specific OpenClaw external
  write lease helper.
- QMD scope is currently policy text only; P11.4 must make it explicit that QMD
  indexes only `projections/openclaw/wiki-mirror/` and necessary runtime-pack
  files, not raw/digests/canonical.

## Construction Table

| Small Package | Purpose | Files / Surfaces | Fixtures / Tests | Acceptance Criteria | Stop Condition |
| --- | --- | --- | --- | --- | --- |
| P11.4a Live adapter | Add deterministic OpenClaw live bridge entrypoint | new `src/knowledge_topology/adapters/openclaw_live.py` or script wrapper | unit tests with fixture projection + summary | adapter reads projection files and emits runtime writeback summary/proposal through existing writeback path | adapter writes canonical or edits projection files |
| P11.4b Runtime maintainer path | Define topology-maintainer read/write surfaces | `docs/OPENCLAW.md`, `POLICY.md`, `SECURITY.md` | docs-content tests | allowed writes are raw packets, pending mutations, `.tmp/writeback`, local queues; canonical/digests/projections are forbidden | OpenClaw is documented as canonical authority |
| P11.4c Queue lease discipline | Add lease guard around external OpenClaw writes | adapter or new helper | stale/missing lease tests | adapter requires a live lease token/job for writes; stale leases fail before writes | external runtime can write proposal surfaces without lease |
| P11.4d QMD scope | Freeze QMD indexing boundary | `docs/OPENCLAW.md`, `POLICY.md`, `SECURITY.md` | docs-content tests | QMD indexes only `projections/openclaw/wiki-mirror/`, `runtime-pack.json`, `runtime-pack.md`, and `memory-prompt.md` | QMD indexes raw/digests/canonical wholesale |
| P11.4e Live proposal tests | Prove runtime observed writeback path | tests | fixture runtime summary creates `runtime_observation` mutation proposal and no canonical writes | runtime observations cannot be proposed live |

## Gemini Requirement

Required before unfreeze.

Reason: P11.4 changes OpenClaw external-root behavior, live runtime writeback
surfaces, queue lease discipline, and trust-boundary policy.

Acceptance:

- Save Gemini output under `.omx/artifacts/gemini-p11-4-*.md`.
- Summarize the artifact in `docs/package-reviews/P11_4_UNFREEZE.md`.
- Missing or rejected Gemini blocks P11.5.

## Live Adapter Contract

Entrypoint:

- Prefer `src/knowledge_topology/adapters/openclaw_live.py`.
- CLI integration can be deferred if the adapter is callable and tested; a
  small script wrapper is acceptable if it only calls the adapter.

Inputs:

- topology root
- project id
- current `canonical_rev`
- current `subject_repo_id`
- current `subject_head_sha`
- leased queue job path under `ops/queue/writeback/leased/`
- runtime summary JSON containing runtime observations, optional task lessons,
  commands/tests, file refs, and conflicts using the P11.1 writeback summary
  schema

Reads:

- `projections/openclaw/runtime-pack.json`
- `projections/openclaw/runtime-pack.md`
- `projections/openclaw/memory-prompt.md`
- `projections/openclaw/wiki-mirror/manifest.json`
- `projections/openclaw/wiki-mirror/pages/*.md`

Allowed writes:

- `raw/packets/`
- `mutations/pending/`
- `.tmp/writeback/` sanitized summary and writeback delta files, excluding
  adapter-private lease issuer state
- `.tmp/openclaw-live/` adapter-private issuer state written only by the
  topology-side adapter/issuer, never by external OpenClaw runtime processes
- `ops/queue/**` local lease/job state written only by the topology-side live
  adapter/issuer, not directly by external OpenClaw runtime processes
- optional semantic `ops/events/`
- `ops/gaps/`
- `ops/escalations/`

Forbidden writes:

- `canonical/`
- `canonical/registry/`
- `digests/`
- `projections/openclaw/`
- `.openclaw-wiki/`
- OpenClaw private config/session/credential paths

## Runtime Observation Proposal Contract

The live adapter must route runtime summaries through existing writeback
business logic rather than constructing mutation packs by hand.

Required mapping:

- `runtime_assumptions[]` -> `runtime_observation` proposal
- runtime observations must carry `authority=runtime_observed`,
  `scope=runtime`, `sensitivity=runtime_only`, and `audiences=["openclaw"]`
- conflicts human-gate the whole mutation pack
- stale `canonical_rev` or `subject_head_sha` fails before writes
- wrong `subject_repo_id` fails before writes

Evidence rules:

- Immediate mutation writeback requires an existing readable `source_id` and
  `digest_id` pair. The adapter verifies `raw/packets/<source_id>/packet.json`
  and `digests/by_source/<source_id>/<digest_id>.json` exist, match, and are
  bound to the runtime summary hash before calling `writeback_session()`.
- Runtime evidence binding is explicit: the source packet or digest JSON must
  contain buildable evidence carriers for the canonical runtime summary hash
  and leased job id, or the adapter rejects the summary before writes. A real
  but unrelated source/digest pair is invalid.
- Source-packet binding uses an artifact entry:
  `{ "kind": "runtime_summary_evidence", "runtime_summary_hash": "...",
  "openclaw_live_job_id": "job_..." }`.
- Digest binding uses a `direct_evidence[]` entry with the same
  `kind=runtime_summary_evidence`, `runtime_summary_hash`, and
  `openclaw_live_job_id` fields.
- This uses current buildable schema surfaces: source artifacts are arbitrary
  dictionaries and digest `direct_evidence` entries are lists of evidence
  objects. P11.4 does not require top-level `metadata` fields.
- The live adapter may also create a new runtime source packet under
  `raw/packets/` and enqueue digest work for later, but that path does not emit
  a mutation pack until the digest exists.
- P11.4 does not write `digests/` directly and does not use fake opaque IDs as
  evidence refs.

The adapter may add runtime metadata under mutation metadata, but it must not
promote runtime observations to active canonical truth. Apply remains the only
canonical writer.

Runtime summary safety:

- The adapter may accept a runtime summary from an arbitrary input path, but it
  must never pass that path to `writeback_session()`.
- The adapter copies only the canonicalized, sanitized summary JSON to
  `.tmp/writeback/<job_id>/summary.json` and passes that safe topology-owned
  path to `writeback_session()` so mutation metadata cannot leak private
  OpenClaw paths.
- Summary staging must use lexical path preflight: `.tmp/`, `.tmp/writeback/`,
  and `.tmp/writeback/<job_id>/` parents are non-symlink directories, the job
  staging directory is created fresh with exclusive create, and preexisting job
  directories, files, final symlinks, or stale staged summaries fail before
  writes.
- Before routing to `writeback.py`, the adapter scans every runtime summary
  string field, including runtime observations, task lessons, commands, tests,
  conflict text, `observed_in`, and file-ref-adjacent metadata.
- Reject values containing `.openclaw`, OpenClaw config/session/workspace path
  markers, credential/token/key/secret markers, absolute local paths, cache
  paths, or private runtime state references.
- File refs still use P11.1 subject/head/path validation.
- Tests cover private OpenClaw config/session/workspace paths and secret-like
  values in every accepted runtime summary field.

## Queue Lease Discipline

P11.4 external writes require a lease:

- use only a topology-created `ops/queue/writeback/leased/job_*.json` job that
  was originally created through a topology-side OpenClaw live lease issuer and
  leased through the queue helper
- external OpenClaw runtime processes may not write directly into
  `ops/queue/writeback/leased/`; they request work through the adapter/issuer
- lease must be under the topology root and inside `ops/queue/writeback/leased`
- lease file and parents must be non-symlink lexical paths
- lease must not be expired
- lease subject/canonical preconditions must match adapter inputs
- lease payload must bind to the runtime summary by a SHA-256 hash of the
  canonical JSON summary, or to a source-packet-only runtime intake payload
- lease payload must include `issuer=topology_openclaw_live`,
  `lease_nonce`, `runtime_summary_hash`, and `project_id`
- an adapter-owned issued-lease index under
  `.tmp/openclaw-live/issued-leases.jsonl` records issued job ID,
  lease nonce, summary hash, project ID, preconditions, and consumed state
- `.tmp/openclaw-live/` and its issued index are adapter-private and excluded
  from the external OpenClaw write surface
- adapter rejects any leased job whose ID/nonce/hash/preconditions are not in
  the issued index or whose issued-index entry is already consumed
- adapter writes fail before touching proposal surfaces when lease validation
  fails
- successful mutation writeback consumes the lease exactly once by annotating
  the mutation pack id on the job, marking the issued-index entry consumed, and
  atomically moving the job to `ops/queue/writeback/done/`
- before calling `writeback_session()`, the adapter marks the issued-index entry
  `in_progress` with the safe staged summary path and expected writeback mode
- if retry sees an `in_progress` issued entry, it first scans
  `mutations/pending/*.json` for a mutation whose metadata references the safe
  staged summary path or `openclaw_live_job_id`; if found, it consumes the lease
  without writing another mutation
- if retry sees `in_progress` but no matching mutation exists, it may retry the
  write once using the same staged summary path
- P11.4 may extend `writeback_session()` metadata to include
  `openclaw_live_job_id` and `runtime_summary_hash`; recovery must still work
  with the safe summary path alone because P11.1 already records
  `metadata.writeback_summary`
- failed writes annotate bounded `last_error` and move the job to
  `ops/queue/writeback/failed/`
- replaying a consumed lease fails because it is no longer in `leased/`

Tests must cover missing lease, wrong queue state, expired lease, fabricated
lease file, missing issued-index entry, nonce mismatch, wrong subject, stale
canonical rev, summary-hash mismatch, parent symlink, final symlink, valid
lease, forged leased job plus forged `.tmp/writeback/` summary surfaces, and
replay after success.
Tests must also inject a failure after mutation write but before issued-index
consumption and prove retry consumes the original mutation instead of creating a
second proposal.

## Projection Read Safety

Projection input preflight:

- projection files and wiki pages must be lexical paths under
  `projections/openclaw/`
- parent components and final files must not be symlinks
- malformed `runtime-pack.json` or `manifest.json` fails before writes
- runtime-pack metadata must match adapter inputs, lease preconditions, and
  manifest metadata for `project_id`, `canonical_rev`, `subject_repo_id`, and
  `subject_head_sha`
- wiki page traversal entries fail closed
- adapter must not read raw/digests/canonical as runtime context

## QMD Scope Contract

QMD / runtime indexing may include only:

- `projections/openclaw/wiki-mirror/`
- `projections/openclaw/runtime-pack.json`
- `projections/openclaw/runtime-pack.md`
- `projections/openclaw/memory-prompt.md`

QMD / runtime indexing must not include:

- `raw/`
- `digests/`
- `canonical/`
- `canonical/registry/`
- `mutations/`
- `ops/`
- private OpenClaw workspace/session/config paths

This scope belongs in `docs/OPENCLAW.md`, `SECURITY.md`, and `POLICY.md`.

## Acceptance Tests

Required tests:

- Adapter reads a valid OpenClaw projection and valid lease, then writes a
  pending mutation pack containing `runtime_observation`.
- Adapter verifies existing source/digest evidence before mutation writeback and
  rejects nonexistent/fake evidence refs before writes.
- Adapter rejects real but unrelated source/digest evidence when runtime summary
  hash or live job id metadata does not match.
- Adapter accepts related evidence when source artifacts and digest
  `direct_evidence` carry matching `runtime_summary_evidence` binding.
- Adapter can create a runtime source packet and digest queue job without
  emitting a mutation pack when digest evidence does not yet exist.
- Adapter-created mutation proposal has runtime-only boundaries and no
  canonical writes.
- Adapter refuses missing/stale/wrong-subject/expired/symlinked lease before
  writes.
- Adapter refuses fabricated leases, summary-hash mismatches, and lease replay
  after success.
- Adapter refuses missing issued-index entries, nonce mismatches, and direct
  leased-job fabrication.
- Adapter refuses forged job plus forged `.tmp/writeback/` surfaces when no
  matching `.tmp/openclaw-live/issued-leases.jsonl` entry exists.
- Adapter refuses malformed projection input before writes.
- Adapter refuses stale/tampered runtime-pack or manifest metadata before
  writes.
- Adapter refuses projection wiki manifest traversal and symlinked wiki pages.
- Adapter rejects OpenClaw private config/session/workspace paths and
  secret-like values in runtime summary fields before writes.
- Adapter copies sanitized summaries to `.tmp/writeback/<job_id>/summary.json`
  and mutation metadata never contains the original private summary input path.
- Adapter refuses parent symlink, final symlink, preexisting job staging
  directory/file, and stale staged summary tampering before writes.
- Adapter routes conflicts to human-gated mutation packs.
- Docs state topology-maintainer allowed/forbidden write surfaces.
- Docs state QMD includes only OpenClaw projection/wiki mirror files and
  excludes raw/digests/canonical.

## Stop Conditions

- OpenClaw can write `canonical/` or `canonical/registry/`.
- Live bridge bypasses `writeback.py` for mutation pack construction.
- Runtime observations lose runtime-only sensitivity/scope/audience fields.
- External runtime writes do not require a valid lease.
- QMD indexing includes raw/digests/canonical wholesale.

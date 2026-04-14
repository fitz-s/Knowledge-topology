# Knowledge Topology Implementation Plan

## 1. Frozen Decisions

Keep these decisions stable:

- The `Knowledge topology` repository root is the canonical topology substrate.
  Do not create a production nested `.topology/` directory.
- Build builder workflow first. The first closed loop remains:
  `ingest -> digest -> reconcile -> apply -> compose builder -> coding agent ->
  writeback -> lint`.
- OpenClaw is a rich runtime consumer, not canonical owner. It reads this repo
  as `KNOWLEDGE_TOPOLOGY_ROOT` and writes only allowed proposal, audit, queue,
  and projection surfaces.
- Builder packs are task-scoped construction packs, not whole-topology dumps.
- Relationship tests are antibodies. Builder-critical invariants without
  relationship-test specs fail lint.
- Mutation packs plus deterministic apply are the only path into canonical
  state.

## 2. New Corrections

These corrections supersede the earlier plan:

- Active queues use spool directories, not shared JSONL queue files.
- Storage has a tracked/local-only boundary from the start.
- Source packets include public-safe content modes and redistribution status.
- Durable entities use immutable opaque ULID-prefixed IDs; slugs are aliases.
- Schema value domains and missing payload contracts are frozen before worker
  code.
- Relationship-test schema moves to Batch 0.5 before builder compose.
- Mutation packs include preconditions: `base_canonical_rev`,
  `subject_repo_id`, and `subject_head_sha`.
- Apply, compile, lint, and doctor are deterministic. LLMs stay in digest and
  reconcile proposal layers.
- Intake, fetch, and digest treat external content as untrusted and cannot touch
  canonical state.
- The CLI/Python library is the only business-logic path. MCP, hooks, skills,
  and OpenClaw adapters are facades.

## 3. Repository Shape

```text
Knowledge-topology/
  README.md
  AGENTS.md
  CLAUDE.md
  POLICY.md
  SCHEMA.md
  AUDIENCE.md
  STORAGE.md
  QUEUES.md
  SUBJECTS.yaml
  pyproject.toml

  src/knowledge_topology/
    __init__.py
    cli.py
    ids.py
    paths.py
    git_state.py
    schema/
    storage/
    workers/
    adapters/

  raw/
    packets/
    excerpts/
    local_blobs/

  digests/
    by_source/

  canonical/
    nodes/
    syntheses/
    registry/

  mutations/
    pending/
    approved/
    applied/
    rejected/

  ops/
    queue/
    events/
    gaps/
    escalations/
    reports/
    leases/

  projections/
    builders/
    tasks/
    openclaw/

  prompts/
  tests/
```

Production topology data lives at repo root. Nested `.topology/` paths may
exist only in migration or compatibility fixtures.

## 4. Subject and Revision Model

The topology can describe many external repositories or projects. Every
implementation-facing artifact must name the subject it is about.

`SUBJECTS.yaml` is the registry for stable subject IDs. A subject record will
eventually include:

- `subject_repo_id`
- human-readable `name`
- local path or remote URL
- default branch
- current observed head SHA
- visibility and sensitivity notes

`canonical_rev` is the revision of this topology repository's canonical truth.
V1 uses a conservative clean-worktree rule: `apply` and
`topology compose builder` are forbidden when the topology repo or subject repo
has uncommitted changes. A later implementation may use
`<commit sha> + <tree hash> + <dirty bit>`, but it must still reject dirty or
stale inputs.

Every mutation pack, job, file reference, builder pack, and writeback envelope
must include enough revision data to decide whether it is stale:

- `base_canonical_rev`
- `subject_repo_id`
- `subject_head_sha`

Apply and writeback must reject stale preconditions rather than attempting to
repair them silently. Re-reconcile against current canonical state instead.

## 5. Storage Contract

Tracked:

- `raw/packets/` metadata, normalized safe text, excerpts, fetch manifests
- `raw/excerpts/`
- `digests/`
- `canonical/`
- `mutations/approved/`
- `mutations/applied/`
- `mutations/rejected/`
- `ops/events/`: semantic audit event records
- `ops/gaps/`
- `ops/escalations/`
- `prompts/`
- `tests/`
- root policy, schema, storage, queue, audience, subject, and routing docs

Local-only or generated:

- `raw/local_blobs/`
- `.tmp/`
- `ops/queue/**`
- `ops/leases/**`
- temporary report/cache directories under `ops/reports/`
- `projections/**` by default
- `projections/tasks/**`
- generated OpenClaw runtime packs and wiki mirrors
- caches, logs, environment files

The `.gitignore` enforces the local-only side of this boundary.

## 6. Queue Contract

Active jobs use spool directories:

```text
ops/queue/<kind>/{pending,leased,done,failed}/job_<ulid>.json
```

Queue kinds:

- ingest
- digest
- reconcile
- apply
- compile
- audit
- writeback

Workers use atomic move/rename for state transitions:

1. write complete job to a temp path
2. rename into `pending/`
3. claim by renaming to `leased/`
4. finish by renaming to `done/` or `failed/`

Durable audit uses `ops/events/<yyyy>/<mm>/<dd>/evt_<ulid>.json`. Tracked
events are semantic history, not the active queue and not queue churn.

## 7. Public-Safe Source Packets

Every source packet declares `content_mode`:

- `public_text`: normalized text is safe to track.
- `excerpt_only`: only metadata and limited excerpts are tracked.
- `local_blob`: tracked packet stores hashes, references, manifests, and
  retrieval metadata; full content stays in `raw/local_blobs/` or a private
  store.

Every source packet declares `redistributable`: `yes`, `no`, or `unknown`.
Public repositories default to `excerpt_only` or `local_blob` unless the source
is clearly redistributable.

## 8. Core Schema

All durable entities use immutable opaque IDs:

- `src_`, `dg_`, `mut_`, `job_`, `evt_`, `gap_`, `clm_`, `edg_`, `nd_`

Human-readable slugs and aliases are mutable lookup fields. References use
opaque IDs.

Source packet minimum fields:

- `id`, `source_type`, `original_url`, `canonical_url`, `retrieved_at`
- `curator_note`, `ingest_depth`, `authority`, `trust_scope`
- `content_status`, `content_mode`, `redistributable`
- `hash_original`, `hash_normalized`, `artifacts`, `fetch_chain`

Digest minimum structure:

- `author_claims`, `direct_evidence`, `model_inferences`
- `boundary_conditions`, `alternative_interpretations`
- `contested_points`, `unresolved_ambiguity`, `open_questions`
- `candidate_edges`, `fidelity_flags`

Node minimum fields:

- `id`, `slug`, `type`, `scope`, `sensitivity`, `authority`
- `status`, `confidence`, `audiences`
- `source_ids`, `claim_ids`, `aliases`, `tags`, `file_refs`
- `supersedes`, `superseded_by`

File ref minimum fields:

- `repo_id`, `commit_sha`, `path`, `line_range`, `symbol`, `verified_at`

Mutation pack minimum fields:

- `id`, `proposal_type`, `proposed_by`
- `base_canonical_rev`, `subject_repo_id`, `subject_head_sha`
- `changes`, `evidence_refs`, `requires_human`, `human_gate_class`
- `merge_confidence`

Builder pack fixed outputs:

- `metadata.json`
- `brief.md`
- `constraints.json`
- `relationship-tests.yaml`
- `source-bundle.json`
- `writeback-targets.json`

`metadata.json` records `canonical_rev`, `subject_repo_id`,
`subject_head_sha`, and `generated_at`.

## 9. Deterministic Surfaces

LLM-assisted stages:

- digest
- reconcile proposal drafting
- optional brief prose in `brief.md`

Deterministic stages:

- ID generation
- path resolution
- spool queue transitions
- source packet validation
- mutation precondition checks
- apply transactions
- registry parity lint
- builder-pack load-bearing outputs
- OpenClaw runtime projection filtering
- public-safe lint
- doctor checks

The builder-pack load-bearing files must be compiled from canonical records:

- `metadata.json`
- `constraints.json`
- `relationship-tests.yaml`
- `source-bundle.json`
- `writeback-targets.json`

This avoids a second translation-loss pass during composition.

## 10. Worker Lifecycle

### Intake

Command:

```bash
topology ingest <url-or-path> \
  --note "why this matters" \
  --depth deep|standard|scan \
  --audience builders|openclaw|all \
  --subject <repo-id>
```

Intake creates immutable source packets and enqueues digest jobs. It does not
merge topology nodes.

### Fetch / Normalize

v1 resolvers:

- local draft
- GitHub artifact
- article/html
- PDF/arXiv

Deferred resolvers:

- audio/video transcript
- deep social thread expansion

Fetch failures become `partial` when useful data exists. Escalate only for
canonical ambiguity, auth/paywall, catastrophic fetch failure, or unclear legal
and trust boundaries.

### Digest

Digest performs the four passes from the source drafts:

1. entity extraction
2. edge candidate detection
3. schema validation
4. fidelity check

Digest emits markdown and JSON. It preserves reasoning chain, assumptions,
boundaries, disagreement, alternative interpretations, and evidence strength.

### Reconcile

Reconcile reads canonical records, registries, aliases, syntheses, and gaps,
then emits mutation packs only. It does not edit canonical state.

Low-confidence matches do not silently merge. They create new nodes,
`RELATED_TO` edges, or contested proposals.

### Apply

Apply is the only canonical writer. It checks mutation preconditions, stages
writes, updates pages and registries, runs parity lint, writes an audit event,
and moves the mutation pack to the correct state.

Apply rejects stale proposals and human-gated proposals without approval.

### Compile

Compile is deterministic. It generates builder and runtime projections from
canonical records and registry data.

Builder compile comes first. OpenClaw compile comes after the builder closed
loop works.

### Writeback

Builder writeback reads git diff, tests changed, commands run, task ID, and
session summary. It emits mutation packs and relationship-test deltas.

OpenClaw writeback emits lower-authority runtime observations, standing orders,
operator preference proposals, and session summaries. Runtime observations do
not auto-promote to active canonical truth.

## 11. Command Surface

All business logic goes through one Python package and CLI. Integrations are
thin facades.

P0-P9 shipped CLI commands:

- `topology init`
- `topology ingest`
- `topology digest`
- `topology reconcile`
- `topology apply`
- `topology compose builder`
- `topology compose openclaw`
- `topology writeback`
- `topology lint`
- `topology doctor`
- `topology agent-guard`
- `topology openclaw`

P0-P9 shipped doctor subcommands:

- `topology doctor stale-anchors`: find file refs whose subject head moved.

P11.5 shipped doctor subcommands:

- `topology doctor queues`: report queue health without mutating jobs.
- `topology doctor public-safe`: find tracked unsafe raw content.
- `topology doctor projections`: find stale or leaking projections.
- `topology doctor canonical-parity`: compare node pages and registries.

P11.6 shipped subject commands:

- `topology subject add`
- `topology subject refresh`
- `topology subject show`
- `topology subject resolve`

OpenClaw bridge commands:

- `topology openclaw capture-source`: capture runtime summary evidence.
- `topology openclaw issue-lease`: issue a topology-owned live writeback lease.
- `topology openclaw lease`: lease the next OpenClaw writeback job.
- `topology openclaw run-writeback`: validate evidence and emit writeback
  proposals through the live bridge.

Adapters may call the CLI or library, but must not implement separate business
rules.

## 12. Integration Strategy

Codex:

- `AGENTS.md` stays thin and route-oriented.
- `.agents/skills/topology-consume/`
- `.agents/skills/topology-writeback/`
- `.codex/config.toml` topology MCP registration is deferred until a tested MCP
  server exists.
- Codex consumes task packs, not whole topology.

Claude Code:

- `CLAUDE.md` stays thin and route-oriented.
- `.claude/skills/topology-consume/`
- `.claude/skills/topology-writeback/`
- `.claude/settings.json` blocks direct `Write` / `Edit` / `MultiEdit`
  canonical writes through a tested guard.
- Claude changed-file lint/writeback hooks are deferred.
- Claude consumes task packs plus skills, not whole topology.

OpenClaw:

- `KNOWLEDGE_TOPOLOGY_ROOT` points at this external repo.
- P9 ships a structured-only local runtime projection under
  `projections/openclaw/`.
- P9 runtime records exclude natural-language `summary` / `statement`, `tags`,
  and `file_refs`.
- P11.6 adds a controlled local-only file index at
  `projections/openclaw/file-index.json`; runtime-pack metadata may point to it,
  but runtime records and docs surfaces must not inline its rows.
- Live OpenClaw adapter/workspace writes, external-write queue leases,
  memory-wiki/QMD import or live validation, and OpenClaw natural-language
  runtime sanitizer are deferred.
- Memory-wiki may consume a derived mirror later; it does not own authority.

## 13. Maintenance Invariants

These invariants must remain true as the system grows:

- Queue jobs are one file per job and move by atomic rename.
- Canonical state changes only through apply.
- Runtime observations start with low authority.
- Stale mutation packs are rejected.
- Builder packs are stale when their canonical or subject revision changes.
- Builder packs traverse only allowed edge types and include bounded nodes,
  sources, and file refs.
- Operator-only and runtime-only records cannot leak into builder packs.
- Public repository safety is checked before source packet tracking.
- File refs carry `repo_id`, `commit_sha`, and `verified_at`.
- Every builder-critical invariant has a relationship-test spec.
- CLI/library code owns business rules; adapters never fork them.
- Every big package requires package-level `$ralplan`, implementation evidence,
  Reviewer approval, Critic approval, and any required Gemini validation before
  the next package is unfrozen.

## 14. Execution Batches

### Batch 0: Spec Freeze

Add or update:

- `CLAUDE.md`
- `POLICY.md`
- `SCHEMA.md`
- `AUDIENCE.md`
- `STORAGE.md`
- `QUEUES.md`
- `SUBJECTS.yaml`
- `.gitignore`
- `pyproject.toml`
- `src/knowledge_topology/__init__.py`
- `tests/fixtures/`

Completion:

- tracked/local-only rules are in `STORAGE.md`
- spool queue semantics are in `QUEUES.md`
- source/digest/node/mutation/builder-pack fields are in `SCHEMA.md`
- root `AGENTS.md` and `CLAUDE.md` remain thin routing files
- `.gitignore` enforces local-only generated surfaces
- `pyproject.toml`, package marker, and fixture directory exist
- no worker behavior is introduced yet

### Batch 0.5: Semantic Freeze Corrections

Build:

- freeze schema enumerations and missing payload contracts
- move relationship-test schema before builder compose
- seed `SUBJECTS.yaml` with an example contract
- freeze clean-worktree or dirty-bit canonical revision rule
- define `mutations/pending/` as tracked durable review artifact only
- mark `projections/**` generated/local-only by default
- split structured registry authority from narrative page authority
- move tracked audit away from queue churn semantics
- state queue v1 as single-filesystem only
- strengthen file refs with anchor kind and excerpt hash
- operationalize worker trust profiles

Completion:

- root docs and `.gitignore` agree
- one fixture validates schema enums and relationship-test shape
- one fixture subject exists
- queue fixture covers poisoned-job handling
- no worker implementation starts

### Batch 1: Engine Skeleton

Build:

- `topology init`
- path resolver
- ID generator
- schema loader
- filesystem transaction helper
- spool queue helper

Completion:

- new repo can run `topology init`
- init is idempotent
- schema fixtures pass
- queue helper can create, lease, complete, fail, and requeue a fixture job
- path helper never creates nested production `.topology/`

### Batch 2: Source Packet + Fetch

Build first:

- local draft
- GitHub artifact
- article/html
- PDF/arXiv

Completion:

- each input creates `raw/packets/src_*`
- packet includes `content_mode`
- partial fetches do not break the pipeline
- public-safe lint catches unsafe tracked blobs
- untrusted fetched content never gains canonical write permissions

### Batch 3: Digest

Build:

- `topology digest`
- `digest.md` and `digest.json`
- prompt runner/model adapter
- fidelity flags and strict output validation

Completion:

- fixture source produces valid digest
- invalid digest output fails before reconcile
- digest separates author claims, direct evidence, model inference, contested
  points, and unresolved ambiguity
- digest records fidelity flags

### Batch 4: Reconcile + Mutation Pack

Build:

- registry reader
- alias matcher
- conservative merge policy
- `topology reconcile`

Completion:

- reconcile only emits mutation packs
- low-confidence matches never silent-merge
- every pack has preconditions
- stale `base_canonical_rev` is detectable before apply
- mutation pack evidence refs resolve

### Batch 5: Apply Gate

Build:

- `topology apply`
- auto gate and human gate
- page/registry transaction writes
- parity lint

Completion:

- only apply writes canonical
- stale proposals are rejected
- high-risk gate classes escalate
- page and registry parity lint passes after apply
- apply writes durable audit events

### Batch 6: Builder Compose

Build:

- `topology compose builder`
- `metadata.json`, `brief.md`, `constraints.json`,
  `relationship-tests.yaml`, `source-bundle.json`, `writeback-targets.json`

Completion:

- real coding task closes one builder loop
- stale pack detection works
- operator/runtime-only data does not leak
- load-bearing pack files are deterministic compiler outputs
- builder-critical invariants emit relationship-test specs

### Batch 7: Writeback + Antibody Lint

Build:

- `topology writeback`
- `topology lint`
- `topology doctor`
- relationship-test schema
- missing-antibody, stale-anchor, projection-leakage, public-safe lints

Completion:

- real code change produces mutation pack and relationship-test delta
- missing builder-critical antibody fails lint
- code/topology conflict becomes contested
- stale file refs are reported by doctor
- projection leakage lint runs

### Batch 8: Codex / Claude Integration

Build:

- topology consume/writeback skills for Codex and Claude
- Codex project MCP config after CLI stability
- Claude hooks after CLI stability

Completion:

- Codex and Claude both compose, implement, and write back through same CLI
- Claude hooks and Codex skills call shared CLI/library code only
- root instruction files remain routing files, not procedure dumps

### Batch 9: OpenClaw Integration

Build last:

- `topology compose openclaw`
- runtime pack and wiki mirror
- OpenClaw adapter
- queue leases around external writes

Completion:

- OpenClaw writes only allowed surfaces
- memory-wiki reads mirror only
- runtime-only directives do not leak into builder packs
- external-root queue writes use leases
- OpenClaw runtime observations do not auto-promote to active canonical truth

## 15. Stop Conditions Before Coding

Do not start worker implementation until Batch 0 is committed and pushed.

Do not start MCP, hooks, Claude skills, Codex skills, or OpenClaw adapters until
the CLI/library contracts are exercised by local tests.

Do not start OpenClaw integration until one builder closed loop has completed
against a real coding task.

Do not ingest full third-party blobs into tracked files unless `content_mode`
and `redistributable` make it safe.

Do not unfreeze the next big package until `PACKAGE_GATES.md` is satisfied:
package ralplan/reality check, verification evidence, Reviewer approval,
Critic approval, and required Gemini artifact or explicit user waiver.

## 16. Risks

- Queue corruption: use spool files, atomic moves, lease expiry, and
  `doctor queues`.
- Generated garbage in Git: enforce `STORAGE.md` through `.gitignore` and lint.
- Public redistribution risk: default uncertain sources to `excerpt_only` or
  `local_blob`.
- Stale proposals: require mutation preconditions and reject stale packs.
- Second LLM translation loss: keep apply/compile deterministic.
- Runtime chatter pollution: treat runtime observations as low authority until
  reconcile/apply promotes them.
- Prompt injection: isolate untrusted source workers and keep them unprivileged.
- Adapter drift: all integrations call the same CLI/Python library.

## 17. ADR

Decision: Freeze Batch 0 around a repo-root canonical substrate with spool
queues, public-safe raw packets, opaque IDs, mutation preconditions,
deterministic apply/compile, and thin builder/runtime routing.

Drivers:

- durable cross-session and cross-runtime knowledge
- low translation loss
- public repository safety
- multi-worker reliability
- builder-first delivery

Rejected:

- Active shared JSONL queues | unsafe under concurrent multi-agent writes.
- Nested production `.topology/` directory | redundant because this repo is the
  topology substrate.
- OpenClaw as canonical owner | private runtime workspace and memory-wiki are
  derived runtime surfaces.
- LLM-generated apply/compile outputs | reintroduces translation loss after
  digest.

Consequences:

- More contract files before worker code.
- The CLI/library must become the single business-logic path.
- OpenClaw integration waits until builder closed loop proves the substrate.

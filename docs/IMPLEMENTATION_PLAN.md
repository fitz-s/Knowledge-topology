# Knowledge Topology Implementation Plan

## 1. Deep Reading Synthesis

You are building a repository-root knowledge substrate, not a generic second
brain and not a search index. The core product is a durable topology that
converts Fitz-curated raw material into executable knowledge for agents.

The first draft establishes the philosophy:

- Translation fidelity is more important than retrieval scale.
- A source is valuable because Fitz curated it, and `curator_note` is the
  human judgment injection point.
- The system must preserve claims, methods, assumptions, boundaries, open
  questions, alternative interpretations, evidence strength, and provenance.
- Raw material should flow through raw ingestion, digest, topology, and
  composition.

The revised implementation-grade decision is:

- This `Knowledge topology` repository root replaces the proposed nested
  `.topology/` directory.
- The top-level project directories are the shared canonical substrate.
- The system has `raw / digests / canonical / mutations / ops / projections /
  prompts / tests`, not only raw/digest/topology/composition.
- Codex and Claude consume task-scoped builder packs; OpenClaw consumes thicker
  runtime packs.
- OpenClaw reads and writes this repository as an external shared topology root,
  not as memory inside an OpenClaw-private agent workspace.
- Canonical edits happen through mutation packs and an apply gate.
- Relationship tests are antibodies: builder-critical invariants must compile
  into machine-checkable specs.
- The maintenance model is a worker network, not one omniscient daemon.

The stable interpretation: this project is a file-first compiler from curated
sources and session learnings into agent-usable construction briefs, runtime
memory packs, and proof obligations.

## 2. Principles

- Preserve reasoning before compressing content.
- Make every claim traceable to sources, evidence, and authority.
- Keep canonical truth in repo files; keep indexes and memories derived.
- Split builder and runtime audiences cleanly.
- Convert important knowledge into constraints, tests, and writeback targets.
- Minimize human review by gating only authority-changing decisions.
- Prefer queue/job contracts over runtime-specific agent magic.

## 3. Decision Drivers

1. Cross-agent durability: knowledge must survive fresh sessions and different
   runtimes.
2. Translation fidelity: ingest and digest must not flatten uncertainty or
   reasoning chains.
3. Builder usefulness: agents need small construction packs with invariants,
   interfaces, file anchors, and tests, not a giant memory dump.

## 4. Chosen Architecture

Use the repository root as the canonical substrate and compile audience
specific projections from it. The old `.topology/` name is now the name of this
repo's role, not a directory to create inside the repo.

```text
Knowledge topology/
  README.md
  AGENTS.md
  POLICY.md
  SCHEMA.md
  AUDIENCE.md
  raw/
  digests/
  canonical/
  mutations/
  ops/
  projections/
  prompts/
  tests/
```

Authority order:

1. `raw/`: original source packets and fetch artifacts.
2. `digests/`: model-produced but provenance-preserving digests.
3. `canonical/`: authoritative nodes, syntheses, and registries.
4. `mutations/`: proposed canonical changes.
5. `ops/`: queues, leases, gaps, events, reports, and escalations.
6. `projections/`: generated builder and OpenClaw views.

Codex and Claude should never consume or edit the entire topology directly.
They receive builder packs under `projections/tasks/<task-id>/`:

- `brief.md`
- `constraints.json`
- `relationship-tests.yaml`
- `source-bundle.json`
- `writeback-targets.json`

OpenClaw receives richer runtime projections from this external repository:

- `runtime-pack.md`
- `runtime-pack.json`
- `memory-prompt.md`
- `wiki-mirror/`

OpenClaw write policy:

- Read access: OpenClaw agents may read the full repository root as shared
  context.
- Direct write access: OpenClaw agents may write `raw/`, `mutations/`, `ops/`,
  and generated `projections/openclaw/` artifacts.
- Restricted write access: OpenClaw agents must not directly edit
  `canonical/`, `canonical/registry/`, or root policy/schema documents outside
  an apply-worker path.
- Sync model: OpenClaw treats the repository as an external mounted path or Git
  checkout, records writes in `ops/events.jsonl`, and uses leases before
  mutating shared queues.

## 5. RALPLAN-DR Summary

### Principles

- File-backed canonical truth beats hidden runtime memory.
- Provenance and authority are part of the data model, not optional metadata.
- Generated projections are disposable; canonical history is not.
- Builder knowledge must become tests, schemas, or constraints when possible.
- Human attention is for authority changes, not routine digestion.

### Viable Options

Option A: Keep the first draft's four-layer model.

- Pros: smaller concept surface and easier first prototype.
- Cons: underspecifies ops, projections, apply gates, writeback, and builder
  antibodies.

Option B: Adopt the `Knowledge topology` repository itself as the substrate and
worker network.

- Pros: handles Codex, Claude, OpenClaw external read/write, canonical
  authority, projections, queues, and proof obligations explicitly.
- Cons: larger initial scaffolding and more schema work before visible value.

Option C: Use a graph or vector database as the primary topology.

- Pros: fast traversal/search and common off-the-shelf tooling.
- Cons: loses human-auditable file authority and makes provenance-bearing
  review harder.

Chosen: Option B, with graph/vector/QMD/OpenClaw wiki as derived accelerators.
No nested `.topology/` directory is created for production use.

## 6. Requirements

- Initialize the repository root with documented topology directory
  responsibilities.
- Define machine-readable schemas for source packets, digests, nodes, edges,
  mutation packs, projections, and relationship tests.
- Provide CLI or script entry points for init, ingest, digest, reconcile,
  apply, compose, lint, doctor, and writeback.
- Preserve `curator_note`, authority, trust scope, evidence strength, and
  content status for every source.
- Produce both human-readable markdown and machine-readable JSON for digests.
- Require mutation packs for canonical changes.
- Compile builder packs before building OpenClaw runtime packs.
- Define OpenClaw external-root read/write rules, leases, queue writes, and
  writeback boundaries.
- Fail lint when builder-critical invariants lack relationship-test specs.
- Emit writeback proposals after builder sessions that change decisions,
  invariants, interfaces, or runtime assumptions.

## 7. Acceptance Criteria

- A fresh repo can run `topology init` and produce the root topology tree that
  passes schema and lint checks.
- Five representative inputs produce valid `raw/src-*` packets: article/html,
  PDF, audio/video transcript, social thread, and GitHub artifact.
- Three sources can pass through digest, reconcile, apply, and canonical node
  creation without direct canonical edits.
- A real coding task can call builder composition, consume a task pack, make a
  code change, and emit writeback proposals.
- A builder-critical invariant without a relationship-test spec fails lint.
- OpenClaw projection is generated only from canonical and ops data, never as
  canonical source.
- OpenClaw agents can read the external topology root and write allowed
  surfaces without direct canonical edits.
- Human escalation cards are emitted for high-impact contradictions,
  supersession/delete, Fitz beliefs, operator directives, and weak high-impact
  merges.

## 8. Implementation Steps

### Phase 0: Repository Contract

- Keep `AGENTS.md` as the agent operating contract.
- Add project docs for architecture, policy, schema, and audience split.
- Decide initial implementation language only when the first executable surface
  is needed; do not add dependencies before the CLI shape is clear.

Verification:

- Markdown files describe authority boundaries, worker roles, and red lines.
- No generated runtime state is committed.

### Phase 1: Topology Skeleton

- Update root `README.md`; create root `POLICY.md`, `SCHEMA.md`, and
  `AUDIENCE.md`.
- Create empty directories for raw, digests, canonical, mutations, ops,
  projections, prompts, and tests.
- Seed registries: `nodes.jsonl`, `claims.jsonl`, `edges.jsonl`,
  `aliases.jsonl`, and `file_refs.jsonl`.
- Seed ops files: queues, `leases.json`, `events.jsonl`, and `gaps.jsonl`.
- Implement `topology init`.

Verification:

- Empty topology passes schema checks.
- Running init twice is idempotent.

### Phase 2: Source Intake and Fetch

- Implement `topology ingest <url-or-path> --note --depth --audience`.
- Normalize source packets with required authority and trust fields.
- Implement resolvers for article/html, PDF/arXiv, audio/video transcript,
  social thread, GitHub artifact, and local draft.
- Store partial fetches with `content_status: partial` instead of failing the
  whole pipeline.

Verification:

- Each source type creates a valid `raw/src-*` packet.
- `curator_note` is carried forward exactly.
- Fetch provenance records original URL, canonical URL, method, timestamp,
  hash, and content status.

### Phase 3: Digest, Reconcile, and Apply

- Store worker prompts under `prompts/`.
- Implement deep digest with entity extraction, edge candidate detection,
  schema validation, and fidelity check.
- Emit `digest.md` and `digest.json`.
- Implement reconcile so it outputs mutation packs only.
- Implement apply gates for automatic and human-gated changes.

Verification:

- Digests separate author claims, direct evidence, model inference, contested
  points, and unresolved ambiguity.
- Reconcile does not silently merge low-confidence matches.
- Apply is the only non-fixture path that writes canonical files.

### Phase 4: Builder Projection First

- Implement `topology compose --audience builder --task <task-id>`.
- Generate `brief.md`, `constraints.json`, `relationship-tests.yaml`,
  `source-bundle.json`, and `writeback-targets.json`.
- Keep packs task-scoped and implementation-focused.

Verification:

- Builder pack excludes operator-only directives and broad background reading.
- Pack contains enough decisions, invariants, interfaces, file anchors, and
  unknowns to guide a coding agent.

### Phase 5: Antibodies, Lint, and Writeback

- Define relationship-test schema.
- Compile every builder-critical invariant into a relationship-test spec.
- Add lint checks for orphan nodes, stale claims, unresolved contradictions,
  broken supersession chains, invalid file refs, projection leakage, and
  missing antibodies.
- Implement `topology writeback` from git diff, tests changed, commands run,
  and session summary.

Verification:

- Missing relationship tests fail lint for builder-critical invariants.
- Writeback produces mutation packs and relationship-test deltas.
- Topology contradictions are marked contested, not overwritten silently.

### Phase 6: Codex and Claude Integration

- Add a topology MCP server when the local CLI contracts are stable.
- Add `topology-consume` and `topology-writeback` skills for both Codex and
  Claude.
- Keep root instruction files thin: routing rules in AGENTS/CLAUDE, procedures
  in skills.
- Add hooks or checks that block direct canonical edits outside apply paths.

Verification:

- Codex and Claude can compose builder packs and emit writeback proposals for
  the same task without duplicating procedure text.

### Phase 7: OpenClaw Runtime Projection

- Treat this repository as `KNOWLEDGE_TOPOLOGY_ROOT`: an external mounted path
  or Git checkout that OpenClaw agents read and write beside their private
  workspaces.
- Implement `topology compose --audience openclaw`.
- Generate runtime pack markdown/JSON, memory-prompt supplement, and
  `wiki-mirror/`.
- Ensure OpenClaw maintainer agents write `raw/`, `mutations/`, `ops/`, and
  generated `projections/openclaw/` only, unless they are explicitly executing
  the apply-worker path.
- Add lease handling for OpenClaw queue writes so concurrent agents do not
  corrupt `ops/queues/*.jsonl`.
- Add writeback envelopes for OpenClaw observations, durable operator
  preferences, standing orders, and session summaries.
- Treat OpenClaw memory-wiki and QMD as derived views.

Verification:

- OpenClaw projection includes runtime observations, standing orders, gaps,
  and pending escalations.
- OpenClaw runtime-only directives do not leak into builder packs.
- OpenClaw can read the external topology root and write allowed surfaces while
  direct edits to canonical surfaces are rejected by lint or hooks.

### Phase 8: Maintenance Network

- Wire queue files for ingest, digest, reconcile, apply, compile, audit, and
  writeback.
- Add lease/lock handling.
- Add nightly or CI lint sweeps.
- Add contradiction, freshness, orphanage, drift, and stale source reports.
- Emit escalation cards for the six human-gated decision classes.

Verification:

- Workers can resume from queues without relying on a single long-lived agent
  session.
- Reports are deterministic and traceable to canonical records.

## 9. Initial File Targets

- `AGENTS.md`: project agent contract.
- `docs/IMPLEMENTATION_PLAN.md`: this implementation plan.
- `README.md`: topology tree and authority explanation.
- `POLICY.md`: write gates, human gates, and red lines.
- `SCHEMA.md`: schema overview and field definitions.
- `AUDIENCE.md`: builder/runtime audience split.
- `prompts/*.md`: intake, digest, reconcile, compose, writeback,
  lint, repair, and escalate worker prompts.
- `tests/schemas/`: schema validation fixtures.

## 10. Risks and Mitigations

- Risk: The project becomes a high-quality note vault instead of an executable
  builder substrate.
  Mitigation: Make relationship tests and constraints first-class projection
  outputs.

- Risk: Agents bypass canonical discipline for speed.
  Mitigation: Block direct canonical edits with lint/hooks and require mutation
  packs.

- Risk: Human gates become too frequent.
  Mitigation: Gate only authority changes, high-impact conflicts, beliefs,
  operator directives, delete/supersede, scope upgrades, and high-consequence
  weak merges.

- Risk: Builder packs become too large.
  Mitigation: Keep them task-scoped and audience-filtered.

- Risk: OpenClaw runtime memory drifts into canonical authority.
  Mitigation: OpenClaw writes proposals and runtime observations; apply owns
  canonical updates.

- Risk: OpenClaw agents mutate the external repository concurrently and corrupt
  queues or canonical surfaces.
  Mitigation: require leases for queue writes, append-only events, and lint or
  hooks that reject direct canonical edits outside apply-worker commits.

## 11. ADR

Decision: Use the `Knowledge topology` repository root as the shared canonical
substrate, replacing the proposed nested `.topology/` directory, with
queue-driven workers and audience-specific projections.

Drivers:

- Durable cross-session and cross-agent knowledge.
- Translation fidelity and provenance.
- Builder usefulness through constraints, relationship tests, and writeback.

Alternatives considered:

- Four-layer topology from the first draft: too underspecified for ops,
  projections, and writeback.
- Nested `.topology/` directory: redundant because this repo is dedicated to
  the topology itself.
- OpenClaw-private topology: not shared enough for Codex and Claude builders.
- Graph/vector primary store: useful for acceleration but weaker as an
  auditable truth surface.

Why chosen:

- It gives every runtime a small, appropriate interface while preserving one
  external canonical truth surface.
- It turns knowledge into actionable construction packs and proof obligations.
- It keeps human judgment focused on high-value authority decisions.

Consequences:

- More up-front schema and CLI work.
- More explicit gates around canonical writes.
- Better long-term portability across Codex, Claude, OpenClaw, CI, and future
  workers.
- OpenClaw integration must handle external-path access, leases, and writeback
  boundaries explicitly.

Follow-ups:

- Build Phase 1 skeleton before adding ingestion dependencies.
- Define JSON schemas before generating real canonical records.
- Prototype one full builder loop before OpenClaw integration.

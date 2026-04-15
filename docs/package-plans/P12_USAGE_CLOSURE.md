# P12 Package Plan: Usage Closure

## Package Ralplan

P12 closes the gap between a working topology substrate and daily use by real
agents. The goal is:

> Let agents in external subject repositories automatically know how to use
> Knowledge Topology; let video sources move from URL to a deepenable evidence
> chain; let OpenClaw and maintainer workers form a routine maintenance loop.

P12 does not replace the canonical file-backed substrate with a graph database,
vector database, OpenClaw memory-wiki, or MCP server. It productizes the
consumer/install surfaces, media evidence workflow, runtime bundle, supervisor
loop, and evaluation layer around the existing authority model.

## External Findings Used

- Karpathy LLM Wiki: useful knowledge compounds when raw sources are compiled
  into durable wiki/schema artifacts instead of rediscovered on every RAG call.
  The risk is second-order muddiness unless compilation discipline and quality
  gates exist.
- OpenClaw memory-wiki: compiled pages, claims, evidence, contradictions, and
  dashboards are a runtime companion, not canonical authority.
- Graphiti: temporal invalidation and provenance are valuable, but graph write
  governance and ingestion latency are real operational risks.
- Mem0 graph memory: graph relations often augment vector retrieval; the graph
  is not automatically the source of truth.
- CodeWiki: cross-file and system-level synthesis are valuable, but generated
  docs cannot become canonical authority without review.
- MCPTube / TubeMCP-style video systems: video knowledge requires an explicit
  pipeline from URL to transcript, frame/vision evidence, metadata, and compiled
  knowledge.
- MemoryGraph / Neo4j Agent Memory: adoption depends on a quick start,
  protocol snippet, and deterministic install story, not only architecture.

## Reality Check

- `real-test` already has `video_platform` locator intake, local video artifact
  attachment, and video text artifacts flowing into digest requests.
- `docs/package-plans/REAL_TEST_PLAN.md` captures the broader external-pattern
  analysis but is not a package-gated mainline plan.
- `docs/MAINLINE_STATUS.md`, `docs/package-plans/P11_7_VIDEO_PLATFORM_INGEST.md`,
  and `docs/package-reviews/P11_7_UNFREEZE.md` now converge on the shipped
  P11.7 video-platform surface after P12.0. This convergence must be preserved
  before later P12 work proceeds.
- `docs/OPENCLAW.md` documents CLI wiring, but external repos do not yet get a
  generated local config, wrapper scripts, skills, or protocol snippets.
- `topology openclaw ...` exists, but there is no `topology bootstrap ...`.
- `topology video attach-artifact` is a low-level primitive; there is no
  operator-facing `topology video ingest` orchestration command.
- Digest depth has no benchmark gate. A shallow five-bullet output can still
  look operationally successful.
- There is no supervisor loop that routinely recovers queues, runs digest,
  reconciles, compiles projections, and reports escalations.

## Principles

1. Canonical stays file-backed, Git-reviewable, mutation-gated, and
   provenance-bearing.
2. Consumer packaging comes before MCP generalization.
3. Video/media extraction is local-provider orchestration, not public-safe fetch
   core behavior.
4. Supervisor automation proposes or applies only within explicit risk lanes;
   builder-active truth remains human-gated.
5. Benchmarks and doctor checks must make shallow knowledge and stale compiled
   artifacts visible.

## Decision Drivers

1. Real agent usability: a fresh external repo agent should know how to compose,
   consume, and write back without reading the whole topology repo.
2. Public-safe media evidence: platform video workflows must handle downloaded
   artifacts while preserving rights, privacy, and local-only blob boundaries.
3. Maintainer autonomy: routine queues and projections should be maintainable
   without turning an agent into an ungated canonical writer.

## Viable Options Considered

### Option A: Consumer Bootstrap First, Then Media/Supervisor

Build install/wiring commands first, then video/media orchestration, then
maintenance supervisor and evaluation.

Pros:

- Directly solves "agent does not know how to use topology."
- Lowers support burden before adding more workflows.
- Keeps MCP optional until the CLI contract is proven.

Cons:

- Video workflow remains partially manual until P12.2 lands.
- Supervisor benefits arrive later.

### Option B: Video Pipeline First

Make `topology video ingest` the first package, then bootstrap agents later.

Pros:

- Attacks the current Douyin/video pain immediately.
- Produces visible operator value quickly.

Cons:

- External agents still need manual wiring to use it.
- Adds new runtime providers before install/doctor conventions are stable.

### Option C: Supervisor First

Create `topology supervisor run` before bootstrap/video orchestration.

Pros:

- Begins daily maintenance loop early.
- Exposes queue and projection drift quickly.

Cons:

- Automates a system whose consumer install story is still manual.
- Higher risk of encoding premature authority behavior.

Chosen path: Option A with a mandatory P12.0 governance patch before any new
functional surface.

## ADR

Decision: P12 will ship as usage closure packages in this order:

1. P12.0 State Convergence Patch
2. P12.1 Consumer Bootstrap Package
3. P12.2 Video / Media Closure Package
4. P12.3 OpenClaw Consumer Bundle
5. P12.4 Maintainer Supervisor Package
6. P12.5 Evaluation / Benchmark Package

Drivers:

- Governance drift must be corrected before new package work.
- Consumer bootstrap unlocks every later surface.
- Video/media closure is the most visible real-use gap.
- OpenClaw bundle and supervisor should consume bootstrap conventions rather
  than invent parallel wiring.
- Evaluation must gate "real usable" claims before broader rollout.

Rejected:

- Build a topology MCP server first. Reason: the current pain is install story
  and deterministic local wiring, not missing protocol abstraction.
- Move canonical truth to graph/vector/OpenClaw memory-wiki. Reason: external
  systems are useful acceleration/projection layers, but they do not replace the
  repo's mutation/apply authority.
- Add an omniscient daemon. Reason: routine maintenance can be automated only
  within explicit authority lanes.

Consequences:

- P12 adds operator-facing commands and generated consumer repo files.
- Bootstrap must be rollbackable and manifest-backed.
- Video/media providers remain optional/local and must degrade to checklist
  mode.
- Supervisor starts with dry-run/proposal-only behavior before any auto-apply.

Follow-ups:

- Revisit MCP only after bootstrap proves the CLI contract.
- Design graph/QMD sidecar as derived rebuildable acceleration after P12.5.

## Package Construction Table

| Package | Goal | Files / Surfaces | Acceptance | Stop Condition |
| --- | --- | --- | --- | --- |
| P12.0 State Convergence Patch | Restore package/status consistency before more work | `docs/package-plans/P11_7_VIDEO_PLATFORM_INGEST.md`, `docs/package-reviews/P11_7_UNFREEZE.md`, `docs/MAINLINE_STATUS.md` | P11.7 plan/review/status all agree; shipped CLI list includes `topology video` explicitly | Status references a shipped surface without plan/review evidence |
| P12.1 Consumer Bootstrap Package | Make external repos self-wiring for Codex/Claude/OpenClaw | new bootstrap worker/module, `cli.py`, docs, generated subject-repo fixtures | `bootstrap claude/codex/openclaw`, `resolve-context`, and `doctor consumer` work in temp subject repos without copying canonical content | Bootstrap writes canonical, copies whole topology, or overwrites user config |
| P12.2 Video / Media Closure Package | Promote video workflow from primitives to operator command | `workers/fetch.py`, video worker/module, `cli.py`, docs, tests | `topology video ingest` orchestrates locator, optional providers, artifact attach, digest queue; unsupported platforms yield checklist, not silent failure | Public-safe fetch downloads rights-unsafe media or video ingest writes canonical |
| P12.3 OpenClaw Consumer Bundle | Turn OpenClaw integration into installable bundle | bootstrap openclaw output, `docs/OPENCLAW.md`, generated skill/config snippets | OpenClaw workspace gets skills, QMD path snippet, env/launcher script, and no canonical write path | OpenClaw/QMD indexes raw/canonical/mutations/ops or writes generated projection |
| P12.4 Maintainer Supervisor Package | Create routine maintenance loop without ungated authority | supervisor worker/module, `cli.py`, `doctor.py`, docs, queue tests | `supervisor run --dry-run` recovers/report queues, runs digest, proposes reconcile/apply/compile actions, emits escalations | Supervisor bypasses apply gate or mutates builder-active truth without human gate |
| P12.5 Evaluation / Benchmark Package | Prove usage closure improves depth and continuity | benchmark fixtures, rubric runner, docs, reports | Benchmarks measure builder success, digest depth, writeback acceptance, stale rate, video manual intervention, OpenClaw proposal acceptance, context relevance | "Real usable" is declared without benchmark evidence |

## P12.0 — State Convergence Patch

### Scope

Add the missing governance artifacts for P11.7 and align shipped status.

### Required Changes

- Add `docs/package-plans/P11_7_VIDEO_PLATFORM_INGEST.md`.
- Add `docs/package-reviews/P11_7_UNFREEZE.md`.
- Update `docs/MAINLINE_STATUS.md` so package matrix, shipped CLI reality, and
  real-use intake sections align.
- Ensure `topology video` is listed in shipped top-level CLI reality, not only
  mentioned in prose.

### Acceptance

- `MAINLINE_STATUS.md`, `package-plans/`, and `package-reviews/` agree on P11.7.
- Current shipped CLI list includes `topology video`.
- A status test fails if shipped commands are mentioned without corresponding
  plan/review artifacts.

### Stop Conditions

- P11.7 remains visible in status without package evidence.
- New P12 work starts before status convergence lands.

## P12.1 — Consumer Bootstrap Package

### New Commands

```bash
topology bootstrap claude --topology-root ... --subject-path ...
topology bootstrap codex --topology-root ... --subject-path ...
topology bootstrap openclaw --topology-root ... --subject-path ... --workspace ...
topology bootstrap remove --subject-path ...
topology resolve-context --topology-root ... --subject-path ... --json
topology doctor consumer --topology-root ... --subject-path ...
```

### Behavior

Bootstrap does wiring only:

- subject add/refresh/resolve
- `.knowledge-topology.json`
- `scripts/topology/compose_builder.sh`
- `scripts/topology/writeback.sh`
- `scripts/topology/resolve_context.sh`
- Codex local skills:
  `.agents/skills/topology-consume`, `.agents/skills/topology-writeback`
- Claude local skills:
  `.claude/skills/topology-consume`, `.claude/skills/topology-writeback`
- `.claude/settings.json` patch or merge-helper, never destructive overwrite
- OpenClaw skill/config snippet and QMD path snippet
- generated manifest recording every file written

### Acceptance

- Temp external repo bootstrap works for each target.
- Existing user config is merged or preserved, not overwritten.
- Generated wrappers compute `canonical_rev` and `subject_head_sha` at runtime.
- `doctor consumer` reports missing/stale generated files and stale subject
  head.
- `bootstrap remove` removes only files recorded in the manifest.

### Stop Conditions

- Bootstrap writes `canonical/`, `digests/`, `mutations/`, or topology
  projection content into the subject repo.
- Bootstrap copies whole topology content into the subject repo.
- Bootstrap requires manual canonical/head values.

### Blast Radius / Rollback / Monitor

- Blast radius: external repo agent config, hooks, skills, wrapper scripts.
- Rollback: generated manifest plus `bootstrap remove`.
- Monitor: bootstrap failure rate, first compose-builder success rate, stale
  subject-head rate, user-modified generated wiring count.

## P12.2 — Video / Media Closure Package

### New Command

```bash
topology video ingest "<url>" \
  --provider youtube|yt-dlp|browser-capture|manual-upload \
  --transcriber whisper|provider|none \
  --vision-provider gemini|openai|none \
  --auto-digest \
  --subject ...
```

`topology video attach-artifact` remains the low-level primitive.

### Provider Layers

1. YouTube transcript / YouTube local download.
2. Browser capture for Douyin, TikTok, Instagram, and app-first platforms.
3. Manual upload fallback.

### Behavior

- Public-safe fetch worker remains locator-only for platform video URLs.
- Local-only media providers handle download/transcription/frame extraction.
- Artifacts attach back to the `video_platform` source packet.
- Digest queue can run once enough evidence exists.
- Unsupported or blocked platforms produce a missing-artifacts checklist.

### Acceptance

- YouTube fixture path can produce packet, transcript or metadata, attached
  artifacts, digest job, and digest artifact in one operator-facing command.
- Douyin/TikTok fixture path degrades to capture plan + missing-artifacts
  checklist when provider cannot pull directly.
- Full media bytes never appear under tracked `raw/packets/`.
- Local blob growth is observable.

### Stop Conditions

- Public-safe fetch core downloads platform media.
- Platform download logic writes canonical state.
- Video ingest hides auth/copyright/platform failures as generic success.

### Blast Radius / Rollback / Monitor

- Blast radius: local dependencies, legal/rights boundary, local blob growth,
  digest prompt load.
- Rollback: existing locator + attach-artifact path.
- Monitor: per-platform success rate, manual-capture rate, transcript-missing
  rate, digest failure rate, local blob size, content-mode violations.

## P12.3 — OpenClaw Consumer Bundle

### Command

```bash
topology bootstrap openclaw \
  --topology-root ... \
  --workspace ... \
  --project-id ... \
  --subject ...
```

### Generated Bundle

- topology-maintainer skill
- runtime-consume skill
- session-end writeback skill
- QMD extra paths config snippet limited to `projections/openclaw/*`
- env file / launcher script that resolves canonical and subject revisions

### Runtime Protocol

1. Session boot: compose OpenClaw projection.
2. Runtime read: only runtime-pack, memory-prompt, wiki-mirror, file-index.
3. New source: `topology openclaw capture-source`.
4. Durable observation: `issue-lease -> lease -> run-writeback`.
5. Apply/compile: rebuild projection.
6. Memory-wiki indexes mirror only and never owns truth.

### Stop Conditions

- OpenClaw can write `canonical/`, `digests/`, or generated projections.
- QMD indexes `raw/`, `canonical/`, `mutations/`, or `ops/`.
- OpenClaw private workspace/session/config is copied into topology.

### Blast Radius / Rollback / Monitor

- Blast radius: external-root wiring, QMD scope, lease discipline.
- Rollback: CLI-only integration from `docs/OPENCLAW.md`.
- Monitor: lease failure rate, sanitizer rejection rate, unauthorized write
  attempts, stale projection mismatch rate, runtime-observed proposal acceptance
  rate.

## P12.4 — Maintainer Supervisor Package

### Command

```bash
topology supervisor run \
  --root ... \
  --digest-provider-command ... \
  --subject ... \
  --dry-run
```

### Behavior

Supervisor is protocol-driven and calls existing workers:

1. recover expired leases
2. run digest queue
3. run reconcile for ready digests
4. promote low-risk mutation packs or emit apply recommendations
5. compile builder/OpenClaw projections after canonical changes
6. run lint/doctor commands
7. emit escalation cards for humans

### Authority Lanes

May automate:

- source packets
- digest artifacts
- aliases / evidence append / gaps / reports
- runtime-only observation proposals

Must human-gate:

- decisions
- invariants
- interfaces
- contradictions
- supersedes/deletes
- Fitz beliefs
- operator directives
- cross-scope upgrades

### Stop Conditions

- Supervisor bypasses apply gate.
- Auto-apply modifies builder-active truth without human audit.
- Supervisor reimplements worker logic instead of calling existing workers.
- Queue backlog has no monitoring.

### Blast Radius / Rollback / Monitor

- Blast radius: maintenance cadence, queue state, accidental writes.
- Rollback: dry-run/proposal-only mode first.
- Monitor: backlog, failed/leased stuck jobs, duplicate proposals, human
  escalation rate, stale projection rate, auto-apply rejected by lint/doctor.

## P12.5 — Evaluation / Benchmark Package

### Metrics

- builder task success with/without builder pack
- task pack size vs success
- writeback acceptance rate
- stale pack rate
- conflict rate
- video ingest manual intervention rate
- OpenClaw runtime proposal acceptance rate
- context fragment relevance score

### Benchmark Fixtures

- code/repo source
- long video/lecture source
- non-technical source
- operator-maintenance scenario

### Acceptance

- A shallow digest cannot pass deep digest benchmark.
- Benchmark report is generated deterministically.
- Evaluation can compare at least two runs.
- Context overload is measured through pack size and relevance sampling.

### Stop Conditions

- "Real usable" is claimed without benchmark data.
- Benchmarks reward more text instead of better structured knowledge.

## Deliberate Pre-Mortem

1. Bootstrap corrupts a user's subject repo config.
   - Mitigation: manifest-backed writes, no destructive overwrite, remove
     command, fixture tests with pre-existing config.
2. Video pipeline becomes an unsafe crawler.
   - Mitigation: public-safe fetch remains locator-only; provider pipeline is
     local-only and explicit; rights-unsafe bytes never enter tracked packets.
3. Supervisor quietly writes bad canonical truth.
   - Mitigation: dry-run first, proposal-only default, strict human gates, lint
     and doctor after every proposed apply.

## Verification Plan

Unit:

- subject bootstrap path resolution and no-follow checks
- config merge helpers
- video provider adapters and missing-artifact status
- benchmark rubric scoring

Integration:

- temp subject repo bootstrap for Codex, Claude, OpenClaw
- video ingest with YouTube fixture and manual fallback fixture
- supervisor dry-run over seeded queues/digests/mutations
- OpenClaw bundle projection + writeback loop

E2E:

- fresh external repo: bootstrap, compose builder, run fake agent writeback
- platform video URL: locator, artifact attach, digest queue, benchmark pass
- maintainer loop: recover failed/leased jobs, run digest, compile projections,
  emit dashboard report

Observability:

- generated bootstrap manifest
- `doctor consumer`
- `doctor real-test`
- supervisor dry-run report
- benchmark report under `ops/reports/`

## Staffing Guidance

Solo/ralph lane:

- P12.0 and P12.1 can be implemented sequentially by one owner because they
  touch shared CLI/docs/config-generation surfaces.

Team lane:

- P12.2-P12.5 can split after P12.1:
  - executor: video/media orchestration
  - test-engineer: benchmark/rubric fixtures
  - architect: supervisor authority lanes
  - writer: agent install docs/protocol snippets
  - critic/security-reviewer: public-safe/media/provider risks

Use team only after P12.1 stabilizes the generated consumer manifest contract.

## P12 Definition of Done

P12 is complete when:

1. P11.7 governance artifacts are consistent.
2. A fresh external repo can be bootstrapped for Codex/Claude/OpenClaw.
3. A fresh agent can resolve context, compose a builder pack, and write back
   without undocumented steps.
4. Video URLs can move through locator, local artifact evidence, digest queue,
   and benchmarked digest.
5. OpenClaw has an installable consumer bundle and remains read-only over
   canonical/projection surfaces.
6. Maintainer supervisor can dry-run routine maintenance and produce human
   escalations.
7. Evaluation reports show whether knowledge is deeper, not merely larger.

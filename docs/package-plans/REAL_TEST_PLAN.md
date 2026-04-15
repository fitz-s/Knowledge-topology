# Real-Test Plan: Productized Knowledge Topology

## Why This Plan Exists

The current system has the right authority model: file-backed canonical state,
source packets, digests, mutation packs, apply gates, writeback, projections,
and runtime lint/doctor checks. The real-test failures are not primarily about
more graph theory. They are about making the system usable by operators and
agents without requiring them to remember a long ritual.

External projects point in the same direction:

- Karpathy's LLM Wiki pattern is valuable because knowledge is compiled into a
  durable artifact instead of rediscovered on every RAG query. The core shape is
  raw sources, wiki, and schema; the wiki compounds as new sources and questions
  arrive. Source: <https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f>
- OpenClaw memory-wiki treats compiled pages, structured claims/evidence,
  provenance, contradictions, dashboards, and digest artifacts as a companion to
  active memory, not a replacement for it. Source:
  <https://docs.openclaw.ai/uk/plugins/memory-wiki>
- Graphiti's strongest lesson is temporal invalidation and provenance; its
  open issue history also shows ingestion latency can become a user-facing
  product problem. Sources:
  <https://deepwiki.com/getzep/graphiti/3.2-temporal-awareness>,
  <https://github.com/getzep/graphiti/issues/356>
- Mem0 graph memory is a retrieval augmentation layer: entities and edges sit
  beside embeddings, while search still returns vector results plus relation
  context. Source: <https://docs.mem0.ai/open-source/features/graph-memory>
- CodeWiki shows that repository knowledge becomes useful when it captures
  cross-file, cross-module, and system-level interactions through hierarchical
  decomposition, not isolated function notes. Source:
  <https://arxiv.org/abs/2510.24428>
- Video systems that work do explicit extraction pipelines: transcript,
  metadata, key frames or scene changes, vision descriptions, then compiled
  knowledge. Sources: <https://0xchamin.github.io/mcptube/>,
  <https://tubemcp.com/>
- MemoryGraph and Neo4j Agent Memory show adoption depends on an install story:
  add this MCP/CLI, paste this protocol into AGENTS/CLAUDE, run this verification
  prompt. Sources: <https://memorygraph.dev/docs/memory-protocol/>,
  <https://neo4j.com/labs/agent-memory/tutorials/mcp-server/>

## Real-Test Thesis

Do not replace the topology with a graph database, vector DB, or OpenClaw wiki.
Instead:

1. Keep canonical truth in this repo.
2. Treat OpenClaw, QMD, graph/vector stores, and memory-wiki as derived
   projections or acceleration layers.
3. Productize the operator and agent surfaces so real users can ingest,
   inspect, deepen, and write back without memorizing the internals.
4. Add benchmarks and health checks that prove knowledge gets deeper, not only
   longer.

## Non-Negotiable Constraints

- Canonical state changes only through mutation/apply.
- OpenClaw never owns canonical truth and never writes `canonical/` or generated
  projection files directly.
- Graph/vector sidecars, if added, are derived acceleration layers only.
- Video/media intake must preserve public-safe boundaries: downloaded media
  stays local-only; tracked records hold hashes, manifests, excerpts, and
  operator-authored descriptions.
- Generic prompts may require structural fidelity, but must not hard-code the
  vocabulary of a single source.

## Construction Packages

| Package | Goal | Files / Surfaces | Acceptance |
| --- | --- | --- | --- |
| RT1 Agent Install Story | Make OpenClaw/Codex/Claude setup copy-pasteable | `docs/OPENCLAW.md`, new `docs/AGENT_INSTALL.md`, `.agents/skills/*`, `.claude/skills/*` | A fresh agent can read one page, compose projection, run lint/doctor, ingest a source, and write back without hidden steps |
| RT2 Video Evidence Pipeline | Promote video from low-level primitives to an operator workflow | `workers/fetch.py`, CLI, docs, tests | A platform URL produces locator packet; downloaded video attaches as local blob; transcript/key-frame/audio artifacts enter digest request; missing artifacts are reported as actionable gaps |
| RT3 Deep Digest Benchmarks | Measure whether digest is deep, not merely present | `tests/fixtures/real-test/`, new benchmark runner under `workers/` or `tests/` | Golden fixture checks misconception, thesis, segments, concepts, mechanisms, evidence, caveats, open questions, and no domain hard-coding |
| RT4 Compile Discipline | Ensure compiled projections remain healthy and stale-aware | `workers/lint.py`, `workers/doctor.py`, docs | Doctor reports stale projection, missing digest artifacts, shallow digest shape, unreviewed writeback backlog, and projection drift |
| RT5 Derived Graph/QMD Plan | Define graph/vector/QMD as acceleration only | `docs/GRAPH_SIDECAR.md`, projection compiler docs | Plan names read-only inputs, rebuild strategy, deletion semantics, provenance mapping, and explicit ban on canonical writes |
| RT6 Repo Archaeology / CodeWiki Lane | Add cross-file synthesis without making auto-docs authoritative | `compose_builder.py`, `compose_openclaw.py`, file-index docs | Builder/OpenClaw packs can include bounded architecture synthesis and file-ref index; canonical adoption still requires mutation/apply |
| RT7 Operator Dashboard | Give the human a queue of what needs attention | `doctor.py`, optional report generator under `ops/reports/` | One command shows pending video artifacts, failed queues, stale subject heads, unreviewed mutations, shallow digests, and projection freshness |

## RT1 Details: Agent Install Story

Borrow from MemoryGraph and Neo4j Agent Memory: the system should ship an
installation narrative, not only primitives.

Required deliverables:

- `docs/AGENT_INSTALL.md`
- copy-paste OpenClaw environment block:
  `KNOWLEDGE_TOPOLOGY_ROOT`, `OPENCLAW_PROJECT_ID`, `SUBJECT_REPO_ID`
- one command sequence:
  `subject refresh -> compose openclaw -> lint runtime -> doctor projections`
- one writeback sequence:
  `openclaw issue-lease -> openclaw lease -> openclaw run-writeback`
- one "paste into agent instructions" protocol:
  read projection first, never write canonical, use writeback bridge, run doctor
- smoke test showing CLI help exposes every documented command

Stop condition:

- If a new agent still needs undocumented repo knowledge to use the topology,
  RT1 is not done.

## RT2 Details: Video Evidence Pipeline

Current state after real-test:

- `video_platform` locator intake exists.
- `topology video attach-artifact` can bind local video, transcript, key-frame,
  audio-summary, or landing metadata evidence.
- Digest requests include attached text artifacts.

Next work:

- Add `topology video status --source-id ...` to report which artifacts are
  missing.
- Add `topology video prepare-digest --source-id ...` to fail with actionable
  missing-artifact messages when the source only has a locator.
- Add optional extractor adapters that are explicitly local/optional:
  `yt-dlp`/browser-download manifest, `ffmpeg` frame sample manifest, transcript
  import. These adapters must not be required for core ingest.
- Add docs for manual download workflows:
  "open link externally -> download file -> attach local blob -> attach
  transcript/key-frame/audio evidence -> run digest queue."

Stop condition:

- If a long video can still only become a locator plus shallow summary, RT2 is
  not done.

## RT3 Details: Deep Digest Benchmarks

Borrow from CodeWiki and video knowledge engines: deep knowledge requires an
evaluation shape.

Benchmark fixture shape:

- source packet fixture
- transcript fixture
- key-frame descriptions fixture
- expected digest rubric, not exact model text

Rubric dimensions:

- target misconception or motivating question
- central thesis
- segment structure
- named concepts as found in the source
- mechanism/causal explanation
- boundary conditions
- examples and evidence role
- implications
- caveats / contested points
- open questions

Important rule:

- Fixtures must be domain-diverse. Use at least one technical/code source, one
  video/lecture source, and one non-technical source. Do not tune the prompt to
  one domain.

Stop condition:

- If a digest with five generic bullet points can pass, RT3 is not done.

## RT4 Details: Compile Discipline

Borrow from the LLM Wiki criticism: compiled second-order information can make
the picture muddier unless quality controls are first-class.

Add doctor/lint checks for:

- digest exists but is shallow against benchmark/rubric
- video locator lacks follow-up artifacts
- writeback proposal backlog
- projection generated from stale `SUBJECTS.yaml` head or canonical rev
- file-index row count changes without projection refresh
- OpenClaw projection text surfaces accidentally inline file-index rows

Stop condition:

- If the system can silently accumulate shallow summaries or stale projections,
  RT4 is not done.

## RT5 Details: Derived Graph/QMD Plan

Borrow from Graphiti/Mem0 without copying their authority model.

Allowed:

- graph/vector/QMD sidecars built from canonical + projections
- temporal invalidation metadata as a derived query index
- relation search and repo archaeology acceleration

Forbidden:

- sidecar writes to canonical
- sidecar-generated claims treated as authoritative without mutation/apply
- graph nodes that cannot trace back to source/digest/mutation IDs

Required design:

- rebuild from scratch command
- source-to-node provenance map
- stale sidecar detection
- no-follow path checks for sidecar output
- deletion/retraction model

Stop condition:

- If graph backend becomes the easiest write path, RT5 is blocked.

## RT6 Details: Repo Archaeology / CodeWiki Lane

Borrow from CodeWiki only where it fits:

- hierarchical decomposition
- cross-file/system-level synthesis
- architecture and data-flow summaries

Do not:

- commit auto-docs as canonical truth
- let generated docs override registry records

Deliverables:

- controlled architecture synthesis projection
- file-ref bounded index by subject/head
- mutation proposal shape for durable architecture decisions
- benchmarks for cross-file synthesis usefulness

## RT7 Details: Operator Dashboard

The operator should see the system state in one command.

Candidate command:

```bash
topology doctor real-test --root "$KNOWLEDGE_TOPOLOGY_ROOT"
```

Report sections:

- subject freshness
- generated projection freshness
- queue state
- pending mutations
- video sources missing artifacts
- digests missing or shallow
- OpenClaw projection availability
- unsafe/local-only surface leakage

Stop condition:

- If the operator has to run five commands and inspect files manually, RT7 is
  not done.

## Priority Order

1. RT1 Agent Install Story
2. RT2 Video Evidence Pipeline
3. RT3 Deep Digest Benchmarks
4. RT4 Compile Discipline
5. RT7 Operator Dashboard
6. RT5 Derived Graph/QMD Plan
7. RT6 Repo Archaeology / CodeWiki Lane

Rationale:

- RT1 and RT2 remove the current real-use friction.
- RT3 and RT4 prevent shallow knowledge from looking complete.
- RT7 gives Fitz and agents operational control.
- RT5 and RT6 are valuable, but only after the core operator loop is visible and
  measurable.

## Definition of Done for Real-Test Phase

The phase is complete when a fresh agent can:

1. Install/read the protocol.
2. Compose OpenClaw projection.
3. Ingest a platform video URL.
4. Attach local video/transcript/key-frame/audio evidence.
5. Run digest queue.
6. Produce a digest that passes the deep-digest rubric.
7. Emit writeback proposals.
8. See all pending work in one doctor report.
9. Never receive canonical write authority.

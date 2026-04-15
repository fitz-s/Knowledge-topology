# OpenClaw Integration

OpenClaw is a runtime consumer of this repository, not the owner of canonical
topology truth.

## External Root

Set `KNOWLEDGE_TOPOLOGY_ROOT` to this repository path when an OpenClaw runtime
needs topology context. OpenClaw may read generated projection files under
`projections/openclaw/`, or configure QMD/extra memory paths to index those
files.

Do not copy OpenClaw config, credentials, sessions, gateway state, or private
workspace memory into this repository.

## Consumer Bundle

Install the workspace-local bundle from the topology repo:

```bash
topology bootstrap openclaw \
  --topology-root "$KNOWLEDGE_TOPOLOGY_ROOT" \
  --subject-path "<subject-repo-path>" \
  --workspace "<openclaw-workspace-path>" \
  --project-id "<runtime-project-id>"
```

The command writes only consumer-local wiring under
`<openclaw-workspace-path>/.openclaw/topology/`:

- `topology.env`
- `qmd-extra-paths.txt`
- `resolve-context.sh`
- `compose-openclaw.sh`
- `doctor-openclaw.sh`
- `capture-source.sh`
- `issue-lease.sh`
- `lease.sh`
- `run-writeback.sh`
- `video-ingest.sh`
- `video-status.sh`
- `video-attach-artifact.sh`
- `video-prepare-digest.sh`
- `video-trace.sh`
- `skills/runtime-consume.md`
- `skills/session-writeback.md`
- `skills/topology-maintainer.md`
- `skills/video-source-intake.md`

The wrappers resolve fresh `canonical_rev`, `subject_repo_id`, and
`subject_head_sha` at runtime. They do not hard-code stale revisions, copy the
topology into the OpenClaw workspace, or grant canonical write authority.

Recommended runtime flow:

1. Run `.openclaw/topology/compose-openclaw.sh`.
2. Run `.openclaw/topology/doctor-openclaw.sh`.
3. Read only the projection files listed in `qmd-extra-paths.txt`.
4. Capture runtime evidence with `.openclaw/topology/capture-source.sh`.
5. After digest evidence exists, use `.openclaw/topology/issue-lease.sh`,
   `.openclaw/topology/lease.sh`, and
   `.openclaw/topology/run-writeback.sh` with an enriched summary that includes
   `source_id`, `digest_id`, and evidence bound to the leased job.

`capture-source.sh` is a low-level capture primitive. It creates source
evidence and digest queue work; it does not make the original runtime summary
ready for `run-writeback.sh` by itself.

Use `topology doctor consumer --workspace "<openclaw-workspace-path>"` to
check generated bundle drift. Use
`topology bootstrap remove --workspace "<openclaw-workspace-path>"` to remove
unchanged generated bundle files recorded in the manifest.

## Video Operator Protocol

OpenClaw must not summarize video content from title, description, or chapter
lists. A `video_platform` locator packet is not learned video knowledge.

Video deep digest requires real modality evidence:

- transcript: platform captions, audio transcription, or human transcript
- key frames: frame extraction, vision frame analysis, or human frame notes
- audio summary: audio-derived model summary or human audio summary

Page-visible excerpts, page-visible chapter lists, and inferred page summaries
are shallow locator evidence only. They must not be labeled as transcript, key
frames, or audio summary for deep digest readiness.

No `dg_` path means no digest. No `mut_` path means no proposal.

## Runtime Projection

Generate the local-only projection with:

```bash
topology compose openclaw \
  --root "$KNOWLEDGE_TOPOLOGY_ROOT" \
  --project-id "<runtime-project-id>" \
  --canonical-rev "<topology-head-sha>" \
  --subject "<subject-repo-id>" \
  --subject-head-sha "<subject-head-sha>"
```

Outputs are generated and ignored by Git:

- `projections/openclaw/file-index.json`
- `projections/openclaw/runtime-pack.json`
- `projections/openclaw/runtime-pack.md`
- `projections/openclaw/memory-prompt.md`
- `projections/openclaw/wiki-mirror/`

These files are read-only derived artifacts. Regenerate them from canonical
records instead of editing them by hand.

## Memory Wiki Boundary

The generated `wiki-mirror/` is not an OpenClaw `memory-wiki` vault root and
does not create `.openclaw-wiki/` cache state. OpenClaw memory-wiki may ingest
or index the mirror as derived context, but it must not become canonical
authority for this repository.

Do not use `openclaw wiki apply` as a topology authority path. Topology changes
return through mutation packs and the deterministic apply gate.

## Writeback

Runtime observations begin as `runtime_observed` authority. OpenClaw writeback
must emit mutation proposals or local queue jobs with the projection
preconditions:

- `canonical_rev`
- `subject_repo_id`
- `subject_head_sha`

Allowed writeback surfaces are limited to source packets, pending mutation
packs, local writeback deltas, local queue surfaces, semantic events, gaps, and
escalations. OpenClaw must not write `canonical/`, `canonical/registry/`,
`digests/`, generated `projections/openclaw/` files, or `.openclaw-wiki/`.

## Live Bridge

The OpenClaw live bridge is topology-side code. External OpenClaw runtimes do
not write directly into `ops/queue/writeback/leased/` or adapter-private
`.tmp/openclaw-live/` issuer state. A live writeback requires a topology-issued
lease, fresh projection metadata, evidence bound to the runtime summary, and a
sanitized summary staged under `.tmp/writeback/<job_id>/summary.json`.

The bridge routes runtime observations through `writeback.py`; it does not
construct canonical records by hand and does not grant canonical write
authority.

## Agent Wiring

OpenClaw agents should use the CLI bridge rather than importing topology Python
modules directly.

Read path:

```bash
topology compose openclaw \
  --root "$KNOWLEDGE_TOPOLOGY_ROOT" \
  --project-id "$OPENCLAW_PROJECT_ID" \
  --canonical-rev "$TOPOLOGY_HEAD_SHA" \
  --subject "$SUBJECT_REPO_ID" \
  --subject-head-sha "$SUBJECT_HEAD_SHA"

topology lint runtime --root "$KNOWLEDGE_TOPOLOGY_ROOT"
topology doctor projections \
  --root "$KNOWLEDGE_TOPOLOGY_ROOT" \
  --project-id "$OPENCLAW_PROJECT_ID" \
  --canonical-rev "$TOPOLOGY_HEAD_SHA" \
  --subject "$SUBJECT_REPO_ID" \
  --subject-head-sha "$SUBJECT_HEAD_SHA"
```

OpenClaw then reads only the QMD/read-scope projection files listed below.

Runtime evidence capture:

```bash
topology openclaw capture-source \
  --root "$KNOWLEDGE_TOPOLOGY_ROOT" \
  --project-id "$OPENCLAW_PROJECT_ID" \
  --canonical-rev "$TOPOLOGY_HEAD_SHA" \
  --subject "$SUBJECT_REPO_ID" \
  --subject-head-sha "$SUBJECT_HEAD_SHA" \
  --runtime-summary-json "$SUMMARY_JSON"
```

Writeback lease path:

```bash
topology openclaw issue-lease \
  --root "$KNOWLEDGE_TOPOLOGY_ROOT" \
  --project-id "$OPENCLAW_PROJECT_ID" \
  --canonical-rev "$TOPOLOGY_HEAD_SHA" \
  --subject "$SUBJECT_REPO_ID" \
  --subject-head-sha "$SUBJECT_HEAD_SHA" \
  --runtime-summary-json "$SUMMARY_JSON"

topology openclaw lease \
  --root "$KNOWLEDGE_TOPOLOGY_ROOT" \
  --owner "$OPENCLAW_AGENT_ID"

topology openclaw run-writeback \
  --root "$KNOWLEDGE_TOPOLOGY_ROOT" \
  --project-id "$OPENCLAW_PROJECT_ID" \
  --canonical-rev "$TOPOLOGY_HEAD_SHA" \
  --subject "$SUBJECT_REPO_ID" \
  --subject-head-sha "$SUBJECT_HEAD_SHA" \
  --lease-path "$LEASE_PATH" \
  --runtime-summary-json "$SUMMARY_JSON"
```

The summary JSON must be a JSON object and must not include private OpenClaw
paths, tokens, session identifiers, credentials, cache paths, or absolute
private filesystem locations.

## QMD Scope

QMD may index only:

- `projections/openclaw/file-index.json`
- `projections/openclaw/wiki-mirror/`
- `projections/openclaw/runtime-pack.json`
- `projections/openclaw/runtime-pack.md`
- `projections/openclaw/memory-prompt.md`

QMD must not index `raw/`, `digests/`, `canonical/`, `canonical/registry/`,
`mutations/`, `ops/`, or private OpenClaw workspace/session/config paths.

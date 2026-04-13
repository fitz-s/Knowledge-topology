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

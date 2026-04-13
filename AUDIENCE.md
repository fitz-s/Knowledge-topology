# Audience Split

The topology serves multiple agent classes without giving every agent the whole
living substrate.

## Builders

Codex and Claude Code are builder agents. They should receive task-scoped
construction packs under `projections/tasks/<task-id>/` and should not browse
the full topology by default.

A builder pack contains:

- `metadata.json`
- `brief.md`
- `constraints.json`
- `relationship-tests.yaml`
- `source-bundle.json`
- `writeback-targets.json`

The load-bearing files are deterministic compiler outputs. `brief.md` may use
natural language, but constraints, relationship tests, source bundles, and
writeback targets are generated from canonical records.

Traversal bounds, sensitivity filtering, and allowed edge types are defined in
`COMPILE.md`.

## OpenClaw

OpenClaw is a rich runtime consumer. It reads this repository as
`KNOWLEDGE_TOPOLOGY_ROOT`, an external checkout or mounted path beside private
agent workspaces.

OpenClaw may write:

- tracked source packets and excerpts
- mutation packs
- durable audit events and gaps
- local-only queue and lease runtime files
- generated `projections/openclaw/` outputs

OpenClaw must not treat private workspace memory, session history, QMD indexes,
or memory-wiki mirrors as canonical authority.

## Humans

Fitz acts as curator and authority reviewer. Human attention should be spent on
source ambiguity, high-impact conflicts, beliefs, operator directives,
supersession/deletion, scope upgrades, and high-consequence weak merges.

# Knowledge topology

This repository is the canonical topology substrate. It replaces the proposed
nested `.topology/` directory: production topology state should live at this
repository root through directories such as `raw/`, `digests/`, `canonical/`,
`mutations/`, `ops/`, `projections/`, `prompts/`, and `tests/`.

The system turns Fitz-curated sources and agent session learnings into
provenance-bearing, executable knowledge for Codex, Claude Code, OpenClaw, CI,
and future worker jobs.

## Current Artifacts

- `AGENTS.md`: operating contract for agents working in this repository.
- `CLAUDE.md`: thin Claude Code routing contract.
- `docs/IMPLEMENTATION_PLAN.md`: phased implementation plan and ADR.
- `POLICY.md`: canonical write gates and trust boundaries.
- `SCHEMA.md`: frozen Batch 0 data-model contract.
- `STORAGE.md`: tracked versus local-only storage rules.
- `QUEUES.md`: spool queue semantics for multi-agent workers.

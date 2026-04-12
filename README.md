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
- `docs/IMPLEMENTATION_PLAN.md`: phased implementation plan and ADR.

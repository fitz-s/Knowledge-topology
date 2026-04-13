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
- `GIT_PROTOCOL.md`: commit, push, conflict, and apply-writer rules.
- `SECURITY.md`: untrusted-content threat model and deny rules.
- `RAW_POLICY.md`: source content modes and redistribution defaults.
- `ESCALATIONS.md`: structured human-gate card contract.
- `SCHEMA_EVOLUTION.md`: versioning and migration policy.
- `COMPILE.md`: deterministic projection and traversal policy.
- `PACKAGE_GATES.md`: package review, critic, Gemini, and unfreeze gate policy.
- `docs/MAINLINE_STATUS.md`: P0-P9 mainline completion status and deferred
  work inventory.

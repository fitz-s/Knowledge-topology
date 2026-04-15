# P12.4 Package Plan: Maintainer Supervisor

## Package Ralplan

P12.4 adds a protocol-driven maintainer supervisor that orchestrates existing
workers and queue surfaces. It must not become an omniscient daemon and must not
gain a shortcut around mutation apply gates.

The supervisor is an operational runner for daily maintenance:

- recover expired queue leases
- run digest queue work through an adapter
- reconcile ready digest artifacts into mutation proposals
- optionally auto-apply only low-risk mutation packs
- compile available OpenClaw projections after safe changes
- run repo/runtime lint and doctor checks
- emit escalation cards for human gate items and failed checks

## Reality Check

- P11.2 already has `run_digest_queue()` with JSON-file and command provider
  adapters.
- P11.5 already has `lint repo`, `lint runtime`, and doctor checks.
- P11.4/P12.3 already provide OpenClaw projection and live bridge surfaces.
- Apply can safely reject human-gated or stale packs, but the supervisor must
  conservatively classify what it attempts to auto-apply.

## Construction Table

| Small Package | Purpose | Files / Surfaces | Tests | Acceptance | Stop Condition |
| --- | --- | --- | --- | --- | --- |
| P12.4a Supervisor worker | Add deterministic orchestration over existing workers | `workers/supervisor.py` | focused supervisor tests | runner recovers leases, runs digest queue, reconciles ready digests, emits report | duplicates digest/reconcile/apply business logic |
| P12.4b Safe apply policy | Gate auto-apply to narrow low-risk packs | `workers/supervisor.py` | low/high risk tests | only open-gap packs can auto-apply; claims/nodes/edges remain pending/escalated | auto-apply can write builder-active truth |
| P12.4c CLI surface | Add operator command | `cli.py` | CLI smoke/status tests | `topology supervisor run --root ... --digest-provider-command ... --subject ...` works | CLI requires hand-built JSON beyond provider adapter |
| P12.4d Docs/status/review | Record package status | `MAINLINE_STATUS.md`, `IMPLEMENTATION_PLAN.md`, review | P10 status test | shipped CLI reality includes supervisor | status overclaims before gate |

## Gemini Requirement

Required before unfreeze: yes.

Reason: P12.4 introduces an autonomous maintenance runner touching queues,
digest/reconcile/apply orchestration, and projection compilation. If Gemini is
unavailable, explicit user waiver is required before unfreeze.

## Acceptance Tests

- Supervisor recovers expired leased jobs and does not leave stuck leases.
- Supervisor can run a digest provider command from pending source packet to
  digest artifact and mutation proposal without manual model-output JSON.
- Supervisor does not auto-apply claims, nodes, edges, contradictions,
  supersedes, deletes, decisions, invariants, interfaces, Fitz beliefs,
  operator directives, or cross-scope upgrades.
- With an explicit auto-apply flag, supervisor may apply only low-risk open-gap
  packs and must still use `apply_mutation()`.
- Supervisor emits a structured report/escalation card listing failed checks,
  pending human gates, skipped high-risk packs, and generated artifacts.
- `lint repo`, `lint runtime`, `doctor queues`, `doctor public-safe`,
  `doctor projections`, and `doctor canonical-parity` are invoked and reported.

## Stop Conditions

- Supervisor bypasses `apply_mutation()` or mutates canonical registries by hand.
- Supervisor auto-applies builder-active truth.
- Supervisor hides failed queue, lint, doctor, or reconcile work.
- Supervisor embeds provider-specific business rules instead of using adapter
  boundaries.

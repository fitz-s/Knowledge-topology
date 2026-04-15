# P12.3 Package Plan: OpenClaw Consumer Bundle

## Package Ralplan

P12.3 turns OpenClaw integration from documented CLI steps into an installable
workspace-local consumer bundle. OpenClaw remains a runtime consumer of the
external topology root; it reads only projections and sends writeback through
topology-owned leases.

P12.3 builds on `topology bootstrap openclaw` from P12.1. It does not add
canonical write authority and does not let QMD or memory-wiki own topology truth.

## Reality Check

- `topology bootstrap openclaw` already writes basic env, QMD paths, a compose
  script, and three skill snippets.
- The current OpenClaw bundle does not expose wrapper scripts for
  `capture-source`, `issue-lease`, `lease`, or `run-writeback`.
- `docs/OPENCLAW.md` still reads like a manual CLI page rather than an
  installable bundle contract.
- QMD scope must remain limited to `projections/openclaw/*`.

## Construction Table

| Small Package | Purpose | Files / Surfaces | Tests | Acceptance | Stop Condition |
| --- | --- | --- | --- | --- | --- |
| P12.3a OpenClaw wrappers | Generate runnable workspace scripts for consume/writeback loop | `workers/bootstrap.py` | temp workspace tests | scripts for compose, doctor, capture-source, issue-lease, lease, run-writeback exist and resolve context | OpenClaw must remember raw topology CLI rituals |
| P12.3b Skill bundle hardening | Make runtime-consume/session-writeback/topology-maintainer snippets operational | `workers/bootstrap.py`, docs | content tests | snippets state read-only surfaces, forbidden writes, and wrapper usage | Skills imply OpenClaw owns canonical truth |
| P12.3c QMD/env contract | Tighten env and QMD path outputs | `workers/bootstrap.py`, `docs/OPENCLAW.md` | qmd/env tests | qmd paths only include `projections/openclaw/*`; env is shell-safe | QMD indexes raw/canonical/mutations/ops |
| P12.3d Docs/status/review | Record shipped bundle | `docs/OPENCLAW.md`, `MAINLINE_STATUS.md`, review | status tests | status and docs list OpenClaw bundle commands | Status overclaims bundle before review |

## Gemini Requirement

Required before unfreeze: yes.

Reason: P12.3 changes OpenClaw consumer installation, QMD scope, and live
writeback wrapper surfaces. If Gemini remains unavailable, explicit user waiver
is required before unfreeze.

## Acceptance Tests

- `bootstrap openclaw` writes executable scripts:
  `compose-openclaw.sh`, `doctor-openclaw.sh`, `capture-source.sh`,
  `issue-lease.sh`, `lease.sh`, `run-writeback.sh`.
- Generated scripts use shell-safe embedded paths and runtime context
  resolution.
- Generated skills mention projection read surfaces, forbidden writes, and
  lease/writeback wrappers.
- QMD paths contain only:
  `file-index.json`, `runtime-pack.json`, `runtime-pack.md`,
  `memory-prompt.md`, and `wiki-mirror/`.
- Generated `compose-openclaw.sh` and `doctor-openclaw.sh` run successfully in
  a temp workspace after subject/topology state is clean.
- Generated runtime evidence wrapper can create a source packet without writing
  canonical state.

## Stop Conditions

- OpenClaw bundle can write `canonical/`, `digests/`, or generated projections
  directly.
- QMD snippet includes `raw/`, `canonical/`, `mutations/`, or `ops/`.
- OpenClaw private workspace/session/config paths are copied into topology.
- Generated scripts hard-code stale revisions instead of resolving context.

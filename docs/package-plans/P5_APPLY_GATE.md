# P5 Package Plan: Apply Gate

## Package Ralplan

P5 implements deterministic apply for validated mutation packs. Apply is the
only writer for canonical pages and registries.

## Reality Check

- Apply must revalidate mutation packs from `mutations/pending`.
- Apply must reject stale preconditions, missing evidence refs, and unapproved
  human-gated packs.
- Apply writes pages and registries in a single deterministic path.
- Apply moves mutation packs to `mutations/applied` only after successful writes.
- Apply writes semantic audit events, not queue churn.
- P5 changes canonical write mechanics, so Gemini is required before P6
  unfreeze.

## Construction Table

| Small Package | Purpose | Files / Surfaces | Fixtures / Tests | Acceptance Criteria | Stop Condition |
| --- | --- | --- | --- | --- | --- |
| P5.1 Apply schema revalidation | Revalidate mutation pack and preconditions | `workers/apply.py` | stale/malformed mutation fixtures | stale and bad packs reject before writes | apply trusts P4 output blindly |
| P5.2 Evidence resolution | Check `evidence_refs` exist | apply worker | missing evidence tests | missing source/digest refs reject | evidence location ambiguous |
| P5.3 Canonical writes | Write node/claim/edge pages and tracked gap pages/registries | apply worker | page/registry fixtures | page and registry overlap match | parity cannot be checked |
| P5.4 Human gates | Require approval for human-gated packs | apply worker | gate tests | unapproved gates reject | destructive edge bypasses gate |
| P5.5 Audit and mutation movement | Move pending to applied and write semantic event | apply worker | event/move tests | only after successful apply | partial move on failure |
| P5.6 CLI apply | Add `topology apply` | `cli.py` | CLI smoke | applies fixture mutation | CLI accepts dirty/stale inputs silently |

## Team Decision

Do not use `$team` for P5 implementation. Canonical write mechanics need a
single-owner path.

## Gemini Requirement

Required before unfreeze because P5 defines canonical write mechanics.

## Acceptance Criteria

- `topology apply` applies a pending mutation pack only when preconditions and
  evidence refs pass.
- unapproved human-gated mutation packs are rejected.
- applied claim/edge/node records are written to canonical registries.
- applied gap records are written to tracked `ops/gaps/` surfaces.
- canonical pages and registry records are written together.
- mutation pack moves from pending to applied after success.
- semantic audit event is written under `ops/events/<yyyy>/<mm>/<dd>/`.
- failed apply leaves no canonical writes and does not move the mutation pack.
- P0-P4 tests still pass.

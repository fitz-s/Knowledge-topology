# Package Gates

Each big package is frozen until it passes package-level planning, execution,
review, and unfreeze gates. This is the default work mode for this repository.

## Gate 1: Package Ralplan and Reality Check

Before implementation starts, each big package must have a package-level
`$ralplan` and reality check.

Required outputs:

- package goal and scope
- construction table
- affected files/surfaces
- fixtures and tests to add or update
- acceptance criteria
- blockers and stop conditions
- explicit decision on whether `$team` is appropriate for implementation

Reality check dimensions:

- filesystem and Git behavior
- public repository safety
- untrusted-content handling
- concurrency and queue semantics
- testability
- adapter/facade boundaries
- canonical authority and write gates

## Gate 2: Implementation Verification

Package implementation must provide fresh evidence before review:

- package-specific tests pass
- affected contract tests pass
- static/syntax checks pass where available
- generated/local-only surfaces are not staged
- no scope outside the package construction table

## Gate 3: Reviewer and Critic Dialectic

Completion requires two adversarial roles:

- Reviewer: checks implementation against package plan, contracts, tests, and
  acceptance criteria.
- Critic: attacks failure modes, edge cases, stale-state paths, authority leaks,
  deterministic assumptions, public-safety gaps, and missing tests.

Both must approve before the next package is unfrozen. A Critic veto blocks
unfreeze until fixed or escalated.

## Gemini External Validation

Use `$ask-gemini` as a third-party external validator when any trigger applies:

- architecture boundary changes
- `SCHEMA.md`, `POLICY.md`, `STORAGE.md`, `QUEUES.md`, `SECURITY.md`, or
  `COMPILE.md` core mechanics change
- security or trust-boundary changes
- public/private leakage risk
- OpenClaw external-root behavior changes
- adapter/facade boundary changes
- reviewer and critic disagree
- user explicitly requests third-party validation

Gemini output must be saved as an artifact under `.omx/artifacts/` and
summarized in the package review record. If Gemini is required but unavailable,
unfreeze is blocked unless the user explicitly waives the external validation
for that package.

## Unfreeze Record

Each package unfreeze record must include:

- package ID
- package plan path
- implementation commit(s)
- verification commands and results
- reviewer verdict
- critic verdict
- Gemini artifact path or reason not required
- unresolved risks
- final decision: `approved`, `blocked`, or `waived_by_user`

## Blocking Conditions

Do not unfreeze the next package when:

- implementation diverges from the package plan
- reviewer or critic rejects
- critic identifies an uncovered high-risk failure mode
- required Gemini validation is missing
- tests or contract fixtures fail
- apply/compile/lint/doctor paths become non-deterministic
- generated/local-only surfaces are staged
- public-safe or sensitivity filters fail
- stale proposal or dirty revision handling is ambiguous

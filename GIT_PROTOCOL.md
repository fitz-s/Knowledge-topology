# Git Protocol

This protocol prevents multi-agent work from corrupting canonical state or
burying decisions in ad hoc commits.

## Roles

- Builder agents may edit implementation files and emit mutation packs.
- Reconcile workers may emit mutation packs.
- Apply workers are the only writers for `canonical/` and
  `canonical/registry/`.
- Human operators review authority-changing escalation cards.

## Branching

Use short-lived branches for implementation work once worker code exists.

Recommended branch names:

- `p0/<topic>` for contract changes
- `p1/<topic>` for engine skeleton changes
- `apply/<mutation-id>` for canonical apply commits
- `adapter/<target>` for Codex, Claude, or OpenClaw facades

Do not combine canonical apply changes with unrelated implementation changes.

## Pull / Rebase / Push

Before committing:

1. run the package-specific verification
2. inspect `git status --short`
3. avoid staging ignored runtime state

Before pushing:

1. fetch `origin`
2. confirm local branch is not stale
3. rebase or merge only when the conflict is understood
4. rerun affected verification

If push is rejected, fetch and inspect before retrying. Do not force-push
shared branches unless a human explicitly requests it.

## Canonical Apply Commits

Apply commits must be narrow:

- one mutation pack or closely related mutation batch
- matching canonical pages and registries
- audit event
- verification evidence

Apply rejects stale mutation preconditions instead of editing around them.

## Conflict Recovery

If two agents propose conflicting canonical changes:

1. mark both mutation packs as contested
2. preserve both evidence bundles
3. emit an escalation card when authority changes are involved
4. re-reconcile after the current canonical revision is clear

## Lore Commit Requirement

Every commit follows the repository Lore protocol from `AGENTS.md`: an intent
line first and useful trailers such as `Constraint`, `Rejected`, `Confidence`,
`Scope-risk`, `Directive`, `Tested`, and `Not-tested`.

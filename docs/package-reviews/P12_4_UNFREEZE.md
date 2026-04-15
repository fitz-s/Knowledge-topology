# P12.4 Unfreeze Review

## Package

P12.4 Maintainer Supervisor

## Package Plan

- `docs/package-plans/P12_4_MAINTAINER_SUPERVISOR.md`

## Implementation Commits

- `80b9980` - Freeze P12.4 maintainer supervisor plan
- This unfreeze commit - implement and approve P12.4 maintainer supervisor

Final implementation evidence note: the commit that updates this record is the
terminal P12.4 implementation commit. Treat the pushed HEAD and final response
as the authoritative terminal commit reference for this package.

## Verification Evidence

Commands run:

```bash
PYTHONPATH=src python -m pytest tests/test_p12_4_maintainer_supervisor.py -q
PYTHONPATH=src python -m pytest tests/test_p10_mainline_closure.py -q
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m compileall -q src tests
git diff --check
```

Results:

- P12.4 focused suite after blocker fixes: `9 passed`.
- Mainline/status suite after blocker fixes: `5 passed`.
- Focused P11.2/P12.4/P10 suite after blocker fixes:
  `27 passed, 3 subtests passed`.
- Full suite after blocker fixes: `224 passed, 44 subtests passed`.
- `compileall`: clean.
- `git diff --check`: clean.

## Reviewer Verdict

Approved after blocker fixes.

Reviewer blockers addressed:

- Supervisor reports and escalation cards are written under ignored local-only
  `ops/reports/tmp/supervisor/` paths and serialize repo-relative/sanitized
  paths.
- Lease recovery has focused coverage for requeue, max-attempt failure,
  malformed leased jobs, and symlinked corrupt digest leases.
- Reconcile requires digest-level completed-job binding, not only source-level
  binding.

## Critic Verdict

Approved after blocker fixes.

Critic blockers addressed:

- `reconcile_ready_digests()` requires completed digest job metadata matching
  `source_id`, `digest_id`, `digest_json_path`, `subject_repo_id`,
  `subject_head_sha`, and `canonical_rev` before issuing a mutation proposal.
- If digest lease recovery finds malformed or symlinked digest leased jobs,
  supervisor skips the digest provider path for that run and emits
  `lease_recovery_errors` instead of crashing inside `run_digest_queue()`.
- Projection errors are sanitized before entering report/escalation payloads.
- Auto-apply remains opt-in and limited to pure `open_gap` packs through
  `apply_mutation()`.

## Gemini Status

Required: yes.

Reason: P12.4 introduces an autonomous maintenance runner touching queues,
digest/reconcile/apply orchestration, projection compilation, lint, and doctor
checks.

Artifacts: not produced for this package.

Gemini final verdict: unavailable / waived. Earlier package validations in
this repository repeatedly encountered Gemini CLI timeout or capacity failures.

Waiver: user explicitly waived Gemini on 2026-04-14 / 2026-04-15 and requested
continuing to the next package if Gemini remains unavailable.

## Residual Risks

- The supervisor is a one-shot CLI runner, not a hosted daemon or scheduler.
- OpenClaw projection compilation still obeys existing clean-repo projection
  preconditions and may report an escalation instead of forcing `allow_dirty`.
- Auto-apply is limited to explicit `--auto-apply-low-risk` and pure open-gap
  packs.

## Final Decision

`waived_by_user`

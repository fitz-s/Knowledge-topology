# P11.5 Unfreeze Review

## Package

P11.5 Lint / Doctor Split

## Package Plan

- `docs/package-plans/P11_5_LINT_DOCTOR_SPLIT.md`

## Implementation Commits

- `5db7fa8` - Freeze lint doctor split plan
- This unfreeze commit - implement and approve P11.5 lint/doctor split

Final implementation evidence note: the commit that updates this record is the
terminal P11.5 implementation commit. Treat the pushed HEAD and final response
as the authoritative terminal commit reference for this package.

## Verification Evidence

Commands run:

```bash
PYTHONPATH=src python -m pytest tests/test_p11_5_lint_doctor_split.py tests/test_p7_writeback_lint_doctor.py tests/test_p10_mainline_closure.py -q
git diff --check
PYTHONPATH=src python -m compileall -q src tests
PYTHONPATH=src python -m pytest -q
```

Results:

- Focused P11.5/P7/P10 suite: `28 passed, 8 subtests passed`.
- Full suite: `177 passed, 44 subtests passed`.
- `git diff --check`: clean.
- `compileall`: clean.

## Reviewer Verdict

Approved after blocker fixes.

Reviewer blockers addressed:

- Runtime lint and doctor no-follow parent symlink paths instead of crashing.
- Runtime lint rejects symlinked `brief.md` and OpenClaw wiki pages.
- Public-safe catches local blob payloads with neutral filenames.
- Canonical parity reports missing pages for registry rows.

## Critic Verdict

Approved after blocker fixes.

Critic blockers addressed:

- Repo lint remains strict and is still the default `topology lint` mode.
- Runtime lint no longer follows symlinked projection parents and does not own
  queue diagnostics.
- Queue doctor reports unknown kind/state and symlinked queue surfaces without
  mutating state.
- Public-safe reports external `public_text` over the 8,000-character cap and
  binary-looking tracked packet payloads.
- Canonical parity uses explicit op-to-registry mapping and reports missing
  pages as well as mismatches.

## Gemini Status

Required: no.

Reason: P11.5 adds deterministic lint/doctor command routing and diagnostics. It
does not introduce new trust-boundary behavior beyond enforcing existing policy.

Artifact: not required.

## Residual Risks

- `doctor canonical-parity` compares only overlapping fields and does not repair
  mismatches.
- Queue doctor remains read-only; explicit repair/requeue commands are still
  deferred.
- Runtime lint validates generated builder/OpenClaw surfaces structurally, while
  deeper freshness checks remain in doctor projections.
- P11.6 subject/file-index is still pending.

## Final Decision

`approved`

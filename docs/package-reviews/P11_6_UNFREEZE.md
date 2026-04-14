# P11.6 Unfreeze Review

## Package

P11.6 Subject / File-Index

## Package Plan

- `docs/package-plans/P11_6_SUBJECT_FILE_INDEX.md`

## Implementation Commits

- `30da744` - Freeze subject file-index closure plan
- This unfreeze commit - implement and approve P11.6 subject/file-index closure

Final implementation evidence note: the commit that updates this record is the
terminal P11.6 implementation commit. Treat the pushed HEAD and final response
as the authoritative terminal commit reference for this package.

## Verification Evidence

Commands run:

```bash
PYTHONPATH=src python -m pytest tests/test_p11_6_subject_file_index.py tests/test_p9_openclaw_projection.py tests/test_p11_4_openclaw_live.py tests/test_p11_5_lint_doctor_split.py tests/test_p10_mainline_closure.py -q
git diff --check
PYTHONPATH=src python -m compileall -q src tests
PYTHONPATH=src python -m pytest -q
```

Results:

- Focused P11.6/P9/P11.4/P11.5/P10 suite: `53 passed, 8 subtests passed`.
- Full suite: `188 passed, 44 subtests passed`.
- `git diff --check`: clean.
- `compileall`: clean.

## Reviewer Verdict

Waived by user after blocker fixes.

Reviewer blockers addressed before waiver:

- Expanded acceptance coverage for multiple subjects, refresh failures,
  subject-path mismatch/symlink checks, dirty subject repo rejection, stale
  projection checks, malformed/symlinked file-index checks, deterministic
  truncation, and metadata parity.
- OpenClaw file-index path filtering no longer drops legitimate safe paths such
  as `storage/registry.py` and `workers/apply.py`.

## Critic Verdict

Waived by user after blocker fixes.

Critic blockers addressed before waiver:

- `compose openclaw` still rejects dirty subject repos when `allow_dirty=false`.
- Runtime lint and projection doctor re-run subject authority checks through
  `SUBJECTS.yaml`, including no-follow location validation and null-head
  rejection.
- Runtime projection metadata binds the subject location through
  `subject_location_hash`, so same-head subject-location rebinding is reported
  as stale.
- Command-like file-index paths are excluded from the OpenClaw file index while
  safe registry/apply implementation paths remain valid.

## Gemini Status

Required: yes.

Reason: P11.6 changes OpenClaw projection behavior and adds a new local-only
file-index surface with public/private leakage risk.

Artifacts:

- `.omx/artifacts/gemini-p11-6-subject-file-index-20260414T045115Z.md`
- `.omx/artifacts/gemini-p11-6-subject-file-index-rerun-20260414T152657Z.md`

Gemini final verdict: unavailable. Both validation attempts failed with Gemini
capacity errors (`429 MODEL_CAPACITY_EXHAUSTED`) or CLI invocation failure.

Waiver: user explicitly waived Gemini on 2026-04-14 and requested proceeding to
OpenClaw wiring.

## Residual Risks

- `SUBJECTS.yaml` uses a constrained stdlib parser/serializer rather than a
  general YAML implementation.
- `subject_location_hash` intentionally binds location authority without
  exposing the path in runtime projection consumers.
- OpenClaw file-index paths are path-safe and metadata-only but still derived
  from canonical file refs; stale or unsafe rows are excluded rather than
  repaired.

## Final Decision

`waived_by_user`

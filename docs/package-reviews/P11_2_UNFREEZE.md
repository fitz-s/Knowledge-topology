# P11.2 Unfreeze Review

## Package

P11.2 Digest Runner Closure

## Package Plan

- `docs/package-plans/P11_2_DIGEST_RUNNER_CLOSURE.md`

## Implementation Commits

- `39d06ce` - Freeze digest runner closure plan
- This unfreeze commit - implement and approve P11.2 digest runner closure

Final implementation evidence note: the commit that updates this record is the
terminal P11.2 implementation commit. Treat the pushed HEAD and final response
as the authoritative terminal commit reference for this package.

## Verification Evidence

Commands run:

```bash
PYTHONPATH=src python -m pytest tests/test_p11_2_digest_runner.py -q
PYTHONPATH=src python -m pytest tests/test_p2_source_packet_fetch.py tests/test_p3_digest_contract.py tests/test_p11_2_digest_runner.py -q
git diff --check
PYTHONPATH=src python -m compileall -q src tests
PYTHONPATH=src python -m pytest -q
```

Results:

- P11.2 focused suite after final idempotency fix:
  `13 passed, 3 subtests passed`.
- Affected P2/P3/P11.2 suite after final idempotency fix:
  `29 passed, 8 subtests passed`.
- Full suite after final idempotency fix:
  `153 passed, 15 subtests passed`.
- `git diff --check`: clean.
- `compileall`: clean.

## Reviewer Verdict

Approved after blocker fixes.

Reviewer blockers addressed:

- Fixture provider rejects symlinked parent paths for `model-output-dir`.
- Source packet prompt construction performs lexical parent preflight under
  `raw/packets/<source_id>/`.
- Legacy `topology digest --source-id --model-output` remains separate from
  queue mode.
- Queue mode requires current subject/canonical preconditions and exactly one
  provider source.
- Duplicate digest guard runs before provider invocation in sequential retry
  paths.

## Critic Verdict

Approved after blocker fixes.

Critic blockers addressed:

- Command provider uses argv-only execution with `shell=False`; source text is
  sent through stdin JSON only.
- Provider request metadata is allowlisted and redacts local draft paths and
  local-blob storage hints.
- Expired leases are recovered before new pending leases.
- Stale canonical revision, wrong subject repo, and stale subject head fail
  before provider invocation.
- Source prompt text rejects symlinked packet parents and final text symlinks.
- Fixture provider rejects final and parent symlinks.
- Existing digest artifacts fail jobs before provider invocation in sequential
  paths.
- Concurrent duplicate jobs cannot write multiple digests for one source:
  `write_digest_artifacts()` now uses an atomic per-source lock and final
  one-digest-per-source check.

## Gemini Status

Required: yes.

Reason: P11.2 changes provider adapter boundaries, prompt/model execution,
queue runner behavior, CLI command shape, and public-safe prompt leakage
filters.

Artifacts:

- Final approved artifact:
  `.omx/artifacts/gemini-p11-2-final-short-no-tools-20260414T010501Z.md`
- Earlier blocked duplicate-idempotency artifact:
  `.omx/artifacts/gemini-p11-2-digest-runner-closure-20260414T004532Z.md`
- Earlier no-verdict unpinned artifact:
  `.omx/artifacts/gemini-p11-2-final-short-unpinned-20260414T010340Z.md`
- Earlier environment failure artifact:
  `.omx/artifacts/gemini-p11-2-final-short-unpinned-20260414T010243Z.md`

Gemini final verdict: `APPROVE`.

## Residual Risks

- P11.2 supports command-provider and JSON-directory provider paths, not a
  first-party hosted SDK integration.
- Queue runner mode is intentionally one digest per source. Explicit redigest
  or rebuild policy is deferred.
- A crash while holding `.digest-write.lock` can leave a manual cleanup item;
  stale lock recovery is deferred because the lock protects artifact creation,
  not queue lease state.
- P11.3 fetch V2, P11.4 OpenClaw live bridge, P11.5 lint/doctor split, and
  P11.6 subject/file-index remain unimplemented.

## Final Decision

`approved`

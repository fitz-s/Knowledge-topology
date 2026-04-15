# P13.0 Unfreeze Review

## Package

P13.0 Video Evidence Discipline / OpenClaw Video Operator Protocol

## Package Plan

- `docs/package-plans/P13_0_VIDEO_EVIDENCE_DISCIPLINE.md`

## Implementation Commits

- `0e473e7` - Freeze P13.0 video evidence discipline plan
- This unfreeze commit - implement and approve P13.0 video evidence discipline

Final implementation evidence note: the commit that updates this record is the
terminal P13.0 implementation commit. Treat the pushed HEAD and final response
as the authoritative terminal commit reference for this package.

## Verification Evidence

Commands run:

```bash
PYTHONPATH=src python -m pytest tests/test_p12_2_video_media_closure.py -q
PYTHONPATH=src python -m pytest tests/test_p11_3_fetch_v2.py -q
PYTHONPATH=src python -m pytest tests/test_p12_3_openclaw_consumer_bundle.py -q
PYTHONPATH=src python -m pytest tests/test_p10_mainline_closure.py -q
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m compileall -q src tests
git diff --check
```

Results:

- P13 focused video suite after blocker fixes: `8 passed`.
- Fetch/video/OpenClaw bundle regression suite after blocker fixes:
  `35 passed, 21 subtests passed`.
- Mainline/status suite after blocker fixes: `5 passed`.
- Full suite after blocker fixes: `231 passed, 44 subtests passed`.
- `compileall`: clean.
- `git diff --check`: clean.

## Reviewer Verdict

Approved after blocker fixes.

Reviewer blockers addressed:

- Generated OpenClaw `video-ingest.sh` injects resolved `subject_repo_id`,
  `subject_head_sha`, and `canonical_rev` instead of requiring hidden CLI
  preconditions.
- P13 surfaces are marked shipped only after review approval.
- OpenClaw default attach wrapper cannot pass `--evidence-attestation` or
  `--attestation-manifest`.

## Critic Verdict

Approved after blocker fixes.

Critic blockers addressed:

- Ordinary CLI/agent attach paths cannot create `operator_attested` or
  `provider_generated` deep-ready evidence, even with a matching manifest.
- Deep-ready evidence requires the internal trusted provider/operator path
  (`trusted_attestation=True`), which is not exposed through CLI or generated
  OpenClaw wrappers.
- `video status` and `video trace` return repo-relative paths.
- `prepare-digest --allow-locator-only` reports `digest_ready=false`,
  `deep_digest_ready=false`, and `locator_digest_allowed=true`.

## Gemini Status

Required: no.

Reason: P13.0 is deterministic video evidence gating and generated agent
protocol text. It does not add network video download, provider execution, or
new canonical authority.

Artifact: not required.

## Residual Risks

- This package does not implement YouTube/Douyin download, transcription, or
  frame extraction providers.
- Legacy video artifacts without provenance become shallow-only and must be
  reattached with real evidence origin before deep digest.

## Final Decision

`approved`

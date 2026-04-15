# P11.7 Unfreeze Review

## Package

P11.7 Video Platform Ingest

## Package Plan

- `docs/package-plans/P11_7_VIDEO_PLATFORM_INGEST.md`

## Implementation Commits

- `584bea2` - Turn platform video links into intake locators
- `ed4f658` - Record video platform intake writeback proposal
- `2fda190` - Attach downloaded video artifacts safely
- `502a343` - Record video artifact attachment writeback proposal
- `01b3334` - Feed video evidence into deep digest requests
- `a01e905` - Keep video digest prompts domain-neutral
- `db91be1` - Record domain-neutral video digest invariant

## Verification Evidence

Commands run:

```bash
PYTHONPATH=src python -m pytest tests/test_p11_3_fetch_v2.py tests/test_p2_source_packet_fetch.py -q
PYTHONPATH=src python -m pytest tests/test_p11_3_fetch_v2.py tests/test_p11_2_digest_runner.py tests/test_p2_source_packet_fetch.py tests/test_p3_digest_contract.py -q
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m compileall -q src tests
git diff --check
```

Results:

- Focused video/fetch suite after locator + attach-artifact: `23 passed, 26 subtests passed`.
- Focused digest/fetch suite after video evidence request fix: `44 passed, 29 subtests passed`.
- Full suite after final domain-neutral prompt fix: `196 passed, 44 subtests passed`.
- `compileall`: clean.
- `git diff --check`: clean.

Manual smoke:

```bash
topology ingest 'https://v.douyin.com/6l8q1jGwRl4/ Slp:/ 06/05 K@W.MJ' ...
```

Result:

- created `video_platform` packet
- `content_status: partial`
- `fetch_chain[0].method: video_platform_locator`
- digest job enqueued
- no network fetcher required

## Reviewer Verdict

Approved by implementation evidence and tests.

Reviewer-relevant fixes:

- Douyin short links no longer fail as ordinary `article_html` fetches.
- Platform locator packets explicitly say they are capture plans, not complete
  video evidence.
- Downloaded videos attach through local-only blob refs and do not expose source
  local paths.
- Digest requests include attached transcript/key-frame/audio/landing metadata
  text.
- Generic prompts were corrected to avoid one-video domain hard-coding.

## Critic Verdict

Approved by implementation evidence and tests.

Critic-relevant fixes:

- Public-safe fetch remains locator-only for platform video sources.
- Local media bytes stay under `raw/local_blobs/`.
- Attachment rejects symlinked artifacts and non-video packets.
- Prompt tests verify domain-neutral extraction constraints.
- Video workflow decisions were emitted as writeback proposals rather than
  canonical writes.

## Gemini Status

Required: no.

Reason: P11.7 adds deterministic local workflow surfaces while preserving
existing public-safe media boundaries and canonical write gates.

Artifact: not required.

## Residual Risks

- P11.7 does not implement direct provider download or transcription.
- Platform limitations, login gates, and copyright boundaries remain external
  to public-safe fetch.
- Deep digest quality still needs the P12 evaluation/benchmark package.

## Final Decision

`approved`

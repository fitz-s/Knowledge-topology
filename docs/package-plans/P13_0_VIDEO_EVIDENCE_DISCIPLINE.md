# P13.0 Package Plan: Video Evidence Discipline / OpenClaw Video Operator Protocol

## Package Ralplan

P13.0 closes the second real-test failure: an agent produced `src_`, `dg_`,
and `mut_` artifacts for a Douyin video, but the attached "transcript",
"key_frames", and "audio_summary" were only page-visible title, description,
and chapter-list evidence. The system accepted the labels and reported
`ready_for_deep_digest: true`.

The package makes video deep readiness semantic, not label-based, and teaches
OpenClaw agents to fail closed instead of summarizing a video from its page
metadata.

## Decision

Implement both sides:

- topology-side video artifact provenance and deep-readiness gates
- consumer/OpenClaw-side video operator protocol and artifact-path proof rules

## Drivers

- `artifact_kind=transcript` must not be enough to satisfy transcript evidence.
- Page-visible metadata is useful locator evidence, but not video understanding.
- OpenClaw agents need a hard runbook: no `dg_`/`mut_` path means no learned
  video knowledge.
- Public-safe fetch boundaries remain intact; this package is not a downloader
  or platform bypass.

## Alternatives Considered

- Only update prompts/skills: rejected because fake artifact labels would still
  pass the topology gate.
- Only update topology readiness: rejected because OpenClaw would still not know
  the correct video operator behavior.
- Add direct video downloader/provider now: rejected because provider automation
  is a separate package and must not weaken public-safe boundaries.

## Construction Table

| Small Package | Purpose | Files / Surfaces | Tests | Acceptance | Stop Condition |
| --- | --- | --- | --- | --- | --- |
| P13.0a Provenance schema | Add evidence origin, coverage, and modality to video artifacts | `fetch.py`, `video.py` | provenance tests | text artifacts record and validate semantic origin | `artifact_kind` alone satisfies deep readiness |
| P13.0b Deep readiness gate | Reject page-visible/inferred evidence for deep digest | `video.py`, `digest.py` | low-quality real-test fixture | page-visible transcript/keyframes/audio summary are shallow-only | `ready_for_deep_digest` is true for page metadata |
| P13.0c Trace surface | Let agents inspect actual stage and artifact paths | `video.py`, `cli.py` | trace tests | stages locator_only, shallow_evidence, deep_ready, digested, reconciled | agent must infer state from prose |
| P13.0d OpenClaw protocol | Generate video source intake skill/wrappers | `bootstrap.py`, `OPENCLAW.md` | bundle content tests | skill forbids summary-only learning and false artifacts | OpenClaw can claim learned video with only locator |
| P13.0e Consumer skills | Harden generic consumer instructions | `.agents/skills`, `.claude/skills` | content tests | no `src_/dg_/mut_` paths means no learning claim | chat summary can masquerade as topology ingest |
| P13.0f Governance | Status/review docs | status/review tests | P13 plan/review align with CLI reality | status overclaims before gate |

## Acceptance Tests

- The exact real-test failure pattern is rejected:
  - `transcript` with `evidence_origin=page_visible_excerpt`
  - `key_frames` with `evidence_origin=page_visible_chapter_list`
  - `audio_summary` with `evidence_origin=inferred_from_page`
- `topology video status` reports `ready_for_deep_digest: false`,
  `shallow_only_artifacts`, and rejection reasons.
- `topology video prepare-digest` refuses deep digest for shallow-only evidence.
- `build_digest_model_request()` refuses shallow-only video artifacts.
- Valid modality evidence can become deep-ready:
  - transcript: `platform_caption`, `audio_transcription`, or
    `human_transcript`
  - key frames: `frame_extraction`, `vision_frame_analysis`, or
    `human_frame_notes`
  - audio summary: `audio_model_summary` or `human_audio_summary`
- OpenClaw generated bundle contains video intake instructions and wrappers.
- `topology video trace` returns real stage and artifact paths without private
  path leakage.

## Stop Conditions

- Page-visible metadata can still satisfy video deep digest readiness.
- OpenClaw skill permits natural-language summary as evidence.
- `--allow-locator-only` can be mistaken for deep readiness.
- Trace claims `digested` without an actual `dg_` file or `reconciled` without a
  `mut_` file.

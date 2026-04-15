# P11.7 Package Plan: Video Platform Ingest

## Package Ralplan

P11.7 closes the first real-use video gap: platform video links such as Douyin,
TikTok, YouTube, Bilibili, Vimeo, and Instagram are not ordinary article pages
or stable direct media URLs. They need a public-safe locator packet first, then
local-only evidence attachment, then digest.

P11.7 does not make the public-safe fetch worker into a platform video crawler.
It creates a controlled video evidence workflow around existing source packet,
local blob, digest, and writeback contracts.

## Reality Check

- Before P11.7, a Douyin short link was classified as `article_html` and could
  fail before any packet was written when network resolution or platform
  redirects hit SSRF/private-address safety checks.
- Platform video sources often require opening the platform, authenticated
  browser flows, or operator-side download before useful content evidence
  exists.
- The repository already had public-safe storage boundaries:
  tracked packet metadata and excerpts under `raw/packets/`; full media bytes
  under local-only `raw/local_blobs/`.
- Digest requests previously read only `content.md` or `excerpt.md`; attached
  transcript/key-frame/audio artifacts were not guaranteed to reach providers.

## Construction Table

| Small Package | Purpose | Files / Surfaces | Tests | Acceptance | Stop Condition |
| --- | --- | --- | --- | --- | --- |
| P11.7a Video locator source type | Add `video_platform` packets for platform URLs | `schema/source_packet.py`, `workers/fetch.py`, `cli.py`, `SCHEMA.md`, `RAW_POLICY.md` | P2/P11.3 tests | Douyin-style short links create locator packets and digest jobs without network media fetching | Video URLs still fail as article fetches |
| P11.7b Capture-plan excerpt | Generate actionable capture checklist | `workers/fetch.py`, docs | P11.3 tests | Packet has locator metadata, platform, shortlink flag, recommended artifacts, and capture-plan excerpt | Packet implies full content was captured |
| P11.7c Artifact attachment | Bind downloaded video/transcript/key-frame/audio evidence | `workers/fetch.py`, `cli.py`, docs | P2/P11.3 tests | `topology video attach-artifact` records local blob refs or bounded text artifacts on the video packet | Downloaded media bytes enter tracked packet dirs |
| P11.7d Video evidence in digest request | Send attached text artifacts to digest providers | `workers/digest.py`, prompts | P11.2/P11.3 tests | Digest request includes transcript/key-frame/audio/landing metadata text as `video_artifacts` | Digest still sees only locator brief |
| P11.7e Domain-neutral depth prompt | Avoid single-source prompt contamination | `prompts/digest_deep.md`, `prompts/digest_standard.md` | P11.2/P11.3 tests | Prompt requires structural fidelity without hard-coded source-domain vocabulary | Prompt/test optimizes for one video |
| P11.7f Writeback proposals | Capture new durable workflow decisions | `mutations/pending/` | runtime lint | Video workflow decisions emitted as proposals, not canonical writes | Workflow knowledge bypasses mutation review |

## Gemini Requirement

Required before unfreeze: no.

Reason: P11.7 extends deterministic source packet, CLI, prompt, and local blob
workflows. It does not grant new canonical write authority or loosen public-safe
storage rules. If future video providers fetch external media automatically,
that provider package should reconsider Gemini/security validation.

## Video Source Contract

`video_platform` packet:

- `content_mode: excerpt_only`
- `content_status: partial`
- `trust_scope: external`
- `artifacts[0].kind: video_platform_locator`
- no platform media bytes under `raw/packets/`

Locator artifacts may include:

- `platform`
- `host`
- `url`
- `shortlink`
- `requires_operator_capture`
- `recommended_artifacts`

Artifact roles:

- `video_file`
- `transcript`
- `key_frames`
- `audio_summary`
- `landing_page_metadata`

Binary/video artifacts are represented as `local_blob_ref` metadata and copied
under `raw/local_blobs/<source_id>/`. Text artifacts may be tracked as bounded
markdown excerpts when the operator explicitly requests `--track-text`.

## Acceptance Tests

- Douyin short link with share text is classified as `video_platform`.
- Video locator ingest writes `packet.json`, `excerpt.md`, and a digest job
  without calling a network fetcher.
- `video_platform` rejects `public_text` and `local_blob` ingest modes.
- `topology video attach-artifact` attaches local video bytes as local-only blob
  refs without storing source filesystem paths in packet metadata.
- `topology video attach-artifact --track-text` attaches bounded transcript or
  summary markdown.
- Attachment rejects non-video source packets and symlinked artifacts.
- Digest request includes attached video text artifacts and labels the request
  as `video_artifacts`.
- Generic digest prompts require argument-structure fidelity without hard-coded
  domain vocabulary from a single source.

## Stop Conditions

- Public-safe fetch downloads platform media directly.
- Downloaded media bytes are tracked under `raw/packets/`.
- Video ingest writes canonical nodes without digest/reconcile/apply.
- Generic prompt or tests hard-code the contents of the current example video.

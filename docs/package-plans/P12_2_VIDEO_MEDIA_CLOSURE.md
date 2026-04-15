# P12.2 Package Plan: Video / Media Closure

## Package Ralplan

P12.2 promotes video handling from low-level primitives to an operator-facing
workflow. The target behavior is not "turn public-safe fetch into a video
crawler." The target behavior is: one command takes a platform URL, creates the
locator packet, runs safe/local provider steps when available, attaches
artifacts, reports missing evidence, and optionally starts digest.

## Reality Check

- `video_platform` locator intake exists.
- `topology video attach-artifact` can bind local video/text artifacts.
- Digest requests include attached text artifacts.
- There is no high-level `topology video ingest` orchestration command.
- There is no `video status` or `prepare-digest` command to explain which
  artifacts are missing before a deep digest.
- `yt-dlp` is not installed in this environment; `ffmpeg` is installed. Provider
  implementations must degrade cleanly.

## Construction Table

| Small Package | Purpose | Files / Surfaces | Tests | Acceptance | Stop Condition |
| --- | --- | --- | --- | --- | --- |
| P12.2a Video status | Report evidence completeness for video packets | new video worker/module, `cli.py` | video fixture tests | `topology video status --source-id` lists present/missing artifacts and local blob size | Status requires manual packet inspection |
| P12.2b Prepare digest gate | Fail with actionable checklist when only locator exists | video worker/module, `cli.py` | tests | `prepare-digest` succeeds only when enough text evidence exists or `--allow-locator-only` is set | Locator-only sources silently enter shallow digest |
| P12.2c Operator ingest orchestration | Add `topology video ingest` | video worker/module, `cli.py` | temp root tests | command creates locator packet, attempts selected provider, attaches available artifacts, optionally enqueues/runs digest, and prints checklist | Command hides provider failures as success |
| P12.2d Provider boundary | Stub provider adapters for youtube/yt-dlp/browser/manual | video worker/module | provider tests | unavailable providers return structured missing-artifact status, not tracebacks | Provider logic enters public-safe fetch core |
| P12.2e Docs/status | Document platform limits and fallback flow | `RAW_POLICY.md`, `MAINLINE_STATUS.md`, package review | docs tests | docs distinguish locator intake, local providers, manual upload, and digest readiness | Docs promise universal direct pull |

## Gemini Requirement

Required before unfreeze: no for the first deterministic/manual provider
orchestration.

Reason: this package keeps media download/transcription optional and local, and
does not add a direct external downloader implementation. If future work adds
real network media download providers, that provider package should require
Gemini/security review.

## CLI Contract

```bash
topology video ingest "<url>" \
  --provider youtube|yt-dlp|browser-capture|manual-upload \
  --transcriber whisper|provider|none \
  --vision-provider gemini|openai|none \
  --auto-digest \
  --subject ...

topology video status --source-id src_... --root ...
topology video prepare-digest --source-id src_... --root ... [--allow-locator-only]
```

Rules:

- `video ingest` always creates or reports a `video_platform` locator packet.
- Provider failures are structured checklist output, not hard crashes unless the
  locator packet itself cannot be created safely.
- `manual-upload` never downloads anything; it creates the locator and reports
  missing artifacts.
- `yt-dlp`, `youtube`, and `browser-capture` are provider names at this stage,
  but unavailable providers degrade to missing artifacts.
- `auto-digest` may enqueue digest only when `prepare-digest` passes.
- Full media bytes never enter tracked `raw/packets/`.

## Acceptance Tests

- `topology video status` reports missing transcript/key_frames/audio_summary
  for a locator-only packet.
- `topology video prepare-digest` fails locator-only packets with a checklist.
- `prepare-digest --allow-locator-only` succeeds but marks shallow risk.
- `topology video ingest <Douyin URL> --provider manual-upload` creates packet
  and prints missing-artifact checklist.
- `topology video ingest <YouTube URL> --provider yt-dlp` degrades cleanly when
  provider is unavailable.
- `topology video ingest ... --auto-digest` does not enqueue digest when
  required evidence is missing.
- After attaching transcript/key_frames/audio_summary, `status` reports ready
  and `prepare-digest` succeeds.

## Stop Conditions

- Public-safe fetch worker downloads platform media.
- Provider failure is indistinguishable from success.
- Locator-only sources enter digest as if they had deep evidence.
- Media bytes appear under tracked packet directories.

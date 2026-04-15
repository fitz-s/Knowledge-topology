# P13.1 Package Plan: Trusted Video Provider / Attestation Bridge

## Package Ralplan

P13.1 gives OpenClaw a legitimate next step after `shallow_evidence`: request a
topology-owned trusted video provider bridge. The bridge promotes staged,
signed provider/operator output into deep-ready video evidence. OpenClaw and
ordinary CLI users still cannot self-attest transcript, key-frame, or
audio-summary artifacts.

## Decision

Implement a staged trusted bundle bridge:

- external trusted provider/operator process writes a signed bundle under
  `.tmp/video-provider/trusted/<source_id>/`
- `topology video provider-run` verifies the bundle signature and artifact
  hashes
- provider-run internally calls `attach_video_artifact(... trusted_attestation=True)`
- OpenClaw calls `.openclaw/topology/video-provider-run.sh` and either gets
  deep-ready evidence or a structured blocker

## Drivers

- P13.0 correctly blocks agent self-attestation.
- OpenClaw still needs a safe command after `shallow_evidence`.
- A matching local JSON manifest is not a trust boundary.
- Provider output must bind `source_id`, artifact kind, artifact bytes, provider
  identity, and attestation metadata.

## Alternatives Considered

- Expose `--trusted-attestation` through CLI: rejected, recreates the original
  self-attestation bug.
- Let OpenClaw pass `--artifact-dir` to local-fixture provider: rejected, agents
  can write arbitrary local directories.
- Implement platform download/transcription now: rejected, provider automation
  is separate from the attestation boundary.

## Construction Table

| Small Package | Purpose | Files / Surfaces | Tests | Acceptance | Stop Condition |
| --- | --- | --- | --- | --- | --- |
| P13.1a Staged bundle schema | Define signed provider bundle and manifest fields | `workers/video_provider.py` | signature/hash tests | bundle binds source/artifacts/provider/hash | arbitrary manifest accepted |
| P13.1b Provider run CLI | Verify staged bundle and attach trusted evidence | `video_provider.py`, `cli.py` | provider-run tests | status becomes deep-ready only from signed bundle | CLI can self-attest |
| P13.1c OpenClaw wrapper | Add `video-provider-run.sh` and runbook text | `bootstrap.py`, docs | OpenClaw bundle tests | wrapper has no artifact-dir/self-trust path | OpenClaw can forge trusted evidence |
| P13.1d Auto digest handoff | Optional queue job after deep-ready | `video_provider.py` | queue tests | `--auto-digest` only after deep-ready | shallow evidence enqueues digest |
| P13.1e Governance | Status/review docs | status tests | package status aligns with shipped CLI | status overclaims before review |

## Acceptance Tests

- Ordinary CLI attach with accepted labels and matching manifest is still
  rejected.
- OpenClaw attach wrapper still rejects attestation flags.
- Provider-run fails when no staged trusted bundle exists.
- Provider-run succeeds when a signed staged bundle exists and attaches
  transcript, key_frames, and audio_summary as deep-ready.
- Provider-run rejects wrong source_id, wrong artifact hash, missing file, and
  symlinked staged artifacts.
- Provider-run output and manifests do not leak local absolute paths.
- Provider-run writes no canonical, digest, or mutation records.
- `--auto-digest` creates a digest queue job only after deep-ready evidence.
- OpenClaw `video-provider-run.sh` injects root/subject preconditions and can run
  against a staged trusted bundle.

## Stop Conditions

- OpenClaw can pass an artifact directory and receive trusted evidence.
- Any ordinary CLI flag grants `trusted_attestation=True`.
- A self-written manifest can become authority.
- Provider-run bypasses public-safe or canonical gates.
- Provider-run tracks media bytes in Git.

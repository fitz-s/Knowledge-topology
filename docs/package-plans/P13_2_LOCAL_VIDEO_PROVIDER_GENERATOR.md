# P13.2 Package Plan: Local Video Provider Bundle Generator

## Package Ralplan

P13.2 gives the operator/provider side a real way to create trusted video
provider bundles. P13.1 consumes only staged signed bundles; P13.2 adds the
offline key and staging commands that produce those bundles without exposing
private signing material to OpenClaw wrappers.

## Decision

Add provider-side CLI commands:

- `topology video provider-keygen --root <topology-root>`
- `topology video provider-stage`

OpenClaw still receives only `video-provider-run.sh`; it cannot pass artifact
directories, manifests, private keys, or trusted flags. Provider public keys
enter `ops/keys/video_provider_public_keys.json` through reviewed topology
changes, not through an agent-callable registration command.

## Acceptance

- Provider keygen rejects output inside topology or OpenClaw private state.
- Provider keygen emits a registry entry snippet for review.
- Public key registry updates remain governance changes.
- Provider-stage requires a private key outside topology and OpenClaw private
  state.
- Provider-stage requires artifact input directories outside topology and
  OpenClaw private state.
- Provider-stage binds provider identity and allowed attestation modes to the
  reviewed registry entry.
- Provider-stage creates a signed bundle under an external provider root.
- Provider-run consumes that bundle and makes video evidence deep-ready.
- Provider-stage output does not leak private paths.

## Rollback

- Remove the staged bundle directory under the external provider root for the
  affected `src_` id.
- Revoke or rotate the provider public key through a reviewed
  `ops/keys/video_provider_public_keys.json` change.
- Re-run `topology video provider-run` only after the registry is tracked and
  clean.

## Monitor

- Failed signature or key-id mismatch count.
- Stale or dirty provider registry rejection count.
- Provider private-key, provider-root, and artifact-dir private-state rejection
  count.
- Provider-stage identity mismatch and disallowed attestation count.
- Later lint/doctor rejection rate for bundles accepted by provider-run.

# Storage Contract

This document freezes which topology surfaces are tracked, local-only, or
derived. It prevents generated runtime state and redistribution-sensitive
content from polluting the public repository.

## Tracked

Track these surfaces:

- `raw/packets/`: source packet metadata, normalized safe text, excerpts, and
  fetch manifests
- `raw/excerpts/`: public-safe excerpts that are explicitly permitted
- `digests/`
- `canonical/`
- `mutations/approved/`
- `mutations/applied/`
- `mutations/rejected/`
- `ops/events/`: durable semantic audit event records
- `ops/gaps/`
- `ops/escalations/`
- `prompts/`
- `tests/`
- root policy, schema, storage, queue, audience, subject, and routing docs

`mutations/pending/` is tracked durable review artifact storage only.
Transient proposals never live under `mutations/`; use `.tmp/mutations/` or
local-only queue/runtime surfaces until a proposal is promoted for review.

## Local-Only

Do not track these surfaces:

- `raw/local_blobs/`
- `.tmp/`
- `ops/queue/**`
- `ops/leases/**`
- temporary report/cache directories under `ops/reports/`
- `projections/**` by default
- `projections/tasks/**`
- `projections/openclaw/runtime-pack.md`
- `projections/openclaw/runtime-pack.json`
- `projections/openclaw/memory-prompt.md`
- `projections/openclaw/wiki-mirror/**`
- generated caches, logs, and environment files

Tracked projection examples belong under `tests/fixtures/`, not under
`projections/`.

## Public-Safe Source Packets

Every source packet declares `content_mode`:

- `public_text`: normalized text is safe to track.
- `excerpt_only`: only limited excerpts and metadata are tracked.
- `local_blob`: tracked packet stores blob references, hashes, manifests, and
  retrieval metadata; full content stays in `raw/local_blobs/` or a private
  store.

Every source packet also declares `redistributable`: `yes`, `no`, or `unknown`.
Public repositories default to `excerpt_only` or `local_blob` unless the source
is clearly redistributable.

Source-type defaults and excerpt rules are defined in `RAW_POLICY.md`.

## Blob References

Tracked packet metadata may reference local or private blobs by:

- opaque source ID
- hash
- content length
- original retrieval location
- storage hint
- content status

Do not commit private, paywalled, large binary, or uncertain-rights artifacts.

# P2 Package Plan: Source Packet and Fetch V1

## Package Ralplan

P2 creates public-safe source packets for the first resolver set and enqueues
digest jobs. It does not digest, reconcile, apply, compose, writeback, or call
models.

## Reality Check

- `SCHEMA.md` defines required source packet fields but P2 must make them
  executable through typed validation.
- `RAW_POLICY.md` sets source-type defaults but P2 must enforce them.
- `SECURITY.md` treats external content as untrusted; P2 readers cannot touch
  canonical surfaces.
- `STORAGE.md` keeps `raw/local_blobs/` local-only; P2 must not track blob bytes.
- `QUEUES.md` already provides the local spool contract; P2 should reuse it.
- P2 changes public/private leakage mechanics, so Gemini validation is required
  before unfreezing P3.

## Construction Table

| Small Package | Purpose | Files / Surfaces | Fixtures / Tests | Acceptance Criteria | Stop Condition |
| --- | --- | --- | --- | --- | --- |
| P2.1 Source packet model | Make source packet fields and enums executable | `src/knowledge_topology/schema/source_packet.py` | `tests/test_p2_source_packet_fetch.py` | validates required fields, `source_type`, `content_status`, `content_mode`, `redistributable` | model requires non-stdlib dependency |
| P2.2 Resolver classification | Classify local draft, GitHub artifact, article/html, PDF/arXiv | `src/knowledge_topology/workers/fetch.py` | resolver unit tests | correct resolver and default content mode per source | URL/path ambiguity cannot be handled safely |
| P2.3 Packet writer | Write `raw/packets/src_*/packet.json` and safe artifacts | `workers/fetch.py` | local draft/article/pdf/github fixtures | creates packet directory and safe content only | would write unsafe raw bytes |
| P2.4 Digest job enqueue | Enqueue digest job with subject/revision preconditions | `workers/fetch.py`, spool helper | integration test | job payload carries `source_id` and preconditions | subject/head preconditions unavailable |
| P2.5 CLI ingest | Add `topology ingest` command | `cli.py` | CLI smoke tests | command creates packet and digest job | CLI would need network/model behavior |
| P2.6 Public-safe checks | Reject unsafe `public_text` and local blob tracking | source packet model/tests | safety tests | `public_text` requires `redistributable=yes`; `local_blob` stores refs only | public safety rule is untestable |

## Team Decision

Do not use `$team` for P2 implementation. The package is small and touches one
cohesive source/fetch boundary. Ultrawork parallelism was useful for planning
and review, but implementation should remain single-owner to avoid divergence
in packet shape.

## Gemini Requirement

Required before unfreeze because P2 touches untrusted-content and
public/private leakage mechanics.

## Acceptance Criteria

- `topology ingest` can create source packets for:
  - local draft
  - GitHub artifact URL
  - article/html URL
  - PDF/arXiv URL
- `public_text` is rejected unless `redistributable == yes`.
- external/uncertain content defaults to `excerpt_only`.
- PDF/arXiv can use `local_blob` references without storing blob bytes.
- partial fetch behavior creates valid packets.
- digest queue job is enqueued with `subject_repo_id`, `subject_head_sha`, and
  `base_canonical_rev`.
- P0/P1 tests still pass.

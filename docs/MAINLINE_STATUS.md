# Mainline Status

The P0-P9 mainline is complete.

This file records what is shipped, what is deliberately deferred, and what
evidence supports the claim. It is a status document, not a new architecture
contract.

## Evidence Model

- P0 is a contract reality pass, represented by
  `docs/P0_CONTRACT_REALITY_PASS.md` and `tests/test_p0_contracts.py`.
- P1-P9 are package-gated implementation packages, represented by tracked
  package plans and unfreeze records.
- P10 is the mainline closure package.

## Package Matrix

| Package | Status | Plan / Evidence | Review |
| --- | --- | --- | --- |
| P0 Contract Reality Pass | complete | `docs/P0_CONTRACT_REALITY_PASS.md` | `tests/test_p0_contracts.py` |
| P1 Engine Skeleton | approved | `docs/package-plans/P1_ENGINE_SKELETON.md` | `docs/package-reviews/P1_UNFREEZE.md` |
| P2 Source Packet and Fetch V1 | approved | `docs/package-plans/P2_SOURCE_PACKET_FETCH.md` | `docs/package-reviews/P2_UNFREEZE.md` |
| P3 Digest Contract | approved | `docs/package-plans/P3_DIGEST_CONTRACT.md` | `docs/package-reviews/P3_UNFREEZE.md` |
| P4 Reconcile and Mutation | approved | `docs/package-plans/P4_RECONCILE_MUTATION.md` | `docs/package-reviews/P4_UNFREEZE.md` |
| P5 Apply Gate | approved | `docs/package-plans/P5_APPLY_GATE.md` | `docs/package-reviews/P5_UNFREEZE.md` |
| P6 Builder Compose | approved | `docs/package-plans/P6_BUILDER_COMPOSE.md` | `docs/package-reviews/P6_UNFREEZE.md` |
| P7 Writeback, Lint, Doctor | approved | `docs/package-plans/P7_WRITEBACK_LINT_DOCTOR.md` | `docs/package-reviews/P7_UNFREEZE.md` |
| P8 Codex and Claude Integration | approved | `docs/package-plans/P8_CODEX_CLAUDE_INTEGRATION.md` | `docs/package-reviews/P8_UNFREEZE.md` |
| P9 OpenClaw Runtime Projection | approved | `docs/package-plans/P9_OPENCLAW_INTEGRATION.md` | `docs/package-reviews/P9_UNFREEZE.md` |
| P10 Mainline Closure | approved | `docs/package-plans/P10_MAINLINE_CLOSURE.md` | `docs/package-reviews/P10_UNFREEZE.md` |
| P11.1 Builder Compose / Writeback Symmetry | approved | `docs/package-plans/P11_1_BUILDER_WRITEBACK_SYMMETRY.md` | `docs/package-reviews/P11_1_UNFREEZE.md` |
| P11.2 Digest Runner Closure | approved | `docs/package-plans/P11_2_DIGEST_RUNNER_CLOSURE.md` | `docs/package-reviews/P11_2_UNFREEZE.md` |
| P11.3 Fetch V2 | approved | `docs/package-plans/P11_3_FETCH_V2.md` | `docs/package-reviews/P11_3_UNFREEZE.md` |
| P11.4 OpenClaw Live Bridge | approved | `docs/package-plans/P11_4_OPENCLAW_LIVE_BRIDGE.md` | `docs/package-reviews/P11_4_UNFREEZE.md` |
| P11.5 Lint / Doctor Split | approved | `docs/package-plans/P11_5_LINT_DOCTOR_SPLIT.md` | `docs/package-reviews/P11_5_UNFREEZE.md` |
| P11.6 Subject / File-Index | waived_by_user | `docs/package-plans/P11_6_SUBJECT_FILE_INDEX.md` | `docs/package-reviews/P11_6_UNFREEZE.md` |
| P11.7 Video Platform Ingest | approved | `docs/package-plans/P11_7_VIDEO_PLATFORM_INGEST.md` | `docs/package-reviews/P11_7_UNFREEZE.md` |
| P12.0 State Convergence Patch | approved | `docs/package-plans/P12_USAGE_CLOSURE.md` | `docs/package-reviews/P12_0_UNFREEZE.md` |
| P12.1 Consumer Bootstrap | waived_by_user | `docs/package-plans/P12_1_CONSUMER_BOOTSTRAP.md` | `docs/package-reviews/P12_1_UNFREEZE.md` |
| P12.2 Video / Media Closure | approved | `docs/package-plans/P12_2_VIDEO_MEDIA_CLOSURE.md` | `docs/package-reviews/P12_2_UNFREEZE.md` |
| P12.3 OpenClaw Consumer Bundle | waived_by_user | `docs/package-plans/P12_3_OPENCLAW_CONSUMER_BUNDLE.md` | `docs/package-reviews/P12_3_UNFREEZE.md` |

## Shipped CLI Reality

Top-level shipped commands:

- `topology init`
- `topology ingest`
- `topology digest`
- `topology reconcile`
- `topology apply`
- `topology subject`
- `topology compose`
- `topology lint`
- `topology doctor`
- `topology writeback`
- `topology agent-guard`
- `topology openclaw`
- `topology video`
- `topology bootstrap`
- `topology resolve-context`

Shipped compose subcommands:

- `topology compose builder`
- `topology compose openclaw`

Shipped doctor subcommands:

- `topology doctor stale-anchors`
- `topology doctor queues`
- `topology doctor public-safe`
- `topology doctor projections`
- `topology doctor canonical-parity`

Shipped subject subcommands:

- `topology subject add`
- `topology subject refresh`
- `topology subject show`
- `topology subject resolve`

Shipped OpenClaw bridge subcommands:

- `topology openclaw capture-source`
- `topology openclaw issue-lease`
- `topology openclaw lease`
- `topology openclaw run-writeback`

Shipped video subcommands:

- `topology video ingest`
- `topology video status`
- `topology video prepare-digest`
- `topology video attach-artifact`

Shipped bootstrap / consumer subcommands:

- `topology bootstrap codex`
- `topology bootstrap claude`
- `topology bootstrap openclaw`
- `topology bootstrap remove`
- `topology resolve-context`
- `topology doctor consumer`

## Deferred Surfaces

The following items are intentionally not shipped in the P0-P9 mainline:

- audio/video transcript resolver
- deep social thread expansion resolver
- Codex topology MCP registration
- Claude changed-file lint/writeback hooks
- hosted OpenClaw service or topology MCP server
- OpenClaw private workspace writes
- OpenClaw memory-wiki import or live validation
- OpenClaw QMD live indexing validation
- OpenClaw natural-language runtime context sanitizer

## Real-Use Intake Surfaces

Shipped after P11.7:

- `video_platform` source packets for platform video locators such as Douyin,
  TikTok, YouTube, Bilibili, Vimeo, and Instagram.
- Platform video intake is metadata/capture-plan only. It does not try to turn a
  short link into a direct media download inside the public-safe fetch worker.
- `topology video attach-artifact` binds downloaded local videos, transcripts,
  key-frame descriptions, audio summaries, or landing metadata back to the
  source packet through public-safe metadata and local-only blobs.

## OpenClaw Consumer Bundle

Shipped after P12.3:

- `topology bootstrap openclaw` generates an OpenClaw workspace-local bundle
  under `.openclaw/topology/`.
- Generated wrappers include `resolve-context.sh`, `compose-openclaw.sh`,
  `doctor-openclaw.sh`, `capture-source.sh`, `issue-lease.sh`, `lease.sh`, and
  `run-writeback.sh`.
- Generated snippets include runtime consume, session writeback, and topology
  maintainer skills that keep OpenClaw on projection reads and topology-owned
  writeback leases.
- Generated QMD extra paths include only `projections/openclaw/file-index.json`,
  `runtime-pack.json`, `runtime-pack.md`, `memory-prompt.md`, and
  `wiki-mirror/`.
- `topology doctor consumer --workspace ...` and
  `topology bootstrap remove --workspace ...` check and remove unchanged
  OpenClaw workspace generated files from the manifest.
- The bundle remains consumer-local wiring. It does not copy whole topology
  content into OpenClaw and does not grant canonical, digest, or projection
  write authority.

## Mainline Boundary

P0-P9 delivered the repo-root canonical substrate, builder-first loop pieces,
Codex/Claude routing, and a conservative OpenClaw runtime projection.

Post-mainline operational closure packages shipped the runtime doctor split,
subject registry command surface, and the controlled OpenClaw file-index
projection. Remaining deferred work is limited to the items listed above.

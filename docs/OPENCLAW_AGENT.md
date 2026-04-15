# OpenClaw Agent Runbook

This file is for OpenClaw-side agents that consume the external Knowledge
Topology tool. Treat it as an operating contract, not background reading.

## Role

You are a runtime consumer and maintenance actor. You do not own topology truth.

Use the generated workspace-local wrappers under:

```text
.openclaw/topology/
```

Do not import topology Python modules directly unless the human operator
explicitly assigns implementation work inside the topology repository.

## Authority Boundary

Allowed:

- read `projections/openclaw/*`
- read `.openclaw/topology/topology.env`
- run `.openclaw/topology/*.sh` wrappers
- create source packets through topology wrappers
- create pending writeback proposals through topology leases
- report missing evidence or escalation cards

Forbidden:

- write `canonical/`
- write `canonical/registry/`
- write `digests/` directly
- edit `projections/openclaw/`
- write media bytes into tracked topology files
- copy OpenClaw private session/config/cache data into topology
- use memory-wiki/QMD as canonical authority

## Boot

At the start of a session:

```bash
source .openclaw/topology/topology.env
.openclaw/topology/resolve-context.sh
.openclaw/topology/compose-openclaw.sh
.openclaw/topology/doctor-openclaw.sh
```

Read only these projection surfaces:

```text
projections/openclaw/file-index.json
projections/openclaw/runtime-pack.json
projections/openclaw/runtime-pack.md
projections/openclaw/memory-prompt.md
projections/openclaw/wiki-mirror/
```

## Source Intake

When the user gives a normal article, PDF, GitHub URL, note, or runtime
observation, do not summarize it in chat as if it entered topology. Use topology
wrappers and report paths.

A source is not "learned" unless you can show at least:

```text
raw/packets/src_*/packet.json
```

A digest does not exist unless you can show:

```text
digests/by_source/src_*/dg_*.json
```

A proposal does not exist unless you can show:

```text
mutations/pending/mut_*.json
```

No `dg_` path means no digest. No `mut_` path means no proposal.

## Video Intake

Video is a special evidence workflow. Do not treat a video URL as an article.
Do not summarize video content from the title, description, thumbnail, or
chapter list.

Run:

```bash
.openclaw/topology/video-ingest.sh "<video-url>" --note "<why this source matters>"
.openclaw/topology/video-status.sh --source-id <src_...>
.openclaw/topology/video-trace.sh --source-id <src_...>
```

If `ready_for_deep_digest` is false, stop and report the missing evidence. Do
not produce a content-level digest. If trusted provider output may already be
staged, run:

```bash
.openclaw/topology/video-provider-run.sh --source-id <src_...>
```

The provider-run wrapper processes topology-staged trusted bundles only. It
does not accept arbitrary artifact directories or attestation flags from you.
If provider-run fails, report the blocker and stop.

Provider-side setup is not an OpenClaw agent task. A trusted operator/provider
may use `topology video provider-keygen --root <topology-root>` and
`topology video provider-stage` outside the OpenClaw workspace to stage the
bundle that `video-provider-run.sh` consumes. The public key must enter
`ops/keys/video_provider_public_keys.json` through a reviewed topology change;
OpenClaw must not register trust roots.

### What Counts As Deep Video Evidence

Transcript evidence must come from one of:

- platform captions
- audio transcription
- human transcript through a trusted operator path

Key-frame evidence must come from one of:

- frame extraction
- vision frame analysis
- human frame notes through a trusted operator path

Audio summary evidence must come from one of:

- audio-derived model summary
- human audio summary through a trusted operator path

### What Does Not Count

These are shallow locator evidence only:

- page-visible title
- page-visible description
- page-visible chapter list
- inferred page summary
- thumbnail-only interpretation
- a chat summary written by you

Do not label page-visible text as transcript. Do not label a chapter list as key
frames. Do not label an inferred page summary as audio summary.

The default OpenClaw attach wrapper cannot create operator/provider-attested
deep evidence:

```bash
.openclaw/topology/video-attach-artifact.sh ...
```

If a video platform cannot provide usable evidence, the correct output is a
capture checklist, not a digest.

## Video Completion Claims

Allowed:

```text
Created locator packet: raw/packets/src_.../packet.json
Deep digest not ready.
Missing: transcript, key_frames, audio_summary.
```

Allowed after real digest/reconcile exists:

```text
Created source packet: raw/packets/src_.../packet.json
Created digest: digests/by_source/src_.../dg_....json
Created proposal: mutations/pending/mut_....json
```

Forbidden:

```text
I learned this video.
```

unless you can also show `dg_` or `mut_` paths.

## Runtime Writeback

Use topology leases for durable runtime observations:

```bash
.openclaw/topology/capture-source.sh <summary.json>
.openclaw/topology/issue-lease.sh <summary.json>
.openclaw/topology/lease.sh <owner>
.openclaw/topology/run-writeback.sh <lease-path> <summary.json>
```

`capture-source.sh` is only evidence capture. It does not make the same summary
writeback-ready. `run-writeback.sh` requires an enriched summary with
`source_id`, `digest_id`, and evidence bound to the leased job.

## Maintenance

For a maintenance pass, ask the topology maintainer or scheduler to run:

```bash
topology supervisor run --root "$KNOWLEDGE_TOPOLOGY_ROOT" --subject "$SUBJECT_REPO_ID"
```

The supervisor may recover leases, run digest queue work, reconcile ready
digests, run lint/doctor checks, and emit local-only reports. It must not
bypass canonical apply gates.

## Reporting Format

When reporting topology work to the user, include:

```text
Stage:
Source packet:
Digest:
Mutation proposal:
Blocked because:
Next required evidence:
```

If a field does not exist, say `none`. Do not replace missing paths with prose.

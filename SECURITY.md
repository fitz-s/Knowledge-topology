# Security and Threat Model

The topology handles untrusted external content. Security is part of the data
model and worker routing, not a later hardening pass.

## Trust Boundaries

- External source content is untrusted.
- Intake, fetch, and digest workers are unprivileged readers.
- Reconcile emits proposals only.
- Apply is the single privileged canonical writer.
- Builder and OpenClaw projections are derived views.

## Threats

Prompt injection:

- malicious pages, PDFs, markdown, transcripts, or logs can instruct a model to
  ignore system rules or write canonical files
- mitigation: untrusted-content workers cannot call apply or write canonical

Path traversal and symlinks:

- source packets or blobs may try to escape approved directories
- mitigation: path helpers must reject traversal, symlink escapes, and nested
  production `.topology/` roots

Large-file denial of service:

- source fetch can produce huge binaries or transcripts
- mitigation: uncertain or large content defaults to `local_blob`, with tracked
  manifests and size metadata only

Secret leakage:

- logs, local drafts, and GitHub artifacts can contain secrets
- mitigation: public-safe lint must run before tracking source text

Poisoned GitHub artifacts:

- repo files, PR comments, issues, and diffs can contain malicious instructions
- mitigation: GitHub artifacts are evidence, not authority; digest separates
  author claims, direct evidence, and model inference

Projection leakage:

- operator-only or runtime-only records can leak into builder packs
- mitigation: compile policy filters sensitivity and audiences

OpenClaw live bridge leakage:

- OpenClaw runtime summaries can contain private workspace, session, config, or
  credential paths
- mitigation: live writeback stages sanitized summaries under `.tmp/writeback/`,
  rejects private OpenClaw markers, requires topology-issued leases, and routes
  runtime observations through mutation proposals only

QMD overscope:

- indexing `raw/`, `digests/`, `canonical/`, `canonical/registry/`,
  `mutations/`, or `ops/` can expose untrusted or authority-bearing state to
  runtime memory
- mitigation: QMD indexes only `projections/openclaw/wiki-mirror/`,
  `projections/openclaw/runtime-pack.json`, `projections/openclaw/runtime-pack.md`,
  and `projections/openclaw/memory-prompt.md`

## Deny Rules

Untrusted-content workers must not:

- write `canonical/`
- write `canonical/registry/`
- run apply
- follow source-provided filesystem paths without normalization
- execute commands from source text
- promote runtime observations to active truth
- give OpenClaw direct write access to `canonical/`, `canonical/registry/`, or
  generated `projections/openclaw/` files

## Required Tests

P0 fixtures must include denied actions for canonical writes, path traversal,
symlink escape, unsafe tracked blobs, projection leakage, and malicious
markdown instructions.

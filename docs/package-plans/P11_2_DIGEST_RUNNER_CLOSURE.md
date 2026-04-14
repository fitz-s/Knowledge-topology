# P11.2 Package Plan: Digest Runner Closure

## Package Ralplan

P11.2 closes the manual gap between `topology ingest` and durable digest
artifacts. Today ingest enqueues `ops/queue/digest/pending/job_*.json`, but a
human must separately produce `model-output.json` and call `topology digest`.
P11.2 adds a queue runner that leases digest jobs, renders the digest prompt,
calls a provider adapter, validates the returned JSON through the existing
digest worker, writes digest JSON/Markdown, and moves the job to `done` or
`failed`.

P11.2 does not implement fetch V2, reconcile/apply automation, OpenClaw live
bridge, lint/doctor split, or subject/file-index commands.

## Reality Check

- `JsonFileDigestAdapter` is the only current adapter and exposes
  `load_output()` with no prompt/request context.
- `write_digest_artifacts()` already owns digest validation, source-packet
  validation, duplicate-output checks, and JSON/Markdown writes. The runner
  must call it instead of duplicating those rules.
- `ingest_source()` already creates digest spool jobs with source preconditions
  and payload `source_id`.
- Existing spool helpers support `pending -> leased -> done|failed`; they do
  not yet annotate failed jobs with an error payload.
- Prompt files exist for `deep` and `standard`. `scan` can use the standard
  prompt unless a later package adds a separate scan prompt.
- Real provider access cannot be assumed in tests. The production-facing
  adapter should be command/provider based so callers can plug in Gemini,
  OpenAI, Claude, or another local provider without moving business logic into
  agent prompts.
- Current source packets can contain absolute local draft paths and local blob
  storage hints. Provider requests must use a positive allowlist and redaction
  layer rather than serializing packet JSON wholesale.
- Existing spool jobs record `lease_expires_at`, but no worker currently
  reclaims expired leases. P11.2 must define runner-owned recovery before it can
  be autonomous.

## Construction Table

| Small Package | Purpose | Files / Surfaces | Fixtures / Tests | Acceptance Criteria | Stop Condition |
| --- | --- | --- | --- | --- | --- |
| P11.2a Adapter boundary | Keep JSON-file adapter and add prompt/provider request abstractions | `src/knowledge_topology/adapters/digest_model.py` | adapter unit tests with fake command provider and injection text | adapters only generate/load raw JSON; validation stays in worker; command execution is argv-only | digest validation logic appears inside provider adapters or source content reaches argv/shell |
| P11.2b Prompt rendering | Build deterministic sanitized digest requests from packet + prompt files | `src/knowledge_topology/workers/digest.py`, `prompts/` | prompt/request tests for deep/standard/scan, local paths, local blobs, traversal, and symlinks | request includes prompt contract, redacted packet metadata, safe source text/excerpt when available | prompt includes raw local paths, blob storage hints, canonical data, symlink content, or whole unsafe artifacts |
| P11.2c Queue runner | Lease digest pending jobs, recover expired leases, and land digest artifacts | new `src/knowledge_topology/workers/run_digest_queue.py`, `storage/spool.py` if needed | queue success/failure/stale/expired tests | pending job becomes done on valid provider output; failed/requeued on defined failure paths; artifacts written through `write_digest_artifacts()` | runner writes digest files without schema validation or leaves expired leased jobs stranded |
| P11.2d CLI closure | Expose mutually exclusive queue runner mode while preserving legacy JSON-file digest | `src/knowledge_topology/cli.py` | CLI smoke and parser-shape tests | old `topology digest --source-id --model-output` still works; new queue mode does not require manual `model-output.json` | existing P3 CLI breaks or runner mode still requires source/model-output args |
| P11.2e Prompt docs | Make prompt contract explicit for provider adapters | `prompts/digest_deep.md`, `prompts/digest_standard.md` | prompt-content assertions | prompts require JSON-only output and preserve fidelity separation | prompts ask provider to mutate canonical state |

## Gemini Requirement

Required before unfreeze.

Reason: P11.2 changes adapter/facade boundaries, provider execution surface,
CLI command contract, and prompt/model behavior.

Acceptance:

- Save Gemini output under `.omx/artifacts/gemini-p11-2-*.md`.
- Summarize the artifact in `docs/package-reviews/P11_2_UNFREEZE.md`.
- Missing or rejected Gemini blocks P11.3.

## Digest Adapter Contract

Keep the legacy JSON-file path:

- `JsonFileDigestAdapter(path).load_output()` remains valid for existing
  fixture/manual workflows.
- `topology digest --source-id ... --model-output ...` remains valid.

Add a provider-request path:

- `DigestModelRequest` carries `source_id`, `digest_depth`, rendered prompt,
  sanitized source packet metadata, and bounded source text/excerpt.
- Provider adapters return raw digest JSON only.
- Provider adapters must not validate digest schema, write files, move jobs,
  reconcile mutations, or touch canonical state.
- A command provider adapter runs an explicit local command with sanitized
  request JSON on stdin and reads digest JSON from stdout.
- Tests use a local scripted command provider so no network/provider secrets are
  required.

Command provider execution contract:

- Parse `--provider-command` with `shlex.split()`.
- Require a non-empty argv vector and run with `subprocess.run(...,
  shell=False)`.
- Never append source-derived text to argv; all prompt/source text travels only
  through stdin JSON.
- Use a deterministic cwd: the topology root.
- Use a bounded, explicit environment: inherit only `PATH`, `HOME`, and provider
  API key variables already present in the process environment.
- Enforce a timeout, default 120 seconds, configurable by CLI.
- Capture stdout/stderr; bound stdout to 1 MiB and stderr/last-error text to
  4 KiB.
- Require stdout to parse as a JSON object. Nonzero exit, timeout, oversize
  output, invalid JSON, or scalar JSON are provider failures and move the job to
  `failed/` with bounded `last_error`.
- Tests must include malicious source text such as shell metacharacters and
  verify it appears only inside stdin JSON, never argv or shell execution.

Fixture provider contract:

- `--model-output-dir` maps a leased job to exactly
  `<model-output-dir>/<source_id>.json`.
- The fixture file must be a regular non-symlink file under the output
  directory; missing file, directory, final symlink, parent symlink, invalid
  JSON, scalar JSON, or source mismatch fails the job.
- No globbing, fallback names, or implicit "next JSON file" behavior is allowed.

## Queue Runner Contract

Runner input:

- topology root
- owner string
- max jobs
- provider adapter
- lease seconds
- max attempts, default 3
- current canonical revision
- current subject repo ID
- current subject HEAD SHA

Runner behavior:

1. Before leasing any new pending work, inspect `ops/queue/digest/leased/` for
   expired leases. Recovered jobs are eligible to be leased in the same runner
   invocation after this pre-pass.
2. For each expired lease, if a job's `lease_expires_at` is in the past and
   `attempts < max_attempts`, clear lease fields and atomically move it back to
   `pending/`. If `attempts >= max_attempts`, annotate bounded `last_error` and
   move it to `failed/`.
3. Lease the next digest job from `ops/queue/digest/pending/`.
4. Read `payload.source_id` from the leased job.
5. Check stale preconditions before provider work:
   `job.base_canonical_rev == current_canonical_rev`,
   `job.subject_repo_id == current_subject_repo_id`, and
   `job.subject_head_sha == current_subject_head_sha`. Stale or wrong-subject
   jobs move to `failed/` with bounded `last_error` and do not call the
   provider.
6. Load and validate the source packet.
7. Render the prompt request from `prompts/digest_deep.md` or
   `prompts/digest_standard.md`; `scan` uses the standard prompt.
8. If any digest JSON artifact already exists under
   `digests/by_source/<source_id>/`, fail the job before provider invocation.
   Queue runner mode is one-digest-per-source-id for idempotency; explicit
   redigest/rebuild policy is deferred.
9. Call the provider adapter.
10. Feed the returned raw JSON into `write_digest_artifacts()`.
11. Move the leased job to `done` on success.
12. If any step fails, annotate the leased job with a bounded `last_error` and
   move it to `failed`.

Runner output:

- structured result object with counts and paths:
  `leased`, `completed`, `failed`, `digest_json_paths`, `digest_md_paths`,
  `done_job_paths`, `failed_job_paths`

## Prompt Request Safety

Allowed source content in provider requests:

- `content.md` for redistributable `public_text`
- `excerpt.md` for `excerpt_only`
- sanitized source packet metadata:
  `id`, `source_type`, `retrieved_at`, `curator_note`, `ingest_depth`,
  `authority`, `trust_scope`, `content_status`, `content_mode`,
  `redistributable`, `hash_original`, and `hash_normalized`
- sanitized artifact summaries:
  `kind`, `path`, `hash_sha256`, and `note` only when fields are scalar and
  non-path-sensitive

Disallowed source content:

- raw/local blob bytes
- local absolute paths from `original_url`
- local blob `storage_hint` values
- paths outside the packet directory
- files reached through symlinks or traversal
- canonical registry contents
- mutation packs or projections

Bound source text/excerpt length in requests to keep provider calls stable.

Prompt renderer file safety:

- Only read `content.md` or `excerpt.md` from the source packet directory.
- The target file and every parent component must be a real directory/file
  under `raw/packets/<source_id>/`, not a symlink.
- Artifact paths are not trusted for reads. They are metadata only after
  allowlist sanitization.
- If packet metadata points to `content.md`/`excerpt.md` but the safe file is
  missing, treat source text as unavailable instead of reading another path.
- Negative tests must cover traversal artifact paths, final symlink, parent
  symlink, symlink to canonical data, local draft absolute path redaction, and
  local_blob manifest-only behavior.

## CLI Contract

Legacy:

```bash
topology digest \
  --root "$KNOWLEDGE_TOPOLOGY_ROOT" \
  --source-id "src_..." \
  --model-output ".tmp/model-output.json"
```

New queue runner:

```bash
topology digest \
  --root "$KNOWLEDGE_TOPOLOGY_ROOT" \
  --run-queue \
  --owner "digest-runner" \
  --provider-command "/path/to/provider-script" \
  --subject "<subject-repo-id>" \
  --current-canonical-rev "<current-topology-head-sha>" \
  --current-subject-head-sha "<current-subject-head-sha>" \
  --max-jobs 1
```

Optional fixture mode:

```bash
topology digest \
  --root "$KNOWLEDGE_TOPOLOGY_ROOT" \
  --run-queue \
  --owner "digest-runner" \
  --model-output-dir ".tmp/digest-model-outputs" \
  --subject "<subject-repo-id>" \
  --current-canonical-rev "<current-topology-head-sha>" \
  --current-subject-head-sha "<current-subject-head-sha>" \
  --max-jobs 1
```

CLI parser contract:

- Legacy mode requires `--source-id` and `--model-output`.
- Queue mode requires `--run-queue`, `--owner`, `--subject`,
  `--current-canonical-rev`, `--current-subject-head-sha`, and exactly one of
  `--provider-command` or `--model-output-dir`.
- `--provider-command` and `--model-output-dir` are mutually exclusive.
- Queue mode must not require `--source-id` or `--model-output`.
- Legacy mode must reject queue-only flags.
- Parser tests must cover both valid modes and mutual-exclusion failures.

Fixture mode preserves JSON-file adapter workflows; provider-command mode
closes the manual JSON-preparation gap.

## Acceptance Tests

Required tests:

- Existing P3 JSON-file digest tests still pass.
- CLI legacy digest smoke still passes.
- Queue runner consumes a pending digest job produced by `topology ingest`,
  invokes a local command provider, writes digest JSON and Markdown, and moves
  the job to `done` without any prewritten `model-output.json`.
- Queue runner fixture mode maps by `<source_id>.json` and fails missing,
  non-regular, symlink, malformed, scalar, or source-mismatched fixture files.
- Invalid provider JSON moves the leased job to `failed`, records a bounded
  `last_error`, and writes no digest artifact.
- Nonzero provider exit, timeout, oversized output, and stderr-heavy failures
  move the job to `failed` with bounded `last_error`.
- Existing digest artifacts for the same `source_id` fail the job before
  provider invocation and without overwriting the existing artifact.
- Expired leased jobs are requeued when attempts remain and failed when
  attempts are exhausted.
- Stale `base_canonical_rev`, wrong `subject_repo_id`, or stale
  `subject_head_sha` jobs fail before provider invocation.
- Prompt request for `public_text` includes bounded `content.md`; request for
  `excerpt_only` includes bounded `excerpt.md`; `local_blob` includes metadata
  only.
- Prompt request redacts local absolute paths and local blob storage hints.
- Prompt renderer rejects or ignores traversal and symlinked source content
  paths instead of reading them.
- Command provider tests prove malicious source text cannot reach shell/argv.
- Prompt files explicitly require JSON-only digest output and no canonical
  writes.

## Stop Conditions

- `topology ingest` followed by queue-runner CLI still requires a human to hand
  assemble `model-output.json`.
- Provider adapters duplicate digest schema validation or artifact-write
  business logic.
- Failed provider output leaves jobs in `leased/`.
- Runner reads local blobs, canonical records, mutations, projections, or
  symlinked packet content into the provider prompt.
- Existing `topology digest --model-output` behavior breaks.

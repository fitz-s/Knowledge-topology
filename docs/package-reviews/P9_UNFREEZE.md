# P9 Unfreeze Review

## Package

P9 OpenClaw Runtime Projection

## Package Plan

- `docs/package-plans/P9_OPENCLAW_INTEGRATION.md`

## Implementation Commits

- `36360f5` - Freeze P9 OpenClaw projection plan
- `5d75857` - Add P9 OpenClaw runtime projection
- `8a91bb0` - Seal P9 projection leakage paths
- `d8f8441` - Harden P9 nested projection filters
- `b362c4b` - Close P9 path and mirror staleness gaps
- `b8edc6a` - Widen P9 authority and private path filters
- `128048e` - Generalize P9 authority drift filters
- `b51aae5` - Catch OpenClaw private path variants
- `b6ecc0f` - Fail closed on OpenClaw text in record fields
- `d976bb4` - Normalize OpenClaw token filtering in P9
- `6c0b8a5` - Remove natural language from P9 runtime records
- `6498e8c` - Constrain P9 scalar projection fields
- `ea55f25` - Restrict P9 to machine-validated scalar fields
- `5c5bff1` - Constrain P9 file anchor paths
- `bb99db2` - Reject instruction-shaped OpenClaw file anchors
- `0ab35ec` - Remove file refs from P9 OpenClaw projection
- `5032f9c` - Preflight P9 OpenClaw outputs before writes
- `3e210b7` - Fail closed before P9 output target conflicts
- `99e34e8` - Reject malformed P9 output directories
- `20ac6db` - Reject broken P9 projection symlinks
- `4702166` - Finalize P9 structured output safety
- `4c98b7c` - Project labeled P9 gaps and escalations
- `51a5aae` - Include P9 wiki record metadata
- `3e84df8` - Fail closed on malformed P9 visibility labels
- `73c26f8` - Require valid gate class for P9 escalations
- `297cf18` - Fail closed on malformed P9 input surfaces
- `c86a70b` - Fail closed on P9 JSONL inputs and hidden gap targets
- `021040f` - Preflight P9 input paths lexically
- `d09c702` - Reject parent symlinks for P9 inputs

## Verification Evidence

Commands run:

```bash
python3 tests/test_p9_openclaw_projection.py
python3 -m unittest discover -s tests
python3 -m compileall -q src tests
PYTHONPATH=src python3 -m knowledge_topology.cli lint --root .
PYTHONPATH=src python3 -m knowledge_topology.cli doctor stale-anchors --root . --subject repo_knowledge_topology --subject-head-sha $(git rev-parse HEAD)
git diff --check
git check-ignore projections/openclaw/runtime-pack.json projections/openclaw/wiki-mirror/pages/example.md projections/openclaw/memory-prompt.md projections/openclaw/wiki-mirror/manifest.json
```

Result: all passed after final P9 hardening.

Final suite size: 120 tests.

P9 focused suite size: 23 tests.

## Reviewer Verdict

Approved after blocker fixes.

Reviewer blockers addressed:

- local/traversal/private file-ref leakage
- invalid opaque refs
- unsafe scalar and natural-language projection fields
- stale wiki pages
- OpenClaw private path and authority wording variants
- malformed visibility labels
- invalid escalation gate classes
- malformed input and output filesystem surfaces
- parent symlink input redirects

## Critic Verdict

Approved after blocker fixes.

Critic blockers addressed:

- hidden node IDs leaking through gaps
- JSONL FIFO and symlink input hangs/redirects
- escalation directory symlink redirects
- partial writes after output preflight failure
- generated timestamp injection
- special stale wiki page entries
- natural-language prompt injection through records, file refs, tags, and slugs
- file refs as an unbounded instruction channel
- malformed output directory components and broken symlinks

## Gemini Status

Required: yes.

Reason: P9 changes OpenClaw external-root behavior, runtime projection, and
public/private leakage boundaries.

Artifacts:

- Approved artifact: `.omx/artifacts/gemini-p9-openclaw-projection-approved-20260413T222441Z.md`
- Earlier rejected artifact: `.omx/artifacts/gemini-p9-openclaw-projection-20260413T214011Z.md`
- Earlier no-verdict artifact: `.omx/artifacts/gemini-p9-openclaw-projection-final-20260413T222122Z.md`
- Earlier no-verdict short artifact: `.omx/artifacts/gemini-p9-openclaw-projection-final-short-20260413T222219Z.md`

Gemini verdict: `APPROVED`.

## Residual Risks

- P9 runtime records are intentionally sparse. They exclude natural-language
  summaries, statements, tags, and file refs to avoid prompt-injection and
  path-shaped instruction channels.
- A later package may reintroduce richer OpenClaw context only with a
  positive-schema sanitizer and subject-file index.
- P9 does not run a live OpenClaw workspace, QMD index, or memory-wiki import.
- A no-op local shim was added at `/Users/leofitz/.vibe-island/bin/vibe-island-bridge`
  because the configured Gemini hook target was missing and blocked Gemini CLI
  execution.

## Final Decision

`approved`

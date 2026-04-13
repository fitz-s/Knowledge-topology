# P8 Unfreeze Review

## Package

P8 Codex and Claude Integration

## Package Plan

- `docs/package-plans/P8_CODEX_CLAUDE_INTEGRATION.md`

## Implementation Commits

- `cf6ff89` - Freeze P8 agent integration plan
- `336a74c` - Add P8 Codex Claude integration guards
- `c8304e0` - Block case-variant canonical guard bypasses

## Verification Evidence

Commands run:

```bash
python3 tests/test_p8_agent_integration.py
python3 -m unittest discover -s tests
python3 -m compileall -q src tests
PYTHONPATH=src python3 -m knowledge_topology.cli lint --root .
PYTHONPATH=src python3 -m knowledge_topology.cli doctor stale-anchors --root . --subject repo_knowledge_topology --subject-head-sha $(git rev-parse HEAD)
PYTHONPATH=src python3 -m knowledge_topology.cli agent-guard claude-pre-tool-use --help
git diff --check
```

Result: all passed after case-insensitive path hardening.

Final suite size: 97 tests.

## Plan Review

Approved after plan-level iteration.

Plan blockers addressed:

- guard CLI command, stdin, exit, and no-write contract
- Claude hook settings matcher and shell command shape
- absolute/relative path normalization and symlink/root-escape behavior
- Codex advisory-only scope
- explicit residual risk that P8 does not sandbox Bash or future Claude tools

## Reviewer Verdict

Approved after blocker fixes.

Reviewer evidence:

- skills are thin routing surfaces
- Claude settings use only `PreToolUse` with `Write|Edit|MultiEdit`
- hook script uses `PYTHONPATH="$CLAUDE_PROJECT_DIR/src" python3 -m knowledge_topology.cli`
- no `.codex/config.toml` or fake MCP registration exists
- tests cover guard, shell hook, settings, and skills

## Critic Verdict

Approved after blocker fixes.

Critic blockers addressed:

- case-insensitive `Canonical/` and `CANONICAL/` bypasses on macOS
- root/cwd/traversal/symlink escape handling
- malformed hook JSON and malformed `Write`/`Edit`/`MultiEdit` payloads
- explicit allowed proposal/writeback surfaces
- scoped residual risk for Bash and future file-writing tools

## Gemini Status

Required: yes.

Reason: P8 changes adapter/facade boundaries and Claude hook behavior.

Artifact:

- `.omx/artifacts/gemini-p8-agent-integration-20260413T193912Z.md`

Gemini verdict: `APPROVED`.

Note: the first pinned-model request returned through the OMX wrapper with a
nonzero status, then the direct Gemini CLI fallback returned the approval
recorded in the artifact.

## Residual Risks

- P8 blocks only Claude direct `Write`, `Edit`, and `MultiEdit` canonical
  writes. It is not a Bash/shell sandbox.
- Codex remains advisory through repo skills and `AGENTS.md`; no deterministic
  Codex write-blocking hook is claimed.
- Live Claude Code runtime behavior was not exercised beyond project hook
  command smoke tests.
- Topology MCP registration remains deferred until a tested MCP server exists.

## Final Decision

`approved`

# P8 Package Plan: Codex and Claude Integration

## Package Ralplan

P8 connects existing deterministic topology commands to Codex and Claude as
thin facades. It does not add OpenClaw runtime packs, memory-wiki mirrors,
MCP servers, or a second business-logic path.

### Principles

- Agents consume task packs and write mutation proposals; they do not consume
  the whole topology or edit canonical state directly.
- Integration files are routing and enforcement surfaces only. Topology logic
  stays in the Python CLI/library.
- Hook behavior must be testable with local fixture JSON before it is enabled
  in project settings.
- Do not register live MCP config for a server that does not exist yet.
- Generated task packs and writeback deltas remain local-only.
- Codex enforcement in P8 is advisory through repo instructions and skills.
  Deterministic write blocking is added only for Claude, where a verified
  `PreToolUse` hook surface exists.
- Claude deterministic blocking in P8 covers only direct `Write`, `Edit`, and
  `MultiEdit` file tools. It is not a shell command sandbox and does not claim
  protection against `Bash` writes or future Claude file-writing tools.

### Decision Drivers

1. Preserve canonical authority and write gates from P5/P7.
2. Keep Codex and Claude procedure thin so project instructions do not become
   another source of truth.
3. Avoid speculative config that cannot be verified against local runtime
   behavior.

### Options Considered

- **A. Full integration now:** add skills, project config, hooks, and MCP
  registration.
  - Rejected because the MCP server is not implemented and a live config would
    create a false capability.
- **B. Skills only:** add Codex/Claude skills with no deterministic guards.
  - Rejected because Claude direct writes to `canonical/` would remain only
    conventionally discouraged.
- **C. Thin skills plus tested hook guard:** add skills and a deterministic
  guard command used by Claude project hooks; defer MCP/OpenClaw.
  - Chosen because it advances agent integration while preserving the CLI as
    the sole logic path.

## Reality Check

- Filesystem/Git: `.agents/`, `.claude/`, and `.codex/` are currently absent
  from the repo. New tracked files must be small and deterministic. Generated
  `projections/**` remains ignored.
- Public repository safety: skills and hooks must not embed local secrets,
  tokens, private absolute paths, or generated source contents.
- Untrusted-content handling: skills must preserve the rule that fetched
  source material is untrusted and cannot drive privileged apply operations.
- Concurrency: P8 does not change queue semantics. Hook guards are local
  single-event checks only.
- Testability: hook guard behavior must be testable by feeding Claude-like
  JSON stdin fixtures. Skill files must be checked for required routing
  commands and forbidden canonical-write language.
- Adapter/facade boundary: skills and hooks call `topology` CLI behavior. They
  must not reimplement compose, writeback, lint, or apply logic.
- Canonical authority: only `topology apply` writes `canonical/`; P8 guards
  should block direct Claude `Write`/`Edit`/`MultiEdit` attempts under
  `canonical/` and `canonical/registry/`.
- Hook scope: P8 wires only Claude `PreToolUse` write blocking. Session-start
  context injection is deferred because it cannot block writes and interacts
  with clean-worktree and stale-pack behavior.
- Current-runtime check: local Claude settings already use project-style hook
  objects. Anthropic docs confirm project `.claude/settings.json`, JSON stdin,
  exit code 2 blocking, and `$CLAUDE_PROJECT_DIR` script references. Codex
  local config supports MCP and environment sections globally, but P8 will not
  add project MCP registration until a real topology MCP server exists.

References checked:

- Claude Code settings: https://code.claude.com/docs/en/settings
- Claude Code hooks: https://code.claude.com/docs/en/hooks
- Local Codex config: `/Users/leofitz/.codex/config.toml`

## Construction Table

| Small Package | Purpose | Files / Surfaces | Fixtures / Tests | Acceptance Criteria | Stop Condition |
| --- | --- | --- | --- | --- | --- |
| P8.1 Agent skills | Add thin consume/writeback skills for Codex and Claude | `.agents/skills/topology-consume/SKILL.md`, `.agents/skills/topology-writeback/SKILL.md`, `.claude/skills/topology-consume/SKILL.md`, `.claude/skills/topology-writeback/SKILL.md` | skill-content tests | skills route through `topology compose builder`, `topology writeback`, and `topology lint`; no whole-topology dump instructions | skills tell agents to edit `canonical/` directly |
| P8.2 Guard CLI | Add deterministic guard subcommand for Claude hook events | `src/knowledge_topology/workers/agent_guard.py`, `cli.py` | guard JSON fixtures for `Write`, `Edit`, `MultiEdit`, malformed JSON, missing paths, traversal, symlink escape, allowed proposal paths | direct writes to `canonical/` and `canonical/registry/` are denied; `mutations/pending/` and `.tmp/writeback/` remain allowed; invalid or unsupported write payloads fail closed | guard reimplements apply/writeback logic |
| P8.3 Claude hooks | Wire project `PreToolUse` hooks to the guard only | `.claude/settings.json`, `.claude/hooks/topology-pre-tool-use.sh` | JSON syntax and shell-hook stdin smoke tests using the exact command contract | hook command uses `$CLAUDE_PROJECT_DIR`, exits 2 on denied writes, emits clear denial, and avoids local absolute secrets | hook schema cannot be validated locally |
| P8.4 Codex routing | Add Codex repo skill discoverability and non-MCP config notes | `.agents/skills/**`, optional `.codex/README.md` | tests only | Codex has repo-scoped advisory skills; no fake MCP server registration or claimed deterministic Codex write blocking | project `.codex/config.toml` would be speculative |

## Guard CLI Contract

Command:

```bash
topology agent-guard claude-pre-tool-use --root <topology-root>
```

Contract:

- Reads one Claude `PreToolUse` hook JSON object from stdin.
- Returns exit `0` to allow the tool call.
- Returns exit `2` to deny the tool call and writes a concise reason to stderr.
- Never writes files.
- Invalid JSON, non-object JSON, missing tool name, unsupported write payload
  shapes, missing path fields, path traversal, and root-escaping paths fail
  closed with exit `2`.
- Non-file tools are allowed by default because P8 guard scope is direct file
  write prevention, not command sandboxing.

Path extraction rules:

- `Write`: read `tool_input.file_path`.
- `Edit`: read `tool_input.file_path`.
- `MultiEdit`: read `tool_input.file_path`.
- Candidate paths may be absolute or relative.
- Relative paths resolve against the hook event `cwd` if present, otherwise
  against `--root`.
- `cwd`, when present, must resolve equal to or inside `--root`; otherwise the
  guard denies the event.
- Absolute candidate paths use `Path.resolve(strict=False)` and must resolve
  equal to or inside `--root`.
- Relative candidate paths join against the validated `cwd` or `--root`, then
  use `Path.resolve(strict=False)`.
- Symlinked ancestors are resolved before policy comparison.
- Deny paths equal to `canonical/` or under `canonical/`.
- Deny paths equal to `canonical/registry/` or under `canonical/registry/`.
- Allow paths under `mutations/pending/` and `.tmp/writeback/`; apply/writeback
  workers still validate contents later.
- Deny candidate paths that escape the topology root.

## Claude Hook Contract

Project settings skeleton:

```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"$CLAUDE_PROJECT_DIR/.claude/hooks/topology-pre-tool-use.sh\""
          }
        ]
      }
    ]
  }
}
```

Shell script contract:

```bash
PYTHONPATH="$CLAUDE_PROJECT_DIR/src" \
  python3 -m knowledge_topology.cli agent-guard claude-pre-tool-use \
  --root "$CLAUDE_PROJECT_DIR"
```

The shell hook reads the original Claude hook JSON from stdin and passes it
unchanged to the CLI command. Tests must smoke-run this exact shell command
shape with fixture stdin.

## Team Decision

Do not use `$team` for P8 implementation. The package changes multiple small
facade files and tests that need one owner to keep routing language consistent.
Use Reviewer and Critic after implementation, per package gates.

## Gemini Requirement

Required before unfreeze.

Reason: P8 changes adapter/facade boundaries and Claude hook behavior.

## Acceptance Criteria

- Codex and Claude each have `topology-consume` and `topology-writeback`
  skills.
- Skills tell agents to use builder packs and writeback proposals, not whole
  topology dumps or direct canonical edits.
- Claude project hook config is valid JSON and uses `$CLAUDE_PROJECT_DIR`
  scripts.
- Guard tests cover allowed mutation/writeback surfaces and denied canonical
  surfaces for `Write`, `Edit`, and `MultiEdit`-shaped inputs.
- Invalid hook JSON fails closed with a clear denial.
- Missing path fields, traversal, symlink escape, non-list edits, scalar edits,
  malformed settings JSON, and shell-hook stdin smoke cases are covered.
- No new dependency is added.
- No MCP server, `.codex/config.toml` MCP registration, OpenClaw runtime config,
  or SessionStart context injection is registered in P8.
- Skills and settings do not claim full Claude shell-write protection; P8 only
  blocks direct `Write`, `Edit`, and `MultiEdit` canonical writes.
- Full test suite, compile check, lint, reviewer, critic, and Gemini pass
  before P9 starts.

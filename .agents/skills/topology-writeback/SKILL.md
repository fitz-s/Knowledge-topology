---
name: topology-writeback
description: Emit Knowledge Topology writeback proposals after a coding task.
---

# Topology Writeback

Use this skill at the end of a coding task that used or changed topology-relevant
knowledge.

## Contract

- Write mutation proposals, not canonical records.
- Include only decisions, invariants, interfaces, runtime observations, task
  lessons, commands, tests, file refs, and conflicts that are grounded in the
  session.
- Keep generated writeback deltas local until reviewed.
- Run lint after creating the writeback proposal.

## Summary JSON

Create a local summary JSON under `.tmp/` with:

```json
{
  "source_id": "src_...",
  "digest_id": "dg_...",
  "decisions": [{"statement": "...", "status": "draft"}],
  "invariants": [{"statement": "...", "status": "draft"}],
  "interfaces": [
    {
      "name": "Public contract name",
      "contract": "What callers can rely on.",
      "file_refs": [
        {
          "repo_id": "repo_...",
          "commit_sha": "...",
          "path": "src/example.py",
          "line_range": [1, 20],
          "anchor_kind": "line"
        }
      ]
    }
  ],
  "runtime_assumptions": [
    {"statement": "Observed runtime fact.", "observed_in": "builder pack task id or runtime path"}
  ],
  "task_lessons": [
    {"lesson": "Reusable implementation lesson.", "applies_to": "future matching tasks"}
  ],
  "tests_run": [
    {"command": "pytest tests/test_example.py", "result": "passed", "notes": "focused regression"}
  ],
  "commands_run": [
    {"command": "topology lint --root ...", "exit_code": 0, "notes": "clean"}
  ],
  "file_refs": [
    {"repo_id": "repo_...", "commit_sha": "...", "path": "src/example.py"}
  ],
  "conflicts": [
    {
      "summary": "What disagrees.",
      "expected": "Previous topology expectation.",
      "observed": "Session observation.",
      "severity": "medium",
      "refs": ["nd_...", "src_..."]
    }
  ]
}
```

At least one of `decisions`, `invariants`, `interfaces`,
`runtime_assumptions`, `task_lessons`, `tests_run`, `commands_run`, or
`conflicts` must be populated. `file_refs` alone only add metadata and do not
create a proposal. All `file_refs` must match the active `--subject` and
`--subject-head-sha`. Any conflict makes the mutation pack human-gated.

`runtime_assumptions` become runtime-only observations for OpenClaw. If
`task_lessons` is present, `tests_run` and `commands_run` stay as metadata; if
no explicit lesson is present, tests and commands synthesize task lesson
proposals.

## Workflow

```bash
topology writeback \
  --root "$KNOWLEDGE_TOPOLOGY_ROOT" \
  --summary-json ".tmp/<summary>.json" \
  --subject "<subject-repo-id>" \
  --subject-head-sha "<subject-head-sha>" \
  --base-canonical-rev "<pack-canonical-rev>" \
  --current-canonical-rev "<current-topology-head-sha>" \
  --current-subject-head-sha "<current-subject-head-sha>"
```

Then verify:

```bash
topology lint --root "$KNOWLEDGE_TOPOLOGY_ROOT"
```

If writeback rejects stale preconditions, re-compose or re-reconcile instead of
editing proposal metadata by hand.

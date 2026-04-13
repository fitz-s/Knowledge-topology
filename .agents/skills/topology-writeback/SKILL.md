---
name: topology-writeback
description: Emit Knowledge Topology writeback proposals after a coding task.
---

# Topology Writeback

Use this skill at the end of a coding task that used or changed topology-relevant
knowledge.

## Contract

- Write mutation proposals, not canonical records.
- Include only decisions and invariants that are grounded in the session.
- Keep generated writeback deltas local until reviewed.
- Run lint after creating the writeback proposal.

## Summary JSON

Create a local summary JSON under `.tmp/` with:

```json
{
  "source_id": "src_...",
  "digest_id": "dg_...",
  "decisions": ["..."],
  "invariants": ["..."]
}
```

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

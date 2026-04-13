# P0 Contract Reality Pass

## Mini-Ralplan

P0 converts the Knowledge Topology philosophy into construction-ready contracts
before worker code begins. It does not implement runtime workers.

### Principles

- Add new governance files only when an existing root contract would become too
  broad or ambiguous.
- Every governance artifact must have an executable fixture or test target.
- Public-repo safety, Git concurrency, untrusted input, deterministic compile,
  and human-gate behavior must be explicit before Batch 1.
- Keep root `AGENTS.md` and `CLAUDE.md` thin.

### Decision Drivers

- Avoid worker code inventing its own protocol.
- Avoid committing generated/runtime or unsafe third-party content.
- Make future package-level `$ralplan` handoffs concrete enough for `$ralph`
  or `$team`.

### Options

Option A: Fold all P0 details into existing root contracts.

- Pros: fewer files.
- Cons: `POLICY.md`, `SCHEMA.md`, `STORAGE.md`, and `AUDIENCE.md` become too
  dense and hard to test.

Option B: Add focused P0 contracts for Git, security, raw policy, escalations,
schema evolution, and compile behavior.

- Pros: each contract can have narrow fixtures and tests.
- Cons: more files to keep in sync.

Option C: Start Batch 1 and backfill P0 when problems appear.

- Pros: faster code feedback.
- Cons: high risk of incompatible first implementations.

Chosen: Option B, with each new artifact backed by fixture validation.

## Reality Check

- Git: multiple agents can create local changes; only a documented protocol can
  prevent stale pushes and canonical-write conflicts.
- Public repo: source ingestion must not assume raw full text or binaries are
  safe to track.
- Untrusted input: fetch/digest content can carry malicious instructions or
  unsafe paths; workers need explicit deny rules.
- Compile: builder packs must be deterministic and bounded before they guide
  implementation.
- Human gates: escalation prompts must be structured cards, not ad hoc chat.
- Schema: records need versions and migration rules before fixtures accumulate.

## Construction Table

| Small Package | Purpose | Files / Surfaces | Fixtures / Tests | Acceptance Criteria | Stop Condition |
| --- | --- | --- | --- | --- | --- |
| P0.1 Git protocol | Define commit, branch, pull/rebase, push, conflict, and single apply-writer rules | `GIT_PROTOCOL.md`, `POLICY.md` | `tests/fixtures/p0/git_protocol/stale_apply_conflict.json`, `tests/test_p0_contracts.py` | Implementers know who may commit what and how stale pushes recover | Cannot define conflict recovery without destructive steps |
| P0.2 Threat model | Enumerate prompt injection, symlink, path traversal, malicious markdown, large-file DoS, secret leakage, poisoned artifacts | `SECURITY.md`, `POLICY.md` | `tests/fixtures/p0/security/threat_denials.json`, `tests/test_p0_contracts.py` | Untrusted source workers cannot gain canonical write paths | Any threat requires runtime sandbox behavior not yet possible |
| P0.3 Public raw policy | Define source-type defaults for `public_text`, `excerpt_only`, `local_blob` | `RAW_POLICY.md`, `STORAGE.md`, `SCHEMA.md` | `tests/fixtures/p0/raw_policy/source_mode_matrix.json`, `tests/test_p0_contracts.py` | Unsafe third-party content defaults away from tracked full text | Cannot express redistribution rule testably |
| P0.4 Escalations | Define escalation card schema, default recommendation, evidence bundle, timeout/retry | `ESCALATIONS.md`, `POLICY.md`, `SCHEMA.md` | `tests/fixtures/p0/escalations/escalation_card.json`, `tests/test_p0_contracts.py` | Human gates produce structured cards, not free-text prompts | Human gate class lacks default safe action |
| P0.5 Schema evolution | Define schema versioning, migrations, compatibility fixtures | `SCHEMA_EVOLUTION.md`, `SCHEMA.md` | `tests/fixtures/p0/schema_evolution/node_v1.json`, `tests/test_p0_contracts.py` | Schema changes cannot silently break old records | Migration cannot be tested on fixture data |
| P0.6 Compile policy | Define edge whitelist, sensitivity filters, authority ordering, traversal bounds | `COMPILE.md`, `AUDIENCE.md` | `tests/fixtures/p0/compile/traversal_case.json`, `tests/test_p0_contracts.py` | Builder packs are deterministic and bounded | Traversal rule requires model judgment |

## Verification

Run:

```bash
python3 -m unittest discover -s tests
```

P0 is complete when this test passes and no worker implementation is added.

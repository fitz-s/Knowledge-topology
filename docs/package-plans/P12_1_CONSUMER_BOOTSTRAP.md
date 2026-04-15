# P12.1 Package Plan: Consumer Bootstrap

## Package Ralplan

P12.1 makes external subject repositories self-wiring consumers of Knowledge
Topology. A subject repo should get local scripts, skills, config snippets, and
context resolution from one command, without copying canonical topology content
or requiring the operator to manually compute revisions.

P12.1 does not add an MCP server and does not implement new topology business
logic in generated files. Generated files are wrappers and protocol snippets
over the existing CLI/library.

## Reality Check

- `topology subject ...` exists and can add/refresh/resolve subject records.
- `topology compose builder`, `topology writeback`, and `topology openclaw ...`
  exist, but external repos do not get generated wrapper scripts.
- Topology consume/writeback skills exist inside the topology repo for Codex and
  Claude, but bootstrap does not install them into subject repos.
- Existing `.claude/settings.json` must be merged safely, never overwritten.
- OpenClaw integration is documented but not packaged into workspace-local
  skills or QMD path snippets.

## Construction Table

| Small Package | Purpose | Files / Surfaces | Tests | Acceptance | Stop Condition |
| --- | --- | --- | --- | --- | --- |
| P12.1a Context resolver | Compute topology/subject context from roots | new `workers/bootstrap.py`, `cli.py` | temp git repo tests | `topology resolve-context --json` returns canonical rev, subject repo id, subject head, paths, dirty flags | Context requires manual revisions |
| P12.1b Consumer manifest/wrappers | Generate local config and scripts | subject `.knowledge-topology.json`, `.knowledge-topology-manifest.json`, `scripts/topology/*.sh` | fixture subject repo tests | wrappers compute current context and call topology CLI | Generated scripts copy topology content or hard-code stale revisions |
| P12.1c Codex/Claude skills | Install minimal local skills | `.agents/skills/*`, `.claude/skills/*`, `.claude/settings.json`, `.claude/hooks/*` | existing config merge tests | skills and hook wrappers are generated without destructive overwrite | Existing Claude/Codex config is clobbered |
| P12.1d OpenClaw bundle snippet | Generate workspace-local OpenClaw protocol files | OpenClaw workspace `.openclaw/topology/*` or equivalent | temp workspace tests | QMD paths only reference `projections/openclaw/*`; env/launcher resolves context | OpenClaw snippet grants canonical write access |
| P12.1e Remove/doctor | Roll back and diagnose generated wiring | `bootstrap remove`, `doctor consumer` | mutation-safe remove tests | remove deletes only manifest-recorded unchanged files; doctor reports missing/stale/modified generated files | remove deletes user-owned files |

## Gemini Requirement

Required before unfreeze: yes.

Reason: P12.1 changes consumer repo wiring, Claude hook/config behavior, and
OpenClaw install surfaces. It touches integration and trust-boundary behavior.
If Gemini is unavailable, unfreeze requires explicit user waiver.

## CLI Contract

Commands:

```bash
topology bootstrap codex --topology-root ... --subject-path ...
topology bootstrap claude --topology-root ... --subject-path ...
topology bootstrap openclaw --topology-root ... --subject-path ... --workspace ... --project-id ...
topology bootstrap remove --subject-path ...
topology resolve-context --topology-root ... --subject-path ... --json
topology doctor consumer --topology-root ... --subject-path ...
```

Rules:

- `--topology-root` points to this topology repo.
- `--subject-path` points to an external git repo.
- Bootstrap may add/refresh `SUBJECTS.yaml` in the topology root.
- Bootstrap writes only consumer-local wiring and manifests.
- Generated wrappers must compute current `canonical_rev` and
  `subject_head_sha` at invocation time.
- Bootstrap must not write `canonical/`, `digests/`, topology projections, or
  whole topology content into the subject repo.
- Remove is manifest-based and deletes only unchanged generated files.

## Acceptance Tests

- `resolve-context --json` works for a temp external git subject and returns
  fresh topology/subject revisions.
- `bootstrap codex` writes `.knowledge-topology.json`, manifest,
  `scripts/topology/compose_builder.sh`, `writeback.sh`, `resolve_context.sh`,
  and Codex skills.
- `bootstrap claude` installs Claude skills and merges existing
  `.claude/settings.json` without deleting unrelated keys.
- Generated wrapper scripts are executable and contain no hard-coded stale
  revision values.
- `bootstrap openclaw` writes workspace-local env/skills/QMD path snippets that
  only reference `projections/openclaw/file-index.json`,
  `runtime-pack.json`, `runtime-pack.md`, `memory-prompt.md`, and
  `wiki-mirror/`.
- `doctor consumer` reports missing generated files, modified generated files,
  missing config, and stale subject head.
- `bootstrap remove` removes only manifest-recorded unchanged files and
  preserves modified files.

## Stop Conditions

- Bootstrap copies the full topology or canonical data into a consumer repo.
- Bootstrap overwrites user config without merge/preserve behavior.
- Generated files contain fixed stale revision values instead of resolving at
  runtime.
- OpenClaw bootstrap allows writes to canonical/projection surfaces.

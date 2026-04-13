# Codex Topology Routing

P8 intentionally keeps Codex integration advisory.

Use the repo-scoped skills under `.agents/skills/`:

- `topology-consume`
- `topology-writeback`

Do not register a topology MCP server in `.codex/config.toml` until
`src/knowledge_topology/adapters/mcp_server.py` exists and has tests. Codex
must consume task-scoped builder packs and write writeback proposals; it must
not read the whole topology or edit `canonical/` directly.

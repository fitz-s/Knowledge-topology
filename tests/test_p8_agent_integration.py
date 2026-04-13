import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from knowledge_topology.workers.agent_guard import guard_claude_pre_tool_use
from knowledge_topology.workers.init import init_topology


def event(tool_name, file_path, *, cwd=None, **extra):
    payload = {"tool_name": tool_name, "tool_input": {"file_path": file_path, **extra}}
    if cwd is not None:
        payload["cwd"] = str(cwd)
    return json.dumps(payload)


class P8AgentIntegrationTests(unittest.TestCase):
    def test_guard_denies_direct_canonical_writes_for_file_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            cases = [
                event("Write", "canonical/nodes/example.md"),
                event("Edit", "canonical/registry/nodes.jsonl"),
                event("MultiEdit", "canonical", edits=[{"old_string": "a", "new_string": "b"}]),
            ]
            for payload in cases:
                result = guard_claude_pre_tool_use(root, payload)
                self.assertFalse(result.allowed)
                self.assertIn("canonical", result.reason)

    def test_guard_denies_case_variant_canonical_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            cases = [
                event("Write", "Canonical/nodes/case_bypass.md"),
                event("Write", "CANONICAL/registry/nodes.jsonl"),
                event("Edit", str(root / "Canonical/registry/nodes.jsonl")),
            ]
            for payload in cases:
                result = guard_claude_pre_tool_use(root, payload)
                self.assertFalse(result.allowed)
                self.assertIn("canonical", result.reason)

    def test_guard_allows_mutation_and_writeback_surfaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            cases = [
                event("Write", "mutations/pending/mut_01KP43CMB1DRD5B8ZR1N3Q7X61.json"),
                event("Edit", ".tmp/writeback/mut_01KP43CMB1DRD5B8ZR1N3Q7X61/relationship-tests.yaml"),
                event("Write", "docs/note.md"),
            ]
            for payload in cases:
                self.assertTrue(guard_claude_pre_tool_use(root, payload).allowed)

    def test_guard_fails_closed_for_malformed_hook_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            cases = [
                "{bad json",
                json.dumps([]),
                json.dumps({"tool_input": {"file_path": "docs/x.md"}}),
                json.dumps({"tool_name": "Write", "tool_input": {}}),
                json.dumps({"tool_name": "Write", "tool_input": {"file_path": ""}}),
                json.dumps({"tool_name": "MultiEdit", "tool_input": {"file_path": "docs/x.md", "edits": "bad"}}),
                json.dumps({"tool_name": "MultiEdit", "tool_input": {"file_path": "docs/x.md", "edits": ["bad"]}}),
            ]
            for payload in cases:
                self.assertFalse(guard_claude_pre_tool_use(root, payload).allowed)

    def test_guard_path_normalization_denies_escapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "topology"
            outside = Path(tmp) / "outside"
            init_topology(root)
            outside.mkdir()
            self.assertFalse(guard_claude_pre_tool_use(root, event("Write", "../outside/file.md")).allowed)
            self.assertFalse(guard_claude_pre_tool_use(root, event("Write", str(outside / "file.md"))).allowed)
            self.assertFalse(guard_claude_pre_tool_use(root, event("Write", "docs/x.md", cwd=outside)).allowed)
            try:
                (root / "escape").symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("symlinks unavailable")
            self.assertFalse(guard_claude_pre_tool_use(root, event("Write", "escape/file.md")).allowed)

    def test_guard_allows_non_file_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            result = guard_claude_pre_tool_use(root, json.dumps({"tool_name": "Bash", "tool_input": {"command": "echo ok"}}))
            self.assertTrue(result.allowed)

    def test_agent_guard_cli_exit_codes(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        deny = subprocess.run(
            [sys.executable, "-m", "knowledge_topology.cli", "agent-guard", "claude-pre-tool-use", "--root", str(ROOT)],
            input=event("Write", "canonical/nodes/example.md"),
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(deny.returncode, 2)
        self.assertIn("canonical", deny.stderr)
        allow = subprocess.run(
            [sys.executable, "-m", "knowledge_topology.cli", "agent-guard", "claude-pre-tool-use", "--root", str(ROOT)],
            input=event("Write", "docs/example.md"),
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(allow.returncode, 0, allow.stderr)

    def test_claude_settings_and_hook_shell_contract(self):
        settings = json.loads((ROOT / ".claude/settings.json").read_text(encoding="utf-8"))
        self.assertNotIn("SessionStart", settings.get("hooks", {}))
        pre_tool_use = settings["hooks"]["PreToolUse"][0]
        self.assertEqual(pre_tool_use["matcher"], "Write|Edit|MultiEdit")
        command = pre_tool_use["hooks"][0]["command"]
        self.assertIn("$CLAUDE_PROJECT_DIR/.claude/hooks/topology-pre-tool-use.sh", command)
        hook = ROOT / ".claude/hooks/topology-pre-tool-use.sh"
        self.assertTrue(os.access(hook, os.X_OK))
        env = os.environ.copy()
        env["CLAUDE_PROJECT_DIR"] = str(ROOT)
        deny = subprocess.run(
            [str(hook)],
            input=event("Write", "canonical/nodes/example.md"),
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(deny.returncode, 2)
        self.assertIn("canonical", deny.stderr)

    def test_skills_are_thin_routing_surfaces(self):
        skill_paths = [
            ROOT / ".agents/skills/topology-consume/SKILL.md",
            ROOT / ".agents/skills/topology-writeback/SKILL.md",
            ROOT / ".claude/skills/topology-consume/SKILL.md",
            ROOT / ".claude/skills/topology-writeback/SKILL.md",
        ]
        for skill_path in skill_paths:
            text = skill_path.read_text(encoding="utf-8")
            self.assertIn("topology", text)
            self.assertNotIn("topology apply", text)
            self.assertNotIn("whole topology dump", text)
        self.assertIn("topology compose builder", skill_paths[0].read_text(encoding="utf-8"))
        self.assertIn("topology writeback", skill_paths[1].read_text(encoding="utf-8"))
        self.assertIn("topology lint", skill_paths[1].read_text(encoding="utf-8"))

    def test_p8_does_not_register_fake_codex_mcp(self):
        self.assertFalse((ROOT / ".codex/config.toml").exists())
        readme = (ROOT / ".codex/README.md").read_text(encoding="utf-8")
        self.assertIn("advisory", readme)
        self.assertIn("Do not register a topology MCP server", readme)


if __name__ == "__main__":
    unittest.main()

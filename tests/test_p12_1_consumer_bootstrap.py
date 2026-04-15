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

from knowledge_topology.workers.init import init_topology


def init_git(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "README.md").write_text("repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, stdout=subprocess.PIPE, text=True, check=True).stdout.strip()


def cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    return subprocess.run(
        [sys.executable, "-m", "knowledge_topology.cli", *args],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class P12ConsumerBootstrapTests(unittest.TestCase):
    def make_roots(self) -> tuple[tempfile.TemporaryDirectory, Path, Path]:
        tmp = tempfile.TemporaryDirectory()
        base = Path(tmp.name)
        topology = base / "topology"
        subject = base / "subject"
        init_topology(topology)
        (topology / "src").symlink_to(SRC, target_is_directory=True)
        init_git(topology)
        init_git(subject)
        return tmp, topology, subject

    def make_roots_with_topology_name(self, name: str) -> tuple[tempfile.TemporaryDirectory, Path, Path]:
        tmp = tempfile.TemporaryDirectory()
        base = Path(tmp.name)
        topology = base / name
        subject = base / "subject"
        init_topology(topology)
        (topology / "src").symlink_to(SRC, target_is_directory=True)
        init_git(topology)
        init_git(subject)
        return tmp, topology, subject

    def test_resolve_context_requires_bootstrap_then_reports_current_revisions(self):
        tmp, topology, subject = self.make_roots()
        with tmp:
            missing = cli("resolve-context", "--topology-root", str(topology), "--subject-path", str(subject), "--json")
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("run topology bootstrap first", missing.stderr)
            bootstrap = cli("bootstrap", "codex", "--topology-root", str(topology), "--subject-path", str(subject))
            self.assertEqual(bootstrap.returncode, 0, bootstrap.stderr)
            subprocess.run(["git", "add", "SUBJECTS.yaml"], cwd=topology, check=True)
            subprocess.run(["git", "commit", "-m", "register subject"], cwd=topology, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            result = cli("resolve-context", "--topology-root", str(topology), "--subject-path", str(subject), "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["topology_root"], str(topology.resolve()))
            self.assertEqual(payload["subject_path"], str(subject.resolve()))
            self.assertTrue(payload["subject_repo_id"].startswith("repo_subject"))
            self.assertEqual(payload["subject_head_sha"], subprocess.run(["git", "rev-parse", "HEAD"], cwd=subject, stdout=subprocess.PIPE, text=True, check=True).stdout.strip())
            subjects = (topology / "SUBJECTS.yaml").read_text(encoding="utf-8")
            self.assertIn(payload["subject_repo_id"], subjects)
            self.assertEqual(subprocess.run(["git", "status", "--porcelain"], cwd=topology, stdout=subprocess.PIPE, text=True, check=True).stdout.strip(), "")

    def test_bootstrap_codex_writes_manifest_scripts_and_skills(self):
        tmp, topology, subject = self.make_roots()
        with tmp:
            result = cli("bootstrap", "codex", "--topology-root", str(topology), "--subject-path", str(subject))
            self.assertEqual(result.returncode, 0, result.stderr)
            for relative in [
                ".knowledge-topology.json",
                ".knowledge-topology-manifest.json",
                "scripts/topology/compose_builder.sh",
                "scripts/topology/writeback.sh",
                "scripts/topology/resolve_context.sh",
                ".agents/skills/topology-consume/SKILL.md",
                ".agents/skills/topology-writeback/SKILL.md",
            ]:
                self.assertTrue((subject / relative).exists(), relative)
            self.assertTrue(os.access(subject / "scripts/topology/compose_builder.sh", os.X_OK))
            config = json.loads((subject / ".knowledge-topology.json").read_text(encoding="utf-8"))
            self.assertEqual(config["topology_root"], str(topology.resolve()))
            self.assertNotIn("canonical/", json.dumps(config))
            script = (subject / "scripts/topology/compose_builder.sh").read_text(encoding="utf-8")
            self.assertIn("resolve-context", script)
            self.assertIn("PYTHONPATH", script)
            self.assertNotIn(config["canonical_rev"], script)
            self.assertFalse((subject / "canonical").exists())
            env = os.environ.copy()
            env.pop("PYTHONPATH", None)
            wrapper = subprocess.run(
                [str(subject / "scripts/topology/resolve_context.sh")],
                cwd=subject,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(wrapper.returncode, 0, wrapper.stderr)
            self.assertEqual(json.loads(wrapper.stdout)["subject_repo_id"], config["subject_repo_id"])

    def test_generated_wrappers_shell_quote_embedded_paths(self):
        tmp, topology, subject = self.make_roots_with_topology_name("topology_$(touch PWNED)")
        with tmp:
            pwned = Path(tmp.name) / "PWNED"
            result = cli("bootstrap", "codex", "--topology-root", str(topology), "--subject-path", str(subject))
            self.assertEqual(result.returncode, 0, result.stderr)
            env = os.environ.copy()
            env.pop("PYTHONPATH", None)
            wrapper = subprocess.run(
                [str(subject / "scripts/topology/resolve_context.sh")],
                cwd=subject,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(wrapper.returncode, 0, wrapper.stderr)
            self.assertFalse(pwned.exists())

    def test_bootstrap_claude_merges_existing_settings_without_clobber(self):
        tmp, topology, subject = self.make_roots()
        with tmp:
            settings = subject / ".claude/settings.json"
            settings.parent.mkdir(parents=True)
            settings.write_text(json.dumps({"custom": {"keep": True}, "hooks": {"PostToolUse": []}}, indent=2), encoding="utf-8")
            result = cli("bootstrap", "claude", "--topology-root", str(topology), "--subject-path", str(subject))
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(settings.read_text(encoding="utf-8"))
            self.assertEqual(payload["custom"], {"keep": True})
            self.assertIn("PostToolUse", payload["hooks"])
            self.assertIn("PreToolUse", payload["hooks"])
            self.assertTrue((subject / ".claude/hooks/topology-pre-tool-use.sh").exists())
            self.assertTrue((subject / ".claude/skills/topology-consume/SKILL.md").exists())

    def test_bootstrap_openclaw_writes_workspace_snippets_with_limited_qmd_scope(self):
        tmp, topology, subject = self.make_roots()
        with tmp:
            workspace = Path(tmp.name) / "openclaw-workspace"
            result = cli(
                "bootstrap",
                "openclaw",
                "--topology-root",
                str(topology),
                "--subject-path",
                str(subject),
                "--workspace",
                str(workspace),
                "--project-id",
                "openclaw_project",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            qmd = (workspace / ".openclaw/topology/qmd-extra-paths.txt").read_text(encoding="utf-8")
            self.assertIn("projections/openclaw/runtime-pack.json", qmd)
            self.assertIn("projections/openclaw/file-index.json", qmd)
            self.assertNotIn("/raw/", qmd)
            self.assertNotIn("/canonical/", qmd)
            self.assertNotIn("/mutations/", qmd)
            env_text = (workspace / ".openclaw/topology/topology.env").read_text(encoding="utf-8")
            self.assertIn(f"SUBJECT_PATH={subject.resolve()}", env_text)
            launcher = (workspace / ".openclaw/topology/compose-openclaw.sh").read_text(encoding="utf-8")
            self.assertIn(str(subject.resolve()), launcher)
            self.assertTrue((workspace / ".openclaw/topology/skills/runtime-consume.md").exists())
            self.assertTrue((workspace / ".openclaw/topology/compose-openclaw.sh").exists())

            injected = cli(
                "bootstrap",
                "openclaw",
                "--topology-root",
                str(topology),
                "--subject-path",
                str(subject),
                "--workspace",
                str(workspace / "bad"),
                "--project-id",
                "safe_project\nMALICIOUS=1",
            )
            self.assertNotEqual(injected.returncode, 0)
            self.assertIn("project_id must be a safe token", injected.stderr)

    def test_doctor_consumer_reports_modified_missing_and_stale_wiring(self):
        tmp, topology, subject = self.make_roots()
        with tmp:
            result = cli("bootstrap", "codex", "--topology-root", str(topology), "--subject-path", str(subject))
            self.assertEqual(result.returncode, 0, result.stderr)
            healthy = cli("doctor", "consumer", "--topology-root", str(topology), "--subject-path", str(subject))
            self.assertEqual(healthy.returncode, 0, healthy.stderr)
            (subject / "scripts/topology/compose_builder.sh").write_text("changed\n", encoding="utf-8")
            modified = cli("doctor", "consumer", "--topology-root", str(topology), "--subject-path", str(subject))
            self.assertNotEqual(modified.returncode, 0)
            self.assertIn("modified", modified.stdout)
            (subject / ".knowledge-topology.json").unlink()
            missing = cli("doctor", "consumer", "--topology-root", str(topology), "--subject-path", str(subject))
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("missing", missing.stdout)

            subprocess.run(["git", "commit", "--allow-empty", "-m", "advance topology"], cwd=topology, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            stale_topology = cli("doctor", "consumer", "--topology-root", str(topology), "--subject-path", str(subject))
            self.assertNotEqual(stale_topology.returncode, 0)
            self.assertIn("canonical_rev is stale", stale_topology.stdout)

            subprocess.run(["git", "commit", "--allow-empty", "-m", "advance"], cwd=subject, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            stale = cli("doctor", "consumer", "--topology-root", str(topology), "--subject-path", str(subject))
            self.assertNotEqual(stale.returncode, 0)
            self.assertIn("stale", stale.stdout)

    def test_bootstrap_remove_preserves_modified_generated_files(self):
        tmp, topology, subject = self.make_roots()
        with tmp:
            result = cli("bootstrap", "codex", "--topology-root", str(topology), "--subject-path", str(subject))
            self.assertEqual(result.returncode, 0, result.stderr)
            claude = cli("bootstrap", "claude", "--topology-root", str(topology), "--subject-path", str(subject))
            self.assertEqual(claude.returncode, 0, claude.stderr)
            changed = subject / "scripts/topology/compose_builder.sh"
            changed.write_text("user modified\n", encoding="utf-8")
            removed = cli("bootstrap", "remove", "--subject-path", str(subject))
            self.assertEqual(removed.returncode, 0, removed.stderr)
            self.assertTrue(changed.exists())
            self.assertIn("modified generated file preserved", removed.stdout)
            self.assertFalse((subject / ".knowledge-topology-manifest.json").exists())
            self.assertFalse((subject / ".agents/skills/topology-consume/SKILL.md").exists())
            self.assertFalse((subject / ".claude/skills/topology-consume/SKILL.md").exists())


if __name__ == "__main__":
    unittest.main()

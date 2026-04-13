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

from knowledge_topology.ids import new_id
from knowledge_topology.workers.doctor import stale_anchors
from knowledge_topology.workers.init import init_topology
from knowledge_topology.workers.lint import run_lints
from knowledge_topology.workers.writeback import writeback_session


class P7WritebackLintDoctorTests(unittest.TestCase):
    def test_lint_detects_projection_leakage_and_missing_antibody(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            pack = root / "projections/tasks/task_bad"
            pack.mkdir(parents=True)
            (pack / "metadata.json").write_text("{}", encoding="utf-8")
            (pack / "constraints.json").write_text(json.dumps({"count": 1, "invariants": [{"id": new_id("nd")}]}) + "\n", encoding="utf-8")
            (pack / "relationship-tests.yaml").write_text("[]\n", encoding="utf-8")
            result = run_lints(root)
            self.assertFalse(result.ok)
            joined = "\n".join(result.messages)
            self.assertIn("generated projection file", joined)
            self.assertIn("missing relationship tests", joined)

    def test_lint_detects_malformed_relationship_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            pack = root / "projections/tasks/task_rel"
            pack.mkdir(parents=True)
            (pack / "relationship-tests.yaml").write_text("- id: bad\n", encoding="utf-8")
            result = run_lints(root)
            self.assertFalse(result.ok)
            joined = "\n".join(result.messages)
            self.assertIn("missing schema_version", joined)
            self.assertIn("missing reltest_ id", joined)

    def test_doctor_reports_stale_file_refs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            (root / "canonical/registry/file_refs.jsonl").write_text(
                json.dumps({
                    "repo_id": "repo_knowledge_topology",
                    "commit_sha": "old",
                    "path": "src/example.py",
                }) + "\n",
                encoding="utf-8",
            )
            result = stale_anchors(root, subject_repo_id="repo_knowledge_topology", subject_head_sha="new")
            self.assertFalse(result.ok)
            self.assertIn("stale anchor old != new", result.messages[0])

    def test_writeback_creates_pending_mutation_and_reltest_delta_without_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            summary = root / ".tmp/summary.json"
            summary.parent.mkdir(exist_ok=True)
            source_id = new_id("src")
            digest_id = new_id("dg")
            summary.write_text(json.dumps({
                "source_id": source_id,
                "digest_id": digest_id,
                "decisions": ["Use deterministic writeback"],
                "invariants": ["Writeback must not write canonical"],
            }), encoding="utf-8")
            # Evidence placeholders for MutationPack validation are intentionally not required at writeback proposal time.
            mutation, reltest = writeback_session(
                root,
                summary_path=summary,
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                base_canonical_rev="rev_current",
            )
            self.assertEqual(mutation.parent.name, "pending")
            self.assertTrue(reltest.exists())
            self.assertIn("reltest_", reltest.read_text(encoding="utf-8"))
            self.assertEqual((root / "canonical/registry/nodes.jsonl").read_text(encoding="utf-8"), "")

    def test_cli_lint_doctor_writeback_smoke(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            env = os.environ.copy()
            env["PYTHONPATH"] = str(SRC)
            lint_ok = subprocess.run([sys.executable, "-m", "knowledge_topology.cli", "lint", "--root", tmp], cwd=ROOT, env=env, text=True)
            self.assertEqual(lint_ok.returncode, 0)
            doctor_ok = subprocess.run(
                [sys.executable, "-m", "knowledge_topology.cli", "doctor", "stale-anchors", "--root", tmp, "--subject", "repo_knowledge_topology", "--subject-head-sha", "abc123"],
                cwd=ROOT,
                env=env,
                text=True,
            )
            self.assertEqual(doctor_ok.returncode, 0)
            summary = root / ".tmp/summary.json"
            summary.parent.mkdir(exist_ok=True)
            summary.write_text(json.dumps({"source_id": new_id("src"), "digest_id": new_id("dg"), "decisions": ["D"], "invariants": []}), encoding="utf-8")
            writeback = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "knowledge_topology.cli",
                    "writeback",
                    "--root",
                    tmp,
                    "--summary-json",
                    str(summary),
                    "--subject",
                    "repo_knowledge_topology",
                    "--subject-head-sha",
                    "abc123",
                    "--base-canonical-rev",
                    "rev_current",
                ],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(writeback.returncode, 0, writeback.stderr)
            self.assertIn("created writeback mutation pack:", writeback.stdout)


if __name__ == "__main__":
    unittest.main()

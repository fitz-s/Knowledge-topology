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
from knowledge_topology.storage.transaction import atomic_write_text
from knowledge_topology.subjects import add_subject, refresh_subject
from knowledge_topology.workers.evaluation import run_evaluation
from knowledge_topology.workers.init import init_topology


def init_git(path: Path) -> str:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
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


class P12EvaluationBenchmarkTests(unittest.TestCase):
    def make_topology(self) -> tuple[tempfile.TemporaryDirectory, Path, str]:
        tmp = tempfile.TemporaryDirectory()
        base = Path(tmp.name)
        root = base / "topology"
        subject = base / "subject"
        subject.mkdir(parents=True)
        (subject / "README.md").write_text("subject\n", encoding="utf-8")
        init_git(subject)
        init_topology(root)
        add_subject(
            root,
            subject_repo_id="repo_subject",
            name="Subject",
            kind="git",
            location=str(subject.resolve()),
            default_branch="main",
            visibility="public",
            sensitivity="internal",
            now="2026-04-15T00:00:00Z",
        )
        refresh_subject(root, "repo_subject", now="2026-04-15T00:00:01Z")
        head = init_git(root)
        return tmp, root, head

    def test_evaluation_report_measures_artifacts_without_path_leaks(self):
        tmp, root, head = self.make_topology()
        with tmp:
            task = root / "projections/tasks/task_eval"
            task.mkdir(parents=True)
            (task / "metadata.json").write_text(json.dumps({
                "task_id": "task_eval",
                "canonical_rev": head,
                "subject_repo_id": "repo_subject",
                "subject_head_sha": head,
            }), encoding="utf-8")
            (task / "brief.md").write_text("brief", encoding="utf-8")
            source_id = new_id("src")
            packet_dir = root / "raw/packets" / source_id
            packet_dir.mkdir(parents=True)
            atomic_write_text(packet_dir / "packet.json", json.dumps({
                "id": source_id,
                "source_type": "video_platform",
                "artifacts": [{"kind": "video_platform_locator", "requires_operator_capture": True}],
            }))
            mutation = {
                "id": new_id("mut"),
                "proposal_type": "session_writeback",
                "base_canonical_rev": "old",
                "subject_repo_id": "repo_subject",
                "subject_head_sha": "old",
                "changes": [],
                "metadata": {"conflicts": [{"kind": "test"}]},
            }
            atomic_write_text(root / "mutations/pending" / f"{mutation['id']}.json", json.dumps(mutation))
            applied = {
                **mutation,
                "id": new_id("mut"),
                "base_canonical_rev": head,
                "subject_head_sha": head,
                "metadata": {"openclaw_live_job_id": "job_openclaw_applied"},
            }
            rejected = {
                **mutation,
                "id": new_id("mut"),
                "base_canonical_rev": head,
                "subject_head_sha": head,
                "metadata": {"openclaw_live_job_id": "job_openclaw_rejected"},
            }
            atomic_write_text(root / "mutations/applied" / f"{applied['id']}.json", json.dumps(applied))
            atomic_write_text(root / "mutations/rejected" / f"{rejected['id']}.json", json.dumps(rejected))
            result = run_evaluation(root, subject_repo_id="repo_subject")
            metrics = result.payload["metrics"]
            self.assertEqual(metrics["builder_packs"]["count"], 1)
            self.assertEqual(metrics["mutations"]["pending_count"], 1)
            self.assertEqual(metrics["mutations"]["stale_precondition_count"], 1)
            self.assertEqual(metrics["mutations"]["stale_precondition_field_failures"], 2)
            self.assertLessEqual(metrics["mutations"]["stale_precondition_rate"], 1.0)
            self.assertLessEqual(metrics["mutations"]["conflict_rate"], 1.0)
            self.assertEqual(metrics["video"]["video_platform_sources"], 1)
            self.assertEqual(metrics["video"]["manual_intervention_count"], 1)
            self.assertEqual(metrics["openclaw"]["runtime_decided_count"], 2)
            self.assertEqual(metrics["openclaw"]["runtime_proposal_acceptance_rate"], 0.5)
            self.assertEqual(metrics["builder_task_success_rate"]["status"], "not_measured")
            report_text = result.report_path.read_text(encoding="utf-8")
            self.assertIn("ops/reports/tmp/evaluations", result.payload["report_path"])
            self.assertNotIn(str(root), report_text)
            self.assertNotIn(str(root.resolve()), report_text)

    def test_eval_cli_smoke(self):
        tmp, root, _head = self.make_topology()
        with tmp:
            result = cli("eval", "run", "--root", str(root), "--subject", "repo_subject")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("metrics", payload)
            self.assertEqual(payload["metrics"]["context_fragment_relevance_score"]["status"], "not_measured")


if __name__ == "__main__":
    unittest.main()

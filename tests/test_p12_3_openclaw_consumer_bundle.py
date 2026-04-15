import json
import os
import subprocess
import sys
import tempfile
import time
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


class P12OpenClawConsumerBundleTests(unittest.TestCase):
    def make_roots(self) -> tuple[tempfile.TemporaryDirectory, Path, Path, Path]:
        tmp = tempfile.TemporaryDirectory()
        base = Path(tmp.name) / "base with space"
        topology = base / "topology"
        subject = base / "subject"
        workspace = base / "openclaw"
        init_topology(topology)
        (topology / "src").symlink_to(SRC, target_is_directory=True)
        init_git(subject)
        init_git(topology)
        boot = cli(
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
        assert boot.returncode == 0, boot.stderr
        subprocess.run(["git", "add", "SUBJECTS.yaml"], cwd=topology, check=True)
        subprocess.run(["git", "commit", "-m", "register subject"], cwd=topology, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        boot = cli(
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
        assert boot.returncode == 0, boot.stderr
        return tmp, topology, subject, workspace

    def test_openclaw_bundle_writes_expected_scripts_skills_and_qmd_scope(self):
        tmp, topology, subject, workspace = self.make_roots()
        with tmp:
            for relative in [
                ".openclaw/topology/resolve-context.sh",
                ".openclaw/topology/compose-openclaw.sh",
                ".openclaw/topology/doctor-openclaw.sh",
                ".openclaw/topology/capture-source.sh",
                ".openclaw/topology/issue-lease.sh",
                ".openclaw/topology/lease.sh",
                ".openclaw/topology/run-writeback.sh",
                ".openclaw/topology/video-ingest.sh",
                ".openclaw/topology/video-status.sh",
                ".openclaw/topology/video-attach-artifact.sh",
                ".openclaw/topology/video-prepare-digest.sh",
                ".openclaw/topology/video-trace.sh",
            ]:
                path = workspace / relative
                self.assertTrue(path.exists(), relative)
                self.assertTrue(os.access(path, os.X_OK), relative)
            qmd = (workspace / ".openclaw/topology/qmd-extra-paths.txt").read_text(encoding="utf-8")
            allowed = [
                "projections/openclaw/file-index.json",
                "projections/openclaw/runtime-pack.json",
                "projections/openclaw/runtime-pack.md",
                "projections/openclaw/memory-prompt.md",
                "projections/openclaw/wiki-mirror/",
            ]
            for needle in allowed:
                self.assertIn(needle, qmd)
            for forbidden in ["/raw/", "/canonical/", "/mutations/", "/ops/"]:
                self.assertNotIn(forbidden, qmd)
            env_text = (workspace / ".openclaw/topology/topology.env").read_text(encoding="utf-8")
            self.assertIn("SUBJECT_PATH=", env_text)
            sourced_env = subprocess.run(
                [
                    "bash",
                    "-lc",
                    f"source {str(workspace / '.openclaw/topology/topology.env')!r}; printf '%s\\n' \"$KNOWLEDGE_TOPOLOGY_ROOT\" \"$SUBJECT_PATH\"",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(sourced_env.returncode, 0, sourced_env.stderr)
            self.assertEqual(sourced_env.stdout.splitlines(), [str(topology.resolve()), str(subject.resolve())])
            maintainer = (workspace / ".openclaw/topology/skills/topology-maintainer.md").read_text(encoding="utf-8")
            self.assertIn("Forbidden write surfaces", maintainer)
            self.assertIn("canonical/", maintainer)
            session = (workspace / ".openclaw/topology/skills/session-writeback.md").read_text(encoding="utf-8")
            self.assertIn("issue-lease.sh", session)
            self.assertIn("run-writeback.sh", session)
            self.assertIn("source_id", session)
            self.assertIn("digest_id", session)
            video_skill = (workspace / ".openclaw/topology/skills/video-source-intake.md").read_text(encoding="utf-8")
            self.assertIn("No `dg_` path means no digest", video_skill)
            self.assertIn("Page-visible title", video_skill)
            self.assertIn("Do not label page-visible text as transcript", video_skill)

    def test_openclaw_compose_doctor_and_capture_wrappers_run(self):
        tmp, topology, subject, workspace = self.make_roots()
        with tmp:
            compose = subprocess.run(
                [str(workspace / ".openclaw/topology/compose-openclaw.sh")],
                cwd=workspace,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(compose.returncode, 0, compose.stderr)
            self.assertTrue((topology / "projections/openclaw/runtime-pack.json").exists())
            doctor = subprocess.run(
                [str(workspace / ".openclaw/topology/doctor-openclaw.sh")],
                cwd=workspace,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(doctor.returncode, 0, doctor.stderr)
            summary = workspace / "summary.json"
            summary.write_text(json.dumps({"runtime_assumptions": [], "task_lessons": []}), encoding="utf-8")
            capture = subprocess.run(
                [str(workspace / ".openclaw/topology/capture-source.sh"), str(summary)],
                cwd=workspace,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(capture.returncode, 0, capture.stderr)
            self.assertIn("created OpenClaw runtime source packet", capture.stdout)
            self.assertFalse((workspace / "canonical").exists())

    def test_openclaw_video_ingest_wrapper_injects_resolved_context(self):
        tmp, topology, subject, workspace = self.make_roots()
        with tmp:
            ingest = subprocess.run(
                [
                    str(workspace / ".openclaw/topology/video-ingest.sh"),
                    "https://v.douyin.com/6l8q1jGwRl4/",
                    "--note",
                    "video note",
                ],
                cwd=workspace,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(ingest.returncode, 0, ingest.stderr)
            self.assertIn("created video source packet", ingest.stdout)
            packet = next((topology / "raw/packets").glob("src_*/packet.json"))
            payload = json.loads(packet.read_text(encoding="utf-8"))
            self.assertEqual(payload["source_type"], "video_platform")

    def test_openclaw_video_attach_wrapper_cannot_self_attest_deep_evidence(self):
        tmp, topology, subject, workspace = self.make_roots()
        with tmp:
            ingest = subprocess.run(
                [
                    str(workspace / ".openclaw/topology/video-ingest.sh"),
                    "https://v.douyin.com/6l8q1jGwRl4/",
                    "--note",
                    "video note",
                ],
                cwd=workspace,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(ingest.returncode, 0, ingest.stderr)
            source_id = json.loads(next((topology / "raw/packets").glob("src_*/packet.json")).read_text(encoding="utf-8"))["id"]
            transcript = workspace / "transcript.txt"
            transcript.write_text("operator words\n", encoding="utf-8")
            attach = subprocess.run(
                [
                    str(workspace / ".openclaw/topology/video-attach-artifact.sh"),
                    "--source-id",
                    source_id,
                    "--artifact-kind",
                    "transcript",
                    "--artifact-path",
                    str(transcript),
                    "--track-text",
                    "--evidence-attestation",
                    "operator_attested",
                ],
                cwd=workspace,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertNotEqual(attach.returncode, 0)
            self.assertIn("cannot create operator/provider-attested", attach.stderr)

    def test_openclaw_private_summary_rejected_before_packet_or_lease_writes(self):
        tmp, topology, subject, workspace = self.make_roots()
        with tmp:
            summary = workspace / "private-summary.json"
            summary.write_text(
                json.dumps({"runtime_assumptions": [{"statement": "/Users/test/.openclaw/session/token-secret"}]}),
                encoding="utf-8",
            )
            capture = subprocess.run(
                [str(workspace / ".openclaw/topology/capture-source.sh"), str(summary)],
                cwd=workspace,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertNotEqual(capture.returncode, 0)
            self.assertIn("private", capture.stderr)
            issue = subprocess.run(
                [str(workspace / ".openclaw/topology/issue-lease.sh"), str(summary)],
                cwd=workspace,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertNotEqual(issue.returncode, 0)
            self.assertIn("private", issue.stderr)
            self.assertEqual(list((topology / "raw/packets").glob("src_*")), [])
            self.assertEqual(list((topology / "ops/queue/digest/pending").glob("job_*.json")), [])
            self.assertEqual(list((topology / "ops/queue/writeback/pending").glob("job_*.json")), [])

    def test_openclaw_bundle_doctor_and_remove_support_workspace_manifest(self):
        tmp, topology, subject, workspace = self.make_roots()
        with tmp:
            doctor = cli(
                "doctor",
                "consumer",
                "--topology-root",
                str(topology),
                "--subject-path",
                str(subject),
                "--workspace",
                str(workspace),
            )
            self.assertEqual(doctor.returncode, 0, doctor.stderr)
            remove = cli(
                "bootstrap",
                "remove",
                "--subject-path",
                str(subject),
                "--workspace",
                str(workspace),
            )
            self.assertEqual(remove.returncode, 0, remove.stderr)
            self.assertFalse((workspace / ".knowledge-topology-manifest.json").exists())
            self.assertFalse((workspace / ".openclaw/topology/compose-openclaw.sh").exists())

    def test_openclaw_rebootstrap_does_not_dirty_clean_topology(self):
        tmp, topology, subject, workspace = self.make_roots()
        with tmp:
            self.assertEqual(subprocess.run(["git", "status", "--porcelain"], cwd=topology, text=True, stdout=subprocess.PIPE, check=True).stdout, "")
            time.sleep(1.1)
            boot = cli(
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
            self.assertEqual(boot.returncode, 0, boot.stderr)
            self.assertEqual(subprocess.run(["git", "status", "--porcelain"], cwd=topology, text=True, stdout=subprocess.PIPE, check=True).stdout, "")
            compose = subprocess.run(
                [str(workspace / ".openclaw/topology/compose-openclaw.sh")],
                cwd=workspace,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(compose.returncode, 0, compose.stderr)


if __name__ == "__main__":
    unittest.main()

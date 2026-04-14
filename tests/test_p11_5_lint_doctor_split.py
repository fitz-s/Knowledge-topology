import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from knowledge_topology.ids import new_id
from knowledge_topology.storage.spool import create_job, lease_next
from knowledge_topology.workers.compose_builder import write_builder_pack
from knowledge_topology.workers.compose_openclaw import write_openclaw_projection
from knowledge_topology.workers.doctor import doctor_canonical_parity, doctor_projections, doctor_public_safe, doctor_queues
from knowledge_topology.workers.init import init_topology
from knowledge_topology.workers.lint import run_repo_lints, run_runtime_lints


class P11LintDoctorSplitTests(unittest.TestCase):
    def seed_invariant(self, root: Path) -> str:
        node_id = new_id("nd")
        (root / "canonical/registry/nodes.jsonl").write_text(
            json.dumps({
                "id": node_id,
                "type": "invariant",
                "status": "active",
                "authority": "source_grounded",
                "audiences": ["builders"],
                "source_ids": [new_id("src")],
            }) + "\n",
            encoding="utf-8",
        )
        return node_id

    def test_repo_lint_flags_generated_projection_but_runtime_lint_accepts_valid_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            self.seed_invariant(root)
            write_builder_pack(
                root,
                task_id="task_runtime_ok",
                goal="goal",
                canonical_rev="rev",
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                allow_dirty=True,
            )
            self.assertFalse(run_repo_lints(root).ok)
            result = run_runtime_lints(root)
            self.assertTrue(result.ok, "\n".join(result.messages))

    def test_runtime_lint_rejects_malformed_pack_and_symlinked_reltests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            pack = root / "projections/tasks/task_bad"
            pack.mkdir(parents=True)
            (pack / "metadata.json").write_text("{}", encoding="utf-8")
            result = run_runtime_lints(root)
            self.assertFalse(result.ok)
            self.assertIn("missing files", "\n".join(result.messages))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            pack = root / "projections/tasks/task_link"
            pack.mkdir(parents=True)
            for filename in ["metadata.json", "constraints.json", "source-bundle.json", "writeback-targets.json"]:
                (pack / filename).write_text("{}\n", encoding="utf-8")
            (pack / "brief.md").write_text("brief\n", encoding="utf-8")
            outside = Path(tempfile.mkdtemp()) / "rel.yaml"
            outside.write_text("[]\n", encoding="utf-8")
            (pack / "relationship-tests.yaml").symlink_to(outside)
            result = run_runtime_lints(root)
            self.assertFalse(result.ok)
            self.assertIn("symlink", "\n".join(result.messages))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            pack = root / "projections/tasks/task_brief"
            pack.mkdir(parents=True)
            for filename in ["metadata.json", "constraints.json", "source-bundle.json", "writeback-targets.json"]:
                (pack / filename).write_text("{}\n", encoding="utf-8")
            outside = Path(tempfile.mkdtemp()) / "brief.md"
            outside.write_text("private", encoding="utf-8")
            (pack / "brief.md").symlink_to(outside)
            (pack / "relationship-tests.yaml").write_text("[]\n", encoding="utf-8")
            result = run_runtime_lints(root)
            self.assertFalse(result.ok)
            self.assertIn("brief.md", "\n".join(result.messages))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            init_topology(root)
            outside = Path(tempfile.mkdtemp()) / "projections"
            task_dir = outside / "tasks" / "task_bad"
            task_dir.mkdir(parents=True)
            (task_dir / "constraints.json").write_text("{bad json", encoding="utf-8")
            shutil.rmtree(root / "projections")
            (root / "projections").symlink_to(outside, target_is_directory=True)
            result = run_runtime_lints(root)
            self.assertFalse(result.ok)
            self.assertIn("symlinked", "\n".join(result.messages))

    def test_doctor_queues_reports_unknowns_symlinks_expired_and_failed_without_mutating(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            init_topology(root)
            (root / "ops/queue/unknown").mkdir()
            (root / "ops/queue/digest/stuck").mkdir()
            (root / "ops/queue/stray.txt").write_text("bad", encoding="utf-8")
            failed = create_job(
                root,
                "digest",
                payload={"source_id": new_id("src")},
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                base_canonical_rev="rev",
                created_by="test",
            )
            failed_target = root / "ops/queue/digest/failed" / failed.name
            failed.rename(failed_target)
            create_job(
                root,
                "digest",
                payload={"source_id": new_id("src")},
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                base_canonical_rev="rev",
                created_by="test",
            )
            lease_next(root, "digest", owner="test", lease_seconds=-1)
            outside = Path(tempfile.mkdtemp())
            linked_job = root / "ops/queue/digest/pending/job_link.json"
            linked_job.symlink_to(outside / "private.json")
            result = doctor_queues(root)
            joined = "\n".join(result.messages)
            self.assertFalse(result.ok)
            self.assertIn("unknown queue kind", joined)
            self.assertIn("unknown queue state", joined)
            self.assertIn("stray file", joined)
            self.assertIn("expired lease", joined)
            self.assertIn("failed job", joined)
            self.assertIn("symlinked", joined)
            self.assertTrue(failed_target.exists())

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            init_topology(root)
            outside = Path(tempfile.mkdtemp()) / "ops"
            outside.mkdir()
            shutil.rmtree(root / "ops")
            (root / "ops").symlink_to(outside, target_is_directory=True)
            result = doctor_queues(root)
            self.assertFalse(result.ok)
            self.assertIn("symlinked", result.messages[0])

    def test_doctor_projections_reports_expected_metadata_and_manifest_safety(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            write_openclaw_projection(
                root,
                project_id="openclaw_project",
                canonical_rev="rev_current",
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                allow_dirty=True,
            )
            stale = doctor_projections(
                root,
                project_id="openclaw_project",
                canonical_rev="new",
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
            )
            self.assertFalse(stale.ok)
            self.assertIn("stale", "\n".join(stale.messages))
            manifest = root / "projections/openclaw/wiki-mirror/manifest.json"
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["pages"] = [{"path": "../bad.md"}]
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            unsafe = doctor_projections(root)
            self.assertFalse(unsafe.ok)
            self.assertIn("unsafe", "\n".join(unsafe.messages))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            init_topology(root)
            outside = Path(tempfile.mkdtemp()) / "raw"
            packets = outside / "packets"
            packet_dir = packets / new_id("src")
            packet_dir.mkdir(parents=True)
            (packet_dir / "packet.json").write_text("{}", encoding="utf-8")
            shutil.rmtree(root / "raw")
            (root / "raw").symlink_to(outside, target_is_directory=True)
            result = doctor_public_safe(root)
            self.assertFalse(result.ok)
            self.assertIn("symlinked", result.messages[0])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            write_openclaw_projection(
                root,
                project_id="openclaw_project",
                canonical_rev="rev_current",
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                allow_dirty=True,
            )
            manifest = root / "projections/openclaw/wiki-mirror/manifest.json"
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["pages"] = [{"path": "pages/fake.md"}]
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            outside = Path(tempfile.mkdtemp()) / "fake.md"
            outside.write_text("private", encoding="utf-8")
            (root / "projections/openclaw/wiki-mirror/pages/fake.md").symlink_to(outside)
            unsafe = doctor_projections(root)
            self.assertFalse(unsafe.ok)
            self.assertIn("unsafe", "\n".join(unsafe.messages))

    def test_doctor_canonical_parity_uses_op_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            claim_id = new_id("clm")
            (root / "canonical/registry/claims.jsonl").write_text(json.dumps({"claim_id": claim_id, "status": "active"}) + "\n", encoding="utf-8")
            page_dir = root / "canonical/nodes/claim"
            page_dir.mkdir(parents=True, exist_ok=True)
            (page_dir / f"{claim_id}.md").write_text(
                "---\n"
                f"id: {claim_id}\n"
                "op: create_claim\n"
                "status: draft\n"
                "---\n",
                encoding="utf-8",
            )
            result = doctor_canonical_parity(root)
            self.assertFalse(result.ok)
            self.assertIn("status mismatch", "\n".join(result.messages))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            node_id = new_id("nd")
            (root / "canonical/registry/nodes.jsonl").write_text(json.dumps({"id": node_id, "status": "active"}) + "\n", encoding="utf-8")
            result = doctor_canonical_parity(root)
            self.assertFalse(result.ok)
            self.assertIn("missing page", "\n".join(result.messages))

    def test_doctor_public_safe_reports_caps_symlinks_and_private_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            source_id = new_id("src")
            packet_dir = root / "raw/packets" / source_id
            packet_dir.mkdir(parents=True)
            (packet_dir / "content.md").write_text("x" * 9000, encoding="utf-8")
            (packet_dir / "packet.json").write_text(json.dumps({
                "schema_version": "1.0",
                "id": source_id,
                "source_type": "article_html",
                "original_url": "https://example.com",
                "canonical_url": "https://example.com",
                "retrieved_at": "2026-04-14T00:00:00Z",
                "curator_note": "note",
                "ingest_depth": "standard",
                "authority": "source_grounded",
                "trust_scope": "external",
                "content_status": "complete",
                "content_mode": "public_text",
                "redistributable": "yes",
                "hash_original": None,
                "hash_normalized": None,
                "artifacts": [{"kind": "note", "path": ".openclaw/private"}, {"kind": "local_blob", "path": "blob.bin"}],
                "fetch_chain": [],
            }), encoding="utf-8")
            (packet_dir / "blob.bin").write_bytes(b"blob")
            outside = Path(tempfile.mkdtemp()) / "secret"
            outside.write_text("secret", encoding="utf-8")
            (packet_dir / "linked.txt").symlink_to(outside)
            (packet_dir / "paper.pdf").write_bytes(b"%PDF")
            (packet_dir / "payload.bin").write_bytes(b"\x00" * 10000)
            result = doctor_public_safe(root)
            self.assertFalse(result.ok)
            joined = "\n".join(result.messages)
            self.assertIn("8000", joined)
            self.assertIn("symlink", joined)
            self.assertIn("PDF bytes", joined)
            self.assertIn("binary-looking", joined)
            self.assertIn("OpenClaw", joined)

    def test_cli_lint_and_doctor_split_smoke(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            env = os.environ.copy()
            env["PYTHONPATH"] = str(SRC)
            commands = [
                [sys.executable, "-m", "knowledge_topology.cli", "lint", "--root", tmp],
                [sys.executable, "-m", "knowledge_topology.cli", "lint", "repo", "--root", tmp],
                [sys.executable, "-m", "knowledge_topology.cli", "lint", "runtime", "--root", tmp],
                [sys.executable, "-m", "knowledge_topology.cli", "doctor", "queues", "--root", tmp],
                [sys.executable, "-m", "knowledge_topology.cli", "doctor", "projections", "--root", tmp],
                [sys.executable, "-m", "knowledge_topology.cli", "doctor", "canonical-parity", "--root", tmp],
                [sys.executable, "-m", "knowledge_topology.cli", "doctor", "public-safe", "--root", tmp],
                [
                    sys.executable,
                    "-m",
                    "knowledge_topology.cli",
                    "doctor",
                    "stale-anchors",
                    "--root",
                    tmp,
                    "--subject",
                    "repo_knowledge_topology",
                    "--subject-head-sha",
                    "abc123",
                ],
            ]
            for command in commands:
                with self.subTest(command=command):
                    result = subprocess.run(command, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

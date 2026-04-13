import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from knowledge_topology.git_state import read_git_state
from knowledge_topology.ids import is_valid_id, new_id
from knowledge_topology.paths import PathSafetyError, TopologyPaths
from knowledge_topology.schema.loader import SchemaLoadError, load_json, require_fields
from knowledge_topology.storage.spool import complete_job, create_job, fail_job, lease_next, read_job, requeue_failed_job
from knowledge_topology.storage.transaction import atomic_writer, atomic_write_text
from knowledge_topology.workers.init import init_topology


class P1EngineSkeletonTests(unittest.TestCase):
    def test_id_generation_uses_valid_prefixes_and_sortable_suffix(self):
        random_bytes = b"\x00" * 10
        first = new_id("nd", timestamp_ms=1, random_bytes=random_bytes)
        second = new_id("nd", timestamp_ms=2, random_bytes=random_bytes)
        self.assertTrue(is_valid_id(first, prefix="nd"))
        self.assertLess(first, second)
        with self.assertRaises(ValueError):
            new_id("slug", timestamp_ms=1, random_bytes=random_bytes)

    def test_path_helper_rejects_escape_and_nested_topology(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = TopologyPaths.from_root(tmp)
            self.assertEqual(paths.resolve("raw/packets").parent, Path(tmp).resolve() / "raw")
            with self.assertRaises(PathSafetyError):
                paths.resolve("../outside")
            with self.assertRaises(PathSafetyError):
                paths.resolve(".topology/raw")
            with self.assertRaises(PathSafetyError):
                TopologyPaths.from_root(Path(tmp) / ".topology" / "prod-root")
            fixture_path = paths.resolve("tests/fixtures/.topology/raw", allow_fixture_topology=True)
            self.assertIn("tests", fixture_path.parts)
            fixture_root = TopologyPaths.from_root(Path(tmp) / ".topology" / "fixture-root", allow_fixture_topology=True)
            self.assertEqual(fixture_root.root.name, "fixture-root")

    def test_init_creates_expected_tree_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            init_topology(tmp)
            init_topology(tmp)
            root = Path(tmp)
            for rel in [
                "raw/packets",
                "digests/by_source",
                "canonical/registry",
                "ops/queue/ingest/pending",
                "ops/queue/writeback/failed",
                "projections/openclaw",
            ]:
                self.assertTrue((root / rel).is_dir(), rel)
            self.assertTrue((root / "canonical/registry/nodes.jsonl").exists())
            self.assertFalse((root / ".topology").exists())

    def test_git_state_reports_head_and_dirty_state(self):
        state = read_git_state(ROOT, strict=True)
        self.assertIsNotNone(state.head_sha)
        self.assertIsInstance(state.dirty, bool)
        with tempfile.TemporaryDirectory() as tmp:
            outside = read_git_state(tmp)
            self.assertIsNone(outside.head_sha)
            self.assertFalse(outside.dirty)

    def test_schema_loader_requires_fields(self):
        payload = load_json(ROOT / "tests/fixtures/p0/schema_evolution/node_v1.json")
        require_fields(payload, ["schema_version", "id", "type"])
        with self.assertRaises(SchemaLoadError):
            require_fields(payload, ["missing"])

    def test_atomic_writer_preserves_old_target_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target.txt"
            atomic_write_text(target, "old")
            with self.assertRaises(RuntimeError):
                with atomic_writer(target) as temp_path:
                    temp_path.write_text("new", encoding="utf-8")
                    raise RuntimeError("boom")
            self.assertEqual(target.read_text(encoding="utf-8"), "old")
            atomic_write_text(target, "new")
            self.assertEqual(target.read_text(encoding="utf-8"), "new")

    def test_spool_queue_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            pending = create_job(
                tmp,
                "digest",
                payload={"source_id": "src_01HZXAMPLE0000000000000008"},
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                base_canonical_rev="rev_current",
                created_by="reader",
            )
            self.assertEqual(pending.parent.name, "pending")
            leased = lease_next(tmp, "digest", owner="worker-1", lease_seconds=60)
            self.assertIsNotNone(leased)
            job = read_job(leased)
            self.assertEqual(job["lease_owner"], "worker-1")
            self.assertEqual(job["attempts"], 1)
            done = complete_job(leased)
            self.assertEqual(done.parent.name, "done")

            pending2 = create_job(
                tmp,
                "digest",
                payload={"source_id": "src_01HZXAMPLE0000000000000009"},
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                base_canonical_rev="rev_current",
                created_by="reader",
            )
            leased2 = lease_next(tmp, "digest", owner="worker-1")
            failed = fail_job(leased2)
            self.assertEqual(failed.parent.name, "failed")
            requeued = requeue_failed_job(failed)
            self.assertEqual(requeued.parent.name, "pending")
            self.assertEqual(requeued.name, pending2.name)
            self.assertTrue(requeued.exists())

    def test_cli_help_and_init(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(SRC)
            help_result = subprocess.run(
                [sys.executable, "-m", "knowledge_topology.cli", "--help"],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(help_result.returncode, 0, help_result.stderr)
            init_result = subprocess.run(
                [sys.executable, "-m", "knowledge_topology.cli", "init", "--root", tmp],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(init_result.returncode, 0, init_result.stderr)
            self.assertTrue((Path(tmp) / "ops/queue/ingest/pending").is_dir())

            nested = Path(tmp) / ".topology" / "prod-root"
            nested_result = subprocess.run(
                [sys.executable, "-m", "knowledge_topology.cli", "init", "--root", str(nested)],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertNotEqual(nested_result.returncode, 0)
            self.assertFalse((nested / "raw").exists())


if __name__ == "__main__":
    unittest.main()

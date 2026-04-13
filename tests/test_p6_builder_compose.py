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
from knowledge_topology.workers.compose_builder import write_builder_pack
from knowledge_topology.workers.init import init_topology


class P6BuilderComposeTests(unittest.TestCase):
    def seed_applied_state(self, root: Path) -> dict[str, str]:
        init_topology(root)
        invariant_id = new_id("nd")
        runtime_id = new_id("nd")
        claim_id = new_id("clm")
        edge_id = new_id("edg")
        gap_id = new_id("gap")
        (root / "canonical/registry/nodes.jsonl").write_text(
            "\n".join([
                json.dumps({
                    "id": invariant_id,
                    "type": "invariant",
                    "status": "active",
                    "sensitivity": "internal",
                    "audiences": ["builders"],
                    "source_ids": ["src_01HZXAMPLE0000000000000001"],
                    "unsafe_raw_text": "must not leak",
                }),
                json.dumps({
                    "id": runtime_id,
                    "type": "runtime_observation",
                    "status": "active",
                    "sensitivity": "runtime_only",
                    "audiences": ["openclaw"],
                }),
            ]) + "\n",
            encoding="utf-8",
        )
        (root / "canonical/registry/claims.jsonl").write_text(
            json.dumps({"claim_id": claim_id, "statement": "builder visible claim", "status": "active", "audiences": ["builders"], "unsafe_raw_text": "must not leak"}) + "\n",
            encoding="utf-8",
        )
        (root / "canonical/registry/edges.jsonl").write_text(
            json.dumps({"edge_id": edge_id, "edge_type": "INVARIANT_FOR", "from_id": "src_01HZXAMPLE0000000000000001", "to_id": invariant_id, "confidence": "high", "status": "active", "audiences": ["builders"]}) + "\n",
            encoding="utf-8",
        )
        (root / "ops/gaps/open.jsonl").write_text(
            json.dumps({"gap_id": gap_id, "summary": "open builder gap", "status": "active", "audiences": ["builders"]}) + "\n",
            encoding="utf-8",
        )
        pending = {
            "id": new_id("mut"),
            "changes": [{"op": "create_claim", "statement": "pending should not appear"}],
        }
        (root / "mutations/pending" / f"{pending['id']}.json").write_text(json.dumps(pending), encoding="utf-8")
        return {"invariant_id": invariant_id, "runtime_id": runtime_id, "claim_id": claim_id, "edge_id": edge_id}

    def read_pack_json(self, pack: Path, name: str) -> dict:
        return json.loads((pack / name).read_text(encoding="utf-8"))

    def test_builder_pack_writes_fixed_outputs_and_filters_runtime_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ids = self.seed_applied_state(root)
            pack = write_builder_pack(
                root,
                task_id="task_demo",
                goal="Use applied canonical state",
                canonical_rev="rev_current",
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                allow_dirty=True,
            )
            self.assertEqual({path.name for path in pack.iterdir()}, {
                "metadata.json",
                "brief.md",
                "constraints.json",
                "relationship-tests.yaml",
                "source-bundle.json",
                "writeback-targets.json",
            })
            metadata = self.read_pack_json(pack, "metadata.json")
            self.assertEqual(metadata["canonical_rev"], "rev_current")
            self.assertEqual(metadata["subject_repo_id"], "repo_knowledge_topology")
            bundle = self.read_pack_json(pack, "source-bundle.json")
            serialized = json.dumps(bundle)
            self.assertIn(ids["invariant_id"], serialized)
            self.assertNotIn(ids["runtime_id"], serialized)
            self.assertNotIn("pending should not appear", serialized)
            self.assertNotIn("unsafe_raw_text", serialized)
            reltests = (pack / "relationship-tests.yaml").read_text(encoding="utf-8")
            self.assertIn(ids["invariant_id"], reltests)
            self.assertIn("schema_version: 1.0", reltests)
            self.assertIn("reltest_", reltests)

    def test_builder_pack_is_deterministic_except_generated_at(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.seed_applied_state(root)
            first = write_builder_pack(root, task_id="task_a", goal="goal", canonical_rev="rev", subject_repo_id="repo", subject_head_sha="sha", allow_dirty=True)
            first_bundle = self.read_pack_json(first, "source-bundle.json")
            second = write_builder_pack(root, task_id="task_b", goal="goal", canonical_rev="rev", subject_repo_id="repo", subject_head_sha="sha", allow_dirty=True)
            second_bundle = self.read_pack_json(second, "source-bundle.json")
            self.assertEqual(first_bundle, second_bundle)

    def test_compose_requires_metadata_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            with self.assertRaises(Exception):
                write_builder_pack(root, task_id="", goal="goal", canonical_rev="rev", subject_repo_id="repo", subject_head_sha="sha", allow_dirty=True)
            with self.assertRaises(Exception):
                write_builder_pack(root, task_id="../../canonical/registry/p6_escape", goal="goal", canonical_rev="rev", subject_repo_id="repo", subject_head_sha="sha", allow_dirty=True)
            self.assertFalse((root / "canonical/registry/p6_escape").exists())

    def test_operator_scope_and_missing_audience_are_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.seed_applied_state(root)
            with (root / "canonical/registry/nodes.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"id": new_id("nd"), "type": "operator_directive", "scope": "operator", "sensitivity": "internal", "audiences": ["builders"], "status": "active", "statement": "do not leak"}) + "\n")
                handle.write(json.dumps({"id": new_id("nd"), "type": "invariant", "sensitivity": "internal", "status": "active", "statement": "missing audience"}) + "\n")
            pack = write_builder_pack(root, task_id="task_filters", goal="goal", canonical_rev="rev", subject_repo_id="repo", subject_head_sha="sha", allow_dirty=True)
            serialized = json.dumps(self.read_pack_json(pack, "source-bundle.json"))
            self.assertNotIn("do not leak", serialized)
            self.assertNotIn("missing audience", serialized)

    def test_cli_compose_builder_smoke(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.seed_applied_state(root)
            env = os.environ.copy()
            env["PYTHONPATH"] = str(SRC)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "knowledge_topology.cli",
                    "compose",
                    "builder",
                    "--root",
                    tmp,
                    "--task-id",
                    "task_cli",
                    "--goal",
                    "CLI compose",
                    "--canonical-rev",
                    "rev",
                    "--subject",
                    "repo_knowledge_topology",
                    "--subject-head-sha",
                    "abc123",
                    "--allow-dirty",
                ],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("created builder pack:", result.stdout)
            self.assertTrue((root / "projections/tasks/task_cli/metadata.json").exists())


if __name__ == "__main__":
    unittest.main()

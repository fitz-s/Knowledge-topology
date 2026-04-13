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
from knowledge_topology.schema.mutation_pack import MutationPack, MutationPackError
from knowledge_topology.storage.registry import Registry, RegistryError
from knowledge_topology.workers.digest import write_digest_artifacts
from knowledge_topology.workers.fetch import ingest_source
from knowledge_topology.workers.init import init_topology
from knowledge_topology.workers.reconcile import ReconcileError, reconcile_digest
from knowledge_topology.adapters.digest_model import JsonFileDigestAdapter


def digest_payload(source_id: str, *, target_id: str, edge_type: str = "SUPPORTS", confidence: str = "low") -> dict:
    return {
        "schema_version": "1.0",
        "id": new_id("dg"),
        "source_id": source_id,
        "digest_depth": "deep",
        "passes_completed": [1, 2, 3, 4],
        "author_claims": [{"text": "claim from source"}],
        "direct_evidence": [{"quote": "evidence"}],
        "model_inferences": [{"text": "inference"}],
        "boundary_conditions": [],
        "alternative_interpretations": [],
        "contested_points": [],
        "unresolved_ambiguity": [],
        "open_questions": [],
        "candidate_edges": [{
            "target_id": target_id,
            "edge_type": edge_type,
            "confidence": confidence,
            "note": "candidate edge",
        }],
        "fidelity_flags": {
            "reasoning_chain_preserved": "yes",
            "boundary_conditions_preserved": "yes",
            "alternative_interpretations_preserved": "yes",
            "hidden_assumptions_extracted": "partial",
            "evidence_strength_graded": "yes",
        },
    }


class P4ReconcileMutationTests(unittest.TestCase):
    def make_digest(self, root: Path, *, target_id: str | None = None, edge_type: str = "SUPPORTS", confidence: str = "low") -> Path:
        init_topology(root)
        draft = root / "draft.md"
        draft.write_text("source text\n", encoding="utf-8")
        source_id = ingest_source(
            root,
            str(draft),
            note="curated",
            depth="deep",
            audience="builders",
            subject_repo_id="repo_knowledge_topology",
            subject_head_sha="abc123",
            base_canonical_rev="rev_current",
            redistributable="yes",
        ).packet_id
        output_dir = root / ".tmp"
        output_dir.mkdir(exist_ok=True)
        model_output = output_dir / "digest.json"
        model_output.write_text(json.dumps(digest_payload(source_id, target_id=target_id or new_id("nd"), edge_type=edge_type, confidence=confidence)), encoding="utf-8")
        digest_json, _ = write_digest_artifacts(root, source_id=source_id, model_adapter=JsonFileDigestAdapter(model_output))
        return digest_json

    def add_known_node(self, root: Path, node_id: str) -> None:
        registry = root / "canonical/registry/nodes.jsonl"
        registry.write_text(json.dumps({"id": node_id, "type": "invariant", "status": "active"}) + "\n", encoding="utf-8")

    def test_unknown_low_confidence_target_opens_gap_not_edge(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            digest_json = self.make_digest(root, target_id=new_id("nd"), confidence="low")
            digest_payload_json = json.loads(digest_json.read_text(encoding="utf-8"))
            mutation_path = reconcile_digest(
                root,
                digest_json=digest_json,
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                base_canonical_rev="rev_current",
            )
            pack = MutationPack.from_dict(json.loads(mutation_path.read_text(encoding="utf-8")))
            ops = [change["op"] for change in pack.changes]
            self.assertIn("create_claim", ops)
            self.assertIn("open_gap", ops)
            self.assertNotIn("add_edge", ops)
            self.assertFalse(pack.requires_human)
            self.assertIn(digest_payload_json["id"], pack.evidence_refs)
            self.assertTrue((root / f"digests/by_source/{digest_payload_json['source_id']}/{digest_payload_json['id']}.json").exists())
            self.assertIn(digest_payload_json["source_id"], pack.evidence_refs)
            self.assertTrue((root / f"raw/packets/{digest_payload_json['source_id']}/packet.json").exists())

    def test_known_target_with_medium_confidence_adds_edge(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = new_id("nd")
            digest_json = self.make_digest(root, target_id=target, confidence="medium")
            self.add_known_node(root, target)
            mutation_path = reconcile_digest(
                root,
                digest_json=digest_json,
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                base_canonical_rev="rev_current",
            )
            pack = MutationPack.from_dict(json.loads(mutation_path.read_text(encoding="utf-8")))
            edges = [change for change in pack.changes if change["op"] == "add_edge"]
            self.assertEqual(len(edges), 1)
            self.assertEqual(edges[0]["to_id"], target)
            self.assertIn(pack.id, mutation_path.name)

    def test_contradiction_requires_human_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = new_id("nd")
            digest_json = self.make_digest(root, target_id=target, edge_type="CONTRADICTS", confidence="high")
            self.add_known_node(root, target)
            mutation_path = reconcile_digest(
                root,
                digest_json=digest_json,
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                base_canonical_rev="rev_current",
            )
            pack = MutationPack.from_dict(json.loads(mutation_path.read_text(encoding="utf-8")))
            self.assertTrue(pack.requires_human)
            self.assertEqual(pack.human_gate_class, "high_impact_contradiction")

    def test_blank_preconditions_fail_before_pending_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            digest_json = self.make_digest(root)
            with self.assertRaises(ReconcileError):
                reconcile_digest(
                    root,
                    digest_json=digest_json,
                    subject_repo_id=" ",
                    subject_head_sha=" ",
                    base_canonical_rev=" ",
                )
            self.assertEqual(list((root / "mutations/pending").glob("*.json")), [])

    def test_reconcile_does_not_write_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            digest_json = self.make_digest(root)
            before = sorted(path.relative_to(root).as_posix() for path in (root / "canonical").rglob("*.*"))
            reconcile_digest(
                root,
                digest_json=digest_json,
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                base_canonical_rev="rev_current",
            )
            after = sorted(path.relative_to(root).as_posix() for path in (root / "canonical").rglob("*.*"))
            self.assertEqual(before, after)

    def test_mutation_pack_schema_rejects_missing_human_gate(self):
        with self.assertRaises(MutationPackError):
            MutationPack(
                schema_version="1.0",
                id=new_id("mut"),
                proposal_type="digest_reconcile",
                proposed_by="reconciler",
                base_canonical_rev="rev",
                subject_repo_id="repo",
                subject_head_sha="sha",
                changes=[{"op": "open_gap"}],
                evidence_refs=["dg_01HZXAMPLE0000000000000001"],
                requires_human=True,
                human_gate_class=None,
                merge_confidence="low",
            ).validate()

    def test_registry_rejects_malformed_jsonl_and_non_opaque_node_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            registry = root / "canonical/registry/nodes.jsonl"
            registry.write_text("{not-json}\n", encoding="utf-8")
            with self.assertRaises(RegistryError):
                Registry(root).known_node_ids()
            registry.write_text(json.dumps({"id": "not-an-opaque-node-id"}) + "\n", encoding="utf-8")
            with self.assertRaises(RegistryError):
                Registry(root).known_node_ids()

    def test_reconcile_rejects_malformed_candidate_target_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            digest_json = self.make_digest(root, target_id="not-an-opaque-node-id", confidence="high")
            with self.assertRaises(ReconcileError):
                reconcile_digest(
                    root,
                    digest_json=digest_json,
                    subject_repo_id="repo_knowledge_topology",
                    subject_head_sha="abc123",
                    base_canonical_rev="rev_current",
                )

    def test_mutation_pack_schema_validates_op_specific_ids(self):
        with self.assertRaises(MutationPackError):
            MutationPack(
                schema_version="1.0",
                id=new_id("mut"),
                proposal_type="digest_reconcile",
                proposed_by="reconciler",
                base_canonical_rev="rev",
                subject_repo_id="repo",
                subject_head_sha="sha",
                changes=[{
                    "op": "add_edge",
                    "edge_id": new_id("edg"),
                    "from_id": "src_01HZXAMPLE0000000000000001",
                    "to_id": "not-an-opaque-node-id",
                    "edge_type": "SUPPORTS",
                    "confidence": "high",
                    "note": "bad",
                    "basis_digest_id": "dg_01HZXAMPLE0000000000000002",
                }],
                evidence_refs=["dg_01HZXAMPLE0000000000000002"],
                requires_human=False,
                human_gate_class=None,
                merge_confidence="medium",
            ).validate()

    def test_cli_reconcile_smoke(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            digest_json = self.make_digest(root)
            env = os.environ.copy()
            env["PYTHONPATH"] = str(SRC)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "knowledge_topology.cli",
                    "reconcile",
                    "--root",
                    tmp,
                    "--digest-json",
                    str(digest_json),
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
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("created mutation pack:", result.stdout)


if __name__ == "__main__":
    unittest.main()

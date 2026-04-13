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
from knowledge_topology.workers.apply import ApplyError, apply_mutation
from knowledge_topology.workers.digest import write_digest_artifacts
from knowledge_topology.workers.fetch import ingest_source
from knowledge_topology.workers.init import init_topology
from knowledge_topology.workers.reconcile import reconcile_digest
from knowledge_topology.adapters.digest_model import JsonFileDigestAdapter
from knowledge_topology.storage.registry import Registry


def digest_payload(source_id: str, *, target_id: str = "NEW", edge_type: str = "SUPPORTS", confidence: str = "low") -> dict:
    return {
        "schema_version": "1.0",
        "id": new_id("dg"),
        "source_id": source_id,
        "digest_depth": "deep",
        "passes_completed": [1, 2, 3, 4],
        "author_claims": [{"text": "claim from source"}],
        "direct_evidence": [{"quote": "evidence"}],
        "model_inferences": [],
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


class P5ApplyGateTests(unittest.TestCase):
    def make_pending_mutation(self, root: Path, *, edge_type: str = "SUPPORTS", target_id: str = "NEW", confidence: str = "low") -> Path:
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
        model_dir = root / ".tmp"
        model_dir.mkdir(exist_ok=True)
        model = model_dir / "digest.json"
        model.write_text(json.dumps(digest_payload(source_id, target_id=target_id, edge_type=edge_type, confidence=confidence)), encoding="utf-8")
        digest_json, _ = write_digest_artifacts(root, source_id=source_id, model_adapter=JsonFileDigestAdapter(model))
        return reconcile_digest(
            root,
            digest_json=digest_json,
            subject_repo_id="repo_knowledge_topology",
            subject_head_sha="abc123",
            base_canonical_rev="rev_current",
        )

    def test_apply_success_writes_canonical_registries_pages_event_and_moves_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mutation = self.make_pending_mutation(root)
            applied, event = apply_mutation(
                root,
                mutation,
                current_canonical_rev="rev_current",
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
            )
            self.assertEqual(applied.parent.name, "applied")
            self.assertFalse(mutation.exists())
            self.assertTrue(event.exists())
            self.assertTrue((root / "canonical/registry/claims.jsonl").read_text(encoding="utf-8").strip())
            self.assertTrue((root / "canonical/registry/nodes.jsonl").read_text(encoding="utf-8").strip())
            self.assertTrue(list((root / "canonical/nodes/claim").glob("*.md")))
            self.assertEqual(len(Registry(root).known_node_ids()), 1)

    def test_apply_preserves_multiple_records_for_same_registry_and_artifact_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mutation = self.make_pending_mutation(root)
            payload = json.loads(mutation.read_text(encoding="utf-8"))
            claim_changes = [change for change in payload["changes"] if change["op"] == "create_claim"]
            self.assertEqual(len(claim_changes), 1)
            second_claim = dict(claim_changes[0])
            second_claim["claim_id"] = new_id("clm")
            second_claim["statement"] = "second claim from source"
            payload["changes"].append(second_claim)
            mutation.write_text(json.dumps(payload), encoding="utf-8")
            apply_mutation(
                root,
                mutation,
                current_canonical_rev="rev_current",
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
            )
            claim_lines = (root / "canonical/registry/claims.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(claim_lines), 2)
            self.assertEqual(len(list((root / "canonical/nodes/claim").glob("*.md"))), 2)
            self.assertTrue(list((root / "canonical/nodes/artifact").glob("*.md")))

    def test_stale_precondition_rejects_before_writes_or_move(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mutation = self.make_pending_mutation(root)
            before_claims = (root / "canonical/registry/claims.jsonl").read_text(encoding="utf-8")
            with self.assertRaises(ApplyError):
                apply_mutation(
                    root,
                    mutation,
                    current_canonical_rev="rev_new",
                    subject_repo_id="repo_knowledge_topology",
                    subject_head_sha="abc123",
                )
            self.assertTrue(mutation.exists())
            self.assertEqual((root / "canonical/registry/claims.jsonl").read_text(encoding="utf-8"), before_claims)
            self.assertFalse(list((root / "ops/events").rglob("evt_*.json")))

    def test_non_pending_mutation_path_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mutation = self.make_pending_mutation(root)
            external = root / "external.json"
            external.write_text(mutation.read_text(encoding="utf-8"), encoding="utf-8")
            with self.assertRaises(ApplyError):
                apply_mutation(
                    root,
                    external,
                    current_canonical_rev="rev_current",
                    subject_repo_id="repo_knowledge_topology",
                    subject_head_sha="abc123",
                )
            self.assertTrue(external.exists())
            self.assertTrue(mutation.exists())

    def test_human_gate_requires_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = new_id("nd")
            init_topology(root)
            (root / "canonical/registry/nodes.jsonl").write_text(json.dumps({"id": target}) + "\n", encoding="utf-8")
            # Reuse initialized root manually because make_pending_mutation calls init.
            draft = root / "draft.md"
            draft.write_text("source text\n", encoding="utf-8")
            source_id = ingest_source(root, str(draft), note="curated", depth="deep", audience="builders", subject_repo_id="repo_knowledge_topology", subject_head_sha="abc123", base_canonical_rev="rev_current", redistributable="yes").packet_id
            model = root / ".tmp/digest.json"
            model.parent.mkdir(exist_ok=True)
            model.write_text(json.dumps(digest_payload(source_id, target_id=target, edge_type="CONTRADICTS", confidence="high")), encoding="utf-8")
            digest_json, _ = write_digest_artifacts(root, source_id=source_id, model_adapter=JsonFileDigestAdapter(model))
            mutation = reconcile_digest(root, digest_json=digest_json, subject_repo_id="repo_knowledge_topology", subject_head_sha="abc123", base_canonical_rev="rev_current")
            with self.assertRaises(ApplyError):
                apply_mutation(root, mutation, current_canonical_rev="rev_current", subject_repo_id="repo_knowledge_topology", subject_head_sha="abc123")
            applied, _ = apply_mutation(root, mutation, current_canonical_rev="rev_current", subject_repo_id="repo_knowledge_topology", subject_head_sha="abc123", approve_human=True)
            self.assertEqual(applied.parent.name, "applied")

    def test_forged_human_gate_is_reclassified_by_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = new_id("nd")
            init_topology(root)
            (root / "canonical/registry/nodes.jsonl").write_text(json.dumps({"id": target}) + "\n", encoding="utf-8")
            draft = root / "draft.md"
            draft.write_text("source text\n", encoding="utf-8")
            source_id = ingest_source(root, str(draft), note="curated", depth="deep", audience="builders", subject_repo_id="repo_knowledge_topology", subject_head_sha="abc123", base_canonical_rev="rev_current", redistributable="yes").packet_id
            model = root / ".tmp/digest.json"
            model.parent.mkdir(exist_ok=True)
            model.write_text(json.dumps(digest_payload(source_id, target_id=target, edge_type="CONTRADICTS", confidence="high")), encoding="utf-8")
            digest_json, _ = write_digest_artifacts(root, source_id=source_id, model_adapter=JsonFileDigestAdapter(model))
            mutation = reconcile_digest(root, digest_json=digest_json, subject_repo_id="repo_knowledge_topology", subject_head_sha="abc123", base_canonical_rev="rev_current")
            payload = json.loads(mutation.read_text(encoding="utf-8"))
            payload["requires_human"] = False
            payload["human_gate_class"] = None
            mutation.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ApplyError):
                apply_mutation(root, mutation, current_canonical_rev="rev_current", subject_repo_id="repo_knowledge_topology", subject_head_sha="abc123")

    def test_missing_evidence_rejects_before_move(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mutation = self.make_pending_mutation(root)
            payload = json.loads(mutation.read_text(encoding="utf-8"))
            payload["evidence_refs"] = [new_id("dg")]
            mutation.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ApplyError):
                apply_mutation(root, mutation, current_canonical_rev="rev_current", subject_repo_id="repo_knowledge_topology", subject_head_sha="abc123")
            self.assertTrue(mutation.exists())

    def test_change_level_missing_evidence_rejects_before_move(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mutation = self.make_pending_mutation(root)
            payload = json.loads(mutation.read_text(encoding="utf-8"))
            for change in payload["changes"]:
                if "digest_id" in change:
                    change["digest_id"] = new_id("dg")
                if "basis_digest_id" in change:
                    change["basis_digest_id"] = new_id("dg")
            mutation.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ApplyError):
                apply_mutation(root, mutation, current_canonical_rev="rev_current", subject_repo_id="repo_knowledge_topology", subject_head_sha="abc123")
            self.assertTrue(mutation.exists())

    def test_duplicate_registry_id_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mutation = self.make_pending_mutation(root)
            payload = json.loads(mutation.read_text(encoding="utf-8"))
            claim_id = next(change["claim_id"] for change in payload["changes"] if change["op"] == "create_claim")
            (root / "canonical/registry/claims.jsonl").write_text(json.dumps({"claim_id": claim_id}) + "\n", encoding="utf-8")
            mutation.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ApplyError):
                apply_mutation(root, mutation, current_canonical_rev="rev_current", subject_repo_id="repo_knowledge_topology", subject_head_sha="abc123")
            self.assertFalse(list((root / "ops/events").rglob("evt_*.json")))

    def test_failed_write_rolls_back_prior_canonical_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mutation = self.make_pending_mutation(root)
            registry_file = root / "canonical/registry/nodes.jsonl"
            registry_file.unlink()
            registry_file.mkdir()
            with self.assertRaises(Exception):
                apply_mutation(root, mutation, current_canonical_rev="rev_current", subject_repo_id="repo_knowledge_topology", subject_head_sha="abc123")
            self.assertTrue(mutation.exists())
            self.assertFalse(list((root / "canonical/nodes/claim").glob("*.md")))
            self.assertFalse(list((root / "ops/events").rglob("evt_*.json")))

    def test_cli_apply_smoke(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mutation = self.make_pending_mutation(root)
            env = os.environ.copy()
            env["PYTHONPATH"] = str(SRC)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "knowledge_topology.cli",
                    "apply",
                    str(mutation),
                    "--root",
                    tmp,
                    "--current-canonical-rev",
                    "rev_current",
                    "--subject",
                    "repo_knowledge_topology",
                    "--subject-head-sha",
                    "abc123",
                ],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("applied mutation pack:", result.stdout)


if __name__ == "__main__":
    unittest.main()

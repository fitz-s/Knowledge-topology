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

from knowledge_topology.adapters.digest_model import JsonFileDigestAdapter
from knowledge_topology.ids import new_id
from knowledge_topology.schema.digest import DigestError
from knowledge_topology.workers.digest import write_digest_artifacts
from knowledge_topology.workers.fetch import ingest_source
from knowledge_topology.workers.init import init_topology


def valid_digest_payload(source_id: str) -> dict:
    return {
        "schema_version": "1.0",
        "id": new_id("dg"),
        "source_id": source_id,
        "digest_depth": "deep",
        "passes_completed": [1, 2, 3, 4],
        "author_claims": [{"id": "claim-1", "text": "source says a thing"}],
        "direct_evidence": [{"quote": "short evidence", "location": "excerpt"}],
        "model_inferences": [{"text": "inference kept separate"}],
        "boundary_conditions": [{"text": "only in fixture scope"}],
        "alternative_interpretations": [{"text": "another reading"}],
        "contested_points": [{"text": "not settled"}],
        "unresolved_ambiguity": [{"text": "unknown"}],
        "open_questions": [{"text": "what next?"}],
        "candidate_edges": [{"target_id": "nd_01HZXAMPLE0000000000000004", "edge_type": "SUPPORTS", "confidence": "low"}],
        "fidelity_flags": {
            "reasoning_chain_preserved": "yes",
            "boundary_conditions_preserved": "yes",
            "alternative_interpretations_preserved": "yes",
            "hidden_assumptions_extracted": "partial",
            "evidence_strength_graded": "yes",
        },
    }


class P3DigestContractTests(unittest.TestCase):
    def make_source(self, root: Path) -> str:
        init_topology(root)
        draft = root / "draft.md"
        draft.write_text("source text\n", encoding="utf-8")
        result = ingest_source(
            root,
            str(draft),
            note="curated",
            depth="deep",
            audience="builders",
            subject_repo_id="repo_knowledge_topology",
            subject_head_sha="abc123",
            base_canonical_rev="rev_current",
            redistributable="yes",
        )
        return result.packet_id

    def write_model_output(self, root: Path, payload: dict, name: str = "model-output.json") -> Path:
        path = root / ".tmp"
        path.mkdir(exist_ok=True)
        output = path / name
        output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return output

    def test_valid_digest_writes_json_and_markdown_without_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_id = self.make_source(root)
            output = self.write_model_output(root, valid_digest_payload(source_id))
            json_path, md_path = write_digest_artifacts(root, source_id=source_id, model_adapter=JsonFileDigestAdapter(output))
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            digest = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(digest["source_id"], source_id)
            self.assertIn("## Fidelity Flags", md_path.read_text(encoding="utf-8"))
            canonical_files = sorted(path.relative_to(root).as_posix() for path in (root / "canonical").rglob("*.*"))
            self.assertEqual(canonical_files, [
                "canonical/registry/aliases.jsonl",
                "canonical/registry/claims.jsonl",
                "canonical/registry/edges.jsonl",
                "canonical/registry/file_refs.jsonl",
                "canonical/registry/nodes.jsonl",
            ])

    def test_invalid_digest_missing_field_fails_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_id = self.make_source(root)
            payload = valid_digest_payload(source_id)
            payload.pop("fidelity_flags")
            output = self.write_model_output(root, payload)
            with self.assertRaises(DigestError):
                write_digest_artifacts(root, source_id=source_id, model_adapter=JsonFileDigestAdapter(output))
            self.assertFalse((root / f"digests/by_source/{source_id}").exists())

    def test_digest_source_id_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_id = self.make_source(root)
            payload = valid_digest_payload(new_id("src"))
            output = self.write_model_output(root, payload)
            with self.assertRaises(DigestError):
                write_digest_artifacts(root, source_id=source_id, model_adapter=JsonFileDigestAdapter(output))

    def test_bad_fidelity_flag_and_edge_type_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_id = self.make_source(root)
            payload = valid_digest_payload(source_id)
            payload["fidelity_flags"]["reasoning_chain_preserved"] = "maybe"
            output = self.write_model_output(root, payload, "bad-flag.json")
            with self.assertRaises(DigestError):
                write_digest_artifacts(root, source_id=source_id, model_adapter=JsonFileDigestAdapter(output))

            payload = valid_digest_payload(source_id)
            payload["candidate_edges"][0]["edge_type"] = "VIBES_WITH"
            output = self.write_model_output(root, payload, "bad-edge.json")
            with self.assertRaises(DigestError):
                write_digest_artifacts(root, source_id=source_id, model_adapter=JsonFileDigestAdapter(output))

    def test_cli_digest_smoke(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_id = self.make_source(root)
            output = self.write_model_output(root, valid_digest_payload(source_id))
            env = os.environ.copy()
            env["PYTHONPATH"] = str(SRC)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "knowledge_topology.cli",
                    "digest",
                    "--root",
                    tmp,
                    "--source-id",
                    source_id,
                    "--model-output",
                    str(output),
                ],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("created digest json:", result.stdout)


if __name__ == "__main__":
    unittest.main()

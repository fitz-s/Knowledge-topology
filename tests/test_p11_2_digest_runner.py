import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from knowledge_topology.adapters.digest_model import CommandDigestProviderAdapter
from knowledge_topology.adapters.digest_model import JsonDirectoryDigestProviderAdapter
from knowledge_topology.ids import new_id
from knowledge_topology.storage.spool import create_job
from knowledge_topology.storage.spool import lease_next
from knowledge_topology.storage.spool import read_job
from knowledge_topology.storage.transaction import atomic_write_text
from knowledge_topology.workers.digest import DigestWorkerError
from knowledge_topology.workers.digest import build_digest_model_request
from knowledge_topology.workers.fetch import ingest_source
from knowledge_topology.workers.init import init_topology
from knowledge_topology.workers.run_digest_queue import run_digest_queue


DG_ID = "dg_00000000000000000000000000"


def init_with_prompts(root: Path) -> None:
    init_topology(root)
    for prompt in ["digest_deep.md", "digest_standard.md"]:
        (root / "prompts" / prompt).write_text((ROOT / "prompts" / prompt).read_text(encoding="utf-8"), encoding="utf-8")


def valid_digest_payload(source_id: str, digest_id: str = DG_ID) -> dict:
    return {
        "schema_version": "1.0",
        "id": digest_id,
        "source_id": source_id,
        "digest_depth": "deep",
        "passes_completed": [1, 2, 3, 4],
        "author_claims": [{"text": "source says a thing"}],
        "direct_evidence": [],
        "model_inferences": [],
        "boundary_conditions": [],
        "alternative_interpretations": [],
        "contested_points": [],
        "unresolved_ambiguity": [],
        "open_questions": [],
        "candidate_edges": [{"target_id": "NEW", "edge_type": "SUPPORTS", "confidence": "low", "note": "candidate"}],
        "fidelity_flags": {
            "reasoning_chain_preserved": "yes",
            "boundary_conditions_preserved": "yes",
            "alternative_interpretations_preserved": "yes",
            "hidden_assumptions_extracted": "partial",
            "evidence_strength_graded": "yes",
        },
    }


class P11DigestRunnerTests(unittest.TestCase):
    def make_source(
        self,
        root: Path,
        *,
        text: str = "source text\n",
        depth: str = "deep",
        content_mode: str | None = None,
        redistributable: str = "yes",
        source_type: str | None = None,
        value: str | None = None,
    ) -> str:
        if value is None:
            draft = root / "draft.md"
            draft.write_text(text, encoding="utf-8")
            value = str(draft)
        result = ingest_source(
            root,
            value,
            note="curated",
            depth=depth,
            audience="builders",
            subject_repo_id="repo_knowledge_topology",
            subject_head_sha="abc123",
            base_canonical_rev="rev_current",
            redistributable=redistributable,
            content_mode=content_mode,
            source_type=source_type,
        )
        return result.packet_id

    def write_provider(self, root: Path, *, body: str | None = None) -> Path:
        provider = root / "provider.py"
        provider.write_text(
            body
            or (
                "import json, sys\n"
                "request = json.loads(sys.stdin.read())\n"
                "payload = {\n"
                "  'schema_version': '1.0',\n"
                f"  'id': {DG_ID!r},\n"
                "  'source_id': request['source_id'],\n"
                "  'digest_depth': request['digest_depth'],\n"
                "  'passes_completed': [1, 2, 3, 4],\n"
                "  'author_claims': [{'text': 'provider claim'}],\n"
                "  'direct_evidence': [],\n"
                "  'model_inferences': [],\n"
                "  'boundary_conditions': [],\n"
                "  'alternative_interpretations': [],\n"
                "  'contested_points': [],\n"
                "  'unresolved_ambiguity': [],\n"
                "  'open_questions': [],\n"
                "  'candidate_edges': [{'target_id': 'NEW', 'edge_type': 'SUPPORTS', 'confidence': 'low', 'note': 'candidate'}],\n"
                "  'fidelity_flags': {\n"
                "    'reasoning_chain_preserved': 'yes',\n"
                "    'boundary_conditions_preserved': 'yes',\n"
                "    'alternative_interpretations_preserved': 'yes',\n"
                "    'hidden_assumptions_extracted': 'partial',\n"
                "    'evidence_strength_graded': 'yes'\n"
                "  }\n"
                "}\n"
                "print(json.dumps(payload))\n"
            ),
            encoding="utf-8",
        )
        return provider

    def run_queue(self, root: Path, provider) -> object:
        return run_digest_queue(
            root,
            provider_adapter=provider,
            owner="test-runner",
            current_subject_repo_id="repo_knowledge_topology",
            current_subject_head_sha="abc123",
            current_canonical_rev="rev_current",
            max_jobs=1,
            lease_seconds=30,
        )

    def test_command_provider_runner_closes_ingest_to_digest_loop_without_model_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            init_with_prompts(root)
            source_id = self.make_source(root, text="hello; touch should_not_run\n")
            argv_capture = root / "argv.json"
            provider = self.write_provider(
                root,
                body=(
                    "import json, sys\n"
                    f"open({str(argv_capture)!r}, 'w').write(json.dumps(sys.argv))\n"
                    "request = json.loads(sys.stdin.read())\n"
                    "payload = {\n"
                    "  'schema_version': '1.0',\n"
                    f"  'id': {DG_ID!r},\n"
                    "  'source_id': request['source_id'],\n"
                    "  'digest_depth': request['digest_depth'],\n"
                    "  'passes_completed': [1, 2, 3, 4],\n"
                    "  'author_claims': [{'text': request.get('source_text') or 'none'}],\n"
                    "  'direct_evidence': [], 'model_inferences': [], 'boundary_conditions': [],\n"
                    "  'alternative_interpretations': [], 'contested_points': [],\n"
                    "  'unresolved_ambiguity': [], 'open_questions': [],\n"
                    "  'candidate_edges': [{'target_id': 'NEW', 'edge_type': 'SUPPORTS', 'confidence': 'low', 'note': 'candidate'}],\n"
                    "  'fidelity_flags': {\n"
                    "    'reasoning_chain_preserved': 'yes', 'boundary_conditions_preserved': 'yes',\n"
                    "    'alternative_interpretations_preserved': 'yes', 'hidden_assumptions_extracted': 'partial',\n"
                    "    'evidence_strength_graded': 'yes'}\n"
                    "}\n"
                    "print(json.dumps(payload))\n"
                ),
            )
            adapter = CommandDigestProviderAdapter(f"{sys.executable} {provider} --fixed", cwd=root)
            result = self.run_queue(root, adapter)
            self.assertEqual(result.completed, 1)
            self.assertEqual(result.failed, 0)
            self.assertTrue((root / f"digests/by_source/{source_id}/{DG_ID}.json").exists())
            self.assertEqual(list((root / "ops/queue/digest/pending").glob("*.json")), [])
            self.assertEqual(list((root / "ops/queue/digest/leased").glob("*.json")), [])
            self.assertEqual(len(list((root / "ops/queue/digest/done").glob("*.json"))), 1)
            argv = json.loads(argv_capture.read_text(encoding="utf-8"))
            self.assertNotIn("touch", json.dumps(argv))

    def test_fixture_provider_maps_by_source_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            init_with_prompts(root)
            source_id = self.make_source(root)
            fixture_dir = root / ".tmp/model-outputs"
            fixture_dir.mkdir(parents=True)
            (fixture_dir / f"{source_id}.json").write_text(
                json.dumps(valid_digest_payload(source_id)) + "\n",
                encoding="utf-8",
            )
            result = self.run_queue(root, JsonDirectoryDigestProviderAdapter(fixture_dir, root=root.resolve()))
            self.assertEqual(result.completed, 1)
            self.assertTrue((root / f"digests/by_source/{source_id}/{DG_ID}.md").exists())

    def test_fixture_provider_rejects_parent_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            init_with_prompts(root)
            source_id = self.make_source(root)
            target_parent = root / "target-parent"
            fixture_dir = target_parent / "fixtures"
            fixture_dir.mkdir(parents=True)
            (fixture_dir / f"{source_id}.json").write_text(
                json.dumps(valid_digest_payload(source_id)) + "\n",
                encoding="utf-8",
            )
            link_parent = root / "link-parent"
            link_parent.symlink_to(target_parent, target_is_directory=True)
            result = self.run_queue(root, JsonDirectoryDigestProviderAdapter(link_parent / "fixtures", root=root))
            self.assertEqual(result.completed, 0)
            self.assertEqual(result.failed, 1)
            failed = next((root / "ops/queue/digest/failed").glob("job_*.json"))
            self.assertIn("symlink", read_job(failed)["last_error"])

    def test_provider_failures_move_jobs_to_failed_with_bounded_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_with_prompts(root)
            self.make_source(root)
            provider = self.write_provider(root, body="print('{bad json')\n")
            result = self.run_queue(root, CommandDigestProviderAdapter(f"{sys.executable} {provider}", cwd=root))
            self.assertEqual(result.completed, 0)
            self.assertEqual(result.failed, 1)
            failed = next((root / "ops/queue/digest/failed").glob("job_*.json"))
            job = read_job(failed)
            self.assertIn("JSON", job["last_error"])
            self.assertEqual(list((root / "digests/by_source").glob("src_*")), [])

    def test_stale_or_wrong_subject_jobs_fail_before_provider_invocation(self):
        cases = [
            ("repo_other", "abc123", "rev_current", "subject_repo_id"),
            ("repo_knowledge_topology", "old", "rev_current", "subject_head_sha"),
            ("repo_knowledge_topology", "abc123", "old_rev", "base_canonical_rev"),
        ]
        for subject, head, rev, error in cases:
            with self.subTest(error=error):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    init_with_prompts(root)
                    draft = root / "draft.md"
                    draft.write_text("source text\n", encoding="utf-8")
                    ingest_source(
                        root,
                        str(draft),
                        note="curated",
                        depth="deep",
                        audience="builders",
                        subject_repo_id=subject,
                        subject_head_sha=head,
                        base_canonical_rev=rev,
                        redistributable="yes",
                    )
                    marker = root / "provider-called"
                    provider = self.write_provider(root, body=f"open({str(marker)!r}, 'w').write('called')\nprint('{{}}')\n")
                    result = self.run_queue(root, CommandDigestProviderAdapter(f"{sys.executable} {provider}", cwd=root))
                    self.assertEqual(result.failed, 1)
                    self.assertFalse(marker.exists())
                    failed = next((root / "ops/queue/digest/failed").glob("job_*.json"))
                    self.assertIn(error, read_job(failed)["last_error"])

    def test_expired_leases_requeue_or_fail_before_new_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_with_prompts(root)
            source_id = self.make_source(root)
            leased = lease_next(root, "digest", owner="old", lease_seconds=-1)
            self.assertIsNotNone(leased)
            provider = self.write_provider(root)
            result = self.run_queue(root, CommandDigestProviderAdapter(f"{sys.executable} {provider}", cwd=root))
            self.assertEqual(result.requeued, 1)
            self.assertEqual(result.completed, 1)
            self.assertTrue((root / f"digests/by_source/{source_id}/{DG_ID}.json").exists())

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_with_prompts(root)
            self.make_source(root)
            leased = lease_next(root, "digest", owner="old", lease_seconds=-1)
            job = read_job(leased)
            job["attempts"] = 3
            atomic_write_text(leased, json.dumps(job, indent=2, sort_keys=True) + "\n")
            provider = self.write_provider(root)
            result = run_digest_queue(
                root,
                provider_adapter=CommandDigestProviderAdapter(f"{sys.executable} {provider}", cwd=root),
                owner="test-runner",
                current_subject_repo_id="repo_knowledge_topology",
                current_subject_head_sha="abc123",
                current_canonical_rev="rev_current",
                max_jobs=1,
                max_attempts=3,
            )
            self.assertEqual(result.failed, 1)
            self.assertEqual(result.leased, 0)
            self.assertEqual(len(list((root / "ops/queue/digest/failed").glob("job_*.json"))), 1)

    def test_existing_digest_artifact_fails_duplicate_job_before_provider_invocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            init_with_prompts(root)
            source_id = self.make_source(root)
            provider = self.write_provider(root)
            first = self.run_queue(root, CommandDigestProviderAdapter(f"{sys.executable} {provider}", cwd=root))
            self.assertEqual(first.completed, 1)
            marker = root / "provider-called-again"
            second_provider = self.write_provider(
                root,
                body=f"open({str(marker)!r}, 'w').write('called')\nprint('{{}}')\n",
            )
            create_job(
                root,
                "digest",
                payload={"source_id": source_id, "audience": "builders"},
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                base_canonical_rev="rev_current",
                created_by="test",
            )
            second = self.run_queue(
                root,
                CommandDigestProviderAdapter(f"{sys.executable} {second_provider}", cwd=root),
            )
            self.assertEqual(second.completed, 0)
            self.assertEqual(second.failed, 1)
            self.assertFalse(marker.exists())
            failed = next((root / "ops/queue/digest/failed").glob("job_*.json"))
            self.assertIn("already exists", read_job(failed)["last_error"])

    def test_concurrent_duplicate_jobs_cannot_write_multiple_digests(self):
        class BarrierProvider:
            def __init__(self, barrier: threading.Barrier, digest_id: str):
                self.barrier = barrier
                self.digest_id = digest_id

            def generate(self, request):
                self.barrier.wait(timeout=5)
                return valid_digest_payload(request.source_id, digest_id=self.digest_id)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            init_with_prompts(root)
            source_id = self.make_source(root)
            create_job(
                root,
                "digest",
                payload={"source_id": source_id, "audience": "builders"},
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                base_canonical_rev="rev_current",
                created_by="test",
            )
            barrier = threading.Barrier(2)
            results = []
            errors = []

            def run(provider, owner):
                try:
                    results.append(run_digest_queue(
                        root,
                        provider_adapter=provider,
                        owner=owner,
                        current_subject_repo_id="repo_knowledge_topology",
                        current_subject_head_sha="abc123",
                        current_canonical_rev="rev_current",
                        max_jobs=1,
                    ))
                except Exception as exc:
                    errors.append(exc)

            first_id = "dg_00000000000000000000000001"
            second_id = "dg_00000000000000000000000002"
            threads = [
                threading.Thread(target=run, args=(BarrierProvider(barrier, first_id), "runner-1")),
                threading.Thread(target=run, args=(BarrierProvider(barrier, second_id), "runner-2")),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
            self.assertEqual(errors, [])
            self.assertEqual(sum(result.completed for result in results), 1)
            self.assertEqual(sum(result.failed for result in results), 1)
            self.assertEqual(len(list((root / f"digests/by_source/{source_id}").glob("*.json"))), 1)

    def test_prompt_request_redacts_paths_and_rejects_symlinked_source_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_with_prompts(root)
            source_id = self.make_source(root, text="public source\n")
            request = build_digest_model_request(root, source_id)
            serialized = json.dumps(request.to_dict(), sort_keys=True)
            self.assertIn("public source", serialized)
            self.assertNotIn(str(root / "draft.md"), serialized)

            packet = root / f"raw/packets/{source_id}/packet.json"
            payload = json.loads(packet.read_text(encoding="utf-8"))
            payload["artifacts"].append({"kind": "excerpt", "path": "../canonical/registry/nodes.jsonl", "note": "bad"})
            packet.write_text(json.dumps(payload), encoding="utf-8")
            request = build_digest_model_request(root, source_id)
            self.assertNotIn("../canonical", json.dumps(request.to_dict(), sort_keys=True))

            content = root / f"raw/packets/{source_id}/content.md"
            content.unlink()
            content.symlink_to(root / "canonical/registry/nodes.jsonl")
            with self.assertRaises(DigestWorkerError):
                build_digest_model_request(root, source_id)

    def test_prompt_request_rejects_raw_packets_parent_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            init_with_prompts(root)
            source_id = self.make_source(root, text="public source\n")
            packet_dir = root / f"raw/packets/{source_id}"
            fake_packets = root / "canonical/registry/fake_packets"
            fake_packet_dir = fake_packets / source_id
            fake_packet_dir.mkdir(parents=True)
            for path in packet_dir.iterdir():
                target = fake_packet_dir / path.name
                target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
                path.unlink()
            packet_dir.rmdir()
            packets_dir = root / "raw/packets"
            packets_dir.rmdir()
            packets_dir.symlink_to(fake_packets, target_is_directory=True)
            with self.assertRaisesRegex(DigestWorkerError, "parent path is unsafe"):
                build_digest_model_request(root, source_id)

    def test_local_blob_request_is_metadata_only_without_storage_hint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_with_prompts(root)
            source_id = self.make_source(
                root,
                value="https://arxiv.org/pdf/2401.00001.pdf",
                depth="scan",
                content_mode="local_blob",
                redistributable="unknown",
                source_type="pdf_arxiv",
            )
            request = build_digest_model_request(root, source_id)
            serialized = json.dumps(request.to_dict(), sort_keys=True)
            self.assertIsNone(request.source_text)
            self.assertNotIn("raw/local_blobs", serialized)
            self.assertNotIn("storage_hint", serialized)

    def test_cli_digest_queue_smoke_and_mode_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_with_prompts(root)
            source_id = self.make_source(root)
            provider = self.write_provider(root)
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
                    "--run-queue",
                    "--owner",
                    "cli-runner",
                    "--subject",
                    "repo_knowledge_topology",
                    "--current-canonical-rev",
                    "rev_current",
                    "--current-subject-head-sha",
                    "abc123",
                    "--provider-command",
                    f"{sys.executable} {provider}",
                ],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("digest jobs completed: 1", result.stdout)
            self.assertTrue((root / f"digests/by_source/{source_id}/{DG_ID}.json").exists())

            invalid = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "knowledge_topology.cli",
                    "digest",
                    "--root",
                    tmp,
                    "--owner",
                    "legacy-bad",
                ],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(invalid.returncode, 2)
            self.assertIn("queue-only arguments require --run-queue", invalid.stderr)

    def test_prompt_files_require_json_only_and_no_canonical_writes(self):
        for prompt in [ROOT / "prompts/digest_deep.md", ROOT / "prompts/digest_standard.md"]:
            text = prompt.read_text(encoding="utf-8")
            self.assertIn("Never write canonical state", text)
            self.assertIn("Emit one JSON object only", text)


if __name__ == "__main__":
    unittest.main()

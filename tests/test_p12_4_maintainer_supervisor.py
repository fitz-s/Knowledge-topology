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
from knowledge_topology.storage.spool import create_job, lease_next, read_job
from knowledge_topology.storage.transaction import atomic_write_text
from knowledge_topology.subjects import add_subject, refresh_subject
from knowledge_topology.workers.fetch import ingest_source
from knowledge_topology.workers.init import init_topology
from knowledge_topology.workers.supervisor import run_supervisor


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


class P12MaintainerSupervisorTests(unittest.TestCase):
    def make_topology(self) -> tuple[tempfile.TemporaryDirectory, Path, Path, str]:
        tmp = tempfile.TemporaryDirectory()
        base = Path(tmp.name)
        root = base / "topology"
        subject = base / "subject"
        subject.mkdir(parents=True)
        (subject / "README.md").write_text("subject\n", encoding="utf-8")
        subject_head = init_git(subject)
        init_topology(root)
        for prompt in ["digest_deep.md", "digest_standard.md"]:
            (root / "prompts" / prompt).write_text((ROOT / "prompts" / prompt).read_text(encoding="utf-8"), encoding="utf-8")
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
        init_git(root)
        return tmp, root, subject, subject_head

    def make_source(self, root: Path, *, base_rev: str, subject_head: str) -> str:
        draft = root / "draft.md"
        draft.write_text("source text\n", encoding="utf-8")
        result = ingest_source(
            root,
            str(draft),
            note="curated",
            depth="deep",
            audience="builders",
            subject_repo_id="repo_subject",
            subject_head_sha=subject_head,
            base_canonical_rev=base_rev,
            redistributable="yes",
        )
        return result.packet_id

    def write_provider(self, root: Path, *, body: str) -> Path:
        provider = root / "provider.py"
        provider.write_text(body, encoding="utf-8")
        return provider

    def provider_body(self, *, author_claims: str, candidate_edges: str) -> str:
        return (
            "import json, sys\n"
            "request = json.loads(sys.stdin.read())\n"
            "payload = {\n"
            "  'schema_version': '1.0',\n"
            "  'id': 'dg_00000000000000000000000000',\n"
            "  'source_id': request['source_id'],\n"
            "  'digest_depth': request['digest_depth'],\n"
            "  'passes_completed': [1, 2, 3, 4],\n"
            f"  'author_claims': {author_claims},\n"
            "  'direct_evidence': [], 'model_inferences': [], 'boundary_conditions': [],\n"
            "  'alternative_interpretations': [], 'contested_points': [],\n"
            "  'unresolved_ambiguity': [], 'open_questions': [],\n"
            f"  'candidate_edges': {candidate_edges},\n"
            "  'fidelity_flags': {\n"
            "    'reasoning_chain_preserved': 'yes', 'boundary_conditions_preserved': 'yes',\n"
            "    'alternative_interpretations_preserved': 'yes', 'hidden_assumptions_extracted': 'partial',\n"
            "    'evidence_strength_graded': 'yes'}\n"
            "}\n"
            "print(json.dumps(payload))\n"
        )

    def test_supervisor_runs_digest_and_reconcile_but_escalates_builder_active_pack(self):
        tmp, root, _subject, subject_head = self.make_topology()
        with tmp:
            base_rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
            self.make_source(root, base_rev=base_rev, subject_head=subject_head)
            provider = self.write_provider(
                root,
                body=self.provider_body(
                    author_claims="[{'text': 'provider claim'}]",
                    candidate_edges="[{'target_id': 'NEW', 'edge_type': 'SUPPORTS', 'confidence': 'low', 'note': 'candidate'}]",
                ),
            )
            result = run_supervisor(
                root,
                subject_repo_id="repo_subject",
                digest_provider_command=f"{sys.executable} {provider}",
                max_digest_jobs=1,
            )
            self.assertEqual(result.payload["digest_queue"]["completed"], 1)
            self.assertEqual(len(result.payload["reconciled_mutations"]), 1)
            self.assertEqual(result.payload["applied_mutations"], [])
            self.assertEqual(len(result.payload["skipped_mutations"]), 1)
            self.assertIsNotNone(result.escalation_path)
            self.assertTrue(result.report_path.exists())
            self.assertIn("human_gate_required", json.dumps(result.payload["escalations"]))
            report_text = result.report_path.read_text(encoding="utf-8")
            escalation_text = result.escalation_path.read_text(encoding="utf-8")
            self.assertNotIn(str(root), report_text)
            self.assertNotIn(str(root.resolve()), report_text)
            self.assertNotIn(str(root), escalation_text)
            self.assertNotIn(str(root.resolve()), escalation_text)
            self.assertEqual(list((root / "mutations/applied").glob("mut_*.json")), [])

    def test_supervisor_auto_applies_only_open_gap_pack_when_enabled(self):
        tmp, root, _subject, subject_head = self.make_topology()
        with tmp:
            base_rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
            self.make_source(root, base_rev=base_rev, subject_head=subject_head)
            unknown_node = new_id("nd")
            provider = self.write_provider(
                root,
                body=self.provider_body(
                    author_claims="[]",
                    candidate_edges=f"[{{'target_id': {unknown_node!r}, 'edge_type': 'SUPPORTS', 'confidence': 'low', 'note': 'unknown target'}}]",
                ),
            )
            first = run_supervisor(
                root,
                subject_repo_id="repo_subject",
                digest_provider_command=f"{sys.executable} {provider}",
                max_digest_jobs=1,
                auto_apply_low_risk=True,
            )
            self.assertEqual(len(first.payload["applied_mutations"]), 1)
            self.assertEqual(first.payload["skipped_mutations"], [])
            self.assertEqual(len(list((root / "mutations/applied").glob("mut_*.json"))), 1)
            self.assertTrue((root / "ops/gaps/open.jsonl").exists())
            self.assertEqual((root / "canonical/registry/nodes.jsonl").read_text(encoding="utf-8"), "")

    def test_supervisor_skips_digest_without_current_done_job_binding(self):
        tmp, root, _subject, subject_head = self.make_topology()
        with tmp:
            base_rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
            source_id = self.make_source(root, base_rev=base_rev, subject_head=subject_head)
            digest_dir = root / "digests/by_source" / source_id
            digest_dir.mkdir(parents=True)
            (digest_dir / "dg_00000000000000000000000000.json").write_text(
                json.dumps({
                    "schema_version": "1.0",
                    "id": "dg_00000000000000000000000000",
                    "source_id": source_id,
                    "digest_depth": "deep",
                    "passes_completed": [1, 2, 3, 4],
                    "author_claims": [{"text": "stale claim"}],
                    "direct_evidence": [],
                    "model_inferences": [],
                    "boundary_conditions": [],
                    "alternative_interpretations": [],
                    "contested_points": [],
                    "unresolved_ambiguity": [],
                    "open_questions": [],
                    "candidate_edges": [],
                    "fidelity_flags": {
                        "reasoning_chain_preserved": "yes",
                        "boundary_conditions_preserved": "yes",
                        "alternative_interpretations_preserved": "yes",
                        "hidden_assumptions_extracted": "partial",
                        "evidence_strength_graded": "yes",
                    },
                }),
                encoding="utf-8",
            )
            result = run_supervisor(root, subject_repo_id="repo_subject", max_digest_jobs=0)
            self.assertEqual(result.payload["reconciled_mutations"], [])
            self.assertEqual(list((root / "mutations/pending").glob("mut_*.json")), [])
            self.assertIn("stale_digest_skipped", json.dumps(result.payload["escalations"]))

    def test_supervisor_requires_done_job_to_match_specific_digest_id(self):
        tmp, root, _subject, subject_head = self.make_topology()
        with tmp:
            base_rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
            source_id = self.make_source(root, base_rev=base_rev, subject_head=subject_head)
            provider = self.write_provider(
                root,
                body=self.provider_body(
                    author_claims="[]",
                    candidate_edges=f"[{{'target_id': {new_id('nd')!r}, 'edge_type': 'SUPPORTS', 'confidence': 'low', 'note': 'current unknown target'}}]",
                ),
            )
            first = run_supervisor(
                root,
                subject_repo_id="repo_subject",
                digest_provider_command=f"{sys.executable} {provider}",
                max_digest_jobs=1,
                max_reconcile=0,
            )
            self.assertEqual(first.payload["digest_queue"]["completed"], 1)
            stale_digest_id = new_id("dg")
            digest_dir = root / "digests/by_source" / source_id
            (digest_dir / f"{stale_digest_id}.json").write_text(
                json.dumps({
                    "schema_version": "1.0",
                    "id": stale_digest_id,
                    "source_id": source_id,
                    "digest_depth": "deep",
                    "passes_completed": [1, 2, 3, 4],
                    "author_claims": [{"text": "stale sibling claim"}],
                    "direct_evidence": [],
                    "model_inferences": [],
                    "boundary_conditions": [],
                    "alternative_interpretations": [],
                    "contested_points": [],
                    "unresolved_ambiguity": [],
                    "open_questions": [],
                    "candidate_edges": [],
                    "fidelity_flags": {
                        "reasoning_chain_preserved": "yes",
                        "boundary_conditions_preserved": "yes",
                        "alternative_interpretations_preserved": "yes",
                        "hidden_assumptions_extracted": "partial",
                        "evidence_strength_graded": "yes",
                    },
                }),
                encoding="utf-8",
            )
            second = run_supervisor(root, subject_repo_id="repo_subject", max_digest_jobs=0)
            self.assertEqual(len(second.payload["reconciled_mutations"]), 1)
            mutation = json.loads((root / second.payload["reconciled_mutations"][0]).read_text(encoding="utf-8"))
            self.assertEqual(mutation["metadata"]["digest_id"], "dg_00000000000000000000000000")
            self.assertIn("stale_digest_skipped", json.dumps(second.payload["escalations"]))

    def test_supervisor_recovers_expired_leases_and_reports_bad_jobs(self):
        tmp, root, _subject, subject_head = self.make_topology()
        with tmp:
            base_rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
            create_job(
                root,
                "writeback",
                payload={"kind": "retry"},
                subject_repo_id="repo_subject",
                subject_head_sha=subject_head,
                base_canonical_rev=base_rev,
                created_by="test",
            )
            lease_next(root, "writeback", owner="old", lease_seconds=-1)
            create_job(
                root,
                "audit",
                payload={"kind": "fail"},
                subject_repo_id="repo_subject",
                subject_head_sha=subject_head,
                base_canonical_rev=base_rev,
                created_by="test",
            )
            expired_fail = lease_next(root, "audit", owner="old", lease_seconds=-1)
            job = read_job(expired_fail)
            job["attempts"] = 3
            atomic_write_text(expired_fail, json.dumps(job, indent=2, sort_keys=True) + "\n")
            bad = root / "ops/queue/compile/leased" / f"{new_id('job')}.json"
            bad.write_text("{bad json", encoding="utf-8")
            result = run_supervisor(root, subject_repo_id="repo_subject", max_digest_jobs=0, max_attempts=3)
            self.assertEqual(result.payload["lease_recovery"]["requeued"], 1)
            self.assertEqual(result.payload["lease_recovery"]["failed"], 1)
            self.assertTrue(list((root / "ops/queue/writeback/pending").glob("job_*.json")))
            self.assertTrue(list((root / "ops/queue/audit/failed").glob("job_*.json")))
            self.assertIn("lease_recovery_errors", json.dumps(result.payload["escalations"]))
            report_text = result.report_path.read_text(encoding="utf-8")
            escalation_text = result.escalation_path.read_text(encoding="utf-8")
            self.assertNotIn(str(root), report_text)
            self.assertNotIn(str(root.resolve()), report_text)
            self.assertNotIn(str(root), escalation_text)
            self.assertNotIn(str(root.resolve()), escalation_text)

    def test_supervisor_skips_digest_provider_when_digest_recovery_has_bad_job(self):
        tmp, root, _subject, _subject_head = self.make_topology()
        with tmp:
            bad = root / "ops/queue/digest/leased" / f"{new_id('job')}.json"
            bad.write_text("{bad json", encoding="utf-8")
            output_dir = root / ".tmp/model-outputs"
            output_dir.mkdir(parents=True)
            result = run_supervisor(root, subject_repo_id="repo_subject", model_output_dir=str(output_dir.resolve()))
            self.assertEqual(result.payload["digest_queue"]["leased"], 0)
            self.assertEqual(result.payload["digest_queue"]["completed"], 0)
            self.assertIn("lease_recovery_errors", json.dumps(result.payload["escalations"]))
            self.assertIn("digest", result.payload["lease_recovery"]["blocked_queue_kinds"])

    def test_supervisor_skips_digest_provider_for_symlinked_bad_digest_lease(self):
        tmp, root, _subject, _subject_head = self.make_topology()
        with tmp:
            outside = root.parent / "outside_bad.json"
            outside.write_text("{bad json", encoding="utf-8")
            bad = root / "ops/queue/digest/leased" / f"{new_id('job')}.json"
            bad.symlink_to(outside)
            output_dir = root / ".tmp/model-outputs"
            output_dir.mkdir(parents=True)
            result = run_supervisor(root, subject_repo_id="repo_subject", model_output_dir=str(output_dir.resolve()))
            self.assertEqual(result.payload["digest_queue"]["leased"], 0)
            self.assertIn("digest", result.payload["lease_recovery"]["blocked_queue_kinds"])
            self.assertIn("lease_recovery_errors", json.dumps(result.payload["escalations"]))

    def test_supervisor_sanitizes_projection_errors(self):
        tmp, root, subject, _subject_head = self.make_topology()
        with tmp:
            target = root.parent / "outside_projection"
            target.mkdir()
            openclaw = root / "projections/openclaw"
            openclaw.rmdir()
            openclaw.symlink_to(target, target_is_directory=True)
            subprocess.run(["git", "add", "-A"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "track projection symlink"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            result = run_supervisor(
                root,
                subject_repo_id="repo_subject",
                openclaw_project_id="proj",
                subject_path=subject,
            )
            payload_text = json.dumps(result.payload)
            report_text = result.report_path.read_text(encoding="utf-8")
            self.assertIn("projection_error", payload_text)
            self.assertNotIn(str(root), payload_text)
            self.assertNotIn(str(root.resolve()), payload_text)
            self.assertNotIn(str(root), report_text)
            self.assertNotIn(str(root.resolve()), report_text)

    def test_supervisor_cli_smoke_uses_model_output_dir(self):
        tmp, root, _subject, subject_head = self.make_topology()
        with tmp:
            base_rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
            source_id = self.make_source(root, base_rev=base_rev, subject_head=subject_head)
            output_dir = root / ".tmp/model-outputs"
            output_dir.mkdir(parents=True)
            (output_dir / f"{source_id}.json").write_text(
                json.dumps({
                    "schema_version": "1.0",
                    "id": "dg_00000000000000000000000000",
                    "source_id": source_id,
                    "digest_depth": "deep",
                    "passes_completed": [1, 2, 3, 4],
                    "author_claims": [],
                    "direct_evidence": [],
                    "model_inferences": [],
                    "boundary_conditions": [],
                    "alternative_interpretations": [],
                    "contested_points": [],
                    "unresolved_ambiguity": [],
                    "open_questions": [],
                    "candidate_edges": [],
                    "fidelity_flags": {
                        "reasoning_chain_preserved": "yes",
                        "boundary_conditions_preserved": "yes",
                        "alternative_interpretations_preserved": "yes",
                        "hidden_assumptions_extracted": "partial",
                        "evidence_strength_graded": "yes",
                    },
                }),
                encoding="utf-8",
            )
            result = cli(
                "supervisor",
                "run",
                "--root",
                str(root),
                "--subject",
                "repo_subject",
                "--model-output-dir",
                str(output_dir.resolve()),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["digest_queue"]["completed"], 1)
            self.assertTrue((root / payload["report_path"]).exists() if not Path(payload["report_path"]).is_absolute() else Path(payload["report_path"]).exists())


if __name__ == "__main__":
    unittest.main()

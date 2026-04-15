import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from support_subjects import seed_subject_registry
from knowledge_topology.adapters.openclaw_live import OpenClawLiveError
from knowledge_topology.adapters.openclaw_live import canonical_json
from knowledge_topology.adapters.openclaw_live import create_runtime_source_packet
from knowledge_topology.adapters.openclaw_live import issue_openclaw_live_lease
from knowledge_topology.adapters.openclaw_live import lease_openclaw_live_job
from knowledge_topology.adapters.openclaw_live import run_openclaw_live_writeback
from knowledge_topology.adapters.openclaw_live import summary_hash
from knowledge_topology.ids import new_id
from knowledge_topology.storage.spool import lease_next
from knowledge_topology.storage.transaction import atomic_write_text
from knowledge_topology.workers.compose_openclaw import write_openclaw_projection
from knowledge_topology.workers.init import init_topology


FIXED_TIME = "2026-04-14T00:00:00Z"


class P11OpenClawLiveTests(unittest.TestCase):
    def seed_projection(self, root: Path) -> None:
        init_topology(root)
        seed_subject_registry(root)
        node = {
            "id": new_id("nd"),
            "type": "decision",
            "status": "active",
            "authority": "runtime_observed",
            "scope": "runtime",
            "sensitivity": "runtime_only",
            "audiences": ["openclaw"],
            "confidence": "low",
        }
        (root / "canonical/registry/nodes.jsonl").write_text(json.dumps(node) + "\n", encoding="utf-8")
        write_openclaw_projection(
            root,
            project_id="openclaw_project",
            canonical_rev="rev_current",
            subject_repo_id="repo_knowledge_topology",
            subject_head_sha="abc123",
            allow_dirty=True,
            clock=lambda: FIXED_TIME,
        )

    def make_summary(self, source_id: str, digest_id: str) -> dict:
        return {
            "source_id": source_id,
            "digest_id": digest_id,
            "runtime_assumptions": [
                {"statement": "Runtime observed a safe maintainer fact.", "observed_in": "runtime-pack"}
            ],
            "task_lessons": [
                {"lesson": "Runtime summaries must remain proposal-only.", "applies_to": "openclaw runtime"}
            ],
        }

    def write_bound_evidence(self, root: Path, summary: dict, job_id: str) -> tuple[str, str]:
        source_id = summary["source_id"]
        digest_id = summary["digest_id"]
        digest = summary_hash(summary)
        packet_dir = root / "raw/packets" / source_id
        packet_dir.mkdir(parents=True, exist_ok=True)
        packet = {
            "schema_version": "1.0",
            "id": source_id,
            "source_type": "local_draft",
            "original_url": "openclaw-runtime:test",
            "canonical_url": None,
            "retrieved_at": FIXED_TIME,
            "curator_note": "runtime summary evidence",
            "ingest_depth": "standard",
            "authority": "runtime_observed",
            "trust_scope": "runtime",
            "content_status": "partial",
            "content_mode": "excerpt_only",
            "redistributable": "no",
            "hash_original": None,
            "hash_normalized": "sha256:runtime",
            "artifacts": [
                {
                    "kind": "runtime_summary_evidence",
                    "runtime_summary_hash": digest,
                    "openclaw_live_job_id": job_id,
                }
            ],
            "fetch_chain": [{"method": "runtime", "status": "partial", "note": "runtime evidence"}],
        }
        atomic_write_text(packet_dir / "packet.json", json.dumps(packet, indent=2, sort_keys=True) + "\n")
        digest_dir = root / "digests/by_source" / source_id
        digest_dir.mkdir(parents=True, exist_ok=True)
        digest_payload = {
            "schema_version": "1.0",
            "id": digest_id,
            "source_id": source_id,
            "digest_depth": "standard",
            "passes_completed": [1, 2],
            "author_claims": [],
            "direct_evidence": [
                {
                    "kind": "runtime_summary_evidence",
                    "runtime_summary_hash": digest,
                    "openclaw_live_job_id": job_id,
                }
            ],
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
        }
        atomic_write_text(digest_dir / f"{digest_id}.json", json.dumps(digest_payload, indent=2, sort_keys=True) + "\n")
        return source_id, digest_id

    def issue_and_lease(self, root: Path, summary: dict) -> Path:
        issue_openclaw_live_lease(
            root,
            project_id="openclaw_project",
            canonical_rev="rev_current",
            subject_repo_id="repo_knowledge_topology",
            subject_head_sha="abc123",
            runtime_summary=summary,
        )
        return lease_openclaw_live_job(root, owner="openclaw-live", lease_seconds=300)

    def write_summary_file(self, root: Path, summary: dict, name: str = "summary.json") -> Path:
        path = root / ".openclaw/private/session" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def test_live_writeback_creates_runtime_observation_and_consumes_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.seed_projection(root)
            source_id = new_id("src")
            digest_id = new_id("dg")
            summary = self.make_summary(source_id, digest_id)
            lease = self.issue_and_lease(root, summary)
            self.write_bound_evidence(root, summary, lease.stem)
            summary_path = self.write_summary_file(root, summary)
            canonical_before = (root / "canonical/registry/nodes.jsonl").read_text(encoding="utf-8")

            result = run_openclaw_live_writeback(
                root,
                project_id="openclaw_project",
                canonical_rev="rev_current",
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                lease_path=lease,
                runtime_summary_path=summary_path,
            )
            mutation = json.loads(result.mutation_path.read_text(encoding="utf-8"))
            runtime_change = next(change for change in mutation["changes"] if change["type"] == "runtime_observation")
            self.assertEqual(runtime_change["authority"], "runtime_observed")
            self.assertEqual(runtime_change["scope"], "runtime")
            self.assertEqual(runtime_change["sensitivity"], "runtime_only")
            self.assertEqual(runtime_change["audiences"], ["openclaw"])
            self.assertEqual(mutation["metadata"]["openclaw_live_job_id"], lease.stem)
            self.assertNotIn(".openclaw", mutation["metadata"]["writeback_summary"])
            self.assertEqual((root / "canonical/registry/nodes.jsonl").read_text(encoding="utf-8"), canonical_before)
            self.assertTrue((root / "ops/queue/writeback/done" / lease.name).exists())

    def test_live_writeback_rejects_unrelated_real_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.seed_projection(root)
            source_id = new_id("src")
            digest_id = new_id("dg")
            summary = self.make_summary(source_id, digest_id)
            lease = self.issue_and_lease(root, summary)
            wrong = dict(summary)
            wrong["runtime_assumptions"] = [{"statement": "Different summary.", "observed_in": "runtime-pack"}]
            self.write_bound_evidence(root, wrong, lease.stem)
            summary_path = self.write_summary_file(root, summary)
            with self.assertRaisesRegex(OpenClawLiveError, "not bound"):
                run_openclaw_live_writeback(
                    root,
                    project_id="openclaw_project",
                    canonical_rev="rev_current",
                    subject_repo_id="repo_knowledge_topology",
                    subject_head_sha="abc123",
                    lease_path=lease,
                    runtime_summary_path=summary_path,
                )
            self.assertEqual(list((root / "mutations/pending").glob("mut_*.json")), [])

    def test_private_summary_fields_are_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.seed_projection(root)
            source_id = new_id("src")
            digest_id = new_id("dg")
            summary = self.make_summary(source_id, digest_id)
            lease = self.issue_and_lease(root, summary)
            self.write_bound_evidence(root, summary, lease.stem)
            summary["runtime_assumptions"][0]["statement"] = "see .openclaw/session token"
            summary_path = self.write_summary_file(root, summary)
            with self.assertRaisesRegex(OpenClawLiveError, "private OpenClaw"):
                run_openclaw_live_writeback(
                    root,
                    project_id="openclaw_project",
                    canonical_rev="rev_current",
                    subject_repo_id="repo_knowledge_topology",
                    subject_head_sha="abc123",
                    lease_path=lease,
                    runtime_summary_path=summary_path,
                )
            self.assertEqual(list((root / "mutations/pending").glob("mut_*.json")), [])

    def test_issue_and_capture_reject_private_summary_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.seed_projection(root)
            summary = self.make_summary(new_id("src"), new_id("dg"))
            summary["runtime_assumptions"][0]["statement"] = "/Users/test/.openclaw/session/token-secret"
            with self.assertRaisesRegex(OpenClawLiveError, "private path|private OpenClaw"):
                issue_openclaw_live_lease(
                    root,
                    project_id="openclaw_project",
                    canonical_rev="rev_current",
                    subject_repo_id="repo_knowledge_topology",
                    subject_head_sha="abc123",
                    runtime_summary=summary,
                )
            with self.assertRaisesRegex(OpenClawLiveError, "private path|private OpenClaw"):
                create_runtime_source_packet(
                    root,
                    project_id="openclaw_project",
                    canonical_rev="rev_current",
                    subject_repo_id="repo_knowledge_topology",
                    subject_head_sha="abc123",
                    runtime_summary=summary,
                )
            self.assertEqual(list((root / "ops/queue/writeback/pending").glob("job_*.json")), [])
            self.assertEqual(list((root / "ops/queue/digest/pending").glob("job_*.json")), [])
            self.assertEqual(list((root / "raw/packets").glob("src_*")), [])

    def test_fabricated_lease_and_replay_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.seed_projection(root)
            source_id = new_id("src")
            digest_id = new_id("dg")
            summary = self.make_summary(source_id, digest_id)
            lease = root / "ops/queue/writeback/leased" / f"{new_id('job')}.json"
            lease.write_text(json.dumps({
                "schema_version": "1.0",
                "id": lease.stem,
                "kind": "writeback",
                "subject_repo_id": "repo_knowledge_topology",
                "subject_head_sha": "abc123",
                "base_canonical_rev": "rev_current",
                "payload": {
                    "issuer": "topology_openclaw_live",
                    "lease_nonce": "fake",
                    "runtime_summary_hash": summary_hash(summary),
                    "project_id": "openclaw_project",
                },
                "lease_owner": "openclaw-live",
                "leased_at": FIXED_TIME,
                "lease_expires_at": "2999-01-01T00:00:00Z",
            }), encoding="utf-8")
            summary_path = self.write_summary_file(root, summary)
            with self.assertRaisesRegex(OpenClawLiveError, "issued lease entry missing"):
                run_openclaw_live_writeback(
                    root,
                    project_id="openclaw_project",
                    canonical_rev="rev_current",
                    subject_repo_id="repo_knowledge_topology",
                    subject_head_sha="abc123",
                    lease_path=lease,
                    runtime_summary_path=summary_path,
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.seed_projection(root)
            source_id = new_id("src")
            digest_id = new_id("dg")
            summary = self.make_summary(source_id, digest_id)
            pending = issue_openclaw_live_lease(
                root,
                project_id="openclaw_project",
                canonical_rev="rev_current",
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                runtime_summary=summary,
            )
            forged = root / "ops/queue/writeback/leased" / pending.name
            forged.write_text(pending.read_text(encoding="utf-8"), encoding="utf-8")
            job = json.loads(forged.read_text(encoding="utf-8"))
            job["lease_owner"] = "openclaw-live"
            job["leased_at"] = FIXED_TIME
            job["lease_expires_at"] = "2999-01-01T00:00:00Z"
            forged.write_text(json.dumps(job), encoding="utf-8")
            self.write_bound_evidence(root, summary, forged.stem)
            summary_path = self.write_summary_file(root, summary)
            with self.assertRaisesRegex(OpenClawLiveError, "not leased by topology"):
                run_openclaw_live_writeback(
                    root,
                    project_id="openclaw_project",
                    canonical_rev="rev_current",
                    subject_repo_id="repo_knowledge_topology",
                    subject_head_sha="abc123",
                    lease_path=forged,
                    runtime_summary_path=summary_path,
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.seed_projection(root)
            source_id = new_id("src")
            digest_id = new_id("dg")
            summary = self.make_summary(source_id, digest_id)
            lease = self.issue_and_lease(root, summary)
            copied = lease.parent / f"{new_id('job')}.json"
            copied.write_text(lease.read_text(encoding="utf-8"), encoding="utf-8")
            self.write_bound_evidence(root, summary, lease.stem)
            summary_path = self.write_summary_file(root, summary)
            with self.assertRaisesRegex(OpenClawLiveError, "filename"):
                run_openclaw_live_writeback(
                    root,
                    project_id="openclaw_project",
                    canonical_rev="rev_current",
                    subject_repo_id="repo_knowledge_topology",
                    subject_head_sha="abc123",
                    lease_path=copied,
                    runtime_summary_path=summary_path,
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.seed_projection(root)
            source_id = new_id("src")
            digest_id = new_id("dg")
            summary = self.make_summary(source_id, digest_id)
            lease = self.issue_and_lease(root, summary)
            self.write_bound_evidence(root, summary, lease.stem)
            summary_path = self.write_summary_file(root, summary)
            result = run_openclaw_live_writeback(
                root,
                project_id="openclaw_project",
                canonical_rev="rev_current",
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                lease_path=lease,
                runtime_summary_path=summary_path,
            )
            with self.assertRaisesRegex(OpenClawLiveError, "leased"):
                run_openclaw_live_writeback(
                    root,
                    project_id="openclaw_project",
                    canonical_rev="rev_current",
                    subject_repo_id="repo_knowledge_topology",
                    subject_head_sha="abc123",
                    lease_path=result.lease_path,
                    runtime_summary_path=summary_path,
                )

    def test_partial_success_recovery_does_not_duplicate_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.seed_projection(root)
            source_id = new_id("src")
            digest_id = new_id("dg")
            summary = self.make_summary(source_id, digest_id)
            lease = self.issue_and_lease(root, summary)
            self.write_bound_evidence(root, summary, lease.stem)
            summary_path = self.write_summary_file(root, summary)
            with self.assertRaisesRegex(OpenClawLiveError, "injected failure"):
                run_openclaw_live_writeback(
                    root,
                    project_id="openclaw_project",
                    canonical_rev="rev_current",
                    subject_repo_id="repo_knowledge_topology",
                    subject_head_sha="abc123",
                    lease_path=lease,
                    runtime_summary_path=summary_path,
                    fail_after_write=True,
                )
            first_pending = list((root / "mutations/pending").glob("mut_*.json"))
            self.assertEqual(len(first_pending), 1)
            result = run_openclaw_live_writeback(
                root,
                project_id="openclaw_project",
                canonical_rev="rev_current",
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                lease_path=lease,
                runtime_summary_path=summary_path,
            )
            self.assertEqual(result.mutation_path.resolve(), first_pending[0].resolve())
            self.assertEqual(len(list((root / "mutations/pending").glob("mut_*.json"))), 1)
            self.assertTrue((root / "ops/queue/writeback/done" / lease.name).exists())

    def test_stale_projection_and_manifest_traversal_fail_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.seed_projection(root)
            source_id = new_id("src")
            digest_id = new_id("dg")
            summary = self.make_summary(source_id, digest_id)
            lease = self.issue_and_lease(root, summary)
            self.write_bound_evidence(root, summary, lease.stem)
            summary_path = self.write_summary_file(root, summary)
            runtime_pack = root / "projections/openclaw/runtime-pack.json"
            payload = json.loads(runtime_pack.read_text(encoding="utf-8"))
            payload["canonical_rev"] = "old"
            runtime_pack.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(OpenClawLiveError, "runtime pack canonical_rev mismatch"):
                run_openclaw_live_writeback(
                    root,
                    project_id="openclaw_project",
                    canonical_rev="rev_current",
                    subject_repo_id="repo_knowledge_topology",
                    subject_head_sha="abc123",
                    lease_path=lease,
                    runtime_summary_path=summary_path,
                )
            self.assertEqual(list((root / "mutations/pending").glob("mut_*.json")), [])

    def test_lease_symlink_and_projection_files_are_preflighted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.seed_projection(root)
            source_id = new_id("src")
            digest_id = new_id("dg")
            summary = self.make_summary(source_id, digest_id)
            lease = self.issue_and_lease(root, summary)
            self.write_bound_evidence(root, summary, lease.stem)
            summary_path = self.write_summary_file(root, summary)
            outside = Path(tempfile.mkdtemp()) / "lease-link.json"
            outside.symlink_to(lease)
            with self.assertRaisesRegex(OpenClawLiveError, "escaped|leased"):
                run_openclaw_live_writeback(
                    root,
                    project_id="openclaw_project",
                    canonical_rev="rev_current",
                    subject_repo_id="repo_knowledge_topology",
                    subject_head_sha="abc123",
                    lease_path=outside,
                    runtime_summary_path=summary_path,
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.seed_projection(root)
            source_id = new_id("src")
            digest_id = new_id("dg")
            summary = self.make_summary(source_id, digest_id)
            lease = self.issue_and_lease(root, summary)
            self.write_bound_evidence(root, summary, lease.stem)
            summary_path = self.write_summary_file(root, summary)
            (root / "projections/openclaw/memory-prompt.md").unlink()
            with self.assertRaisesRegex(OpenClawLiveError, "memory prompt"):
                run_openclaw_live_writeback(
                    root,
                    project_id="openclaw_project",
                    canonical_rev="rev_current",
                    subject_repo_id="repo_knowledge_topology",
                    subject_head_sha="abc123",
                    lease_path=lease,
                    runtime_summary_path=summary_path,
                )

    def test_docs_capture_qmd_and_write_surface_boundaries(self):
        for relative in ["docs/OPENCLAW.md", "SECURITY.md", "POLICY.md"]:
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("QMD", text)
            self.assertIn("projections/openclaw/wiki-mirror", text)
            self.assertIn("canonical/", text)


if __name__ == "__main__":
    unittest.main()

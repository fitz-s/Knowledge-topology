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

from support_subjects import seed_subject_registry
from knowledge_topology.adapters.openclaw_live import summary_hash
from knowledge_topology.ids import new_id
from knowledge_topology.storage.transaction import atomic_write_text
from knowledge_topology.workers.compose_openclaw import write_openclaw_projection
from knowledge_topology.workers.init import init_topology


FIXED_TIME = "2026-04-14T00:00:00Z"


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


def seed_projection(root: Path) -> None:
    init_topology(root)
    seed_subject_registry(root)
    node = {
        "id": new_id("nd"),
        "type": "runtime_observation",
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


def make_summary(source_id: str | None = None, digest_id: str | None = None) -> dict:
    payload = {
        "runtime_assumptions": [
            {"statement": "Runtime observed a safe integration fact.", "observed_in": "runtime-pack"}
        ],
        "task_lessons": [
            {"lesson": "OpenClaw wiring uses topology-issued leases.", "applies_to": "runtime writeback"}
        ],
    }
    if source_id is not None:
        payload["source_id"] = source_id
    if digest_id is not None:
        payload["digest_id"] = digest_id
    return payload


def write_runtime_evidence(root: Path, summary: dict, job_id: str) -> None:
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


class P11OpenClawWiringTests(unittest.TestCase):
    def test_openclaw_cli_capture_issue_lease_and_run_writeback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            seed_projection(root)

            capture_summary = root / "capture-summary.json"
            capture_summary.write_text(json.dumps(make_summary(), indent=2, sort_keys=True), encoding="utf-8")
            capture = cli(
                "openclaw",
                "capture-source",
                "--root",
                str(root),
                "--project-id",
                "openclaw_project",
                "--canonical-rev",
                "rev_current",
                "--subject",
                "repo_knowledge_topology",
                "--subject-head-sha",
                "abc123",
                "--runtime-summary-json",
                str(capture_summary),
            )
            self.assertEqual(capture.returncode, 0, capture.stderr)
            self.assertIn("created OpenClaw runtime source packet", capture.stdout)
            self.assertTrue(list((root / "raw/packets").glob("src_*/packet.json")))
            self.assertTrue(list((root / "ops/queue/digest/pending").glob("job_*.json")))

            source_id = new_id("src")
            digest_id = new_id("dg")
            summary = make_summary(source_id, digest_id)
            summary_path = root / "runtime-summary.json"
            summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
            issued = cli(
                "openclaw",
                "issue-lease",
                "--root",
                str(root),
                "--project-id",
                "openclaw_project",
                "--canonical-rev",
                "rev_current",
                "--subject",
                "repo_knowledge_topology",
                "--subject-head-sha",
                "abc123",
                "--runtime-summary-json",
                str(summary_path),
            )
            self.assertEqual(issued.returncode, 0, issued.stderr)
            self.assertIn("issued OpenClaw live lease", issued.stdout)
            leased = cli("openclaw", "lease", "--root", str(root), "--owner", "openclaw-live", "--lease-seconds", "300")
            self.assertEqual(leased.returncode, 0, leased.stderr)
            lease_path = Path(leased.stdout.strip().split(": ", 1)[1])
            self.assertTrue(lease_path.exists())

            write_runtime_evidence(root, summary, lease_path.stem)
            result = cli(
                "openclaw",
                "run-writeback",
                "--root",
                str(root),
                "--project-id",
                "openclaw_project",
                "--canonical-rev",
                "rev_current",
                "--subject",
                "repo_knowledge_topology",
                "--subject-head-sha",
                "abc123",
                "--lease-path",
                str(lease_path),
                "--runtime-summary-json",
                str(summary_path),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("created OpenClaw writeback mutation pack", result.stdout)
            self.assertIn("consumed OpenClaw live lease", result.stdout)
            self.assertTrue(list((root / "mutations/pending").glob("mut_*.json")))
            self.assertTrue(list((root / "ops/queue/writeback/done").glob("job_*.json")))

    def test_openclaw_cli_help_is_exposed(self):
        top = cli("--help")
        self.assertEqual(top.returncode, 0, top.stderr)
        self.assertIn("openclaw", top.stdout)
        help_result = cli("openclaw", "--help")
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        for command in ["capture-source", "issue-lease", "lease", "run-writeback"]:
            self.assertIn(command, help_result.stdout)


if __name__ == "__main__":
    unittest.main()

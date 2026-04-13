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
from knowledge_topology.workers.doctor import stale_anchors
from knowledge_topology.workers.init import init_topology
from knowledge_topology.workers.lint import run_lints
from knowledge_topology.workers.writeback import writeback_session


class P7WritebackLintDoctorTests(unittest.TestCase):
    def test_lint_detects_projection_leakage_and_missing_antibody(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            pack = root / "projections/tasks/task_bad"
            pack.mkdir(parents=True)
            (pack / "metadata.json").write_text("{}", encoding="utf-8")
            (pack / "constraints.json").write_text(json.dumps({"count": 1, "invariants": [{"id": new_id("nd")}]}) + "\n", encoding="utf-8")
            (pack / "relationship-tests.yaml").write_text("[]\n", encoding="utf-8")
            result = run_lints(root)
            self.assertFalse(result.ok)
            joined = "\n".join(result.messages)
            self.assertIn("generated projection file", joined)
            self.assertIn("missing relationship tests", joined)

    def test_lint_detects_malformed_relationship_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            pack = root / "projections/tasks/task_rel"
            pack.mkdir(parents=True)
            (pack / "relationship-tests.yaml").write_text("- id: bad\n", encoding="utf-8")
            result = run_lints(root)
            self.assertFalse(result.ok)
            joined = "\n".join(result.messages)
            self.assertIn("malformed relationship tests", joined)
            self.assertIn("missing fields", joined)

    def test_lint_detects_structural_relationship_test_false_negative(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            pack = root / "projections/tasks/task_rel"
            pack.mkdir(parents=True)
            reltest_id = new_id("reltest")
            (pack / "relationship-tests.yaml").write_text(
                "\n".join([
                    "- schema_version: 1.0",
                    f"  id: {reltest_id}",
                    "",
                ]),
                encoding="utf-8",
            )
            result = run_lints(root)
            self.assertFalse(result.ok)
            self.assertIn("missing fields", "\n".join(result.messages))

    def test_lint_detects_missing_antibody_for_uncovered_invariant_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            pack = root / "projections/tasks/task_missing_cover"
            pack.mkdir(parents=True)
            invariant_id = new_id("nd")
            unrelated_id = new_id("nd")
            (pack / "constraints.json").write_text(
                json.dumps({"count": 1, "invariants": [{"id": invariant_id}]}) + "\n",
                encoding="utf-8",
            )
            (pack / "relationship-tests.yaml").write_text(
                "\n".join([
                    "- schema_version: 1.0",
                    f"  id: {new_id('reltest')}",
                    f"  invariant_node_id: {unrelated_id}",
                    '  property: "wrong invariant"',
                    "  evidence_refs: []",
                    "  suggested_test_shape: unit",
                    '  failure_if: ["wrong invariant violated"]',
                    "  status: draft",
                    "",
                ]),
                encoding="utf-8",
            )
            result = run_lints(root)
            self.assertFalse(result.ok)
            joined = "\n".join(result.messages)
            self.assertIn("missing relationship tests", joined)
            self.assertIn(invariant_id, joined)

    def test_lint_detects_missing_antibody_when_reltest_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            pack = root / "projections/tasks/task_no_reltests"
            pack.mkdir(parents=True)
            (pack / "constraints.json").write_text(
                json.dumps({"count": 1, "invariants": [{"id": new_id("nd")}]}) + "\n",
                encoding="utf-8",
            )
            result = run_lints(root)
            self.assertFalse(result.ok)
            self.assertIn("missing relationship tests", "\n".join(result.messages))

    def test_lint_checks_writeback_relationship_test_deltas(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            delta = root / ".tmp/writeback" / new_id("mut")
            delta.mkdir(parents=True)
            (delta / "relationship-tests.yaml").write_text(
                "- schema_version: 1.0\n"
                f"  id: {new_id('reltest')}\n",
                encoding="utf-8",
            )
            result = run_lints(root)
            self.assertFalse(result.ok)
            self.assertIn("malformed relationship tests", "\n".join(result.messages))

    def test_lint_rejects_non_opaque_relationship_test_evidence_refs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            delta = root / ".tmp/writeback" / new_id("mut")
            delta.mkdir(parents=True)
            (delta / "relationship-tests.yaml").write_text(
                "\n".join([
                    "- schema_version: 1.0",
                    f"  id: {new_id('reltest')}",
                    f"  invariant_node_id: {new_id('nd')}",
                    '  property: "prop"',
                    '  evidence_refs: ["not_an_id"]',
                    "  suggested_test_shape: unit",
                    '  failure_if: ["bad"]',
                    "  status: draft",
                    "",
                ]),
                encoding="utf-8",
            )
            result = run_lints(root)
            self.assertFalse(result.ok)
            self.assertIn("evidence_refs must be a list of opaque IDs", "\n".join(result.messages))

    def test_lint_rejects_constraints_count_without_invariant_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            pack = root / "projections/tasks/task_no_invariant_ids"
            pack.mkdir(parents=True)
            (pack / "constraints.json").write_text(
                json.dumps({"count": 1, "invariants": []}) + "\n",
                encoding="utf-8",
            )
            (pack / "relationship-tests.yaml").write_text(
                "\n".join([
                    "- schema_version: 1.0",
                    f"  id: {new_id('reltest')}",
                    f"  invariant_node_id: {new_id('nd')}",
                    '  property: "arbitrary invariant"',
                    "  evidence_refs: []",
                    "  suggested_test_shape: unit",
                    '  failure_if: ["bad"]',
                    "  status: draft",
                    "",
                ]),
                encoding="utf-8",
            )
            result = run_lints(root)
            self.assertFalse(result.ok)
            self.assertIn("count does not match", "\n".join(result.messages))

    def test_lint_rejects_constraints_count_mismatch_and_invalid_invariant_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            mismatch = root / "projections/tasks/task_count_mismatch"
            mismatch.mkdir(parents=True)
            (mismatch / "constraints.json").write_text(
                json.dumps({"count": 2, "invariants": [{"id": new_id("nd")}]}) + "\n",
                encoding="utf-8",
            )
            (mismatch / "relationship-tests.yaml").write_text("[]\n", encoding="utf-8")
            invalid = root / "projections/tasks/task_invalid_ids"
            invalid.mkdir(parents=True)
            (invalid / "constraints.json").write_text(
                json.dumps({"count": 1, "invariants": [{"id": "not_an_id"}]}) + "\n",
                encoding="utf-8",
            )
            (invalid / "relationship-tests.yaml").write_text("[]\n", encoding="utf-8")
            result = run_lints(root)
            self.assertFalse(result.ok)
            joined = "\n".join(result.messages)
            self.assertIn("count does not match", joined)
            self.assertIn("invalid IDs", joined)

    def test_doctor_reports_stale_file_refs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            (root / "canonical/registry/file_refs.jsonl").write_text(
                json.dumps({
                    "repo_id": "repo_knowledge_topology",
                    "commit_sha": "old",
                    "path": "src/example.py",
                }) + "\n",
                encoding="utf-8",
            )
            result = stale_anchors(root, subject_repo_id="repo_knowledge_topology", subject_head_sha="new")
            self.assertFalse(result.ok)
            self.assertIn("stale anchor old != new", result.messages[0])

    def test_writeback_creates_pending_mutation_and_reltest_delta_without_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            summary = root / ".tmp/summary.json"
            summary.parent.mkdir(exist_ok=True)
            source_id = new_id("src")
            digest_id = new_id("dg")
            summary.write_text(json.dumps({
                "source_id": source_id,
                "digest_id": digest_id,
                "decisions": ["Use deterministic writeback"],
                "invariants": ["Writeback must not write canonical"],
            }), encoding="utf-8")
            # Evidence placeholders for MutationPack validation are intentionally not required at writeback proposal time.
            mutation, reltest = writeback_session(
                root,
                summary_path=summary,
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                base_canonical_rev="rev_current",
                current_canonical_rev="rev_current",
                current_subject_head_sha="abc123",
            )
            self.assertEqual(mutation.parent.name, "pending")
            self.assertTrue(reltest.exists())
            self.assertIn("reltest_", reltest.read_text(encoding="utf-8"))
            self.assertEqual((root / "canonical/registry/nodes.jsonl").read_text(encoding="utf-8"), "")

    def test_writeback_rejects_stale_preconditions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            summary = root / ".tmp/summary.json"
            summary.parent.mkdir(exist_ok=True)
            summary.write_text(json.dumps({
                "source_id": new_id("src"),
                "digest_id": new_id("dg"),
                "decisions": ["D"],
                "invariants": [],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "base_canonical_rev is stale"):
                writeback_session(
                    root,
                    summary_path=summary,
                    subject_repo_id="repo_knowledge_topology",
                    subject_head_sha="abc123",
                    base_canonical_rev="old",
                    current_canonical_rev="new",
                    current_subject_head_sha="abc123",
                )
            with self.assertRaisesRegex(ValueError, "subject_head_sha is stale"):
                writeback_session(
                    root,
                    summary_path=summary,
                    subject_repo_id="repo_knowledge_topology",
                    subject_head_sha="old",
                    base_canonical_rev="rev_current",
                    current_canonical_rev="rev_current",
                    current_subject_head_sha="new",
                )

    def test_cli_lint_doctor_writeback_smoke(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            env = os.environ.copy()
            env["PYTHONPATH"] = str(SRC)
            lint_ok = subprocess.run([sys.executable, "-m", "knowledge_topology.cli", "lint", "--root", tmp], cwd=ROOT, env=env, text=True)
            self.assertEqual(lint_ok.returncode, 0)
            doctor_ok = subprocess.run(
                [sys.executable, "-m", "knowledge_topology.cli", "doctor", "stale-anchors", "--root", tmp, "--subject", "repo_knowledge_topology", "--subject-head-sha", "abc123"],
                cwd=ROOT,
                env=env,
                text=True,
            )
            self.assertEqual(doctor_ok.returncode, 0)
            summary = root / ".tmp/summary.json"
            summary.parent.mkdir(exist_ok=True)
            summary.write_text(json.dumps({"source_id": new_id("src"), "digest_id": new_id("dg"), "decisions": ["D"], "invariants": []}), encoding="utf-8")
            writeback = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "knowledge_topology.cli",
                    "writeback",
                    "--root",
                    tmp,
                    "--summary-json",
                    str(summary),
                    "--subject",
                    "repo_knowledge_topology",
                    "--subject-head-sha",
                    "abc123",
                    "--base-canonical-rev",
                    "rev_current",
                    "--current-canonical-rev",
                    "rev_current",
                    "--current-subject-head-sha",
                    "abc123",
                ],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(writeback.returncode, 0, writeback.stderr)
            self.assertIn("created writeback mutation pack:", writeback.stdout)


if __name__ == "__main__":
    unittest.main()

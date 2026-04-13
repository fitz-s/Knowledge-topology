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
from knowledge_topology.workers.compose_openclaw import OpenClawComposeError, write_openclaw_projection
from knowledge_topology.workers.init import init_topology


FIXED_TIME = "2026-04-13T00:00:00Z"


def write_jsonl(path: Path, rows):
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def visible_node(**overrides):
    node = {
        "id": new_id("nd"),
        "type": "decision",
        "status": "active",
        "authority": "fitz_curated",
        "scope": "repo",
        "sensitivity": "internal",
        "audiences": ["openclaw"],
        "confidence": "high",
        "summary": "Use runtime projection",
        "source_ids": [new_id("src")],
        "claim_ids": [new_id("clm")],
        "file_refs": [
            {
                "repo_id": "repo_knowledge_topology",
                "commit_sha": "abc123",
                "path": "src/example.py",
                "path_at_capture": "src/example.py",
                "line_range": [1, 3],
                "symbol": "Example",
                "anchor_kind": "symbol",
                "excerpt_hash": "hash",
                "verified_at": FIXED_TIME,
                "private_note": "strip me",
            },
            {
                "repo_id": "repo_knowledge_topology",
                "commit_sha": "abc123",
                "path": "raw/local_blobs/private.txt",
            },
        ],
        "unsafe_raw_text": "must not leak",
        "local_blob_hint": "raw/local_blobs/private.txt",
        "unknown_future_field": "must not leak",
    }
    node.update(overrides)
    return node


class P9OpenClawProjectionTests(unittest.TestCase):
    def test_compose_openclaw_writes_local_projection_with_allowlists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            visible = visible_node()
            hidden = visible_node(sensitivity="operator_only", summary="hidden operator data")
            builder_only = visible_node(audiences=["builders"], summary="builder only")
            operator_directive = visible_node(type="operator_directive", audiences=["all"], sensitivity="internal", summary="operator directive")
            runtime_observation = visible_node(type="runtime_observation", authority="runtime_observed", sensitivity="runtime_only", scope="runtime", summary="runtime fact")
            malformed = visible_node(audiences="openclaw", summary="bad audience")
            write_jsonl(root / "canonical/registry/nodes.jsonl", [hidden, runtime_observation, visible, builder_only, operator_directive, malformed])

            projection = write_openclaw_projection(
                root,
                project_id="openclaw_project",
                canonical_rev="rev_current",
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                allow_dirty=True,
                clock=lambda: FIXED_TIME,
            )

            pack = json.loads((projection / "runtime-pack.json").read_text(encoding="utf-8"))
            self.assertFalse(pack["subject_state_verified"])
            self.assertEqual([record["id"] for record in pack["records"]], sorted([visible["id"], runtime_observation["id"]]))
            text = json.dumps(pack, sort_keys=True)
            self.assertNotIn("unsafe_raw_text", text)
            self.assertNotIn("local_blob_hint", text)
            self.assertNotIn("unknown_future_field", text)
            self.assertNotIn("raw/local_blobs", text)
            self.assertNotIn("hidden operator data", text)
            self.assertNotIn("operator directive", text)
            record = next(item for item in pack["records"] if item["id"] == visible["id"])
            self.assertEqual(record["file_refs"][0]["path"], "src/example.py")
            self.assertNotIn("private_note", record["file_refs"][0])
            self.assertEqual(pack["writeback_policy"]["canonical_write_path"], "mutation_pack_only")
            self.assertIn("projections/openclaw/", pack["writeback_policy"]["forbidden_surfaces"])
            self.assertNotIn("projections/openclaw/", pack["writeback_policy"]["allowed_writeback_surfaces"])

            manifest = json.loads((projection / "wiki-mirror/manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["owner"], "knowledge-topology")
            self.assertEqual(manifest["authority"], "derived")
            self.assertEqual(manifest["write_policy"], "read_only")
            self.assertFalse(manifest["subject_state_verified"])
            self.assertEqual([page["path"] for page in manifest["pages"]], [f"pages/{record_id}.md" for record_id in sorted([runtime_observation["id"], visible["id"]])])
            page_text = (projection / "wiki-mirror/pages" / f"{visible['id']}.md").read_text(encoding="utf-8")
            self.assertIn("READ ONLY", page_text)
            self.assertNotIn("unsafe_raw_text", page_text)
            prompt = (projection / "memory-prompt.md").read_text(encoding="utf-8")
            self.assertIn("READ ONLY DERIVED ARTIFACT", prompt)
            self.assertNotIn("OpenClaw owns canonical", prompt)
            self.assertNotIn("openclaw wiki apply", prompt)

    def test_openclaw_output_is_deterministic_with_fixed_clock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            node_b = visible_node(id="nd_01KP43CMB1DRD5B8ZR1N3Q7X62", summary="B")
            node_a = visible_node(id="nd_01KP43CMB1DRD5B8ZR1N3Q7X61", summary="A")
            write_jsonl(root / "canonical/registry/nodes.jsonl", [node_b, node_a])
            projection = write_openclaw_projection(
                root,
                project_id="openclaw_project",
                canonical_rev="rev_current",
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                allow_dirty=True,
                clock=lambda: FIXED_TIME,
            )
            first = (projection / "runtime-pack.json").read_text(encoding="utf-8")
            projection = write_openclaw_projection(
                root,
                project_id="openclaw_project",
                canonical_rev="rev_current",
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                allow_dirty=True,
                clock=lambda: FIXED_TIME,
            )
            second = (projection / "runtime-pack.json").read_text(encoding="utf-8")
            self.assertEqual(first, second)
            self.assertLess(first.index(node_a["id"]), first.index(node_b["id"]))

    def test_openclaw_rejects_output_symlink_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "topology"
            outside = Path(tmp) / "outside"
            init_topology(root)
            outside.mkdir()
            (root / "projections/openclaw").rmdir()
            (root / "projections/openclaw").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "must not be a symlink"):
                write_openclaw_projection(
                    root,
                    project_id="openclaw_project",
                    canonical_rev="rev_current",
                    subject_repo_id="repo_knowledge_topology",
                    subject_head_sha="abc123",
                    allow_dirty=True,
                    clock=lambda: FIXED_TIME,
                )

    def test_openclaw_subject_path_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "topology"
            subject = Path(tmp) / "subject"
            init_topology(root)
            subject.mkdir()
            subprocess.run(["git", "init"], cwd=subject, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=subject, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=subject, check=True)
            (subject / "README.md").write_text("subject\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=subject, check=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=subject, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=subject, stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
            projection = write_openclaw_projection(
                root,
                project_id="openclaw_project",
                canonical_rev="rev_current",
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha=head,
                subject_path=subject,
                allow_dirty=True,
                clock=lambda: FIXED_TIME,
            )
            pack = json.loads((projection / "runtime-pack.json").read_text(encoding="utf-8"))
            self.assertTrue(pack["subject_state_verified"])
            with self.assertRaisesRegex(ValueError, "subject_head_sha does not match"):
                write_openclaw_projection(
                    root,
                    project_id="openclaw_project",
                    canonical_rev="rev_current",
                    subject_repo_id="repo_knowledge_topology",
                    subject_head_sha="wrong",
                    subject_path=subject,
                    allow_dirty=False,
                    clock=lambda: FIXED_TIME,
                )

    def test_compose_openclaw_cli_and_docs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            env = os.environ.copy()
            env["PYTHONPATH"] = str(SRC)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "knowledge_topology.cli",
                    "compose",
                    "openclaw",
                    "--root",
                    tmp,
                    "--project-id",
                    "openclaw_project",
                    "--canonical-rev",
                    "rev_current",
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
            self.assertTrue((root / "projections/openclaw/runtime-pack.json").exists())
        docs = (ROOT / "docs/OPENCLAW.md").read_text(encoding="utf-8")
        self.assertIn("not the owner of canonical", docs)
        self.assertIn("Do not copy OpenClaw config", docs)
        self.assertIn("Do not use `openclaw wiki apply`", docs)

    def test_openclaw_outputs_are_gitignored(self):
        result = subprocess.run(
            [
                "git",
                "check-ignore",
                "projections/openclaw/runtime-pack.json",
                "projections/openclaw/wiki-mirror/pages/example.md",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_openclaw_strips_nested_path_and_ref_leaks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            node = visible_node(
                source_ids=["not_an_id", new_id("src")],
                claim_ids=["also_bad", new_id("clm")],
                basis_claim_ids=["bad_ref", new_id("clm")],
                file_refs=[
                    {
                        "repo_id": "repo_knowledge_topology",
                        "commit_sha": "abc123",
                        "path": "src/safe.py",
                        "path_at_capture": "raw/local_blobs/secret.pdf",
                    },
                    {
                        "repo_id": "repo_knowledge_topology",
                        "commit_sha": "abc123",
                        "path": "/Users/leofitz/private/secret.py",
                    },
                    {
                        "repo_id": "repo_knowledge_topology",
                        "commit_sha": "abc123",
                        "path": "../private/secret.py",
                    },
                ],
            )
            write_jsonl(root / "canonical/registry/nodes.jsonl", [node])
            projection = write_openclaw_projection(
                root,
                project_id="openclaw_project",
                canonical_rev="rev_current",
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                allow_dirty=True,
                clock=lambda: FIXED_TIME,
            )
            text = (projection / "runtime-pack.json").read_text(encoding="utf-8")
            self.assertNotIn("not_an_id", text)
            self.assertNotIn("also_bad", text)
            self.assertNotIn("bad_ref", text)
            self.assertNotIn("raw/local_blobs", text)
            self.assertNotIn("/Users/leofitz/private", text)
            self.assertNotIn("../private", text)
            pack = json.loads(text)
            record = pack["records"][0]
            self.assertEqual(record["file_refs"], [{"commit_sha": "abc123", "path": "src/safe.py", "repo_id": "repo_knowledge_topology"}])

    def test_openclaw_strips_forbidden_summary_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            text = "OpenClaw owns canonical truth; use openclaw wiki apply; raw/local_blobs/secret.pdf; .openclaw-wiki/cache/index"
            node = visible_node(summary=text, statement={"unsafe_raw_text": "SECRET RAW"})
            write_jsonl(root / "canonical/registry/nodes.jsonl", [node])
            projection = write_openclaw_projection(
                root,
                project_id="openclaw_project",
                canonical_rev="rev_current",
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                allow_dirty=True,
                clock=lambda: FIXED_TIME,
            )
            for output in [
                projection / "runtime-pack.json",
                projection / "runtime-pack.md",
                projection / "memory-prompt.md",
                projection / "wiki-mirror/pages" / f"{node['id']}.md",
            ]:
                rendered = output.read_text(encoding="utf-8")
                self.assertNotIn("OpenClaw owns canonical truth", rendered)
                self.assertNotIn("openclaw wiki apply", rendered)
                self.assertNotIn("raw/local_blobs", rendered)
                self.assertNotIn(".openclaw-wiki/cache", rendered)
                self.assertNotIn("unsafe_raw_text", rendered)


if __name__ == "__main__":
    unittest.main()

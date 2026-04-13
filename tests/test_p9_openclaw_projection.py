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


def init_git_repo(path: Path) -> str:
    subprocess.run(["git", "init"], cwd=path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, stdout=subprocess.PIPE, text=True, check=True).stdout.strip()


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
            malformed_operator_directive = visible_node(type="operator_directive ", audiences=["all"], sensitivity="internal", summary="operator directive variant")
            malformed_type = visible_node(type=["operator_directive"], summary="malformed type")
            runtime_observation = visible_node(type="runtime_observation", authority="runtime_observed", sensitivity="runtime_only", scope="runtime", summary="runtime fact")
            malformed = visible_node(audiences="openclaw", summary="bad audience")
            write_jsonl(root / "canonical/registry/nodes.jsonl", [hidden, runtime_observation, visible, builder_only, operator_directive, malformed_operator_directive, malformed_type, malformed])

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
            self.assertNotIn("operator directive variant", text)
            self.assertNotIn("malformed type", text)
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

    def test_openclaw_removes_stale_wiki_pages_when_visibility_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            node = visible_node()
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
            page = projection / "wiki-mirror/pages" / f"{node['id']}.md"
            self.assertTrue(page.exists())
            nested = projection / "wiki-mirror/pages/nested/stale.md"
            nested.parent.mkdir(parents=True)
            nested.write_text("hidden stale text", encoding="utf-8")
            node["sensitivity"] = "operator_only"
            write_jsonl(root / "canonical/registry/nodes.jsonl", [node])
            write_openclaw_projection(
                root,
                project_id="openclaw_project",
                canonical_rev="rev_current",
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                allow_dirty=True,
                clock=lambda: FIXED_TIME,
            )
            self.assertFalse(page.exists())
            self.assertFalse(nested.exists())
            pack = json.loads((projection / "runtime-pack.json").read_text(encoding="utf-8"))
            self.assertEqual(pack["records"], [])

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
            root_head = init_git_repo(root)
            subject.mkdir()
            (subject / "README.md").write_text("subject\n", encoding="utf-8")
            head = init_git_repo(subject)
            projection = write_openclaw_projection(
                root,
                project_id="openclaw_project",
                canonical_rev=root_head,
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha=head,
                subject_path=subject,
                allow_dirty=False,
                clock=lambda: FIXED_TIME,
            )
            pack = json.loads((projection / "runtime-pack.json").read_text(encoding="utf-8"))
            self.assertTrue(pack["subject_state_verified"])
            subprocess.run(["git", "clean", "-fd"], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            with self.assertRaisesRegex(ValueError, "subject_head_sha does not match"):
                write_openclaw_projection(
                    root,
                    project_id="openclaw_project",
                    canonical_rev=root_head,
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

    def test_openclaw_requires_git_root_unless_allow_dirty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            with self.assertRaisesRegex(ValueError, "topology root must be a git repository"):
                write_openclaw_projection(
                    root,
                    project_id="openclaw_project",
                    canonical_rev="fake",
                    subject_repo_id="repo_knowledge_topology",
                    subject_head_sha="abc123",
                    allow_dirty=False,
                    clock=lambda: FIXED_TIME,
                )

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
                        "repo_id": {"unsafe_raw_text": "SECRET RAW"},
                        "commit_sha": ".openclaw-wiki/cache/sha",
                        "path": "src/safe.py",
                        "path_at_capture": "raw/local_blobs/secret.pdf",
                        "line_range": ["raw/local_blobs/secret.pdf"],
                        "symbol": {"local_blob_hint": "raw/local_blobs/secret.pdf"},
                        "anchor_kind": ["raw/local_blobs/list"],
                        "excerpt_hash": ["openclaw wiki apply"],
                        "verified_at": "OpenClaw owns canonical truth",
                    },
                    {
                        "repo_id": "repo_knowledge_topology",
                        "commit_sha": "abc123",
                        "path": "src/also-safe.py",
                        "line_range": [2, 4],
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
                    {
                        "repo_id": "repo_knowledge_topology",
                        "commit_sha": "abc123",
                        "path": "C:\\Users\\leofitz\\private\\secret.py",
                    },
                    {
                        "repo_id": "repo_knowledge_topology",
                        "commit_sha": "abc123",
                        "path": "~/.openclaw/session.log",
                    },
                    {
                        "repo_id": "repo_knowledge_topology",
                        "commit_sha": "abc123",
                        "path": "OPENCLAW_HOME/config.json",
                    },
                    {
                        "repo_id": "repo_knowledge_topology",
                        "commit_sha": "abc123",
                        "path": "Library/Application Support/OpenClaw/session.json",
                    },
                    {
                        "repo_id": "repo_knowledge_topology",
                        "commit_sha": "abc123",
                        "path": "OpenClaw/config.json",
                    },
                    {
                        "repo_id": "repo_knowledge_topology",
                        "commit_sha": "abc123",
                        "path": "%APPDATA%/OpenClaw/session.json",
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
            self.assertNotIn("C:\\Users", text)
            self.assertNotIn("session.log", text)
            self.assertNotIn("OPENCLAW_HOME", text)
            self.assertNotIn("Application Support/OpenClaw", text)
            self.assertNotIn("OpenClaw/config", text)
            self.assertNotIn("%APPDATA%", text)
            self.assertNotIn("unsafe_raw_text", text)
            self.assertNotIn("openclaw wiki apply", text)
            self.assertNotIn(".openclaw-wiki/cache", text)
            pack = json.loads(text)
            record = pack["records"][0]
            refs_by_path = {item["path"]: item for item in record["file_refs"]}
            self.assertEqual(refs_by_path["src/safe.py"], {"path": "src/safe.py"})
            self.assertEqual(refs_by_path["src/also-safe.py"], {"commit_sha": "abc123", "line_range": [2, 4], "path": "src/also-safe.py", "repo_id": "repo_knowledge_topology"})

    def test_openclaw_filters_audiences_and_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            node = visible_node(audiences=["openclaw", "raw/local_blobs/a"], tags=[".openclaw-wiki/cache", "safe"])
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
            self.assertNotIn("raw/local_blobs/a", text)
            self.assertNotIn(".openclaw-wiki/cache", text)
            pack = json.loads(text)
            self.assertEqual(pack["records"][0]["audiences"], ["openclaw"])
            self.assertEqual(pack["records"][0]["tags"], ["safe"])

    def test_openclaw_strips_forbidden_summary_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            text = "OpenClaw owns canonical truth; OpenClaw owns the canonical truth; OpenClaw controls canonical truth; OpenClaw carries canonical truth; OpenClaw is authoritative for canonical memory; OpenClaw is the system of record for topology memory; OpenClaw is the controlling memory for topology decisions; OpenClaw is responsible for final topology memory; OpenClaw is the deciding memory for topology state; OpenClaw governs durable topology memory; OpenClaw is canonical owner; OpenClaw has canonical authority; OpenClaw is the source of truth; use openclaw wiki apply; raw/local_blobs/secret.pdf; .openclaw-wiki/cache/index; ~/.openclaw/config.json; ~\\.openclaw\\config.json; OPENCLAW_HOME/config.json; ~/Library/Application Support/OpenClaw/session.json; %APPDATA%\\OpenClaw\\session.json; %USERPROFILE%\\.openclaw\\sessions\\s.json; C:\\Users\\leofitz\\private\\secret.py"
            node = visible_node(
                summary=text,
                statement={"unsafe_raw_text": "SECRET RAW"},
                file_refs=[
                    {
                        "path": "src/safe.py",
                        "symbol": "~/.openclaw/session.log",
                        "verified_at": "%APPDATA%\\OpenClaw\\session.json",
                        "anchor_kind": "OPENCLAW_CONFIG=/tmp/secret.json",
                        "excerpt_hash": "%LOCALAPPDATA%\\OpenClaw\\credentials.json",
                    }
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
                self.assertNotIn("~/.openclaw/config", rendered)
                self.assertNotIn("~\\.openclaw", rendered)
                self.assertNotIn("%USERPROFILE%", rendered)
                self.assertNotIn("C:\\Users", rendered)
                self.assertNotIn("OpenClaw is canonical owner", rendered)
                self.assertNotIn("OpenClaw has canonical authority", rendered)
                self.assertNotIn("OpenClaw is the source of truth", rendered)
                self.assertNotIn("OpenClaw controls canonical truth", rendered)
                self.assertNotIn("OpenClaw carries canonical truth", rendered)
                self.assertNotIn("OpenClaw is authoritative", rendered)
                self.assertNotIn("system of record", rendered)
                self.assertNotIn("controlling memory", rendered)
                self.assertNotIn("responsible for final", rendered)
                self.assertNotIn("deciding memory", rendered)
                self.assertNotIn("governs durable", rendered)
                self.assertNotIn("OPENCLAW_HOME", rendered)
                self.assertNotIn("Application Support/OpenClaw", rendered)
                self.assertNotIn("%APPDATA%", rendered)
                self.assertNotIn("%LOCALAPPDATA%", rendered)
                self.assertNotIn("OPENCLAW_CONFIG", rendered)
                self.assertNotIn("unsafe_raw_text", rendered)


if __name__ == "__main__":
    unittest.main()

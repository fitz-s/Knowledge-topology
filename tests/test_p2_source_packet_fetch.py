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

from knowledge_topology.schema.source_packet import SourcePacketError
from knowledge_topology.storage.spool import read_job
from knowledge_topology.workers.fetch import build_source_packet, classify_source, ingest_source
from knowledge_topology.workers.init import init_topology


class P2SourcePacketFetchTests(unittest.TestCase):
    def test_classifies_p2_source_types(self):
        self.assertEqual(classify_source("notes.md"), "local_draft")
        self.assertEqual(classify_source("https://github.com/fitz-s/Knowledge-topology/pull/1"), "github_artifact")
        self.assertEqual(classify_source("https://example.com/post"), "article_html")
        self.assertEqual(classify_source("https://arxiv.org/abs/2401.00001"), "pdf_arxiv")
        self.assertEqual(classify_source("paper.pdf"), "pdf_arxiv")

    def test_public_text_requires_redistributable_yes(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as handle:
            handle.write("local note")
            path = handle.name
        try:
            with self.assertRaises(SourcePacketError):
                build_source_packet(
                    path,
                    note="test note",
                    depth="standard",
                    redistributable="unknown",
                    content_mode="public_text",
                )
            packet, files = build_source_packet(
                path,
                note="test note",
                depth="standard",
                redistributable="yes",
                content_mode="public_text",
            )
            self.assertEqual(packet.content_mode, "public_text")
            self.assertIn("content.md", files)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_local_draft_ingest_writes_packet_and_digest_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            draft = root / "draft.md"
            draft.write_text("Fitz curated source\\n", encoding="utf-8")
            result = ingest_source(
                root,
                str(draft),
                note="important local draft",
                depth="deep",
                audience="builders",
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                base_canonical_rev="rev_current",
                redistributable="yes",
            )
            packet = json.loads(result.packet_path.read_text(encoding="utf-8"))
            self.assertEqual(packet["source_type"], "local_draft")
            self.assertEqual(packet["content_status"], "complete")
            self.assertEqual(packet["content_mode"], "public_text")
            self.assertTrue((result.packet_path.parent / "content.md").exists())
            job = read_job(result.digest_job_path)
            self.assertEqual(job["payload"]["source_id"], packet["id"])
            self.assertEqual(job["subject_repo_id"], "repo_knowledge_topology")
            self.assertEqual(job["subject_head_sha"], "abc123")
            self.assertEqual(job["base_canonical_rev"], "rev_current")

    def test_external_sources_default_to_excerpt_only_partial_packets(self):
        cases = [
            ("https://github.com/fitz-s/Knowledge-topology/blob/main/README.md", "github_artifact"),
            ("https://example.com/article", "article_html"),
            ("https://arxiv.org/pdf/2401.00001.pdf", "pdf_arxiv"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            for value, expected_type in cases:
                result = ingest_source(
                    root,
                    value,
                    note=f"curated {expected_type}",
                    depth="standard",
                    audience="all",
                    subject_repo_id="repo_knowledge_topology",
                    subject_head_sha="abc123",
                    base_canonical_rev="rev_current",
                )
                packet = json.loads(result.packet_path.read_text(encoding="utf-8"))
                self.assertEqual(packet["source_type"], expected_type)
                self.assertEqual(packet["content_mode"], "excerpt_only")
                self.assertEqual(packet["content_status"], "partial")

    def test_pdf_local_blob_keeps_bytes_out_of_packet_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            result = ingest_source(
                root,
                "https://arxiv.org/pdf/2401.00001.pdf",
                note="paper",
                depth="scan",
                audience="builders",
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                base_canonical_rev="rev_current",
                content_mode="local_blob",
            )
            packet_dir = result.packet_path.parent
            packet = json.loads(result.packet_path.read_text(encoding="utf-8"))
            self.assertEqual(packet["content_mode"], "local_blob")
            self.assertFalse(any(path.suffix == ".pdf" for path in packet_dir.iterdir()))

    def test_cli_ingest_smoke_and_public_text_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = os.environ.copy()
            env["PYTHONPATH"] = str(SRC)
            subprocess.run(
                [sys.executable, "-m", "knowledge_topology.cli", "init", "--root", tmp],
                cwd=ROOT,
                env=env,
                check=True,
            )
            draft = root / "draft.md"
            draft.write_text("hello\\n", encoding="utf-8")
            bad = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "knowledge_topology.cli",
                    "ingest",
                    str(draft),
                    "--root",
                    tmp,
                    "--note",
                    "note",
                    "--subject",
                    "repo_knowledge_topology",
                    "--subject-head-sha",
                    "abc123",
                    "--base-canonical-rev",
                    "rev_current",
                    "--content-mode",
                    "public_text",
                ],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("public_text requires redistributable=yes", bad.stderr)

            good = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "knowledge_topology.cli",
                    "ingest",
                    str(draft),
                    "--root",
                    tmp,
                    "--note",
                    "note",
                    "--subject",
                    "repo_knowledge_topology",
                    "--subject-head-sha",
                    "abc123",
                    "--base-canonical-rev",
                    "rev_current",
                    "--redistributable",
                    "yes",
                ],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(good.returncode, 0, good.stderr)
            self.assertIn("created source packet:", good.stdout)


if __name__ == "__main__":
    unittest.main()

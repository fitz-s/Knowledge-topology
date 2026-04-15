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
from knowledge_topology.storage.spool import SpoolError, read_job
from knowledge_topology.workers.fetch import build_source_packet, classify_source, ingest_source
from knowledge_topology.workers.fetch import FetchResponse
from knowledge_topology.workers.init import init_topology


def fake_fetch(url: str, max_bytes: int) -> FetchResponse:
    if url.endswith(".pdf"):
        return FetchResponse(final_url=url, status_code=200, content_type="application/pdf", body=b"%PDF-1.4\nfixture\n")
    return FetchResponse(
        final_url=url,
        status_code=200,
        content_type="text/html; charset=utf-8",
        body=b"<html><body><main>fixture article body</main></body></html>",
    )


class P2SourcePacketFetchTests(unittest.TestCase):
    def test_classifies_p2_source_types(self):
        self.assertEqual(classify_source("notes.md"), "local_draft")
        self.assertEqual(classify_source("https://github.com/fitz-s/Knowledge-topology/pull/1"), "github_artifact")
        self.assertEqual(classify_source("https://example.com/post"), "article_html")
        self.assertEqual(classify_source("https://arxiv.org/abs/2401.00001"), "pdf_arxiv")
        self.assertEqual(classify_source("https://v.douyin.com/6l8q1jGwRl4/"), "video_platform")
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

    def test_source_packet_rejects_empty_required_fields(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as handle:
            handle.write("local note")
            path = handle.name
        try:
            packet, _ = build_source_packet(
                path,
                note="test note",
                depth="standard",
                redistributable="yes",
            )
            from knowledge_topology.schema.source_packet import SourcePacket

            for field in ["original_url", "retrieved_at", "curator_note", "authority", "trust_scope"]:
                bad = {
                    **packet.to_dict(),
                    field: "   ",
                }
                with self.subTest(field=field):
                    with self.assertRaises(SourcePacketError):
                        SourcePacket(**bad).validate()
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

    def test_local_draft_rejects_symlink_escape_and_local_blob(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            outside = Path(tempfile.mkdtemp()) / "outside.md"
            outside.write_text("outside private text\n", encoding="utf-8")
            symlink = root / "draft-link.md"
            symlink.symlink_to(outside)
            with self.assertRaises(Exception) as symlink_error:
                ingest_source(
                    root,
                    str(symlink),
                    note="symlink",
                    depth="standard",
                    audience="builders",
                    subject_repo_id="repo_knowledge_topology",
                    subject_head_sha="abc123",
                    base_canonical_rev="rev_current",
                    redistributable="yes",
                )
            self.assertIn("inside the topology root", str(symlink_error.exception))

            draft = root / "draft.md"
            draft.write_text("local note", encoding="utf-8")
            with self.assertRaises(Exception) as blob_error:
                ingest_source(
                    root,
                    str(draft),
                    note="local blob",
                    depth="standard",
                    audience="builders",
                    subject_repo_id="repo_knowledge_topology",
                    subject_head_sha="abc123",
                    base_canonical_rev="rev_current",
                    content_mode="local_blob",
                )
            self.assertIn("local_draft does not support local_blob", str(blob_error.exception))

    def test_digest_job_preconditions_are_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            draft = root / "draft.md"
            draft.write_text("local note", encoding="utf-8")
            with self.assertRaises(Exception):
                ingest_source(
                    root,
                    str(draft),
                    note="missing preconditions",
                    depth="standard",
                    audience="builders",
                    subject_repo_id="",
                    subject_head_sha="",
                    base_canonical_rev="",
                    redistributable="yes",
                )
            self.assertEqual(list((root / "raw/packets").glob("src_*")), [])
            with self.assertRaises(Exception):
                ingest_source(
                    root,
                    str(draft),
                    note="blank preconditions",
                    depth="standard",
                    audience="builders",
                    subject_repo_id=" ",
                    subject_head_sha=" ",
                    base_canonical_rev=" ",
                    redistributable="yes",
                )
            self.assertEqual(list((root / "raw/packets").glob("src_*")), [])

    def test_external_sources_default_to_excerpt_only_partial_packets(self):
        cases = [
            ("https://github.com/fitz-s/Knowledge-topology/blob/main/README.md", "github_artifact"),
            ("https://example.com/article", "article_html"),
            ("https://arxiv.org/pdf/2401.00001.pdf", "pdf_arxiv"),
            ("https://www.youtube.com/watch?v=abc123", "video_platform"),
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
                    fetcher=fake_fetch,
                )
                packet = json.loads(result.packet_path.read_text(encoding="utf-8"))
                self.assertEqual(packet["source_type"], expected_type)
                self.assertEqual(packet["content_mode"], "excerpt_only")
                self.assertEqual(packet["content_status"], "partial")
                if expected_type == "github_artifact":
                    github_artifact = packet["artifacts"][0]
                    self.assertEqual(github_artifact["repo"], "fitz-s/Knowledge-topology")
                    self.assertEqual(github_artifact["artifact_type"], "blob")
                    self.assertEqual(github_artifact["ref"], "main")
                    self.assertEqual(github_artifact["path"], "README.md")
                    self.assertIsNone(github_artifact["commit_sha"])

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
                fetcher=fake_fetch,
            )
            packet_dir = result.packet_path.parent
            packet = json.loads(result.packet_path.read_text(encoding="utf-8"))
            self.assertEqual(packet["content_mode"], "local_blob")
            blob_refs = [artifact for artifact in packet["artifacts"] if artifact["kind"] == "local_blob_ref"]
            self.assertEqual(len(blob_refs), 1)
            self.assertIn("hash_sha256", blob_refs[0])
            self.assertIn("storage_hint", blob_refs[0])
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

            video = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "knowledge_topology.cli",
                    "ingest",
                    "https://v.douyin.com/6l8q1jGwRl4/",
                    "--root",
                    tmp,
                    "--note",
                    "video note",
                    "--subject",
                    "repo_knowledge_topology",
                    "--subject-head-sha",
                    "abc123",
                    "--base-canonical-rev",
                    "rev_current",
                ],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(video.returncode, 0, video.stderr)
            packet_path = Path(next(line.split(": ", 1)[1] for line in video.stdout.splitlines() if line.startswith("created source packet:")))
            source_id = json.loads(packet_path.read_text(encoding="utf-8"))["id"]
            downloaded = root / "downloaded.mp4"
            downloaded.write_bytes(b"video bytes")
            attached = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "knowledge_topology.cli",
                    "video",
                    "attach-artifact",
                    "--root",
                    tmp,
                    "--source-id",
                    source_id,
                    "--artifact-kind",
                    "video_file",
                    "--artifact-path",
                    str(downloaded),
                    "--note",
                    "operator download",
                ],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(attached.returncode, 0, attached.stderr)
            self.assertIn("updated video source packet:", attached.stdout)


if __name__ == "__main__":
    unittest.main()

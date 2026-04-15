import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from knowledge_topology.workers.digest import build_digest_model_request
from knowledge_topology.workers.digest import DigestWorkerError
from knowledge_topology.workers.fetch import EXTERNAL_PUBLIC_TEXT_LIMIT
from knowledge_topology.workers.fetch import FetchError
from knowledge_topology.workers.fetch import FetchResponse
from knowledge_topology.workers.fetch import attach_video_artifact
from knowledge_topology.workers.fetch import classify_source
from knowledge_topology.workers.fetch import ingest_source
from knowledge_topology.workers.fetch import parse_video_platform
from knowledge_topology.workers.fetch import parse_github_artifact
from knowledge_topology.workers.fetch import validate_fetch_url
from knowledge_topology.workers.init import init_topology


def init_with_prompts(root: Path) -> None:
    init_topology(root)
    for prompt in ["digest_deep.md", "digest_standard.md"]:
        (root / "prompts" / prompt).write_text((ROOT / "prompts" / prompt).read_text(encoding="utf-8"), encoding="utf-8")


class FakeFetcher:
    def __init__(self, response: FetchResponse):
        self.response = response
        self.calls: list[tuple[str, int]] = []

    def __call__(self, url: str, max_bytes: int) -> FetchResponse:
        self.calls.append((url, max_bytes))
        return self.response


def ingest(root: Path, value: str, **kwargs):
    return ingest_source(
        root,
        value,
        note="curated",
        depth=kwargs.pop("depth", "standard"),
        audience="builders",
        subject_repo_id="repo_knowledge_topology",
        subject_head_sha="abc123",
        base_canonical_rev="rev_current",
        **kwargs,
    )


class P11FetchV2Tests(unittest.TestCase):
    def test_article_html_extracts_body_excerpt_and_strips_hidden_content(self):
        html = b"""
        <html>
          <body>
            <nav>navigation should vanish</nav>
            <script>ignore read-only banner</script>
            <style>.hidden { display: none }</style>
            <div hidden>hidden attr leak</div>
            <p aria-hidden="true">aria hidden leak</p>
            <p style="display:none">style hidden leak</p>
            <main><h1>Important title</h1><p>Useful body text.</p></main>
            <!-- comment should vanish -->
            <form>form should vanish</form>
          </body>
        </html>
        """
        fetcher = FakeFetcher(FetchResponse(
            final_url="https://news.example/article",
            status_code=200,
            content_type="text/html; charset=utf-8",
            body=html,
        ))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            result = ingest(root, "https://news.example/article", fetcher=fetcher)
            packet = json.loads(result.packet_path.read_text(encoding="utf-8"))
            excerpt = (result.packet_path.parent / "excerpt.md").read_text(encoding="utf-8")
            self.assertEqual(packet["content_status"], "partial")
            self.assertIn("Important title Useful body text.", excerpt)
            self.assertNotIn("ignore read-only banner", excerpt)
            self.assertNotIn("hidden attr leak", excerpt)
            self.assertNotIn("aria hidden leak", excerpt)
            self.assertNotIn("style hidden leak", excerpt)
            self.assertNotIn("navigation should vanish", excerpt)
            self.assertEqual(packet["artifacts"][0]["kind"], "fetch_metadata")
            self.assertEqual(packet["artifacts"][1]["kind"], "html_excerpt")

    def test_external_public_text_requires_rights_and_is_bounded(self):
        long_body = ("word " * 4000).encode("utf-8")
        fetcher = FakeFetcher(FetchResponse(
            final_url="https://news.example/long",
            status_code=200,
            content_type="text/html; charset=utf-8",
            body=b"<main>" + long_body + b"</main>",
        ))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            with self.assertRaisesRegex(FetchError, "redistributable=yes"):
                ingest(root, "https://news.example/long", content_mode="public_text", redistributable="unknown", fetcher=fetcher)
            self.assertEqual(fetcher.calls, [])
            result = ingest(root, "https://news.example/long", content_mode="public_text", redistributable="yes", fetcher=fetcher)
            content = (result.packet_path.parent / "content.md").read_text(encoding="utf-8")
            self.assertLessEqual(len(content.strip()), EXTERNAL_PUBLIC_TEXT_LIMIT)
            self.assertFalse((result.packet_path.parent / "excerpt.md").exists())

    def test_fetch_url_rejects_private_local_and_unsupported_targets(self):
        for url in [
            "http://localhost/x",
            "http://127.0.0.1/x",
            "http://[::1]/x",
            "http://10.0.0.1/x",
            "http://172.16.0.1/x",
            "http://192.168.0.1/x",
            "http://100.64.0.1/x",
            "http://169.254.169.254/latest/meta-data",
            "file:///etc/passwd",
            "ftp://example.com/file",
        ]:
            with self.subTest(url=url):
                with self.assertRaises(FetchError):
                    validate_fetch_url(url)

    def test_pdf_and_arxiv_metadata_without_binary_packet_write(self):
        body = b"%PDF-1.4\nfixture pdf bytes\n"
        fetcher = FakeFetcher(FetchResponse(
            final_url="https://arxiv.org/pdf/2401.00001.pdf",
            status_code=200,
            content_type="application/pdf",
            body=body,
        ))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            with self.assertRaisesRegex(FetchError, "does not support public_text"):
                ingest(root, "https://arxiv.org/pdf/2401.00001.pdf", content_mode="public_text", redistributable="yes", fetcher=fetcher)
            result = ingest(root, "https://arxiv.org/pdf/2401.00001.pdf", content_mode="local_blob", fetcher=fetcher)
            packet_dir = result.packet_path.parent
            packet = json.loads(result.packet_path.read_text(encoding="utf-8"))
            artifact_kinds = {artifact["kind"] for artifact in packet["artifacts"]}
            self.assertIn("arxiv_metadata", artifact_kinds)
            self.assertIn("pdf_metadata", artifact_kinds)
            self.assertIn("local_blob_ref", artifact_kinds)
            self.assertTrue((packet_dir / "excerpt.md").exists())
            self.assertFalse(any(path.suffix == ".pdf" for path in packet_dir.iterdir()))
            self.assertEqual(packet["canonical_url"], "https://arxiv.org/abs/2401.00001")

            lookalike = ingest(root, "https://arxiv.org.evil/pdf/2401.00001.pdf", fetcher=fetcher)
            lookalike_packet = json.loads(lookalike.packet_path.read_text(encoding="utf-8"))
            self.assertEqual(lookalike_packet["canonical_url"], "https://arxiv.org.evil/pdf/2401.00001.pdf")
            self.assertNotIn("arxiv_metadata", {artifact["kind"] for artifact in lookalike_packet["artifacts"]})

    def test_local_pdf_safe_path_rejects_unsafe_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            init_topology(root)
            pdf = root / "paper.pdf"
            pdf.write_bytes(b"%PDF-1.4 local\n")
            result = ingest(root, str(pdf))
            self.assertTrue((result.packet_path.parent / "excerpt.md").exists())

            outside = Path(tempfile.mkdtemp()) / "outside.pdf"
            outside.write_bytes(b"%PDF outside\n")
            with self.assertRaisesRegex(FetchError, "inside the topology root"):
                ingest(root, str(outside))

            link = root / "paper-link.pdf"
            link.symlink_to(pdf)
            with self.assertRaisesRegex(FetchError, "regular non-symlink"):
                ingest(root, str(link))

            real_parent = root / "real-parent"
            real_parent.mkdir()
            target = real_parent / "nested.pdf"
            target.write_bytes(b"%PDF nested\n")
            parent_link = root / "parent-link"
            parent_link.symlink_to(real_parent, target_is_directory=True)
            with self.assertRaisesRegex(FetchError, "parent path is unsafe|inside the topology root"):
                ingest(root, str(parent_link / "nested.pdf"))

            outside_parent = Path(tempfile.mkdtemp())
            outside_link = outside_parent / "root-link"
            outside_link.symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(FetchError, "parent path is unsafe"):
                ingest(root, str(outside_link / "paper.pdf"))

            nested = root / ".topology"
            nested.mkdir()
            nested_pdf = nested / "bad.pdf"
            nested_pdf.write_bytes(b"%PDF bad\n")
            with self.assertRaisesRegex(FetchError, ".topology"):
                ingest(root, str(nested_pdf))

    def test_github_artifact_parser_splits_types_and_blocks_unpinned_fetch(self):
        sha = "a" * 40
        cases = {
            "blob": (f"https://github.com/o/r/blob/{sha}/src/a.py", "github_blob", "blob"),
            "issue": ("https://github.com/o/r/issues/12", "github_issue", "issue"),
            "pull": ("https://github.com/o/r/pull/12", "github_pull", "pull"),
            "diff_suffix": ("https://github.com/o/r/pull/12.diff", "github_diff", "diff"),
            "diff_files": ("https://github.com/o/r/pull/12/files", "github_diff", "diff"),
            "commit": (f"https://github.com/o/r/commit/{sha}", "github_commit", "commit"),
            "repo": ("https://github.com/o/r", "github_repo", "repo"),
            "raw": (f"https://raw.githubusercontent.com/o/r/{sha}/src/a.py", "github_blob", "blob"),
        }
        for _, (url, kind, artifact_type) in cases.items():
            with self.subTest(url=url):
                artifact = parse_github_artifact(url)
                self.assertEqual(artifact["kind"], kind)
                self.assertEqual(artifact["artifact_type"], artifact_type)

        unpinned = parse_github_artifact("https://github.com/o/r/blob/feature/x/src/a.py")
        self.assertTrue(unpinned["mutable_ref"])
        self.assertTrue(unpinned["ambiguous_ref"])
        fetcher = FakeFetcher(FetchResponse(
            final_url="https://raw.githubusercontent.com/o/r/feature/x/src/a.py",
            status_code=200,
            content_type="text/plain",
            body=b"should not fetch",
        ))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            result = ingest(root, "https://github.com/o/r/blob/feature/x/src/a.py", fetcher=fetcher)
            self.assertEqual(fetcher.calls, [])
            packet = json.loads(result.packet_path.read_text(encoding="utf-8"))
            self.assertEqual(packet["artifacts"][0]["artifact_type"], "blob")
            self.assertTrue(packet["artifacts"][0]["ambiguous_ref"])

        self.assertEqual(classify_source("https://evilgithub.com/o/r/blob/main/a.py"), "article_html")
        self.assertEqual(classify_source("https://github.com.evil/o/r/blob/main/a.py"), "article_html")

    def test_github_pinned_blob_and_diff_fake_fetch_write_bounded_excerpt(self):
        sha = "b" * 40
        fetcher = FakeFetcher(FetchResponse(
            final_url=f"https://raw.githubusercontent.com/o/r/{sha}/src/a.py",
            status_code=200,
            content_type="text/plain",
            body=b"print('hello')\n" * 200,
        ))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            result = ingest(root, f"https://github.com/o/r/blob/{sha}/src/a.py", fetcher=fetcher)
            excerpt = (result.packet_path.parent / "excerpt.md").read_text(encoding="utf-8")
            self.assertIn("print('hello')", excerpt)
            self.assertLessEqual(len(excerpt.strip()), 800)
            self.assertEqual(fetcher.calls[0][0], f"https://raw.githubusercontent.com/o/r/{sha}/src/a.py")

    def test_digest_request_preserves_safe_fetch_metadata_and_redacts_unsafe_fields(self):
        fetcher = FakeFetcher(FetchResponse(
            final_url="https://news.example/article",
            status_code=200,
            content_type="text/html",
            body=b"<main>digest metadata article</main>",
        ))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_with_prompts(root)
            result = ingest(root, "https://news.example/article", fetcher=fetcher)
            packet = json.loads(result.packet_path.read_text(encoding="utf-8"))
            packet["artifacts"].append({
                "kind": "local_blob_ref",
                "storage_hint": "raw/local_blobs/src_x",
                "private_path": "/tmp/private",
                "repo": "safe/repo",
                "final_url": "file:///Users/leofitz/private/secret.txt",
                "raw_url": "raw/local_blobs/src_secret",
            })
            result.packet_path.write_text(json.dumps(packet), encoding="utf-8")
            request = build_digest_model_request(root, packet["id"])
            serialized = json.dumps(request.to_dict(), sort_keys=True)
            self.assertIn("content_type", serialized)
            self.assertIn("final_url", serialized)
            self.assertIn("byte_length", serialized)
            self.assertIn("safe/repo", serialized)
            self.assertNotIn("storage_hint", serialized)
            self.assertNotIn("/tmp/private", serialized)
            self.assertNotIn("file:///Users", serialized)
            self.assertNotIn("raw/local_blobs", serialized)

            sha = "c" * 40
            blob_fetcher = FakeFetcher(FetchResponse(
                final_url=f"https://raw.githubusercontent.com/o/r/{sha}/src/a.py",
                status_code=200,
                content_type="text/plain",
                body=b"print('safe')\n",
            ))
            blob = ingest(root, f"https://github.com/o/r/blob/{sha}/src/a.py", fetcher=blob_fetcher)
            blob_request = build_digest_model_request(root, json.loads(blob.packet_path.read_text(encoding="utf-8"))["id"])
            self.assertIn("src/a.py", json.dumps(blob_request.to_dict(), sort_keys=True))

    def test_fetcher_timeout_like_failure_creates_blocked_packet(self):
        for error in [FetchError("timeout while fetching"), TimeoutError("timed out"), OSError("connection reset")]:
            with self.subTest(error=type(error).__name__):
                def failing_fetcher(url: str, max_bytes: int, exc=error) -> FetchResponse:
                    raise exc

                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    init_topology(root)
                    result = ingest(root, "https://news.example/timeout", fetcher=failing_fetcher)
                    packet = json.loads(result.packet_path.read_text(encoding="utf-8"))
                    self.assertEqual(packet["content_status"], "blocked")
                    self.assertEqual(packet["fetch_chain"][0]["status"], "blocked")
                    self.assertFalse((result.packet_path.parent / "excerpt.md").exists())

    def test_video_platform_shortlink_ingest_is_locator_only_and_does_not_fetch(self):
        douyin_share = "https://v.douyin.com/6l8q1jGwRl4/ Slp:/ 06/05 K@W.MJ"
        self.assertEqual(classify_source(douyin_share), "video_platform")
        parsed = parse_video_platform(douyin_share)
        self.assertEqual(parsed["platform"], "douyin")
        self.assertTrue(parsed["shortlink"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)

            def failing_fetcher(url: str, max_bytes: int) -> FetchResponse:
                raise AssertionError("video_platform intake must not fetch network content")

            result = ingest(root, douyin_share, fetcher=failing_fetcher)
            packet = json.loads(result.packet_path.read_text(encoding="utf-8"))
            excerpt = (result.packet_path.parent / "excerpt.md").read_text(encoding="utf-8")
            self.assertIsNone(result.digest_job_path)
            self.assertEqual(list((root / "ops/queue/digest/pending").glob("job_*.json")), [])
            self.assertEqual(packet["source_type"], "video_platform")
            self.assertEqual(packet["content_status"], "partial")
            self.assertEqual(packet["content_mode"], "excerpt_only")
            self.assertEqual(packet["fetch_chain"][0]["method"], "video_platform_locator")
            self.assertEqual(packet["artifacts"][0]["kind"], "video_platform_locator")
            self.assertEqual(packet["artifacts"][0]["platform"], "douyin")
            self.assertEqual(packet["artifacts"][0]["url"], "https://v.douyin.com/6l8q1jGwRl4/")
            self.assertIn("Required Follow-Up Artifacts", excerpt)
            self.assertIn("transcript_or_caption_text", excerpt)
            with self.assertRaisesRegex(DigestWorkerError, "missing artifacts"):
                build_digest_model_request(root, packet["id"])

    def test_video_platform_rejects_public_text_and_local_blob_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            with self.assertRaisesRegex(FetchError, "excerpt_only"):
                ingest(root, "https://www.tiktok.com/@user/video/123", content_mode="public_text", redistributable="yes")
            with self.assertRaisesRegex(FetchError, "excerpt_only"):
                ingest(root, "https://youtu.be/abc123", content_mode="local_blob")

    def test_video_artifact_attachment_stores_video_blob_outside_git_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            result = ingest(root, "https://v.douyin.com/6l8q1jGwRl4/")
            outside = Path(tempfile.mkdtemp()) / "downloaded.mp4"
            outside.write_bytes(b"fake video bytes")
            updated_path = attach_video_artifact(
                root,
                source_id=json.loads(result.packet_path.read_text(encoding="utf-8"))["id"],
                artifact_kind="video_file",
                artifact_path=outside,
                note="downloaded by operator",
            )
            packet = json.loads(updated_path.read_text(encoding="utf-8"))
            blob = packet["artifacts"][-1]
            self.assertEqual(blob["kind"], "local_blob_ref")
            self.assertEqual(blob["artifact_kind"], "video_file")
            self.assertEqual(blob["byte_length"], len(b"fake video bytes"))
            self.assertIn("raw/local_blobs/", blob["storage_hint"])
            self.assertNotIn(str(outside), json.dumps(packet))
            self.assertTrue((root / blob["storage_hint"]).exists())

    def test_video_text_artifact_attachment_tracks_bounded_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            result = ingest(root, "https://youtu.be/abc123")
            transcript = root / "transcript.txt"
            transcript.write_text("spoken words " * 2000, encoding="utf-8")
            updated_path = attach_video_artifact(
                root,
                source_id=json.loads(result.packet_path.read_text(encoding="utf-8"))["id"],
                artifact_kind="transcript",
                artifact_path=transcript,
                note="operator transcript",
                track_text=True,
            )
            packet = json.loads(updated_path.read_text(encoding="utf-8"))
            artifact = packet["artifacts"][-1]
            self.assertEqual(artifact["kind"], "video_text_artifact")
            self.assertEqual(artifact["artifact_kind"], "transcript")
            self.assertEqual(artifact["path"], "transcript.md")
            tracked = (updated_path.parent / "transcript.md").read_text(encoding="utf-8")
            self.assertLessEqual(len(tracked.strip()), EXTERNAL_PUBLIC_TEXT_LIMIT)
            self.assertIn("spoken words", tracked)

    def test_video_digest_request_includes_attached_deep_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_with_prompts(root)
            result = ingest(root, "https://v.douyin.com/6l8q1jGwRl4/", depth="deep")
            source_id = json.loads(result.packet_path.read_text(encoding="utf-8"))["id"]
            transcript = root / "transcript.txt"
            transcript.write_text(
                "开头反驳一个常见误区。"
                "核心论证提出中心 thesis、三个章节、两个关键概念、一个反例和一个适用边界。"
                "结论要求听众不要只记住标签，要理解机制、证据和条件。",
                encoding="utf-8",
            )
            key_frames = root / "key_frames.txt"
            key_frames.write_text(
                "关键帧：误区标题；章节结构图；反例对照表；适用条件列表。",
                encoding="utf-8",
            )
            audio = root / "audio_summary.txt"
            audio.write_text("音频摘要：作者区分主张、证据、机制、例外和开放问题。", encoding="utf-8")
            for kind, path in [
                ("transcript", transcript),
                ("key_frames", key_frames),
                ("audio_summary", audio),
            ]:
                attach_video_artifact(
                    root,
                    source_id=source_id,
                    artifact_kind=kind,
                    artifact_path=path,
                    track_text=True,
                )
            request = build_digest_model_request(root, source_id)
            serialized = json.dumps(request.to_dict(), ensure_ascii=False, sort_keys=True)
            self.assertEqual(request.source_text_kind, "video_artifacts")
            self.assertIn("## transcript", request.source_text or "")
            self.assertIn("中心 thesis", serialized)
            self.assertIn("关键概念", serialized)
            self.assertIn("适用边界", serialized)
            self.assertIn("开放问题", serialized)
            self.assertIn("opening misconception", request.prompt)
            self.assertIn("chapter or segment structure", request.prompt)
            self.assertIn("Do not assume the video's domain", request.prompt)

    def test_video_artifact_attachment_rejects_non_video_packets_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            draft = root / "draft.md"
            draft.write_text("note\n", encoding="utf-8")
            result = ingest_source(
                root,
                str(draft),
                note="draft",
                depth="standard",
                audience="builders",
                subject_repo_id="repo_knowledge_topology",
                subject_head_sha="abc123",
                base_canonical_rev="rev_current",
                redistributable="yes",
            )
            video = root / "video.mp4"
            video.write_bytes(b"fake")
            with self.assertRaisesRegex(FetchError, "video_platform"):
                attach_video_artifact(root, source_id=result.packet_id, artifact_kind="video_file", artifact_path=video)

            video_source = ingest(root, "https://v.douyin.com/6l8q1jGwRl4/")
            link = root / "video-link.mp4"
            link.symlink_to(video)
            with self.assertRaisesRegex(FetchError, "regular non-symlink"):
                attach_video_artifact(root, source_id=video_source.packet_id, artifact_kind="video_file", artifact_path=link)


if __name__ == "__main__":
    unittest.main()

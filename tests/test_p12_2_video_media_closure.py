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

from knowledge_topology.workers.fetch import attach_video_artifact
from knowledge_topology.workers.init import init_topology


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


def video_ingest(root: Path, url: str = "https://v.douyin.com/6l8q1jGwRl4/", *, auto_digest: bool = False, provider: str = "manual-upload") -> tuple[str, dict]:
    args = [
        "video",
        "ingest",
        url,
        "--root",
        str(root),
        "--note",
        "video note",
        "--subject",
        "repo_knowledge_topology",
        "--subject-head-sha",
        "abc123",
        "--base-canonical-rev",
        "rev_current",
        "--provider",
        provider,
    ]
    if auto_digest:
        args.append("--auto-digest")
    result = cli(*args)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.split("{", 1)[1].rsplit("}", 1)[0].join(["{", "}"]))
    source_line = next(line for line in result.stdout.splitlines() if line.startswith("created video source packet:"))
    packet_path = Path(source_line.split(": ", 1)[1])
    return json.loads(packet_path.read_text(encoding="utf-8"))["id"], payload


class P12VideoMediaClosureTests(unittest.TestCase):
    def test_video_status_and_prepare_digest_report_missing_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            source_id, status = video_ingest(root)
            self.assertFalse(status["ready_for_deep_digest"])
            self.assertEqual(status["missing_required_artifacts"], ["transcript", "key_frames", "audio_summary"])
            status_result = cli("video", "status", "--root", str(root), "--source-id", source_id)
            self.assertEqual(status_result.returncode, 1)
            self.assertIn("missing_required_artifacts", status_result.stdout)
            prepare = cli("video", "prepare-digest", "--root", str(root), "--source-id", source_id)
            self.assertEqual(prepare.returncode, 1)
            self.assertIn("digest_ready", prepare.stdout)
            allowed = cli("video", "prepare-digest", "--root", str(root), "--source-id", source_id, "--allow-locator-only")
            self.assertEqual(allowed.returncode, 0, allowed.stderr)
            self.assertTrue(json.loads(allowed.stdout)["shallow_risk"])

    def test_manual_video_ingest_with_auto_digest_skips_queue_until_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            source_id, status = video_ingest(root, auto_digest=True)
            self.assertTrue(status["digest_job_skipped"])
            self.assertEqual(list((root / "ops/queue/digest/pending").glob("job_*.json")), [])
            self.assertTrue((root / f"raw/packets/{source_id}/packet.json").exists())

    def test_yt_dlp_provider_degrades_when_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            _, status = video_ingest(root, "https://www.youtube.com/watch?v=abc123", provider="yt-dlp")
            provider_results = status["provider_results"]
            self.assertTrue(provider_results)
            self.assertIn(provider_results[0]["status"], {"unavailable", "not_implemented"})

    def test_prepare_digest_succeeds_after_required_text_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            source_id, _ = video_ingest(root)
            for kind in ["transcript", "key_frames", "audio_summary"]:
                path = root / f"{kind}.txt"
                path.write_text(f"{kind} evidence\n", encoding="utf-8")
                attach_video_artifact(
                    root,
                    source_id=source_id,
                    artifact_kind=kind,
                    artifact_path=path,
                    track_text=True,
                )
            status = cli("video", "status", "--root", str(root), "--source-id", source_id)
            self.assertEqual(status.returncode, 0, status.stderr)
            payload = json.loads(status.stdout)
            self.assertTrue(payload["ready_for_deep_digest"])
            self.assertEqual(payload["missing_required_artifacts"], [])
            prepare = cli("video", "prepare-digest", "--root", str(root), "--source-id", source_id)
            self.assertEqual(prepare.returncode, 0, prepare.stderr)
            self.assertTrue(json.loads(prepare.stdout)["digest_ready"])


if __name__ == "__main__":
    unittest.main()

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

from knowledge_topology.workers.fetch import EXTERNAL_PUBLIC_TEXT_LIMIT, FetchError, _safe_excerpt, attach_video_artifact, sha256_text
from knowledge_topology.workers.digest import DigestWorkerError, build_digest_model_request
from knowledge_topology.workers.init import init_topology
from knowledge_topology.workers.video import video_status


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


def write_attestation(root: Path, source_id: str, kind: str, artifact_path: Path, provenance: tuple[str, str, str, str]) -> Path:
    path = root / f"{kind}_attestation.json"
    path.write_text(
        json.dumps({
            "schema_version": "1.0",
            "source_id": source_id,
            "artifact_kind": kind,
            "evidence_origin": provenance[0],
            "coverage": provenance[1],
            "modality": provenance[2],
            "evidence_attestation": provenance[3],
            "output_hash_sha256": sha256_text(_safe_excerpt(artifact_path.read_text(encoding="utf-8"), EXTERNAL_PUBLIC_TEXT_LIMIT)),
            "input_refs": [{"kind": "test_fixture", "hash_sha256": sha256_text(artifact_path.read_text(encoding="utf-8"))}],
            "attested_by": "operator" if provenance[3] == "operator_attested" else "provider",
        }),
        encoding="utf-8",
    )
    return path


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
            allowed_payload = json.loads(allowed.stdout)
            self.assertFalse(allowed_payload["digest_ready"])
            self.assertTrue(allowed_payload["locator_digest_allowed"])
            self.assertTrue(allowed_payload["shallow_risk"])

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
                provenance = {
                    "transcript": ("human_transcript", "partial", "human_note", "operator_attested"),
                    "key_frames": ("human_frame_notes", "partial", "human_note", "operator_attested"),
                    "audio_summary": ("human_audio_summary", "partial", "human_note", "operator_attested"),
                }[kind]
                attach_video_artifact(
                    root,
                    source_id=source_id,
                    artifact_kind=kind,
                    artifact_path=path,
                    track_text=True,
                    evidence_origin=provenance[0],
                    coverage=provenance[1],
                    modality=provenance[2],
                    evidence_attestation=provenance[3],
                    attestation_manifest=write_attestation(root, source_id, kind, path, provenance),
                    trusted_attestation=True,
                )
            status = cli("video", "status", "--root", str(root), "--source-id", source_id)
            self.assertEqual(status.returncode, 0, status.stderr)
            payload = json.loads(status.stdout)
            self.assertTrue(payload["ready_for_deep_digest"])
            self.assertEqual(payload["text_ready_artifacts"], ["audio_summary", "key_frames", "transcript"])
            self.assertEqual(payload["deep_ready_artifacts"], ["audio_summary", "key_frames", "transcript"])
            self.assertEqual(payload["missing_required_artifacts"], [])
            prepare = cli("video", "prepare-digest", "--root", str(root), "--source-id", source_id)
            self.assertEqual(prepare.returncode, 0, prepare.stderr)
            self.assertTrue(json.loads(prepare.stdout)["digest_ready"])

    def test_prepare_digest_ignores_required_artifacts_that_are_only_local_blobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            source_id, _ = video_ingest(root)
            for kind in ["transcript", "key_frames", "audio_summary"]:
                path = root / f"{kind}.bin"
                path.write_bytes(b"local only")
                attach_video_artifact(
                    root,
                    source_id=source_id,
                    artifact_kind=kind,
                    artifact_path=path,
                    track_text=False,
                )
            status = cli("video", "status", "--root", str(root), "--source-id", source_id)
            self.assertEqual(status.returncode, 1)
            payload = json.loads(status.stdout)
            self.assertEqual(payload["present_artifacts"], ["audio_summary", "key_frames", "transcript"])
            self.assertEqual(payload["text_ready_artifacts"], [])
            self.assertEqual(payload["missing_required_artifacts"], ["transcript", "key_frames", "audio_summary"])
            prepare = cli("video", "prepare-digest", "--root", str(root), "--source-id", source_id)
            self.assertEqual(prepare.returncode, 1)
            with self.assertRaisesRegex(DigestWorkerError, "missing artifacts"):
                build_digest_model_request(root, source_id)

    def test_page_visible_video_artifacts_do_not_satisfy_deep_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            source_id, _ = video_ingest(root)
            shallow = {
                "transcript": ("page_visible_excerpt", "page_visible_only", "page"),
                "key_frames": ("page_visible_chapter_list", "chapter_only", "page"),
                "audio_summary": ("inferred_from_page", "page_visible_only", "page"),
            }
            for kind, provenance in shallow.items():
                path = root / f"{kind}.txt"
                path.write_text(f"{kind} copied from page chrome, not video modality\n", encoding="utf-8")
                attach_video_artifact(
                    root,
                    source_id=source_id,
                    artifact_kind=kind,
                    artifact_path=path,
                    track_text=True,
                    evidence_origin=provenance[0],
                    coverage=provenance[1],
                    modality=provenance[2],
                    evidence_attestation="page_visible",
                )
            status = cli("video", "status", "--root", str(root), "--source-id", source_id)
            self.assertEqual(status.returncode, 1)
            payload = json.loads(status.stdout)
            self.assertFalse(payload["ready_for_deep_digest"])
            self.assertEqual(payload["text_ready_artifacts"], ["audio_summary", "key_frames", "transcript"])
            self.assertEqual(payload["deep_ready_artifacts"], [])
            self.assertEqual(len(payload["shallow_only_artifacts"]), 3)
            self.assertIn("page_visible_excerpt cannot satisfy transcript evidence", json.dumps(payload, ensure_ascii=False))
            prepare = cli("video", "prepare-digest", "--root", str(root), "--source-id", source_id)
            self.assertEqual(prepare.returncode, 1)
            with self.assertRaisesRegex(DigestWorkerError, "shallow-only artifacts"):
                build_digest_model_request(root, source_id)

    def test_forged_deep_labels_over_page_visible_text_do_not_satisfy_deep_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            source_id, _ = video_ingest(root)
            forged = {
                "transcript": ("human_transcript", "full", "human_note", "operator_attested", "This is a page-visible excerpt, not a full audio transcript."),
                "key_frames": ("human_frame_notes", "full", "human_note", "operator_attested", "Visible page chapter list: 00:04 维度诅咒; 01:30 James-Stein."),
                "audio_summary": ("human_audio_summary", "full", "human_note", "operator_attested", "This summary is inferred from the visible page structure."),
            }
            for kind, values in forged.items():
                path = root / f"{kind}.txt"
                path.write_text(values[4], encoding="utf-8")
                with self.assertRaisesRegex(FetchError, "trusted provider/operator"):
                    attach_video_artifact(
                        root,
                        source_id=source_id,
                        artifact_kind=kind,
                        artifact_path=path,
                        track_text=True,
                        evidence_origin=values[0],
                        coverage=values[1],
                        modality=values[2],
                        evidence_attestation=values[3],
                        attestation_manifest=write_attestation(root, source_id, kind, path, values[:4]),
                    )
            status = video_status(root, source_id)
            self.assertFalse(status["ready_for_deep_digest"])
            self.assertEqual(status["deep_ready_artifacts"], [])
            self.assertEqual(status["missing_required_artifacts"], ["transcript", "key_frames", "audio_summary"])

    def test_video_trace_reports_stage_and_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            source_id, _ = video_ingest(root)
            trace = cli("video", "trace", "--root", str(root), "--source-id", source_id)
            self.assertEqual(trace.returncode, 0, trace.stderr)
            payload = json.loads(trace.stdout)
            self.assertEqual(payload["stage"], "locator_only")
            self.assertEqual(payload["packet"], f"raw/packets/{source_id}/packet.json")
            self.assertEqual(payload["digest_paths"], [])
            self.assertTrue(payload["blocking_reasons"])


if __name__ == "__main__":
    unittest.main()

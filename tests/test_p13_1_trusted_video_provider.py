import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from knowledge_topology.workers.digest import DigestWorkerError, build_digest_model_request
from knowledge_topology.workers.fetch import attach_video_artifact
from knowledge_topology.workers.init import init_topology
from knowledge_topology.workers.video import video_status, video_trace
from knowledge_topology.workers.video_provider import VideoProviderError, sign_bundle_with_private_key, stage_trusted_video_bundle


PRIVATE_KEY = Ed25519PrivateKey.generate()
PRIVATE_KEY_HEX = PRIVATE_KEY.private_bytes(
    encoding=serialization.Encoding.Raw,
    format=serialization.PrivateFormat.Raw,
    encryption_algorithm=serialization.NoEncryption(),
).hex()
PUBLIC_KEY_HEX = PRIVATE_KEY.public_key().public_bytes(
    encoding=serialization.Encoding.Raw,
    format=serialization.PublicFormat.Raw,
).hex()
PROVIDER_KEY_ID = "test-provider"


def write_key_registry(root: Path) -> None:
    directory = root / "ops/keys"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "video_provider_public_keys.json").write_text(
        json.dumps({
            "schema_version": "1.0",
            "keys": [
                {
                    "key_id": PROVIDER_KEY_ID,
                    "algorithm": "ed25519",
                    "public_key": PUBLIC_KEY_HEX,
                }
            ],
        }),
        encoding="utf-8",
    )


def provider_root(root: Path) -> Path:
    directory = root.parent / "trusted-provider-root"
    directory.mkdir(exist_ok=True)
    return directory


def provider_env(root: Path) -> dict[str, str]:
    return {
        "KNOWLEDGE_TOPOLOGY_VIDEO_PROVIDER_ROOT": str(provider_root(root)),
    }


def cli(*args: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "knowledge_topology.cli", *args],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def video_ingest(root: Path) -> str:
    result = cli(
        "video",
        "ingest",
        "https://v.douyin.com/6l8q1jGwRl4/",
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
    )
    assert result.returncode == 0, result.stderr
    packet_line = next(line for line in result.stdout.splitlines() if line.startswith("created video source packet:"))
    packet_path = Path(packet_line.split(": ", 1)[1])
    return json.loads(packet_path.read_text(encoding="utf-8"))["id"]


def write_fixture(root: Path, *, shallow: bool = False) -> Path:
    directory = root / ("shallow_fixture" if shallow else "trusted_fixture")
    directory.mkdir()
    if shallow:
        (directory / "transcript.md").write_text("Page title lists counterintuitive statistics and visible description only.\n", encoding="utf-8")
        (directory / "key_frames.md").write_text("Chapter list: 00:04 dimension curse; 01:30 James-Stein.\n", encoding="utf-8")
        (directory / "audio_summary.md").write_text("This is inferred from page description, not audio.\n", encoding="utf-8")
    else:
        (directory / "transcript.md").write_text(
            "[00:00:00] Speaker states the repeated multiplicative wager example.\n"
            "[00:01:20] Speaker distinguishes arithmetic expectation from time-average growth.\n",
            encoding="utf-8",
        )
        (directory / "key_frames.md").write_text(
            "## 00:00:11\nVisual: slide with wager payoff tree.\nOCR: 50% x2, 50% x0.5.\n",
            encoding="utf-8",
        )
        (directory / "audio_summary.md").write_text(
            "The speaker argues that positive arithmetic expectation is insufficient under repeated multiplicative exposure.\n",
            encoding="utf-8",
        )
    return directory


class P13TrustedVideoProviderTests(unittest.TestCase):
    def test_provider_run_requires_staged_trusted_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            write_key_registry(root)
            source_id = video_ingest(root)
            result = cli("video", "provider-run", "--root", str(root), "--source-id", source_id, env_extra=provider_env(root))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("trusted provider bundle is missing", result.stderr)
            self.assertFalse(video_status(root, source_id)["ready_for_deep_digest"])

    def test_staged_provider_bundle_attaches_deep_artifacts_and_digest_request_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            write_key_registry(root)
            for prompt in ["digest_deep.md", "digest_standard.md"]:
                (root / "prompts" / prompt).write_text((ROOT / "prompts" / prompt).read_text(encoding="utf-8"), encoding="utf-8")
            source_id = video_ingest(root)
            with self.assertRaisesRegex(DigestWorkerError, "not ready"):
                build_digest_model_request(root, source_id)
            stage_trusted_video_bundle(root, source_id=source_id, artifact_dir=write_fixture(root), provider_root=provider_root(root), signing_private_key=PRIVATE_KEY_HEX, provider_key_id=PROVIDER_KEY_ID)
            result = cli("video", "provider-run", "--root", str(root), "--source-id", source_id, env_extra=provider_env(root))
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["source_id"], source_id)
            self.assertEqual(payload["provider"], "local-fixture")
            self.assertEqual(payload["attached_artifacts"], ["audio_summary", "key_frames", "transcript"])
            self.assertFalse(payload["status_before"]["ready_for_deep_digest"])
            self.assertTrue(payload["status_after"]["ready_for_deep_digest"])
            self.assertEqual(video_status(root, source_id)["deep_ready_artifacts"], ["audio_summary", "key_frames", "transcript"])
            self.assertEqual(video_trace(root, source_id)["stage"], "deep_ready")
            request = build_digest_model_request(root, source_id)
            self.assertEqual(request.source_text_kind, "video_artifacts")
            self.assertIn("## transcript", request.source_text or "")
            text = json.dumps(payload, sort_keys=True)
            self.assertNotIn(str(root), text)
            self.assertNotIn(str(root.resolve()), text)
            for manifest_path in payload["attestation_manifests"]:
                manifest = json.loads((root / manifest_path).read_text(encoding="utf-8"))
                self.assertEqual(manifest["source_id"], source_id)
                self.assertIn(manifest["artifact_kind"], {"transcript", "key_frames", "audio_summary"})
                self.assertTrue(manifest["output_hash_sha256"].startswith("sha256:"))
                self.assertEqual(manifest["provider"]["name"], "local-fixture")
                self.assertNotIn(str(root), json.dumps(manifest))

    def test_provider_run_rejects_shallow_fixture_without_deep_attach(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            write_key_registry(root)
            source_id = video_ingest(root)
            stage_trusted_video_bundle(root, source_id=source_id, artifact_dir=write_fixture(root, shallow=True), provider_root=provider_root(root), signing_private_key=PRIVATE_KEY_HEX, provider_key_id=PROVIDER_KEY_ID)
            result = cli("video", "provider-run", "--root", str(root), "--source-id", source_id, env_extra=provider_env(root))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("shallow", result.stderr)
            self.assertFalse(video_status(root, source_id)["ready_for_deep_digest"])
            self.assertEqual(video_trace(root, source_id)["stage"], "locator_only")
            packet = json.loads((root / f"raw/packets/{source_id}/packet.json").read_text(encoding="utf-8"))
            self.assertNotIn("provider_generated", json.dumps(packet))

    def test_provider_run_rejects_symlink_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            write_key_registry(root)
            source_id = video_ingest(root)
            fixture = write_fixture(root)
            outside = root / "outside.md"
            outside.write_text("outside transcript\n", encoding="utf-8")
            (fixture / "transcript.md").unlink()
            (fixture / "transcript.md").symlink_to(outside)
            with self.assertRaisesRegex(VideoProviderError, "missing|required|directory|artifact"):
                stage_trusted_video_bundle(root, source_id=source_id, artifact_dir=fixture, provider_root=provider_root(root), signing_private_key=PRIVATE_KEY_HEX, provider_key_id=PROVIDER_KEY_ID)
            self.assertFalse(video_status(root, source_id)["ready_for_deep_digest"])

    def test_provider_run_rejects_tampered_bundle_before_partial_attach(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            write_key_registry(root)
            source_id = video_ingest(root)
            bundle_path = stage_trusted_video_bundle(root, source_id=source_id, artifact_dir=write_fixture(root), provider_root=provider_root(root), signing_private_key=PRIVATE_KEY_HEX, provider_key_id=PROVIDER_KEY_ID)
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            bundle["artifacts"][1]["manifest"]["output_hash_sha256"] = "sha256:" + "0" * 64
            payload = {key: value for key, value in bundle.items() if key not in {"signature", "provider_key_id"}}
            bundle["signature"] = sign_bundle_with_private_key(PRIVATE_KEY_HEX, payload)
            bundle_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            result = cli("video", "provider-run", "--root", str(root), "--source-id", source_id, env_extra=provider_env(root))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("output hash", result.stderr)
            packet = json.loads((root / f"raw/packets/{source_id}/packet.json").read_text(encoding="utf-8"))
            self.assertNotIn("provider_generated", json.dumps(packet))

    def test_ordinary_cli_cannot_use_matching_manifest_to_self_attest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            write_key_registry(root)
            source_id = video_ingest(root)
            transcript = root / "transcript.md"
            transcript.write_text("real words\n", encoding="utf-8")
            manifest = root / "fake_manifest.json"
            manifest.write_text(
                json.dumps({
                    "schema_version": "1.0",
                    "source_id": source_id,
                    "artifact_kind": "transcript",
                    "evidence_origin": "audio_transcription",
                    "coverage": "full",
                    "modality": "audio",
                    "evidence_attestation": "provider_generated",
                    "attested_by": "provider",
                    "output_hash_sha256": "sha256:" + "0" * 64,
                }),
                encoding="utf-8",
            )
            result = cli(
                "video",
                "attach-artifact",
                "--root",
                str(root),
                "--source-id",
                source_id,
                "--artifact-kind",
                "transcript",
                "--artifact-path",
                str(transcript),
                "--track-text",
                "--evidence-origin",
                "audio_transcription",
                "--coverage",
                "full",
                "--modality",
                "audio",
                "--evidence-attestation",
                "provider_generated",
                "--attestation-manifest",
                str(manifest),
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("trusted provider/operator", result.stderr)
            self.assertFalse(video_status(root, source_id)["ready_for_deep_digest"])

    def test_deep_readiness_fails_after_artifact_file_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            write_key_registry(root)
            source_id = video_ingest(root)
            stage_trusted_video_bundle(root, source_id=source_id, artifact_dir=write_fixture(root), provider_root=provider_root(root), signing_private_key=PRIVATE_KEY_HEX, provider_key_id=PROVIDER_KEY_ID)
            self.assertEqual(cli("video", "provider-run", "--root", str(root), "--source-id", source_id, env_extra=provider_env(root)).returncode, 0)
            self.assertTrue(video_status(root, source_id)["ready_for_deep_digest"])
            (root / f"raw/packets/{source_id}/transcript.md").write_text("tampered\n", encoding="utf-8")
            status = video_status(root, source_id)
            self.assertFalse(status["ready_for_deep_digest"])
            self.assertIn("hash", json.dumps(status["rejected_for_deep_digest"]))
            self.assertNotEqual(video_trace(root, source_id)["stage"], "deep_ready")
            with self.assertRaisesRegex(DigestWorkerError, "not ready"):
                build_digest_model_request(root, source_id)

    def test_deep_readiness_fails_after_attestation_manifest_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            write_key_registry(root)
            source_id = video_ingest(root)
            stage_trusted_video_bundle(root, source_id=source_id, artifact_dir=write_fixture(root), provider_root=provider_root(root), signing_private_key=PRIVATE_KEY_HEX, provider_key_id=PROVIDER_KEY_ID)
            self.assertEqual(cli("video", "provider-run", "--root", str(root), "--source-id", source_id, env_extra=provider_env(root)).returncode, 0)
            self.assertTrue(video_status(root, source_id)["ready_for_deep_digest"])
            for manifest in (root / f"raw/packets/{source_id}/attestations").glob("*.json"):
                manifest.unlink()
            status = video_status(root, source_id)
            self.assertFalse(status["ready_for_deep_digest"])
            self.assertIn("manifest", json.dumps(status["rejected_for_deep_digest"]))
            self.assertNotEqual(video_trace(root, source_id)["stage"], "deep_ready")

    def test_trusted_artifact_then_shallow_overwrite_cannot_remain_deep_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            write_key_registry(root)
            source_id = video_ingest(root)
            stage_trusted_video_bundle(root, source_id=source_id, artifact_dir=write_fixture(root), provider_root=provider_root(root), signing_private_key=PRIVATE_KEY_HEX, provider_key_id=PROVIDER_KEY_ID)
            self.assertEqual(cli("video", "provider-run", "--root", str(root), "--source-id", source_id, env_extra=provider_env(root)).returncode, 0)
            self.assertTrue(video_status(root, source_id)["ready_for_deep_digest"])
            shallow = root / "shallow_transcript.md"
            shallow.write_text("Page title and visible description only.\n", encoding="utf-8")
            result = cli(
                "video",
                "attach-artifact",
                "--root",
                str(root),
                "--source-id",
                source_id,
                "--artifact-kind",
                "transcript",
                "--artifact-path",
                str(shallow),
                "--track-text",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            status = video_status(root, source_id)
            self.assertFalse(status["ready_for_deep_digest"])
            self.assertNotIn("transcript", status["deep_ready_artifacts"])

    def test_provider_run_auto_digest_enqueues_only_after_deep_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_topology(root)
            write_key_registry(root)
            source_id = video_ingest(root)
            stage_trusted_video_bundle(root, source_id=source_id, artifact_dir=write_fixture(root), provider_root=provider_root(root), signing_private_key=PRIVATE_KEY_HEX, provider_key_id=PROVIDER_KEY_ID)
            result = cli(
                "video",
                "provider-run",
                "--root",
                str(root),
                "--source-id",
                source_id,
                "--auto-digest",
                "--subject",
                "repo_knowledge_topology",
                "--subject-head-sha",
                "abc123",
                "--base-canonical-rev",
                "rev_current",
                env_extra=provider_env(root),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            jobs = list((root / "ops/queue/digest/pending").glob("job_*.json"))
            self.assertEqual(len(jobs), 1)
            job = json.loads(jobs[0].read_text(encoding="utf-8"))
            self.assertEqual(job["payload"]["source_id"], source_id)
            self.assertEqual(job["subject_repo_id"], "repo_knowledge_topology")
            self.assertEqual(list((root / "digests/by_source").glob("**/*.json")), [])
            self.assertEqual(list((root / "mutations/pending").glob("mut_*.json")), [])


if __name__ == "__main__":
    unittest.main()

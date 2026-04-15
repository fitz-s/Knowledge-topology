import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


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


def init_topology(root: Path) -> None:
    result = cli("init", "--root", str(root))
    assert result.returncode == 0, result.stderr


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
    return json.loads(Path(packet_line.split(": ", 1)[1]).read_text(encoding="utf-8"))["id"]


def write_fixture(root: Path) -> Path:
    directory = root / "provider-input"
    directory.mkdir()
    (directory / "transcript.md").write_text("[00:00] audio transcript\n", encoding="utf-8")
    (directory / "key_frames.md").write_text("Frame: visual evidence\n", encoding="utf-8")
    (directory / "audio_summary.md").write_text("Audio-derived summary\n", encoding="utf-8")
    return directory


def write_registry(root: Path, entry: dict) -> None:
    directory = root / "ops/keys"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "video_provider_public_keys.json").write_text(
        json.dumps({"schema_version": "1.0", "keys": [entry]}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def generate_keypair(root: Path, keys: Path, *, key_id: str = "local_provider", provider_name: str = "local_provider") -> dict:
    keygen = cli(
        "video",
        "provider-keygen",
        "--root",
        str(root),
        "--output-dir",
        str(keys),
        "--key-id",
        key_id,
        "--provider-name",
        provider_name,
    )
    assert keygen.returncode == 0, keygen.stderr
    return json.loads(keygen.stdout)


class P13LocalVideoProviderGeneratorTests(unittest.TestCase):
    def test_keygen_register_stage_and_provider_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "topology"
            keys = Path(tmp) / "keys"
            provider_root = Path(tmp) / "provider-root"
            init_topology(root)
            source_id = video_ingest(root)
            keys_payload = generate_keypair(root, keys)
            private_key_path = keys / "local_provider.private.json"
            public_key_path = keys / "local_provider.public.json"
            self.assertTrue(private_key_path.exists())
            self.assertTrue(public_key_path.exists())
            self.assertNotIn("private_key_path", keys_payload)
            self.assertNotIn("public_key_path", keys_payload)
            write_registry(root, keys_payload["registry_entry"])
            stage = cli(
                "video",
                "provider-stage",
                "--root",
                str(root),
                "--source-id",
                source_id,
                "--artifact-dir",
                str(write_fixture(Path(tmp))),
                "--provider-root",
                str(provider_root),
                "--private-key-file",
                str(private_key_path),
            )
            self.assertEqual(stage.returncode, 0, stage.stderr)
            stage_payload = json.loads(stage.stdout)
            self.assertEqual(stage_payload["source_id"], source_id)
            self.assertEqual(stage_payload["bundle_path"], f"{source_id}/bundle.json")
            self.assertNotIn(str(root), json.dumps(stage_payload))
            run = cli(
                "video",
                "provider-run",
                "--root",
                str(root),
                "--source-id",
                source_id,
                env_extra={"KNOWLEDGE_TOPOLOGY_VIDEO_PROVIDER_ROOT": str(provider_root)},
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            run_payload = json.loads(run.stdout)
            self.assertTrue(run_payload["status_after"]["ready_for_deep_digest"])

    def test_provider_stage_rejects_private_key_inside_topology(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "topology"
            init_topology(root)
            source_id = video_ingest(root)
            keys = Path(tmp) / "keys"
            generate_keypair(root, keys, key_id="bad_provider")
            private_key_path = root / ".tmp/keys/bad_provider.private.json"
            private_key_path.parent.mkdir(parents=True)
            shutil.copyfile(keys / "bad_provider.private.json", private_key_path)
            result = cli(
                "video",
                "provider-stage",
                "--root",
                str(root),
                "--source-id",
                source_id,
                "--artifact-dir",
                str(write_fixture(Path(tmp))),
                "--provider-root",
                str(Path(tmp) / "provider-root"),
                "--private-key-file",
                str(private_key_path),
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("private_key_file must be outside topology root", result.stderr)

    def test_provider_stage_rejects_private_key_symlink_from_openclaw_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "topology"
            keys = Path(tmp) / "keys"
            openclaw = Path(tmp) / ".openclaw/workspace"
            openclaw.mkdir(parents=True)
            init_topology(root)
            source_id = video_ingest(root)
            payload = generate_keypair(root, keys)
            write_registry(root, payload["registry_entry"])
            link = openclaw / "private.json"
            link.symlink_to(keys / "local_provider.private.json")
            result = cli(
                "video",
                "provider-stage",
                "--root",
                str(root),
                "--source-id",
                source_id,
                "--artifact-dir",
                str(write_fixture(Path(tmp))),
                "--provider-root",
                str(Path(tmp) / "provider-root"),
                "--private-key-file",
                str(link),
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("OpenClaw private state", result.stderr)

    def test_provider_keygen_rejects_output_inside_topology(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "topology"
            init_topology(root)
            result = cli(
                "video",
                "provider-keygen",
                "--root",
                str(root),
                "--output-dir",
                str(root / ".tmp/keys"),
                "--key-id",
                "bad_provider",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("output_dir must be outside topology root", result.stderr)

    def test_provider_stage_rejects_artifact_dir_inside_topology(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "topology"
            keys = Path(tmp) / "keys"
            init_topology(root)
            source_id = video_ingest(root)
            payload = generate_keypair(root, keys)
            write_registry(root, payload["registry_entry"])
            result = cli(
                "video",
                "provider-stage",
                "--root",
                str(root),
                "--source-id",
                source_id,
                "--artifact-dir",
                str(write_fixture(root)),
                "--provider-root",
                str(Path(tmp) / "provider-root"),
                "--private-key-file",
                str(keys / "local_provider.private.json"),
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("artifact_dir must be outside topology root", result.stderr)

    def test_provider_stage_rejects_artifact_dir_inside_openclaw_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "topology"
            keys = Path(tmp) / "keys"
            openclaw = Path(tmp) / ".openclaw/workspace"
            openclaw.mkdir(parents=True)
            init_topology(root)
            source_id = video_ingest(root)
            payload = generate_keypair(root, keys)
            write_registry(root, payload["registry_entry"])
            result = cli(
                "video",
                "provider-stage",
                "--root",
                str(root),
                "--source-id",
                source_id,
                "--artifact-dir",
                str(write_fixture(openclaw)),
                "--provider-root",
                str(Path(tmp) / "provider-root"),
                "--private-key-file",
                str(keys / "local_provider.private.json"),
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("OpenClaw private state", result.stderr)

    def test_provider_stage_rejects_provider_name_spoof(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "topology"
            keys = Path(tmp) / "keys"
            init_topology(root)
            source_id = video_ingest(root)
            payload = generate_keypair(root, keys)
            write_registry(root, payload["registry_entry"])
            result = cli(
                "video",
                "provider-stage",
                "--root",
                str(root),
                "--source-id",
                source_id,
                "--artifact-dir",
                str(write_fixture(Path(tmp))),
                "--provider-root",
                str(Path(tmp) / "provider-root"),
                "--private-key-file",
                str(keys / "local_provider.private.json"),
                "--provider-name",
                "spoofed_provider",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("provider_name must match registered provider", result.stderr)

    def test_provider_stage_rejects_operator_attestation_without_registry_capability(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "topology"
            keys = Path(tmp) / "keys"
            init_topology(root)
            source_id = video_ingest(root)
            payload = generate_keypair(root, keys)
            write_registry(root, payload["registry_entry"])
            result = cli(
                "video",
                "provider-stage",
                "--root",
                str(root),
                "--source-id",
                source_id,
                "--artifact-dir",
                str(write_fixture(Path(tmp))),
                "--provider-root",
                str(Path(tmp) / "provider-root"),
                "--private-key-file",
                str(keys / "local_provider.private.json"),
                "--attested-by",
                "operator",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not allowed to create operator attestations", result.stderr)

    def test_provider_run_rejects_provider_root_symlink_from_openclaw_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "topology"
            openclaw = Path(tmp) / ".openclaw/workspace"
            target = Path(tmp) / "provider-root"
            openclaw.mkdir(parents=True)
            target.mkdir()
            init_topology(root)
            source_id = video_ingest(root)
            link = openclaw / "provider-root"
            link.symlink_to(target, target_is_directory=True)
            result = cli(
                "video",
                "provider-run",
                "--root",
                str(root),
                "--source-id",
                source_id,
                env_extra={"KNOWLEDGE_TOPOLOGY_VIDEO_PROVIDER_ROOT": str(link)},
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("OpenClaw private state", result.stderr)


if __name__ == "__main__":
    unittest.main()

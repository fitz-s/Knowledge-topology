"""P13.1 trusted video provider bridge."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization

from knowledge_topology.ids import is_valid_id, new_id
from knowledge_topology.paths import TopologyPaths
from knowledge_topology.storage.spool import create_job
from knowledge_topology.storage.transaction import atomic_write_text
from knowledge_topology.workers.fetch import FetchError, attach_video_artifact, read_packet, sha256_bytes, sha256_text
from knowledge_topology.workers.fetch import _safe_excerpt, EXTERNAL_PUBLIC_TEXT_LIMIT
from knowledge_topology.workers.video import text_contains_shallow_markers, video_status


class VideoProviderError(ValueError):
    """Raised when trusted video provider output cannot be accepted."""


REQUIRED_ARTIFACTS = ("transcript", "key_frames", "audio_summary")
PROVIDER_PROVENANCE = {
    "transcript": ("audio_transcription", "partial", "audio", "provider_generated"),
    "key_frames": ("vision_frame_analysis", "partial", "video", "provider_generated"),
    "audio_summary": ("audio_model_summary", "partial", "audio", "provider_generated"),
}
OPERATOR_PROVENANCE = {
    "transcript": ("human_transcript", "partial", "human_note", "operator_attested"),
    "key_frames": ("human_frame_notes", "partial", "human_note", "operator_attested"),
    "audio_summary": ("human_audio_summary", "partial", "human_note", "operator_attested"),
}
PROVIDER_ROOT_ENV = "KNOWLEDGE_TOPOLOGY_VIDEO_PROVIDER_ROOT"
PROVIDER_KEYS_RELATIVE = "ops/keys/video_provider_public_keys.json"
SAFE_PROVIDER_TOKEN = re.compile(r"[A-Za-z0-9_.:-]+")


@dataclass(frozen=True)
class VideoProviderResult:
    payload: dict[str, Any]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def safe_token(value: str, field: str) -> str:
    if not isinstance(value, str) or not SAFE_PROVIDER_TOKEN.fullmatch(value.strip()):
        raise VideoProviderError(f"{field} must be a safe token")
    return value.strip()


def display_path(paths: TopologyPaths, path: str | Path) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        return str(candidate)
    try:
        return str(candidate.resolve().relative_to(paths.root))
    except ValueError:
        return candidate.name


def bounded_error(paths: TopologyPaths, exc: BaseException) -> str:
    text = " ".join(str(exc).split())[:500]
    return text.replace(str(paths.root), ".").replace(str(paths.root.resolve()), ".")


def sign_bundle_with_private_key(private_key_hex: str, payload: dict[str, Any]) -> str:
    private_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex))
    return private_key.sign(canonical_json(payload).encode("utf-8")).hex()


def public_key_hex_from_private(private_key_hex: str) -> str:
    private_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex))
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()


def safe_external_file(paths: TopologyPaths, path: str | Path, label: str) -> Path:
    raw = Path(path).expanduser()
    if raw.is_symlink() or any(part.casefold() == ".openclaw" for part in raw.parts):
        raise VideoProviderError(f"{label} must not be a symlink or inside OpenClaw private state")
    candidate = raw.resolve()
    if not candidate.is_file():
        raise VideoProviderError(f"{label} must be a regular non-symlink file")
    if candidate == paths.root or paths.root in candidate.parents:
        raise VideoProviderError(f"{label} must be outside topology root")
    if any(part.casefold() == ".openclaw" for part in candidate.parts):
        raise VideoProviderError(f"{label} must not be inside OpenClaw private state")
    return candidate


def safe_external_dir(paths: TopologyPaths, path: str | Path, label: str, *, create: bool = False) -> Path:
    raw = Path(path).expanduser()
    if raw.is_symlink() or any(part.casefold() == ".openclaw" for part in raw.parts):
        raise VideoProviderError(f"{label} must not be a symlink or inside OpenClaw private state")
    candidate = raw.resolve()
    if candidate == paths.root or paths.root in candidate.parents:
        raise VideoProviderError(f"{label} must be outside topology root")
    if any(part.casefold() == ".openclaw" for part in candidate.parts):
        raise VideoProviderError(f"{label} must not be inside OpenClaw private state")
    if create:
        candidate.mkdir(parents=True, exist_ok=True)
    if candidate.is_symlink() or not candidate.is_dir():
        raise VideoProviderError(f"{label} must be a real directory")
    return candidate


def read_key_payload(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise VideoProviderError(f"{label} JSON is invalid: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != "1.0":
        raise VideoProviderError(f"{label} must be a versioned JSON object")
    if payload.get("algorithm") != "ed25519":
        raise VideoProviderError(f"{label} algorithm must be ed25519")
    return payload


def generate_provider_keypair(
    output_dir: str | Path,
    *,
    key_id: str,
    provider_name: str = "local-provider",
    topology_root: str | Path | None = None,
) -> dict[str, Any]:
    safe_key = safe_token(key_id, "key_id")
    safe_provider = safe_token(provider_name, "provider_name")
    if topology_root is None:
        directory = Path(output_dir).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
        if directory.is_symlink() or not directory.is_dir():
            raise VideoProviderError("output_dir must be a real directory")
    else:
        directory = safe_external_dir(TopologyPaths.from_root(topology_root), output_dir, "output_dir", create=True)
    private_key = Ed25519PrivateKey.generate()
    private_hex = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    ).hex()
    public_hex = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()
    private_path = directory / f"{safe_key}.private.json"
    public_path = directory / f"{safe_key}.public.json"
    for path in [private_path, public_path]:
        if path.exists() or path.is_symlink():
            raise VideoProviderError(f"refusing to overwrite key file: {path.name}")
    private_payload = {
        "schema_version": "1.0",
        "key_id": safe_key,
        "provider_name": safe_provider,
        "algorithm": "ed25519",
        "private_key": private_hex,
        "public_key": public_hex,
        "created_at": utc_now(),
    }
    public_payload = {
        "schema_version": "1.0",
        "key_id": safe_key,
        "provider_name": safe_provider,
        "algorithm": "ed25519",
        "public_key": public_hex,
        "created_at": private_payload["created_at"],
    }
    atomic_write_text(private_path, json.dumps(private_payload, indent=2, sort_keys=True) + "\n")
    private_path.chmod(0o600)
    atomic_write_text(public_path, json.dumps(public_payload, indent=2, sort_keys=True) + "\n")
    return {
        "schema_version": "1.0",
        "key_id": safe_key,
        "provider_name": safe_provider,
        "private_key_written": True,
        "public_key_written": True,
        "registry_entry": {
            "key_id": safe_key,
            "provider_name": safe_provider,
            "algorithm": "ed25519",
            "public_key": public_hex,
            "allowed_attestations": ["provider"],
        },
        "registry_instruction": "Add registry_entry to ops/keys/video_provider_public_keys.json through a reviewed topology change and commit it before provider-run.",
    }


def ensure_key_registry_trusted(paths: TopologyPaths) -> Path:
    path = paths.resolve(PROVIDER_KEYS_RELATIVE)
    if path.is_symlink() or not path.is_file():
        raise VideoProviderError("trusted video provider public-key registry is missing")
    inside = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=paths.root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if inside.returncode == 0:
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", PROVIDER_KEYS_RELATIVE], cwd=paths.root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if tracked.returncode != 0:
            raise VideoProviderError("trusted video provider public-key registry must be tracked")
        status = subprocess.run(["git", "status", "--porcelain", "--", PROVIDER_KEYS_RELATIVE], cwd=paths.root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if status.stdout.strip():
            raise VideoProviderError("trusted video provider public-key registry must be clean")
    return path


def load_provider_key_entry(paths: TopologyPaths, key_id: str) -> dict[str, Any]:
    registry = json.loads(ensure_key_registry_trusted(paths).read_text(encoding="utf-8"))
    if not isinstance(registry, dict) or registry.get("schema_version") != "1.0":
        raise VideoProviderError("trusted video provider public-key registry is invalid")
    for item in registry.get("keys", []):
        if isinstance(item, dict) and item.get("key_id") == key_id:
            if item.get("algorithm") != "ed25519":
                raise VideoProviderError("trusted video provider key algorithm is unsupported")
            public_key = item.get("public_key")
            if not isinstance(public_key, str):
                raise VideoProviderError("trusted video provider public key is invalid")
            return item
    raise VideoProviderError("trusted video provider key id is unknown")


def load_provider_public_key(paths: TopologyPaths, key_id: str) -> Ed25519PublicKey:
    public_key = load_provider_key_entry(paths, key_id)["public_key"]
    return Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key))


def verify_signature(paths: TopologyPaths, bundle: dict[str, Any]) -> dict[str, Any]:
    signature = bundle.get("signature")
    key_id = bundle.get("provider_key_id")
    if not isinstance(signature, str):
        raise VideoProviderError("trusted provider bundle signature missing")
    if not isinstance(key_id, str):
        raise VideoProviderError("trusted provider bundle key id missing")
    payload = {key: value for key, value in bundle.items() if key not in {"signature", "provider_key_id"}}
    try:
        load_provider_public_key(paths, key_id).verify(bytes.fromhex(signature), canonical_json(payload).encode("utf-8"))
    except Exception as exc:
        raise VideoProviderError("trusted provider bundle signature mismatch")
    return payload


def provider_root_from_env(paths: TopologyPaths) -> Path:
    value = os.environ.get(PROVIDER_ROOT_ENV, "")
    if not value.strip():
        raise VideoProviderError(f"{PROVIDER_ROOT_ENV} is required")
    return safe_external_dir(paths, value, "trusted provider root")


def safe_trusted_dir(paths: TopologyPaths, provider_root: Path, source_id: str) -> Path:
    if not is_valid_id(source_id, prefix="src"):
        raise VideoProviderError("source_id must use src_ opaque ID")
    directory = provider_root / source_id
    directory.mkdir(parents=True, exist_ok=True)
    if directory.is_symlink():
        raise VideoProviderError("trusted provider directory must not be a symlink")
    if provider_root not in directory.resolve().parents:
        raise VideoProviderError("trusted provider directory escaped provider root")
    return directory


def source_packet_exists(paths: TopologyPaths, source_id: str) -> None:
    try:
        _, packet = read_packet(paths, source_id)
    except FetchError as exc:
        raise VideoProviderError(str(exc)) from exc
    if packet.source_type != "video_platform":
        raise VideoProviderError("source packet is not video_platform")


def safe_input_file(directory: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise VideoProviderError("provider bundle file path is unsafe")
    path = directory / rel
    if path.is_symlink() or not path.is_file():
        raise VideoProviderError("provider bundle file must be regular and non-symlink")
    if directory.resolve() not in path.resolve().parents:
        raise VideoProviderError("provider bundle file escaped trusted directory")
    return path


def staged_body_hash(path: Path) -> str:
    body = _safe_excerpt(path.read_text(encoding="utf-8", errors="replace"), EXTERNAL_PUBLIC_TEXT_LIMIT)
    return sha256_text(body)


def build_manifest(
    *,
    source_id: str,
    artifact_kind: str,
    provenance: tuple[str, str, str, str],
    provider_name: str,
    attested_by: str,
    output_hash: str,
    input_hash: str,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "attestation_id": new_id("evt"),
        "source_id": source_id,
        "artifact_kind": artifact_kind,
        "evidence_origin": provenance[0],
        "coverage": provenance[1],
        "modality": provenance[2],
        "evidence_attestation": provenance[3],
        "attested_by": attested_by,
        "provider": {"name": provider_name, "version": "1"},
        "input_refs": [{"kind": "staged_provider_file", "hash_sha256": input_hash}],
        "output_hash_sha256": output_hash,
        "created_at": utc_now(),
        "trust_scope": provenance[3],
    }


def stage_trusted_video_bundle(
    root: str | Path,
    *,
    source_id: str,
    artifact_dir: str | Path,
    provider_root: str | Path,
    signing_private_key: str,
    provider_key_id: str = "test-provider",
    provider_name: str = "local-fixture",
    attested_by: str = "provider",
) -> Path:
    """Stage a signed trusted provider bundle.

    This helper is intentionally not exposed through the CLI. Tests and future
    trusted provider processes may call it to model provider-owned output.
    """

    paths = TopologyPaths.from_root(root)
    source_packet_exists(paths, source_id)
    provider_root_path = safe_external_dir(paths, provider_root, "trusted provider root", create=True)
    source_dir = Path(artifact_dir).expanduser()
    if source_dir.is_symlink() or not source_dir.is_dir():
        raise VideoProviderError("artifact_dir must be a real directory")
    trusted = safe_trusted_dir(paths, provider_root_path, source_id)
    inputs = trusted / "inputs"
    inputs.mkdir(exist_ok=True)
    if inputs.is_symlink():
        raise VideoProviderError("trusted input directory must not be a symlink")
    provenance_map = PROVIDER_PROVENANCE if attested_by == "provider" else OPERATOR_PROVENANCE
    artifacts = []
    for kind in REQUIRED_ARTIFACTS:
        candidate = source_dir / f"{kind}.md"
        if candidate.is_symlink() or not candidate.is_file():
            raise VideoProviderError(f"trusted provider missing required artifact: {kind}")
        target = inputs / f"{kind}.md"
        shutil.copyfile(candidate, target)
        input_hash = sha256_bytes(target.read_bytes())
        output_hash = staged_body_hash(target)
        provenance = provenance_map[kind]
        manifest = build_manifest(
            source_id=source_id,
            artifact_kind=kind,
            provenance=provenance,
            provider_name=provider_name,
            attested_by=attested_by,
            output_hash=output_hash,
            input_hash=input_hash,
        )
        artifacts.append({
            "artifact_kind": kind,
            "file": f"inputs/{kind}.md",
            "manifest": manifest,
        })
    payload = {
        "schema_version": "1.0",
        "source_id": source_id,
        "provider": {"name": provider_name, "version": "1"},
        "created_at": utc_now(),
        "artifacts": artifacts,
    }
    bundle = {
        **payload,
        "provider_key_id": provider_key_id,
        "signature": sign_bundle_with_private_key(signing_private_key, payload),
    }
    bundle_path = trusted / "bundle.json"
    atomic_write_text(bundle_path, json.dumps(bundle, indent=2, sort_keys=True) + "\n")
    return bundle_path


def stage_video_provider_bundle_from_key(
    root: str | Path,
    *,
    source_id: str,
    artifact_dir: str | Path,
    provider_root: str | Path,
    private_key_file: str | Path,
    provider_key_id: str | None = None,
    provider_name: str | None = None,
    attested_by: str = "provider",
) -> dict[str, Any]:
    paths = TopologyPaths.from_root(root)
    private_path = safe_external_file(paths, private_key_file, "private_key_file")
    source_dir = safe_external_dir(paths, artifact_dir, "artifact_dir")
    key_payload = read_key_payload(private_path, "private_key_file")
    private_key = key_payload.get("private_key")
    if not isinstance(private_key, str):
        raise VideoProviderError("private_key_file private_key is required")
    key_id = safe_token(provider_key_id or key_payload.get("key_id", ""), "provider_key_id")
    if key_payload.get("key_id") and key_payload.get("key_id") != key_id:
        raise VideoProviderError("private_key_file key_id does not match provider_key_id")
    registry_entry = load_provider_key_entry(paths, key_id)
    registered_provider = safe_token(registry_entry.get("provider_name", ""), "registered provider_name")
    payload_provider = key_payload.get("provider_name")
    if isinstance(payload_provider, str) and payload_provider and payload_provider != registered_provider:
        raise VideoProviderError("private_key_file provider_name does not match registered provider")
    requested_provider = safe_token(provider_name, "provider_name") if provider_name is not None else registered_provider
    if requested_provider != registered_provider:
        raise VideoProviderError("provider_name must match registered provider")
    allowed_attestations = registry_entry.get("allowed_attestations")
    if not isinstance(allowed_attestations, list) or not all(isinstance(value, str) for value in allowed_attestations):
        raise VideoProviderError("trusted video provider registry entry must declare allowed_attestations")
    if attested_by not in allowed_attestations:
        raise VideoProviderError(f"provider key is not allowed to create {attested_by} attestations")
    registered_hex = str(registry_entry["public_key"])
    if registered_hex != public_key_hex_from_private(private_key):
        raise VideoProviderError("private key does not match registered provider public key")
    bundle_path = stage_trusted_video_bundle(
        paths.root,
        source_id=source_id,
        artifact_dir=source_dir,
        provider_root=provider_root,
        signing_private_key=private_key,
        provider_key_id=key_id,
        provider_name=registered_provider,
        attested_by=attested_by,
    )
    return {
        "schema_version": "1.0",
        "source_id": source_id,
        "provider": registered_provider,
        "provider_key_id": key_id,
        "bundle_path": f"{source_id}/bundle.json",
        "provider_root_env": PROVIDER_ROOT_ENV,
    }


def read_verified_bundle(paths: TopologyPaths, source_id: str) -> tuple[Path, dict[str, Any]]:
    source_packet_exists(paths, source_id)
    trusted = safe_trusted_dir(paths, provider_root_from_env(paths), source_id)
    bundle_path = trusted / "bundle.json"
    if bundle_path.is_symlink() or not bundle_path.is_file():
        raise VideoProviderError("trusted provider bundle is missing")
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise VideoProviderError(f"trusted provider bundle JSON is invalid: {exc}") from exc
    if not isinstance(bundle, dict):
        raise VideoProviderError("trusted provider bundle must be a JSON object")
    payload = verify_signature(paths, bundle)
    if payload.get("source_id") != source_id:
        raise VideoProviderError("trusted provider bundle source_id mismatch")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise VideoProviderError("trusted provider bundle artifacts must be a list")
    return trusted, payload


def write_attestation_manifest(paths: TopologyPaths, source_id: str, manifest: dict[str, Any]) -> Path:
    directory = paths.ensure_dir(f"raw/packets/{source_id}/attestations")
    artifact_kind = manifest["artifact_kind"]
    attestation_id = manifest["attestation_id"]
    path = directory / f"{artifact_kind}_{attestation_id}.json"
    atomic_write_text(path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return path


def run_video_provider(
    root: str | Path,
    *,
    source_id: str,
    provider: str = "staged-bundle",
    auto_digest: bool = False,
    subject_repo_id: str | None = None,
    subject_head_sha: str | None = None,
    base_canonical_rev: str | None = None,
    audience: str = "all",
) -> VideoProviderResult:
    if provider != "staged-bundle":
        raise VideoProviderError("only staged-bundle provider is supported by this CLI")
    paths = TopologyPaths.from_root(root)
    status_before = video_status(paths.root, source_id)
    trusted_dir, bundle = read_verified_bundle(paths, source_id)
    provider_name = bundle.get("provider", {}).get("name", provider)
    manifests: list[str] = []
    attached: list[str] = []
    seen = set()
    try:
        available = {item.get("artifact_kind") for item in bundle["artifacts"] if isinstance(item, dict)}
        missing = sorted(set(REQUIRED_ARTIFACTS) - available)
        if missing:
            raise VideoProviderError("trusted provider bundle missing artifacts: " + ", ".join(missing))
        validated: list[tuple[str, Path, dict[str, Any]]] = []
        for item in bundle["artifacts"]:
            if not isinstance(item, dict):
                raise VideoProviderError("trusted provider artifact entry must be an object")
            kind = item.get("artifact_kind")
            if kind not in REQUIRED_ARTIFACTS:
                raise VideoProviderError("trusted provider artifact kind is invalid")
            seen.add(kind)
            file_value = item.get("file")
            if not isinstance(file_value, str):
                raise VideoProviderError("trusted provider artifact file is required")
            input_file = safe_input_file(trusted_dir, file_value)
            manifest = item.get("manifest")
            if not isinstance(manifest, dict):
                raise VideoProviderError("trusted provider manifest is required")
            output_hash = staged_body_hash(input_file)
            input_hash = sha256_bytes(input_file.read_bytes())
            if text_contains_shallow_markers(input_file.read_text(encoding="utf-8", errors="replace")):
                raise VideoProviderError("trusted provider artifact appears to be shallow/page-visible evidence")
            if manifest.get("source_id") != source_id:
                raise VideoProviderError("trusted provider manifest source_id mismatch")
            if manifest.get("artifact_kind") != kind:
                raise VideoProviderError("trusted provider manifest artifact_kind mismatch")
            if manifest.get("output_hash_sha256") != output_hash:
                raise VideoProviderError("trusted provider manifest output hash mismatch")
            input_refs = manifest.get("input_refs")
            if not isinstance(input_refs, list) or not any(isinstance(ref, dict) and ref.get("hash_sha256") == input_hash for ref in input_refs):
                raise VideoProviderError("trusted provider manifest input hash mismatch")
            validated.append((kind, input_file, manifest))
        for kind, input_file, manifest in validated:
            manifest_path = write_attestation_manifest(paths, source_id, manifest)
            attach_video_artifact(
                paths.root,
                source_id=source_id,
                artifact_kind=kind,
                artifact_path=input_file,
                note=f"trusted {provider_name} evidence",
                track_text=True,
                evidence_origin=manifest["evidence_origin"],
                coverage=manifest["coverage"],
                modality=manifest["modality"],
                evidence_attestation=manifest["evidence_attestation"],
                attestation_manifest=manifest_path,
                trusted_attestation=True,
            )
            manifests.append(display_path(paths, manifest_path))
            attached.append(kind)
    except Exception as exc:
        raise VideoProviderError(bounded_error(paths, exc)) from exc
    status_after = video_status(paths.root, source_id)
    digest_job_path = None
    if auto_digest:
        if not status_after["ready_for_deep_digest"]:
            raise VideoProviderError("auto-digest requires deep-ready video evidence")
        for field_name, value in {
            "subject_repo_id": subject_repo_id,
            "subject_head_sha": subject_head_sha,
            "base_canonical_rev": base_canonical_rev,
        }.items():
            if not isinstance(value, str) or not value.strip():
                raise VideoProviderError(f"{field_name} is required for --auto-digest")
        digest_job_path = create_job(
            paths.root,
            "digest",
            payload={"source_id": source_id, "audience": audience},
            subject_repo_id=subject_repo_id or "",
            subject_head_sha=subject_head_sha or "",
            base_canonical_rev=base_canonical_rev or "",
            created_by="video-provider-run",
        )
    payload = {
        "schema_version": "1.0",
        "source_id": source_id,
        "provider": provider_name,
        "attached_artifacts": sorted(attached),
        "attestation_manifests": manifests,
        "status_before": status_before,
        "status_after": status_after,
        "digest_job_path": display_path(paths, digest_job_path) if digest_job_path else None,
        "next_command": "topology supervisor run --root <topology-root> --subject <subject-repo-id>",
    }
    return VideoProviderResult(payload)

"""P2/P11.3 source packet and fetch worker."""

from __future__ import annotations

import hashlib
import html
import http.client
import ipaddress
import json
import re
import socket
import ssl
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Any
from urllib.parse import urljoin, urlparse

from knowledge_topology.ids import new_id
from knowledge_topology.paths import TopologyPaths
from knowledge_topology.schema.source_packet import FetchChainEntry, SourceArtifact, LocalBlobRef, SourcePacket
from knowledge_topology.storage.spool import create_job
from knowledge_topology.storage.transaction import atomic_write_text, atomic_writer


class FetchError(ValueError):
    """Raised when a source cannot be represented safely."""


@dataclass(frozen=True)
class IngestResult:
    packet_id: str
    packet_path: Path
    digest_job_path: Path | None


@dataclass(frozen=True)
class FetchResponse:
    final_url: str
    status_code: int
    content_type: str | None
    body: bytes


FetchCallable = Callable[[str, int], FetchResponse]


EXCERPT_LIMIT = 800
EXTERNAL_PUBLIC_TEXT_LIMIT = 8000
HTML_FETCH_LIMIT = 1024 * 1024
PDF_FETCH_LIMIT = 5 * 1024 * 1024
PINNED_SHA_RE = re.compile(r"[0-9a-fA-F]{40}")
URL_RE = re.compile(r"https?://[^\s]+")
VIDEO_PLATFORM_HOSTS = {
    "douyin.com": "douyin",
    "v.douyin.com": "douyin",
    "www.douyin.com": "douyin",
    "iesdouyin.com": "douyin",
    "tiktok.com": "tiktok",
    "www.tiktok.com": "tiktok",
    "vm.tiktok.com": "tiktok",
    "youtube.com": "youtube",
    "www.youtube.com": "youtube",
    "m.youtube.com": "youtube",
    "youtu.be": "youtube",
    "bilibili.com": "bilibili",
    "www.bilibili.com": "bilibili",
    "b23.tv": "bilibili",
    "vimeo.com": "vimeo",
    "www.vimeo.com": "vimeo",
    "instagram.com": "instagram",
    "www.instagram.com": "instagram",
}
VIDEO_SHORTLINK_HOSTS = {"v.douyin.com", "vm.tiktok.com", "youtu.be", "b23.tv"}
VIDEO_ARTIFACT_KINDS = {"video_file", "transcript", "key_frames", "audio_summary", "landing_page_metadata"}
TEXT_VIDEO_ARTIFACT_KINDS = {"transcript", "key_frames", "audio_summary", "landing_page_metadata"}
VIDEO_EVIDENCE_ORIGINS = {
    "platform_caption",
    "audio_transcription",
    "human_transcript",
    "frame_extraction",
    "vision_frame_analysis",
    "human_frame_notes",
    "audio_model_summary",
    "human_audio_summary",
    "page_visible_excerpt",
    "page_visible_chapter_list",
    "inferred_from_page",
    "public_landing_page_metadata",
    "legacy_unknown",
}
VIDEO_COVERAGE_VALUES = {"full", "partial", "excerpt", "chapter_only", "page_visible_only", "legacy_unknown"}
VIDEO_MODALITIES = {"audio", "video", "page", "human_note", "metadata", "legacy_unknown"}
VIDEO_ATTESTATIONS = {"operator_attested", "provider_generated", "page_visible", "legacy_unknown"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def first_http_url(value: str) -> str:
    match = URL_RE.search(value.strip())
    if match:
        return match.group(0)
    return value


def video_platform_for_host(host: str) -> str | None:
    normalized = host.lower().removeprefix("m.")
    if normalized in VIDEO_PLATFORM_HOSTS:
        return VIDEO_PLATFORM_HOSTS[normalized]
    for suffix, platform in VIDEO_PLATFORM_HOSTS.items():
        if normalized.endswith("." + suffix):
            return platform
    return None


def require_preconditions(subject_repo_id: str, subject_head_sha: str, base_canonical_rev: str) -> None:
    for field, value in {
        "subject_repo_id": subject_repo_id,
        "subject_head_sha": subject_head_sha,
        "base_canonical_rev": base_canonical_rev,
    }.items():
        if not value.strip():
            raise FetchError(f"{field} is required")


def classify_source(value: str, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    source_value = first_http_url(value)
    parsed = urlparse(source_value)
    if parsed.scheme in {"http", "https"}:
        host = parsed.netloc.lower()
        path = parsed.path.lower()
        if host in {"github.com", "www.github.com", "raw.githubusercontent.com"}:
            return "github_artifact"
        if host in {"arxiv.org", "www.arxiv.org"} or path.endswith(".pdf"):
            return "pdf_arxiv"
        if parsed.hostname and video_platform_for_host(parsed.hostname) is not None:
            return "video_platform"
        return "article_html"
    suffix = Path(value).suffix.lower()
    if suffix == ".pdf":
        return "pdf_arxiv"
    return "local_draft"


def default_content_mode(source_type: str, redistributable: str) -> str:
    if source_type == "local_draft" and redistributable == "yes":
        return "public_text"
    if source_type in {"pdf_arxiv", "video_platform"}:
        return "excerpt_only"
    return "excerpt_only"


def canonicalize_source(value: str, source_type: str) -> tuple[str | None, str | None]:
    source_value = first_http_url(value)
    parsed = urlparse(source_value)
    if parsed.scheme in {"http", "https"}:
        if source_type == "pdf_arxiv":
            arxiv = parse_arxiv(source_value)
            if arxiv is not None:
                return source_value, arxiv["abs_url"]
        return source_value, source_value
    return str(Path(value).expanduser()), None


def _safe_excerpt(text: str, limit: int = EXCERPT_LIMIT) -> str:
    compact = " ".join(text.split())
    return compact[:limit]


class TextExtractor(HTMLParser):
    """Conservative visible-text extractor for article HTML."""

    SKIP_TAGS = {"script", "style", "noscript", "svg", "form", "nav"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip_stack: list[bool] = []
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.lower(): (value or "") for name, value in attrs}
        style = attributes.get("style", "").replace(" ", "").lower()
        hidden = (
            tag.lower() in self.SKIP_TAGS
            or "hidden" in attributes
            or attributes.get("aria-hidden", "").lower() == "true"
            or "display:none" in style
            or "visibility:hidden" in style
        )
        self.skip_stack.append(hidden)

    def handle_endtag(self, tag: str) -> None:
        if self.skip_stack:
            self.skip_stack.pop()

    def handle_data(self, data: str) -> None:
        if not any(self.skip_stack) and data.strip():
            self.parts.append(data)

    def handle_comment(self, data: str) -> None:
        return

    def text(self) -> str:
        return html.unescape(" ".join(" ".join(self.parts).split()))


def extract_html_text(raw: bytes, content_type: str | None) -> str:
    charset = "utf-8"
    if content_type:
        match = re.search(r"charset=([A-Za-z0-9_.-]+)", content_type, re.IGNORECASE)
        if match:
            charset = match.group(1)
    text = raw.decode(charset, errors="replace")
    parser = TextExtractor()
    parser.feed(text)
    return parser.text()


def safe_ip_address(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return ip.is_global and value != "169.254.169.254"


def resolve_public_addresses(host: str, resolver: Callable[..., Any] = socket.getaddrinfo) -> list[str]:
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not safe_ip_address(str(literal)):
            raise FetchError("URL host resolves to blocked private/local address")
        return [str(literal)]
    addresses = []
    for item in resolver(host, None, type=socket.SOCK_STREAM):
        address = item[4][0]
        if not safe_ip_address(address):
            raise FetchError("URL host resolves to blocked private/local address")
        addresses.append(address)
    if not addresses:
        raise FetchError("URL host did not resolve")
    return sorted(set(addresses))


def validate_fetch_url(url: str, resolver: Callable[..., Any] = socket.getaddrinfo) -> list[str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise FetchError("only http and https URLs may be fetched")
    if not parsed.hostname:
        raise FetchError("URL host is required")
    return resolve_public_addresses(parsed.hostname, resolver=resolver)


class BoundHTTPConnection(http.client.HTTPConnection):
    def __init__(self, original_host: str, connect_host: str, *args: Any, **kwargs: Any):
        super().__init__(original_host, *args, **kwargs)
        self.connect_host = connect_host

    def connect(self) -> None:
        self.sock = socket.create_connection((self.connect_host, self.port), self.timeout, self.source_address)


class BoundHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, original_host: str, connect_host: str, *args: Any, **kwargs: Any):
        super().__init__(original_host, *args, **kwargs)
        self.connect_host = connect_host

    def connect(self) -> None:
        raw_sock = socket.create_connection((self.connect_host, self.port), self.timeout, self.source_address)
        context = self._context or ssl.create_default_context()
        self.sock = context.wrap_socket(raw_sock, server_hostname=self.host)


def default_fetch(url: str, max_bytes: int, *, timeout: int = 15, redirects: int = 5) -> FetchResponse:
    current = url
    for _ in range(redirects + 1):
        addresses = validate_fetch_url(current)
        parsed = urlparse(current)
        assert parsed.hostname is not None
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        connection_cls = BoundHTTPSConnection if parsed.scheme == "https" else BoundHTTPConnection
        connection = connection_cls(parsed.hostname, addresses[0], port=port, timeout=timeout)
        try:
            connection.request("GET", path, headers={"Host": parsed.netloc, "User-Agent": "knowledge-topology-fetch/1"})
            response = connection.getresponse()
            status = response.status
            content_type = response.getheader("Content-Type")
            if status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                if not location:
                    raise FetchError("redirect response did not include Location")
                current = urljoin(current, location)
                validate_fetch_url(current)
                continue
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise FetchError("fetched response exceeded size limit")
            return FetchResponse(final_url=current, status_code=status, content_type=content_type, body=body)
        finally:
            connection.close()
    raise FetchError("too many redirects")


def fetch_or_block(url: str, *, max_bytes: int, fetcher: FetchCallable | None) -> FetchResponse:
    if fetcher is not None:
        return fetcher(url, max_bytes)
    return default_fetch(url, max_bytes)


def fetch_failure_blocks_packet(exc: FetchError) -> bool:
    message = str(exc)
    return not (
        "blocked private/local" in message
        or "only http and https" in message
        or "URL host is required" in message
        or "too many redirects" in message
    )


def exception_blocks_packet(exc: BaseException) -> bool:
    if isinstance(exc, FetchError):
        return fetch_failure_blocks_packet(exc)
    return isinstance(exc, OSError)


def fetch_metadata_artifact(response: FetchResponse) -> dict[str, Any]:
    return {
        "kind": "fetch_metadata",
        "content_type": response.content_type,
        "status_code": response.status_code,
        "final_url": response.final_url,
        "byte_length": len(response.body),
    }


def pdf_metadata_artifact(value: str, data: bytes, content_type: str | None = "application/pdf") -> dict[str, Any]:
    return {
        "kind": "pdf_metadata",
        "content_type": content_type,
        "byte_length": len(data),
        "hash_sha256": sha256_bytes(data),
        "source": "local_file" if not urlparse(value).scheme else "url",
    }


def parse_arxiv(value: str) -> dict[str, str] | None:
    parsed = urlparse(value)
    if parsed.netloc.lower() not in {"arxiv.org", "www.arxiv.org"}:
        return None
    match = re.search(r"/(?:abs|pdf)/([^/?#]+)", parsed.path)
    if not match:
        return None
    arxiv_id = match.group(1).removesuffix(".pdf")
    return {
        "arxiv_id": arxiv_id,
        "abs_url": f"https://arxiv.org/abs/{arxiv_id}",
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
    }


def arxiv_metadata_artifact(value: str) -> dict[str, str] | None:
    parsed = parse_arxiv(value)
    if parsed is None:
        return None
    return {"kind": "arxiv_metadata", **parsed}


def parse_video_platform(value: str) -> dict[str, Any]:
    source_url = first_http_url(value)
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        raise FetchError("video platform source must be an http(s) URL")
    platform = video_platform_for_host(parsed.hostname)
    if platform is None:
        raise FetchError("unsupported video platform host")
    host = parsed.hostname.lower()
    return {
        "kind": "video_platform_locator",
        "platform": platform,
        "host": host,
        "url": source_url,
        "shortlink": host in VIDEO_SHORTLINK_HOSTS,
        "requires_operator_capture": True,
        "recommended_artifacts": [
            "transcript_or_caption_text",
            "key_frame_descriptions_or_manifest",
            "audio_summary",
            "public_landing_page_metadata",
        ],
    }


def video_capture_brief(artifact: dict[str, Any], note: str) -> str:
    lines = [
        "# Video Platform Intake",
        "",
        "This packet records a platform video locator. It does not claim to contain",
        "the full video, transcript, or downloadable media bytes.",
        "",
        f"- platform: {artifact['platform']}",
        f"- host: {artifact['host']}",
        f"- url: {artifact['url']}",
        f"- shortlink: {str(artifact['shortlink']).lower()}",
        f"- curator_note: {note}",
        "",
        "## Required Follow-Up Artifacts",
        "",
        "- transcript_or_caption_text",
        "- key_frame_descriptions_or_manifest",
        "- audio_summary",
        "- public_landing_page_metadata",
        "",
        "Store only excerpts or operator-authored descriptions unless redistribution",
        "rights are clear. Full media bytes belong in local-only blob storage, not in",
        "tracked raw packets.",
        "",
    ]
    return "\n".join(lines)


def safe_blob_filename(value: str) -> str:
    name = Path(value).name
    if not name or name in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9_.@+-]{1,160}", name):
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
        suffix = Path(value).suffix.lower()
        if suffix and re.fullmatch(r"\.[A-Za-z0-9]{1,12}", suffix):
            return f"artifact-{digest}{suffix}"
        return f"artifact-{digest}.bin"
    return name


def read_packet(paths: TopologyPaths, source_id: str) -> tuple[Path, SourcePacket]:
    if not re.fullmatch(r"src_[A-Z0-9]{26}", source_id):
        raise FetchError("source_id must use src_ opaque ID")
    packet_path = paths.resolve(f"raw/packets/{source_id}/packet.json")
    if packet_path.is_symlink() or not packet_path.is_file():
        raise FetchError("source packet must be a regular non-symlink file")
    try:
        payload = json.loads(packet_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FetchError(f"source packet JSON is invalid: {exc}") from exc
    if not isinstance(payload, dict):
        raise FetchError("source packet must be a JSON object")
    packet = SourcePacket(**payload)
    packet.validate()
    return packet_path, packet


def attach_video_artifact(
    root: str | Path,
    *,
    source_id: str,
    artifact_kind: str,
    artifact_path: str | Path,
    note: str = "operator captured artifact",
    track_text: bool = False,
    evidence_origin: str = "legacy_unknown",
    coverage: str = "legacy_unknown",
    modality: str = "legacy_unknown",
    evidence_attestation: str = "legacy_unknown",
    attestation_manifest: str | Path | None = None,
    trusted_attestation: bool = False,
) -> Path:
    if artifact_kind not in VIDEO_ARTIFACT_KINDS:
        raise FetchError("artifact_kind must be one of: " + ", ".join(sorted(VIDEO_ARTIFACT_KINDS)))
    if evidence_origin not in VIDEO_EVIDENCE_ORIGINS:
        raise FetchError("evidence_origin must be one of: " + ", ".join(sorted(VIDEO_EVIDENCE_ORIGINS)))
    if coverage not in VIDEO_COVERAGE_VALUES:
        raise FetchError("coverage must be one of: " + ", ".join(sorted(VIDEO_COVERAGE_VALUES)))
    if modality not in VIDEO_MODALITIES:
        raise FetchError("modality must be one of: " + ", ".join(sorted(VIDEO_MODALITIES)))
    if evidence_attestation not in VIDEO_ATTESTATIONS:
        raise FetchError("evidence_attestation must be one of: " + ", ".join(sorted(VIDEO_ATTESTATIONS)))
    attestation_manifest_path = None
    paths = TopologyPaths.from_root(root)
    packet_path, packet = read_packet(paths, source_id)
    if packet.source_type != "video_platform":
        raise FetchError("video artifacts can only attach to video_platform source packets")
    candidate = Path(artifact_path).expanduser()
    if candidate.is_symlink() or not candidate.is_file():
        raise FetchError("artifact_path must be a regular non-symlink file")
    data = candidate.read_bytes()
    digest = sha256_bytes(data)
    artifacts = list(packet.artifacts)
    if track_text:
        if artifact_kind not in TEXT_VIDEO_ARTIFACT_KINDS:
            raise FetchError("track_text is only allowed for transcript, key_frames, audio_summary, or landing_page_metadata")
        text = data.decode("utf-8", errors="replace")
        body = _safe_excerpt(text, EXTERNAL_PUBLIC_TEXT_LIMIT)
        tracked_hash = sha256_text(body)
        attestation_hash = validate_video_attestation_manifest(
            attestation_manifest,
            source_id=source_id,
            output_hash_sha256=tracked_hash,
            artifact_kind=artifact_kind,
            evidence_origin=evidence_origin,
            coverage=coverage,
            modality=modality,
            evidence_attestation=evidence_attestation,
            trusted_attestation=trusted_attestation,
        )
        if attestation_manifest:
            attestation_manifest_path = str(Path(attestation_manifest).expanduser().resolve().relative_to(paths.root))
        relative = f"{artifact_kind}.md"
        atomic_write_text(packet_path.parent / relative, body + "\n")
        artifacts.append({
            "kind": "video_text_artifact",
            "artifact_kind": artifact_kind,
            "path": relative,
            "hash_sha256": tracked_hash,
            "source_hash_sha256": digest,
            "byte_length": len(data),
            "note": note,
            "evidence_origin": evidence_origin,
            "coverage": coverage,
            "modality": modality,
            "evidence_attestation": evidence_attestation,
            **({"attestation_manifest_hash": attestation_hash} if attestation_hash else {}),
            **({"attestation_manifest_path": attestation_manifest_path} if attestation_manifest_path else {}),
        })
    else:
        attestation_hash = validate_video_attestation_manifest(
            attestation_manifest,
            source_id=source_id,
            output_hash_sha256=digest,
            artifact_kind=artifact_kind,
            evidence_origin=evidence_origin,
            coverage=coverage,
            modality=modality,
            evidence_attestation=evidence_attestation,
            trusted_attestation=trusted_attestation,
        )
        if attestation_manifest:
            attestation_manifest_path = str(Path(attestation_manifest).expanduser().resolve().relative_to(paths.root))
        filename = safe_blob_filename(str(candidate))
        storage_dir = paths.ensure_dir(f"raw/local_blobs/{source_id}")
        storage_path = storage_dir / filename
        with atomic_writer(storage_path) as temp_path:
            with candidate.open("rb") as source, temp_path.open("wb") as target:
                shutil.copyfileobj(source, target)
        artifacts.append({
            "kind": "local_blob_ref",
            "artifact_kind": artifact_kind,
            "hash_sha256": digest,
            "byte_length": len(data),
            "storage_hint": f"raw/local_blobs/{source_id}/{filename}",
            "note": note,
            "evidence_origin": evidence_origin,
            "coverage": coverage,
            "modality": modality,
            "evidence_attestation": evidence_attestation,
            **({"attestation_manifest_hash": attestation_hash} if attestation_hash else {}),
            **({"attestation_manifest_path": attestation_manifest_path} if attestation_manifest_path else {}),
        })
    updated = SourcePacket(
        schema_version=packet.schema_version,
        id=packet.id,
        source_type=packet.source_type,
        original_url=packet.original_url,
        canonical_url=packet.canonical_url,
        retrieved_at=packet.retrieved_at,
        curator_note=packet.curator_note,
        ingest_depth=packet.ingest_depth,
        authority=packet.authority,
        trust_scope=packet.trust_scope,
        content_status=packet.content_status,
        content_mode=packet.content_mode,
        redistributable=packet.redistributable,
        hash_original=packet.hash_original,
        hash_normalized=packet.hash_normalized,
        artifacts=artifacts,
        fetch_chain=[
            *packet.fetch_chain,
            FetchChainEntry(
                method="video_artifact_attach",
                status="partial",
                note=f"Attached {artifact_kind} artifact metadata",
            ).to_dict(),
        ],
    )
    atomic_write_text(packet_path, json.dumps(updated.to_dict(), indent=2, sort_keys=True) + "\n")
    return packet_path


def validate_video_attestation_manifest(
    manifest_path: str | Path | None,
    *,
    source_id: str,
    output_hash_sha256: str,
    artifact_kind: str,
    evidence_origin: str,
    coverage: str,
    modality: str,
    evidence_attestation: str,
    trusted_attestation: bool,
) -> str | None:
    if evidence_attestation in {"operator_attested", "provider_generated"} and not trusted_attestation:
        raise FetchError("deep video evidence requires a trusted provider/operator attestation path")
    if evidence_attestation in {"operator_attested", "provider_generated"} and manifest_path is None:
        raise FetchError("deep video evidence requires --attestation-manifest")
    if manifest_path is None:
        return None
    path = Path(manifest_path).expanduser()
    if path.is_symlink() or not path.is_file():
        raise FetchError("attestation_manifest must be a regular non-symlink file")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FetchError(f"attestation_manifest JSON is invalid: {exc}") from exc
    if not isinstance(payload, dict):
        raise FetchError("attestation_manifest must be a JSON object")
    expected = {
        "schema_version": "1.0",
        "source_id": source_id,
        "artifact_kind": artifact_kind,
        "evidence_origin": evidence_origin,
        "coverage": coverage,
        "modality": modality,
        "evidence_attestation": evidence_attestation,
        "output_hash_sha256": output_hash_sha256,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise FetchError(f"attestation_manifest {key} mismatch")
    attested_by = payload.get("attested_by")
    if evidence_attestation == "operator_attested" and attested_by != "operator":
        raise FetchError("operator_attested manifest requires attested_by=operator")
    if evidence_attestation == "provider_generated" and attested_by != "provider":
        raise FetchError("provider_generated manifest requires attested_by=provider")
    return sha256_file(path)


def parse_github_artifact(value: str) -> dict[str, Any]:
    parsed = urlparse(value)
    host = parsed.netloc.lower()
    parts = [part for part in parsed.path.split("/") if part]
    if host not in {"github.com", "www.github.com", "raw.githubusercontent.com"}:
        raise FetchError("GitHub artifact URL must use github.com or raw.githubusercontent.com")
    if host == "raw.githubusercontent.com":
        if len(parts) < 4:
            raise FetchError("raw GitHub URL must include owner, repository, ref, and path")
        owner, repo_name, ref = parts[0], parts[1], parts[2]
        path = "/".join(parts[3:])
        pinned = bool(PINNED_SHA_RE.fullmatch(ref))
        return {
            "kind": "github_blob",
            "repo": f"{owner}/{repo_name}",
            "artifact_type": "blob",
            "ref": ref,
            "path": path,
            "commit_sha": ref if pinned else None,
            "mutable_ref": not pinned,
            "ambiguous_ref": not pinned,
            "raw_url": value,
        }
    if len(parts) < 2:
        raise FetchError("GitHub artifact URL must include owner and repository")
    repo = f"{parts[0]}/{parts[1]}"
    artifact: dict[str, Any] = {
        "kind": "github_repo",
        "repo": repo,
        "artifact_type": "repo",
        "ref": None,
        "path": None,
        "commit_sha": None,
    }
    if len(parts) >= 4 and parts[2] == "pull" and parts[3].endswith(".diff"):
        number = parts[3].removesuffix(".diff")
        artifact.update({"kind": "github_diff", "artifact_type": "diff", "number": number, "ref": number})
    elif len(parts) >= 5 and parts[2] == "pull" and parts[4] == "files":
        artifact.update({"kind": "github_diff", "artifact_type": "diff", "number": parts[3], "ref": parts[3]})
    elif len(parts) >= 4 and parts[2] == "pull":
        artifact.update({"kind": "github_pull", "artifact_type": "pull", "number": parts[3], "ref": parts[3]})
    elif len(parts) >= 4 and parts[2] == "issues":
        artifact.update({"kind": "github_issue", "artifact_type": "issue", "number": parts[3], "ref": parts[3]})
    elif len(parts) >= 4 and parts[2] == "commit":
        sha = parts[3]
        artifact.update({"kind": "github_commit", "artifact_type": "commit", "ref": sha, "commit_sha": sha if PINNED_SHA_RE.fullmatch(sha) else None})
    elif len(parts) >= 5 and parts[2] == "blob" and PINNED_SHA_RE.fullmatch(parts[3]):
        ref = parts[3]
        path = "/".join(parts[4:])
        artifact.update({
            "kind": "github_blob",
            "artifact_type": "blob",
            "ref": ref,
            "path": path,
            "commit_sha": ref,
            "mutable_ref": False,
            "ambiguous_ref": False,
            "raw_url": f"https://raw.githubusercontent.com/{repo}/{ref}/{path}",
        })
    elif len(parts) >= 5 and parts[2] == "blob":
        ref = parts[3]
        artifact.update({
            "kind": "github_blob",
            "artifact_type": "blob",
            "ref": ref,
            "path": "/".join(parts[4:]),
            "commit_sha": None,
            "mutable_ref": True,
            "ambiguous_ref": True,
        })
    return artifact


def github_should_fetch(artifact: dict[str, Any]) -> bool:
    if artifact.get("artifact_type") == "diff":
        return True
    return artifact.get("artifact_type") == "blob" and artifact.get("commit_sha") is not None


def bounded_external_text(text: str, *, mode: str) -> str:
    limit = EXTERNAL_PUBLIC_TEXT_LIMIT if mode == "public_text" else EXCERPT_LIMIT
    return _safe_excerpt(text, limit=limit)


def safe_local_file_under_root(root: Path, value: str, *, suffix: str | None, label: str) -> Path:
    root = root.resolve()
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    if ".." in Path(value).parts:
        raise FetchError(f"{label} path must not contain traversal")
    try:
        lexical_relative = candidate.relative_to(root)
    except ValueError:
        lexical_relative = None
    if lexical_relative is not None:
        lexical_current = root
        for part in lexical_relative.parts[:-1]:
            lexical_current = lexical_current / part
            if lexical_current.is_symlink():
                raise FetchError(f"{label} parent path is unsafe")
    else:
        for parent in candidate.parents:
            if parent.is_symlink() and parent.resolve() not in root.parents:
                raise FetchError(f"{label} parent path is unsafe")
    resolved_candidate = candidate.resolve()
    current = root
    try:
        relative = resolved_candidate.relative_to(root)
    except ValueError as exc:
        raise FetchError(f"{label} path must resolve inside the topology root") from exc
    for part in relative.parts[:-1]:
        current = current / part
        if current.is_symlink() or not current.is_dir():
            raise FetchError(f"{label} parent path is unsafe")
    if ".topology" in relative.parts:
        raise FetchError(f"{label} path must not resolve through .topology")
    if suffix is not None and resolved_candidate.suffix.lower() != suffix:
        raise FetchError(f"{label} path must end with {suffix}")
    if candidate.is_symlink() or not resolved_candidate.is_file():
        raise FetchError(f"{label} path must be a regular non-symlink file")
    return resolved_candidate


def build_source_packet(
    value: str,
    *,
    note: str,
    depth: str,
    redistributable: str = "unknown",
    content_mode: str | None = None,
    source_type: str | None = None,
    topology_root: str | Path | None = None,
    fetcher: FetchCallable | None = None,
) -> tuple[SourcePacket, dict[str, str]]:
    resolved_type = classify_source(value, source_type)
    mode = content_mode or default_content_mode(resolved_type, redistributable)
    if resolved_type != "local_draft" and mode == "public_text" and redistributable != "yes":
        raise FetchError("external public_text requires redistributable=yes")
    if resolved_type == "pdf_arxiv" and mode == "public_text":
        raise FetchError("pdf_arxiv does not support public_text mode in P11.3")
    if resolved_type == "video_platform" and mode != "excerpt_only":
        raise FetchError("video_platform supports excerpt_only locator intake only")
    original_url, canonical_url = canonicalize_source(value, resolved_type)
    packet_id = new_id("src")
    artifacts: list[dict[str, Any]] = []
    fetch_chain = [FetchChainEntry(method="metadata_only", status="partial", note="P11.3 metadata/excerpt path").to_dict()]
    hash_original: str | None = None
    hash_normalized: str | None = None
    files: dict[str, str] = {}
    content_status = "partial"

    if resolved_type == "local_draft":
        path = Path(value).expanduser()
        if not path.exists() or not path.is_file():
            raise FetchError(f"local draft not found: {value}")
        if mode == "local_blob":
            raise FetchError("local_draft does not support local_blob mode in P2")
        text = path.read_text(encoding="utf-8")
        hash_original = sha256_text(text)
        if mode == "public_text":
            hash_normalized = sha256_text(text)
            files["content.md"] = text
            artifacts.append(SourceArtifact(kind="normalized_text", path="content.md", hash_sha256=hash_normalized).to_dict())
        else:
            excerpt = _safe_excerpt(text)
            hash_normalized = sha256_text(excerpt)
            files["excerpt.md"] = excerpt + "\n"
            artifacts.append(SourceArtifact(kind="excerpt", path="excerpt.md", hash_sha256=hash_normalized).to_dict())
        fetch_chain = [FetchChainEntry(method="local_file", status="complete", note="Read local draft from disk").to_dict()]
        content_status = "complete"
    elif resolved_type == "article_html":
        try:
            response = fetch_or_block(value, max_bytes=HTML_FETCH_LIMIT, fetcher=fetcher)
        except (FetchError, OSError) as exc:
            if not exception_blocks_packet(exc):
                raise
            artifacts.append({"kind": "fetch_metadata", "final_url": value, "note": _safe_excerpt(str(exc), 200)})
            content_status = "blocked"
            fetch_chain = [FetchChainEntry(method="http_fetch", status="blocked", note=_safe_excerpt(str(exc), 200)).to_dict()]
        else:
            artifacts.append(fetch_metadata_artifact(response))
            if response.status_code >= 400:
                content_status = "blocked"
                fetch_chain = [FetchChainEntry(method="http_fetch", status="blocked", note=f"HTTP {response.status_code}").to_dict()]
            else:
                text = extract_html_text(response.body, response.content_type)
                body = bounded_external_text(text, mode=mode)
                filename = "content.md" if mode == "public_text" else "excerpt.md"
                files[filename] = body + "\n"
                hash_original = sha256_bytes(response.body)
                hash_normalized = sha256_text(body)
                artifacts.append({"kind": "html_excerpt", "path": filename, "hash_sha256": hash_normalized})
                fetch_chain = [FetchChainEntry(method="http_fetch", status="complete", note="Fetched bounded article excerpt").to_dict()]
                content_status = "complete" if mode == "public_text" else "partial"
                canonical_url = response.final_url
    elif resolved_type == "pdf_arxiv":
        data: bytes | None = None
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https"}:
            arxiv_artifact = arxiv_metadata_artifact(value)
            if arxiv_artifact is not None:
                artifacts.append(arxiv_artifact)
            try:
                response = fetch_or_block(value, max_bytes=PDF_FETCH_LIMIT, fetcher=fetcher)
            except (FetchError, OSError) as exc:
                if not exception_blocks_packet(exc):
                    raise
                content_status = "blocked"
                artifacts.append({"kind": "fetch_metadata", "final_url": value, "note": _safe_excerpt(str(exc), 200)})
                fetch_chain = [FetchChainEntry(method="http_fetch", status="blocked", note=_safe_excerpt(str(exc), 200)).to_dict()]
            else:
                artifacts.append(fetch_metadata_artifact(response))
                data = response.body if response.status_code < 400 else None
                if response.status_code >= 400:
                    content_status = "blocked"
                    fetch_chain = [FetchChainEntry(method="http_fetch", status="blocked", note=f"HTTP {response.status_code}").to_dict()]
                else:
                    canonical_url = canonicalize_source(value, resolved_type)[1]
                    fetch_chain = [FetchChainEntry(method="http_fetch", status="complete", note="Fetched PDF metadata bytes").to_dict()]
        else:
            if topology_root is None:
                raise FetchError("local PDF intake requires topology root")
            pdf_path = safe_local_file_under_root(Path(topology_root).resolve(), value, suffix=".pdf", label="local PDF")
            data = pdf_path.read_bytes()
            fetch_chain = [FetchChainEntry(method="local_pdf", status="complete", note="Read local PDF metadata bytes").to_dict()]
        if data is not None:
            hash_original = sha256_bytes(data)
            artifacts.append(pdf_metadata_artifact(value, data))
            summary = f"PDF metadata excerpt\nbyte_length: {len(data)}\nhash_sha256: {hash_original}\n"
            files["excerpt.md"] = summary
            hash_normalized = sha256_text(summary)
            artifacts.append({"kind": "pdf_excerpt", "path": "excerpt.md", "hash_sha256": hash_normalized})
            content_status = "partial"
            if mode == "local_blob":
                artifacts.append({
                    "kind": "local_blob_ref",
                    **LocalBlobRef(hash_sha256=hash_original, storage_hint=f"raw/local_blobs/{packet_id}").to_dict(),
                    "note": "Full PDF bytes stay outside Git.",
                })
    elif resolved_type == "github_artifact":
        artifact = parse_github_artifact(value)
        artifacts.append({**artifact, "note": "GitHub artifact metadata captured; mutable refs are metadata-only."})
        if github_should_fetch(artifact):
            fetch_url = artifact.get("raw_url") or value
            try:
                response = fetch_or_block(str(fetch_url), max_bytes=HTML_FETCH_LIMIT, fetcher=fetcher)
            except (FetchError, OSError) as exc:
                if not exception_blocks_packet(exc):
                    raise
                content_status = "blocked"
                artifacts.append({"kind": "fetch_metadata", "final_url": str(fetch_url), "note": _safe_excerpt(str(exc), 200)})
                fetch_chain = [FetchChainEntry(method="github_fetch", status="blocked", note=_safe_excerpt(str(exc), 200)).to_dict()]
            else:
                artifacts.append(fetch_metadata_artifact(response))
                if response.status_code < 400:
                    text = response.body.decode("utf-8", errors="replace")
                    body = bounded_external_text(text, mode=mode)
                    filename = "content.md" if mode == "public_text" else "excerpt.md"
                    files[filename] = body + "\n"
                    hash_original = sha256_bytes(response.body)
                    hash_normalized = sha256_text(body)
                    artifacts.append({"kind": "github_excerpt", "path": filename, "hash_sha256": hash_normalized})
                    fetch_chain = [FetchChainEntry(method="github_fetch", status="complete", note="Fetched bounded GitHub artifact excerpt").to_dict()]
                    content_status = "complete" if mode == "public_text" else "partial"
                else:
                    fetch_chain = [FetchChainEntry(method="github_fetch", status="blocked", note=f"HTTP {response.status_code}").to_dict()]
                    content_status = "blocked"
        else:
            fetch_chain = [FetchChainEntry(method="github_metadata", status="partial", note="Mutable or metadata-only GitHub artifact").to_dict()]
    elif resolved_type == "video_platform":
        artifact = parse_video_platform(value)
        artifacts.append({
            **artifact,
            "note": "Platform video locator captured without direct media download.",
        })
        brief = video_capture_brief(artifact, note)
        files["excerpt.md"] = brief
        hash_original = sha256_text(artifact["url"])
        hash_normalized = sha256_text(brief)
        artifacts.append({
            "kind": "video_capture_brief",
            "path": "excerpt.md",
            "hash_sha256": hash_normalized,
        })
        fetch_chain = [
            FetchChainEntry(
                method="video_platform_locator",
                status="partial",
                note="Captured platform URL; operator must provide transcript/key-frame/audio artifacts.",
            ).to_dict()
        ]
        content_status = "partial"
    else:
        artifacts.append(SourceArtifact(kind="manifest", note="Unknown source type; excerpt_only default").to_dict())

    packet = SourcePacket(
        schema_version="1.0",
        id=packet_id,
        source_type=resolved_type,
        original_url=original_url,
        canonical_url=canonical_url,
        retrieved_at=utc_now_iso(),
        curator_note=note,
        ingest_depth=depth,
        authority="source_grounded",
        trust_scope="external" if resolved_type != "local_draft" else "operator",
        content_status=content_status,
        content_mode=mode,
        redistributable=redistributable,
        hash_original=hash_original,
        hash_normalized=hash_normalized,
        artifacts=artifacts,
        fetch_chain=fetch_chain,
    )
    packet.validate()
    return packet, files


def ingest_source(
    root: str | Path,
    value: str,
    *,
    note: str,
    depth: str,
    audience: str,
    subject_repo_id: str,
    subject_head_sha: str,
    base_canonical_rev: str,
    redistributable: str = "unknown",
    content_mode: str | None = None,
    source_type: str | None = None,
    fetcher: FetchCallable | None = None,
) -> IngestResult:
    paths = TopologyPaths.from_root(root)
    require_preconditions(subject_repo_id, subject_head_sha, base_canonical_rev)
    resolved_type = classify_source(value, source_type)
    if resolved_type == "local_draft":
        local_path = safe_local_file_under_root(paths.root, value, suffix=None, label="local draft")
        value = str(local_path)
    elif resolved_type == "pdf_arxiv" and not urlparse(value).scheme:
        value = str(safe_local_file_under_root(paths.root, value, suffix=".pdf", label="local PDF"))
    packet, files = build_source_packet(
        value,
        note=note,
        depth=depth,
        redistributable=redistributable,
        content_mode=content_mode,
        source_type=resolved_type,
        topology_root=paths.root,
        fetcher=fetcher,
    )
    packet_dir = paths.ensure_dir(f"raw/packets/{packet.id}")
    for relative, text in files.items():
        atomic_write_text(packet_dir / relative, text)
    atomic_write_text(packet_dir / "packet.json", json.dumps(packet.to_dict(), indent=2, sort_keys=True) + "\n")
    digest_job = None
    if packet.source_type != "video_platform":
        digest_job = create_job(
            root,
            "digest",
            payload={"source_id": packet.id, "audience": audience},
            subject_repo_id=subject_repo_id,
            subject_head_sha=subject_head_sha,
            base_canonical_rev=base_canonical_rev,
            created_by="reader",
        )
    return IngestResult(packet.id, packet_dir / "packet.json", digest_job)

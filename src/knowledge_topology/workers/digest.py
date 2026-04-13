"""P3 digest validation and artifact writer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from knowledge_topology.adapters.digest_model import DigestModelAdapter
from knowledge_topology.paths import TopologyPaths
from knowledge_topology.schema.digest import Digest, DigestError
from knowledge_topology.schema.loader import load_json
from knowledge_topology.storage.transaction import atomic_write_text


class DigestWorkerError(ValueError):
    """Raised when digest artifact creation is unsafe or invalid."""


def render_digest_markdown(digest: Digest, source_packet: dict[str, Any]) -> str:
    sections = [
        f"# Digest {digest.id}",
        "",
        f"- Source: `{digest.source_id}`",
        f"- Source type: `{source_packet.get('source_type')}`",
        f"- Digest depth: `{digest.digest_depth}`",
        f"- Passes completed: `{', '.join(str(item) for item in digest.passes_completed)}`",
        "",
        "## Author Claims",
        json.dumps(digest.author_claims, indent=2, sort_keys=True),
        "",
        "## Direct Evidence",
        json.dumps(digest.direct_evidence, indent=2, sort_keys=True),
        "",
        "## Model Inferences",
        json.dumps(digest.model_inferences, indent=2, sort_keys=True),
        "",
        "## Boundary Conditions",
        json.dumps(digest.boundary_conditions, indent=2, sort_keys=True),
        "",
        "## Alternative Interpretations",
        json.dumps(digest.alternative_interpretations, indent=2, sort_keys=True),
        "",
        "## Contested Points",
        json.dumps(digest.contested_points, indent=2, sort_keys=True),
        "",
        "## Unresolved Ambiguity",
        json.dumps(digest.unresolved_ambiguity, indent=2, sort_keys=True),
        "",
        "## Open Questions",
        json.dumps(digest.open_questions, indent=2, sort_keys=True),
        "",
        "## Candidate Edges",
        json.dumps(digest.candidate_edges, indent=2, sort_keys=True),
        "",
        "## Fidelity Flags",
        json.dumps(digest.fidelity_flags, indent=2, sort_keys=True),
        "",
    ]
    return "\n".join(sections)


def write_digest_artifacts(
    root: str | Path,
    *,
    source_id: str,
    model_adapter: DigestModelAdapter,
) -> tuple[Path, Path]:
    paths = TopologyPaths.from_root(root)
    source_packet_path = paths.resolve(f"raw/packets/{source_id}/packet.json")
    if not source_packet_path.exists():
        raise DigestWorkerError(f"source packet not found: {source_id}")
    source_packet = load_json(source_packet_path)
    payload = model_adapter.load_output()
    digest = Digest.from_dict(payload)
    if digest.source_id != source_id:
        raise DigestError("digest source_id does not match requested source")

    digest_dir = paths.ensure_dir(f"digests/by_source/{source_id}")
    json_path = digest_dir / f"{digest.id}.json"
    md_path = digest_dir / f"{digest.id}.md"
    atomic_write_text(json_path, json.dumps(digest.to_dict(), indent=2, sort_keys=True) + "\n")
    atomic_write_text(md_path, render_digest_markdown(digest, source_packet))
    return json_path, md_path

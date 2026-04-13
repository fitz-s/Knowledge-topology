"""Knowledge Topology command line interface."""

from __future__ import annotations

import argparse
from pathlib import Path

from knowledge_topology.schema.source_packet import SourcePacketError
from knowledge_topology.workers.fetch import FetchError, ingest_source
from knowledge_topology.workers.init import init_topology


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="topology", description="Knowledge Topology CLI")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="initialize a topology root")
    init_parser.add_argument("--root", default=".", help="topology root to initialize")

    ingest_parser = subparsers.add_parser("ingest", help="create a source packet and enqueue digest")
    ingest_parser.add_argument("source", help="source URL or local path")
    ingest_parser.add_argument("--root", default=".", help="topology root")
    ingest_parser.add_argument("--note", required=True, help="curator note")
    ingest_parser.add_argument("--depth", choices=["deep", "standard", "scan"], default="standard")
    ingest_parser.add_argument("--audience", choices=["builders", "openclaw", "all"], default="all")
    ingest_parser.add_argument("--subject", required=True, dest="subject_repo_id", help="subject repo id")
    ingest_parser.add_argument("--subject-head-sha", required=True, help="subject HEAD SHA")
    ingest_parser.add_argument("--base-canonical-rev", required=True, help="base canonical revision")
    ingest_parser.add_argument("--redistributable", choices=["yes", "no", "unknown"], default="unknown")
    ingest_parser.add_argument("--content-mode", choices=["public_text", "excerpt_only", "local_blob"])
    ingest_parser.add_argument("--source-type", choices=["local_draft", "github_artifact", "article_html", "pdf_arxiv"])

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "init":
        root = Path(args.root).expanduser().resolve()
        init_topology(root)
        print(f"initialized topology root: {root}")
        return 0
    if args.command == "ingest":
        try:
            result = ingest_source(
                Path(args.root).expanduser().resolve(),
                args.source,
                note=args.note,
                depth=args.depth,
                audience=args.audience,
                subject_repo_id=args.subject_repo_id,
                subject_head_sha=args.subject_head_sha,
                base_canonical_rev=args.base_canonical_rev,
                redistributable=args.redistributable,
                content_mode=args.content_mode,
                source_type=args.source_type,
            )
        except (FetchError, SourcePacketError, ValueError) as exc:
            parser.exit(2, f"topology ingest: {exc}\n")
        print(f"created source packet: {result.packet_path}")
        print(f"enqueued digest job: {result.digest_job_path}")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Knowledge Topology command line interface."""

from __future__ import annotations

import argparse
from pathlib import Path

from knowledge_topology.schema.source_packet import SourcePacketError
from knowledge_topology.adapters.digest_model import JsonFileDigestAdapter
from knowledge_topology.schema.digest import DigestError
from knowledge_topology.schema.mutation_pack import MutationPackError
from knowledge_topology.workers.apply import ApplyError, apply_mutation
from knowledge_topology.workers.compose_builder import ComposeError, write_builder_pack
from knowledge_topology.workers.doctor import stale_anchors
from knowledge_topology.workers.lint import run_lints
from knowledge_topology.workers.writeback import WritebackError, writeback_session
from knowledge_topology.workers.digest import DigestWorkerError, write_digest_artifacts
from knowledge_topology.workers.fetch import FetchError, ingest_source
from knowledge_topology.workers.init import init_topology
from knowledge_topology.workers.reconcile import ReconcileError, reconcile_digest


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

    digest_parser = subparsers.add_parser("digest", help="validate and write digest artifacts")
    digest_parser.add_argument("--root", default=".", help="topology root")
    digest_parser.add_argument("--source-id", required=True, help="source packet ID")
    digest_parser.add_argument("--model-output", required=True, help="path to model-produced digest JSON")

    reconcile_parser = subparsers.add_parser("reconcile", help="create a mutation proposal from digest JSON")
    reconcile_parser.add_argument("--root", default=".", help="topology root")
    reconcile_parser.add_argument("--digest-json", required=True, help="validated digest JSON path")
    reconcile_parser.add_argument("--subject", required=True, dest="subject_repo_id", help="subject repo id")
    reconcile_parser.add_argument("--subject-head-sha", required=True, help="subject HEAD SHA")
    reconcile_parser.add_argument("--base-canonical-rev", required=True, help="base canonical revision")
    reconcile_parser.add_argument("--proposed-by", default="reconciler", help="proposal author")

    apply_parser = subparsers.add_parser("apply", help="apply a pending mutation pack")
    apply_parser.add_argument("mutation_pack", help="path to pending mutation pack JSON")
    apply_parser.add_argument("--root", default=".", help="topology root")
    apply_parser.add_argument("--current-canonical-rev", required=True, help="current canonical revision")
    apply_parser.add_argument("--subject", required=True, dest="subject_repo_id", help="subject repo id")
    apply_parser.add_argument("--subject-head-sha", required=True, help="subject HEAD SHA")
    apply_parser.add_argument("--approve-human", action="store_true", help="approve human-gated mutation")

    compose_parser = subparsers.add_parser("compose", help="compose derived projections")
    compose_subparsers = compose_parser.add_subparsers(dest="compose_command")
    builder_parser = compose_subparsers.add_parser("builder", help="compose a task-scoped builder pack")
    builder_parser.add_argument("--root", default=".", help="topology root")
    builder_parser.add_argument("--task-id", required=True, help="task ID")
    builder_parser.add_argument("--goal", required=True, help="task goal")
    builder_parser.add_argument("--canonical-rev", required=True, help="canonical revision")
    builder_parser.add_argument("--subject", required=True, dest="subject_repo_id", help="subject repo id")
    builder_parser.add_argument("--subject-head-sha", required=True, help="subject HEAD SHA")
    builder_parser.add_argument("--subject-path", help="optional local subject repo path for dirty checks")
    builder_parser.add_argument("--allow-dirty", action="store_true", help="allow dirty topology repo for fixture/test use")

    lint_parser = subparsers.add_parser("lint", help="run deterministic topology lints")
    lint_parser.add_argument("--root", default=".", help="topology root")

    doctor_parser = subparsers.add_parser("doctor", help="run topology doctor checks")
    doctor_subparsers = doctor_parser.add_subparsers(dest="doctor_command")
    stale_parser = doctor_subparsers.add_parser("stale-anchors", help="report stale file refs")
    stale_parser.add_argument("--root", default=".", help="topology root")
    stale_parser.add_argument("--subject", required=True, dest="subject_repo_id", help="subject repo id")
    stale_parser.add_argument("--subject-head-sha", required=True, help="subject HEAD SHA")

    writeback_parser = subparsers.add_parser("writeback", help="create mutation proposal from session summary")
    writeback_parser.add_argument("--root", default=".", help="topology root")
    writeback_parser.add_argument("--summary-json", required=True, help="session summary JSON")
    writeback_parser.add_argument("--subject", required=True, dest="subject_repo_id", help="subject repo id")
    writeback_parser.add_argument("--subject-head-sha", required=True, help="subject HEAD SHA")
    writeback_parser.add_argument("--base-canonical-rev", required=True, help="base canonical revision")
    writeback_parser.add_argument("--current-canonical-rev", required=True, help="current canonical revision")
    writeback_parser.add_argument("--current-subject-head-sha", required=True, help="current subject HEAD SHA")

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
    if args.command == "digest":
        try:
            json_path, md_path = write_digest_artifacts(
                Path(args.root).expanduser().resolve(),
                source_id=args.source_id,
                model_adapter=JsonFileDigestAdapter(args.model_output),
            )
        except (DigestError, DigestWorkerError, ValueError) as exc:
            parser.exit(2, f"topology digest: {exc}\n")
        print(f"created digest json: {json_path}")
        print(f"created digest markdown: {md_path}")
        return 0
    if args.command == "reconcile":
        try:
            mutation_path = reconcile_digest(
                Path(args.root).expanduser().resolve(),
                digest_json=args.digest_json,
                subject_repo_id=args.subject_repo_id,
                subject_head_sha=args.subject_head_sha,
                base_canonical_rev=args.base_canonical_rev,
                proposed_by=args.proposed_by,
            )
        except (DigestError, MutationPackError, ReconcileError, ValueError) as exc:
            parser.exit(2, f"topology reconcile: {exc}\n")
        print(f"created mutation pack: {mutation_path}")
        return 0
    if args.command == "apply":
        try:
            applied_path, event_path = apply_mutation(
                Path(args.root).expanduser().resolve(),
                args.mutation_pack,
                current_canonical_rev=args.current_canonical_rev,
                subject_repo_id=args.subject_repo_id,
                subject_head_sha=args.subject_head_sha,
                approve_human=args.approve_human,
            )
        except (ApplyError, MutationPackError, ValueError) as exc:
            parser.exit(2, f"topology apply: {exc}\n")
        print(f"applied mutation pack: {applied_path}")
        print(f"wrote audit event: {event_path}")
        return 0
    if args.command == "compose" and args.compose_command == "builder":
        try:
            pack_dir = write_builder_pack(
                Path(args.root).expanduser().resolve(),
                task_id=args.task_id,
                goal=args.goal,
                canonical_rev=args.canonical_rev,
                subject_repo_id=args.subject_repo_id,
                subject_head_sha=args.subject_head_sha,
                subject_path=args.subject_path,
                allow_dirty=args.allow_dirty,
            )
        except (ComposeError, ValueError) as exc:
            parser.exit(2, f"topology compose builder: {exc}\n")
        print(f"created builder pack: {pack_dir}")
        return 0
    if args.command == "lint":
        result = run_lints(Path(args.root).expanduser().resolve())
        for message in result.messages:
            print(message)
        return 0 if result.ok else 1
    if args.command == "doctor" and args.doctor_command == "stale-anchors":
        result = stale_anchors(
            Path(args.root).expanduser().resolve(),
            subject_repo_id=args.subject_repo_id,
            subject_head_sha=args.subject_head_sha,
        )
        for message in result.messages:
            print(message)
        return 0 if result.ok else 1
    if args.command == "writeback":
        try:
            mutation_path, reltest_path = writeback_session(
                Path(args.root).expanduser().resolve(),
                summary_path=args.summary_json,
                subject_repo_id=args.subject_repo_id,
                subject_head_sha=args.subject_head_sha,
                base_canonical_rev=args.base_canonical_rev,
                current_canonical_rev=args.current_canonical_rev,
                current_subject_head_sha=args.current_subject_head_sha,
            )
        except (WritebackError, ValueError) as exc:
            parser.exit(2, f"topology writeback: {exc}\n")
        print(f"created writeback mutation pack: {mutation_path}")
        print(f"created relationship-test delta: {reltest_path}")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

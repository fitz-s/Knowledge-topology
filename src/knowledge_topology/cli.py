"""Knowledge Topology command line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from knowledge_topology.schema.source_packet import SourcePacketError
from knowledge_topology.adapters.digest_model import JsonFileDigestAdapter
from knowledge_topology.schema.digest import DigestError
from knowledge_topology.schema.mutation_pack import MutationPackError
from knowledge_topology.adapters.digest_model import CommandDigestProviderAdapter
from knowledge_topology.adapters.digest_model import DigestProviderError
from knowledge_topology.adapters.digest_model import JsonDirectoryDigestProviderAdapter
from knowledge_topology.adapters.openclaw_live import OpenClawLiveError
from knowledge_topology.adapters.openclaw_live import create_runtime_source_packet
from knowledge_topology.adapters.openclaw_live import issue_openclaw_live_lease
from knowledge_topology.adapters.openclaw_live import lease_openclaw_live_job
from knowledge_topology.adapters.openclaw_live import run_openclaw_live_writeback
from knowledge_topology.workers.agent_guard import guard_claude_pre_tool_use
from knowledge_topology.workers.apply import ApplyError, apply_mutation
from knowledge_topology.workers.compose_builder import ComposeError, write_builder_pack
from knowledge_topology.workers.compose_openclaw import OpenClawComposeError, write_openclaw_projection
from knowledge_topology.workers.doctor import doctor_canonical_parity
from knowledge_topology.workers.doctor import doctor_projections
from knowledge_topology.workers.doctor import doctor_public_safe
from knowledge_topology.workers.doctor import doctor_queues
from knowledge_topology.workers.doctor import stale_anchors
from knowledge_topology.workers.lint import run_lints, run_repo_lints, run_runtime_lints
from knowledge_topology.workers.run_digest_queue import DigestQueueRunnerError, run_digest_queue
from knowledge_topology.workers.writeback import WritebackError, writeback_session
from knowledge_topology.workers.digest import DigestWorkerError, write_digest_artifacts
from knowledge_topology.workers.fetch import FetchError, attach_video_artifact, ingest_source
from knowledge_topology.workers.init import init_topology
from knowledge_topology.workers.reconcile import ReconcileError, reconcile_digest
from knowledge_topology.subjects import SubjectRegistryError, add_subject, refresh_subject, resolve_subject, show_subject, utc_now


def json_dumps(payload: dict) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def load_json_object(path: str | Path, label: str) -> dict:
    try:
        payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"{label} cannot be read: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} JSON is invalid: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


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
    ingest_parser.add_argument("--source-type", choices=["local_draft", "github_artifact", "article_html", "pdf_arxiv", "video_platform"])

    digest_parser = subparsers.add_parser("digest", help="validate and write digest artifacts")
    digest_parser.add_argument("--root", default=".", help="topology root")
    digest_parser.add_argument("--source-id", help="source packet ID")
    digest_parser.add_argument("--model-output", help="path to model-produced digest JSON")
    digest_parser.add_argument("--run-queue", action="store_true", help="run pending digest queue jobs")
    digest_parser.add_argument("--owner", help="queue lease owner")
    digest_parser.add_argument("--subject", dest="subject_repo_id", help="current subject repo id for queue mode")
    digest_parser.add_argument("--current-canonical-rev", help="current canonical revision for queue mode")
    digest_parser.add_argument("--current-subject-head-sha", help="current subject HEAD SHA for queue mode")
    digest_parser.add_argument("--provider-command", help="local provider command for queue mode")
    digest_parser.add_argument("--model-output-dir", help="directory containing <source_id>.json fixture outputs")
    digest_parser.add_argument("--provider-timeout-seconds", type=int, default=120, help="provider command timeout")
    digest_parser.add_argument("--max-jobs", type=int, default=1, help="maximum digest jobs to run")
    digest_parser.add_argument("--lease-seconds", type=int, default=900, help="digest job lease duration")
    digest_parser.add_argument("--max-attempts", type=int, default=3, help="maximum attempts before expired jobs fail")

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

    subject_parser = subparsers.add_parser("subject", help="manage subject registry")
    subject_subparsers = subject_parser.add_subparsers(dest="subject_command")
    subject_add = subject_subparsers.add_parser("add", help="add a subject registry entry")
    subject_add.add_argument("--root", default=".", help="topology root")
    subject_add.add_argument("--id", required=True, dest="subject_repo_id", help="subject repo id")
    subject_add.add_argument("--name", required=True, help="subject display name")
    subject_add.add_argument("--kind", required=True, choices=["git"], help="subject kind")
    subject_add.add_argument("--location", required=True, help="subject repo location")
    subject_add.add_argument("--default-branch", required=True, help="default branch")
    subject_add.add_argument("--visibility", required=True, help="subject visibility token")
    subject_add.add_argument("--sensitivity", required=True, help="subject sensitivity token")
    subject_refresh = subject_subparsers.add_parser("refresh", help="refresh subject HEAD")
    subject_refresh.add_argument("--root", default=".", help="topology root")
    subject_refresh.add_argument("--subject", required=True, dest="subject_repo_id", help="subject repo id")
    subject_show = subject_subparsers.add_parser("show", help="show subject record")
    subject_show.add_argument("--root", default=".", help="topology root")
    subject_show.add_argument("--subject", required=True, dest="subject_repo_id", help="subject repo id")
    subject_resolve = subject_subparsers.add_parser("resolve", help="resolve subject location")
    subject_resolve.add_argument("--root", default=".", help="topology root")
    subject_resolve.add_argument("--subject", required=True, dest="subject_repo_id", help="subject repo id")

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
    openclaw_parser = compose_subparsers.add_parser("openclaw", help="compose an OpenClaw runtime projection")
    openclaw_parser.add_argument("--root", default=".", help="topology root")
    openclaw_parser.add_argument("--project-id", required=True, help="OpenClaw runtime project id")
    openclaw_parser.add_argument("--canonical-rev", required=True, help="canonical revision")
    openclaw_parser.add_argument("--subject", required=True, dest="subject_repo_id", help="subject repo id")
    openclaw_parser.add_argument("--subject-head-sha", required=True, help="subject HEAD SHA")
    openclaw_parser.add_argument("--subject-path", help="optional local subject repo path for dirty/head checks")
    openclaw_parser.add_argument("--allow-dirty", action="store_true", help="allow dirty repos for fixture/test use")

    lint_parser = subparsers.add_parser("lint", help="run deterministic topology lints")
    lint_parser.add_argument("lint_mode", nargs="?", choices=["repo", "runtime"], default="repo", help="lint mode")
    lint_parser.add_argument("--root", default=".", help="topology root")

    doctor_parser = subparsers.add_parser("doctor", help="run topology doctor checks")
    doctor_subparsers = doctor_parser.add_subparsers(dest="doctor_command")
    stale_parser = doctor_subparsers.add_parser("stale-anchors", help="report stale file refs")
    stale_parser.add_argument("--root", default=".", help="topology root")
    stale_parser.add_argument("--subject", required=True, dest="subject_repo_id", help="subject repo id")
    stale_parser.add_argument("--subject-head-sha", required=True, help="subject HEAD SHA")
    queues_parser = doctor_subparsers.add_parser("queues", help="report queue health")
    queues_parser.add_argument("--root", default=".", help="topology root")
    projections_parser = doctor_subparsers.add_parser("projections", help="report projection health")
    projections_parser.add_argument("--root", default=".", help="topology root")
    projections_parser.add_argument("--project-id")
    projections_parser.add_argument("--canonical-rev")
    projections_parser.add_argument("--subject", dest="subject_repo_id")
    projections_parser.add_argument("--subject-head-sha")
    canonical_parity_parser = doctor_subparsers.add_parser("canonical-parity", help="report canonical page/registry parity")
    canonical_parity_parser.add_argument("--root", default=".", help="topology root")
    public_safe_parser = doctor_subparsers.add_parser("public-safe", help="report public-safe source packet issues")
    public_safe_parser.add_argument("--root", default=".", help="topology root")

    video_parser = subparsers.add_parser("video", help="attach operator-captured video evidence")
    video_subparsers = video_parser.add_subparsers(dest="video_command")
    video_attach = video_subparsers.add_parser("attach-artifact", help="attach local video/transcript evidence to a video source packet")
    video_attach.add_argument("--root", default=".", help="topology root")
    video_attach.add_argument("--source-id", required=True, help="video_platform source packet id")
    video_attach.add_argument(
        "--artifact-kind",
        required=True,
        choices=["video_file", "transcript", "key_frames", "audio_summary", "landing_page_metadata"],
        help="artifact role",
    )
    video_attach.add_argument("--artifact-path", required=True, help="local artifact file")
    video_attach.add_argument("--note", default="operator captured artifact", help="artifact note")
    video_attach.add_argument("--track-text", action="store_true", help="track bounded text excerpt instead of a local blob ref")

    openclaw_parser = subparsers.add_parser("openclaw", help="run OpenClaw live bridge operations")
    openclaw_subparsers = openclaw_parser.add_subparsers(dest="openclaw_command")
    openclaw_capture = openclaw_subparsers.add_parser("capture-source", help="capture runtime summary as source evidence")
    openclaw_capture.add_argument("--root", default=".", help="topology root")
    openclaw_capture.add_argument("--project-id", required=True, help="OpenClaw runtime project id")
    openclaw_capture.add_argument("--canonical-rev", required=True, help="canonical revision")
    openclaw_capture.add_argument("--subject", required=True, dest="subject_repo_id", help="subject repo id")
    openclaw_capture.add_argument("--subject-head-sha", required=True, help="subject HEAD SHA")
    openclaw_capture.add_argument("--runtime-summary-json", required=True, help="runtime summary JSON object")

    openclaw_issue = openclaw_subparsers.add_parser("issue-lease", help="issue an OpenClaw live writeback lease")
    openclaw_issue.add_argument("--root", default=".", help="topology root")
    openclaw_issue.add_argument("--project-id", required=True, help="OpenClaw runtime project id")
    openclaw_issue.add_argument("--canonical-rev", required=True, help="canonical revision")
    openclaw_issue.add_argument("--subject", required=True, dest="subject_repo_id", help="subject repo id")
    openclaw_issue.add_argument("--subject-head-sha", required=True, help="subject HEAD SHA")
    openclaw_issue.add_argument("--runtime-summary-json", required=True, help="runtime summary JSON object")
    openclaw_issue.add_argument("--created-by", default="openclaw-live-issuer", help="lease issuer label")

    openclaw_lease = openclaw_subparsers.add_parser("lease", help="lease the next OpenClaw live writeback job")
    openclaw_lease.add_argument("--root", default=".", help="topology root")
    openclaw_lease.add_argument("--owner", required=True, help="lease owner")
    openclaw_lease.add_argument("--lease-seconds", type=int, default=900, help="lease duration")

    openclaw_run = openclaw_subparsers.add_parser("run-writeback", help="consume an OpenClaw live writeback lease")
    openclaw_run.add_argument("--root", default=".", help="topology root")
    openclaw_run.add_argument("--project-id", required=True, help="OpenClaw runtime project id")
    openclaw_run.add_argument("--canonical-rev", required=True, help="canonical revision")
    openclaw_run.add_argument("--subject", required=True, dest="subject_repo_id", help="subject repo id")
    openclaw_run.add_argument("--subject-head-sha", required=True, help="subject HEAD SHA")
    openclaw_run.add_argument("--lease-path", required=True, help="leased writeback job path")
    openclaw_run.add_argument("--runtime-summary-json", required=True, help="runtime summary JSON object")

    writeback_parser = subparsers.add_parser("writeback", help="create mutation proposal from session summary")
    writeback_parser.add_argument("--root", default=".", help="topology root")
    writeback_parser.add_argument("--summary-json", required=True, help="session summary JSON")
    writeback_parser.add_argument("--subject", required=True, dest="subject_repo_id", help="subject repo id")
    writeback_parser.add_argument("--subject-head-sha", required=True, help="subject HEAD SHA")
    writeback_parser.add_argument("--base-canonical-rev", required=True, help="base canonical revision")
    writeback_parser.add_argument("--current-canonical-rev", required=True, help="current canonical revision")
    writeback_parser.add_argument("--current-subject-head-sha", required=True, help="current subject HEAD SHA")

    guard_parser = subparsers.add_parser("agent-guard", help="run deterministic agent integration guards")
    guard_subparsers = guard_parser.add_subparsers(dest="guard_command")
    claude_guard = guard_subparsers.add_parser("claude-pre-tool-use", help="guard Claude PreToolUse direct file writes")
    claude_guard.add_argument("--root", default=".", help="topology root")

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
        root = Path(args.root).expanduser().resolve()
        if args.run_queue:
            if args.source_id or args.model_output:
                parser.exit(2, "topology digest: --run-queue cannot be combined with --source-id or --model-output\n")
            missing = [
                name
                for name, value in {
                    "--owner": args.owner,
                    "--subject": args.subject_repo_id,
                    "--current-canonical-rev": args.current_canonical_rev,
                    "--current-subject-head-sha": args.current_subject_head_sha,
                }.items()
                if not value
            ]
            if missing:
                parser.exit(2, f"topology digest: queue mode missing required args: {', '.join(missing)}\n")
            if bool(args.provider_command) == bool(args.model_output_dir):
                parser.exit(2, "topology digest: queue mode requires exactly one of --provider-command or --model-output-dir\n")
            try:
                if args.provider_command:
                    provider = CommandDigestProviderAdapter(
                        args.provider_command,
                        cwd=root,
                        timeout_seconds=args.provider_timeout_seconds,
                    )
                else:
                    provider = JsonDirectoryDigestProviderAdapter(args.model_output_dir, root=root)
                result = run_digest_queue(
                    root,
                    provider_adapter=provider,
                    owner=args.owner,
                    current_subject_repo_id=args.subject_repo_id,
                    current_subject_head_sha=args.current_subject_head_sha,
                    current_canonical_rev=args.current_canonical_rev,
                    max_jobs=args.max_jobs,
                    lease_seconds=args.lease_seconds,
                    max_attempts=args.max_attempts,
                )
            except (DigestProviderError, DigestQueueRunnerError, ValueError) as exc:
                parser.exit(2, f"topology digest: {exc}\n")
            print(f"digest jobs leased: {result.leased}")
            print(f"digest jobs completed: {result.completed}")
            print(f"digest jobs failed: {result.failed}")
            for path in result.digest_json_paths:
                print(f"created digest json: {path}")
            for path in result.digest_md_paths:
                print(f"created digest markdown: {path}")
            return 0 if result.failed == 0 else 1
        queue_only_args = [
            args.owner,
            args.subject_repo_id,
            args.current_canonical_rev,
            args.current_subject_head_sha,
            args.provider_command,
            args.model_output_dir,
            args.provider_timeout_seconds != 120,
            args.max_jobs != 1,
            args.lease_seconds != 900,
            args.max_attempts != 3,
        ]
        if any(queue_only_args):
            parser.exit(2, "topology digest: queue-only arguments require --run-queue\n")
        if not args.source_id or not args.model_output:
            parser.exit(2, "topology digest: legacy mode requires --source-id and --model-output\n")
        try:
            json_path, md_path = write_digest_artifacts(
                root,
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
    if args.command == "subject" and args.subject_command == "add":
        try:
            payload = add_subject(
                Path(args.root).expanduser().resolve(),
                subject_repo_id=args.subject_repo_id,
                name=args.name,
                kind=args.kind,
                location=args.location,
                default_branch=args.default_branch,
                visibility=args.visibility,
                sensitivity=args.sensitivity,
                now=utc_now(),
            )
        except (SubjectRegistryError, ValueError) as exc:
            parser.exit(2, f"topology subject add: {exc}\n")
        print(json_dumps(payload))
        return 0
    if args.command == "subject" and args.subject_command == "refresh":
        try:
            payload = refresh_subject(
                Path(args.root).expanduser().resolve(),
                args.subject_repo_id,
                now=utc_now(),
            )
        except (SubjectRegistryError, ValueError) as exc:
            parser.exit(2, f"topology subject refresh: {exc}\n")
        print(json_dumps(payload))
        return 0
    if args.command == "subject" and args.subject_command == "show":
        try:
            payload = show_subject(Path(args.root).expanduser().resolve(), args.subject_repo_id)
        except (SubjectRegistryError, ValueError) as exc:
            parser.exit(2, f"topology subject show: {exc}\n")
        print(json_dumps(payload))
        return 0
    if args.command == "subject" and args.subject_command == "resolve":
        try:
            payload = resolve_subject(Path(args.root).expanduser().resolve(), args.subject_repo_id)
        except (SubjectRegistryError, ValueError) as exc:
            parser.exit(2, f"topology subject resolve: {exc}\n")
        print(json_dumps(payload))
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
    if args.command == "compose" and args.compose_command == "openclaw":
        try:
            projection_dir = write_openclaw_projection(
                Path(args.root).expanduser().resolve(),
                project_id=args.project_id,
                canonical_rev=args.canonical_rev,
                subject_repo_id=args.subject_repo_id,
                subject_head_sha=args.subject_head_sha,
                subject_path=args.subject_path,
                allow_dirty=args.allow_dirty,
            )
        except (OpenClawComposeError, ValueError) as exc:
            parser.exit(2, f"topology compose openclaw: {exc}\n")
        print(f"created OpenClaw projection: {projection_dir}")
        return 0
    if args.command == "lint":
        if args.lint_mode == "runtime":
            result = run_runtime_lints(Path(args.root).expanduser().resolve())
        else:
            result = run_repo_lints(Path(args.root).expanduser().resolve())
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
    if args.command == "doctor" and args.doctor_command == "queues":
        result = doctor_queues(Path(args.root).expanduser().resolve())
        for message in result.messages:
            print(message)
        return 0 if result.ok else 1
    if args.command == "doctor" and args.doctor_command == "projections":
        result = doctor_projections(
            Path(args.root).expanduser().resolve(),
            project_id=args.project_id,
            canonical_rev=args.canonical_rev,
            subject_repo_id=args.subject_repo_id,
            subject_head_sha=args.subject_head_sha,
        )
        for message in result.messages:
            print(message)
        return 0 if result.ok else 1
    if args.command == "doctor" and args.doctor_command == "canonical-parity":
        result = doctor_canonical_parity(Path(args.root).expanduser().resolve())
        for message in result.messages:
            print(message)
        return 0 if result.ok else 1
    if args.command == "doctor" and args.doctor_command == "public-safe":
        result = doctor_public_safe(Path(args.root).expanduser().resolve())
        for message in result.messages:
            print(message)
        return 0 if result.ok else 1
    if args.command == "video" and args.video_command == "attach-artifact":
        try:
            packet_path = attach_video_artifact(
                Path(args.root).expanduser().resolve(),
                source_id=args.source_id,
                artifact_kind=args.artifact_kind,
                artifact_path=args.artifact_path,
                note=args.note,
                track_text=args.track_text,
            )
        except (FetchError, ValueError) as exc:
            parser.exit(2, f"topology video attach-artifact: {exc}\n")
        print(f"updated video source packet: {packet_path}")
        return 0
    if args.command == "openclaw" and args.openclaw_command == "capture-source":
        try:
            packet_path = create_runtime_source_packet(
                Path(args.root).expanduser().resolve(),
                project_id=args.project_id,
                canonical_rev=args.canonical_rev,
                subject_repo_id=args.subject_repo_id,
                subject_head_sha=args.subject_head_sha,
                runtime_summary=load_json_object(args.runtime_summary_json, "runtime summary"),
            )
        except (OpenClawLiveError, ValueError) as exc:
            parser.exit(2, f"topology openclaw capture-source: {exc}\n")
        print(f"created OpenClaw runtime source packet: {packet_path}")
        return 0
    if args.command == "openclaw" and args.openclaw_command == "issue-lease":
        try:
            lease_path = issue_openclaw_live_lease(
                Path(args.root).expanduser().resolve(),
                project_id=args.project_id,
                canonical_rev=args.canonical_rev,
                subject_repo_id=args.subject_repo_id,
                subject_head_sha=args.subject_head_sha,
                runtime_summary=load_json_object(args.runtime_summary_json, "runtime summary"),
                created_by=args.created_by,
            )
        except (OpenClawLiveError, ValueError) as exc:
            parser.exit(2, f"topology openclaw issue-lease: {exc}\n")
        print(f"issued OpenClaw live lease: {lease_path}")
        return 0
    if args.command == "openclaw" and args.openclaw_command == "lease":
        try:
            lease_path = lease_openclaw_live_job(
                Path(args.root).expanduser().resolve(),
                owner=args.owner,
                lease_seconds=args.lease_seconds,
            )
        except (OpenClawLiveError, ValueError) as exc:
            parser.exit(2, f"topology openclaw lease: {exc}\n")
        print(f"leased OpenClaw live job: {lease_path}")
        return 0
    if args.command == "openclaw" and args.openclaw_command == "run-writeback":
        try:
            result = run_openclaw_live_writeback(
                Path(args.root).expanduser().resolve(),
                project_id=args.project_id,
                canonical_rev=args.canonical_rev,
                subject_repo_id=args.subject_repo_id,
                subject_head_sha=args.subject_head_sha,
                lease_path=args.lease_path,
                runtime_summary_path=args.runtime_summary_json,
            )
        except (OpenClawLiveError, ValueError) as exc:
            parser.exit(2, f"topology openclaw run-writeback: {exc}\n")
        if result.mutation_path is not None:
            print(f"created OpenClaw writeback mutation pack: {result.mutation_path}")
        if result.relationship_tests_path is not None:
            print(f"created OpenClaw relationship-test delta: {result.relationship_tests_path}")
        print(f"consumed OpenClaw live lease: {result.lease_path}")
        return 0
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
    if args.command == "agent-guard" and args.guard_command == "claude-pre-tool-use":
        result = guard_claude_pre_tool_use(Path(args.root).expanduser().resolve(), sys.stdin.read())
        if result.allowed:
            return 0
        print(result.reason, file=sys.stderr)
        return 2
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

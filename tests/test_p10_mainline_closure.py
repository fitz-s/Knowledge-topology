import subprocess
import sys
import unittest
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def cli(*args: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "knowledge_topology.cli", *args],
        cwd=ROOT,
        env={"PYTHONPATH": str(SRC)},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout


class P10MainlineClosureTests(unittest.TestCase):
    def test_mainline_status_links_tracked_evidence(self):
        status = read("docs/MAINLINE_STATUS.md")
        self.assertIn("The P0-P9 mainline is complete.", status)
        self.assertIn("P0 is a contract reality pass", status)
        self.assertIn("docs/P0_CONTRACT_REALITY_PASS.md", status)
        self.assertIn("tests/test_p0_contracts.py", status)
        for package in range(1, 10):
            self.assertIn(f"docs/package-reviews/P{package}_UNFREEZE.md", status)
        for plan in [
            "docs/package-plans/P1_ENGINE_SKELETON.md",
            "docs/package-plans/P2_SOURCE_PACKET_FETCH.md",
            "docs/package-plans/P3_DIGEST_CONTRACT.md",
            "docs/package-plans/P4_RECONCILE_MUTATION.md",
            "docs/package-plans/P5_APPLY_GATE.md",
            "docs/package-plans/P6_BUILDER_COMPOSE.md",
            "docs/package-plans/P7_WRITEBACK_LINT_DOCTOR.md",
            "docs/package-plans/P8_CODEX_CLAUDE_INTEGRATION.md",
            "docs/package-plans/P9_OPENCLAW_INTEGRATION.md",
            "docs/package-plans/P11_1_BUILDER_WRITEBACK_SYMMETRY.md",
            "docs/package-plans/P11_2_DIGEST_RUNNER_CLOSURE.md",
            "docs/package-plans/P11_3_FETCH_V2.md",
            "docs/package-plans/P11_4_OPENCLAW_LIVE_BRIDGE.md",
            "docs/package-plans/P11_5_LINT_DOCTOR_SPLIT.md",
            "docs/package-plans/P11_6_SUBJECT_FILE_INDEX.md",
            "docs/package-plans/P11_7_VIDEO_PLATFORM_INGEST.md",
            "docs/package-plans/P12_1_CONSUMER_BOOTSTRAP.md",
            "docs/package-plans/P12_2_VIDEO_MEDIA_CLOSURE.md",
            "docs/package-plans/P12_3_OPENCLAW_CONSUMER_BUNDLE.md",
            "docs/package-plans/P12_4_MAINTAINER_SUPERVISOR.md",
            "docs/package-plans/P12_5_EVALUATION_BENCHMARK.md",
            "docs/package-plans/P13_0_VIDEO_EVIDENCE_DISCIPLINE.md",
        ]:
            self.assertTrue((ROOT / plan).exists(), plan)
            self.assertIn(plan, status)
        for review in [
            "docs/package-reviews/P11_1_UNFREEZE.md",
            "docs/package-reviews/P11_2_UNFREEZE.md",
            "docs/package-reviews/P11_3_UNFREEZE.md",
            "docs/package-reviews/P11_4_UNFREEZE.md",
            "docs/package-reviews/P11_5_UNFREEZE.md",
            "docs/package-reviews/P11_6_UNFREEZE.md",
            "docs/package-reviews/P11_7_UNFREEZE.md",
            "docs/package-reviews/P12_1_UNFREEZE.md",
            "docs/package-reviews/P12_2_UNFREEZE.md",
            "docs/package-reviews/P12_3_UNFREEZE.md",
            "docs/package-reviews/P12_4_UNFREEZE.md",
            "docs/package-reviews/P12_5_UNFREEZE.md",
            "docs/package-reviews/P13_0_UNFREEZE.md",
        ]:
            self.assertTrue((ROOT / review).exists(), review)
            self.assertIn(review, status)
        self.assertNotIn("P0_UNFREEZE.md", status)
        self.assertNotIn(".omx/plans/", status)

    def test_deferred_surfaces_are_explicit(self):
        status = read("docs/MAINLINE_STATUS.md")
        plan = read("docs/IMPLEMENTATION_PLAN.md")
        deferred = [
            "audio/video transcript resolver",
            "deep social thread expansion resolver",
            "Codex topology MCP registration",
            "Claude changed-file lint/writeback hooks",
            "hosted OpenClaw service or topology MCP server",
            "OpenClaw private workspace writes",
            "OpenClaw memory-wiki import or live validation",
            "OpenClaw QMD live indexing validation",
            "OpenClaw natural-language runtime context sanitizer",
        ]
        for item in deferred:
            self.assertIn(item, status)
        self.assertIn("P11.5 shipped doctor subcommands", plan)
        self.assertIn("P11.6 shipped subject commands", plan)
        self.assertIn("topology MCP registration is deferred", plan)
        self.assertIn("Claude changed-file lint/writeback hooks are deferred", plan)
        self.assertIn("structured-only local runtime projection", plan)
        self.assertIn("P12.3 packages the OpenClaw read/writeback protocol", plan)

    def test_cli_reality_matches_status(self):
        plan = read("docs/IMPLEMENTATION_PLAN.md")
        top_help = cli("--help")
        for command in ["init", "ingest", "digest", "reconcile", "apply", "subject", "compose", "lint", "doctor", "writeback", "agent-guard", "openclaw", "video", "bootstrap", "resolve-context", "supervisor", "eval"]:
            self.assertIn(command, top_help)
            self.assertIn(f"topology {command}", plan)

        compose_help = cli("compose", "--help")
        self.assertIn("builder", compose_help)
        self.assertIn("openclaw", compose_help)

        subject_help = cli("subject", "--help")
        for shipped in ["add", "refresh", "show", "resolve"]:
            self.assertIn(shipped, subject_help)

        openclaw_help = cli("openclaw", "--help")
        for shipped in ["capture-source", "issue-lease", "lease", "run-writeback"]:
            self.assertIn(shipped, openclaw_help)

        video_help = cli("video", "--help")
        for shipped in ["ingest", "status", "trace", "prepare-digest", "attach-artifact"]:
            self.assertIn(shipped, video_help)

        bootstrap_help = cli("bootstrap", "--help")
        for shipped in ["codex", "claude", "openclaw", "remove"]:
            self.assertIn(shipped, bootstrap_help)

        supervisor_help = cli("supervisor", "--help")
        self.assertIn("run", supervisor_help)

        eval_help = cli("eval", "--help")
        self.assertIn("run", eval_help)

        doctor_help = cli("doctor", "--help")
        self.assertIn("stale-anchors", doctor_help)
        for shipped in ["queues", "public-safe", "projections", "canonical-parity", "consumer"]:
            self.assertIn(shipped, doctor_help)

    def test_p10_plan_and_unfreeze_contract_are_declared(self):
        plan = read("docs/package-plans/P10_MAINLINE_CLOSURE.md")
        self.assertIn("docs/package-reviews/P10_UNFREEZE.md", plan)
        self.assertIn("Gemini remains not required only if P10 does not change", plan)
        self.assertTrue((ROOT / "docs/package-reviews/P10_UNFREEZE.md").exists())
        status = read("docs/MAINLINE_STATUS.md")
        review = read("docs/package-reviews/P10_UNFREEZE.md")
        self.assertIn("| P10 Mainline Closure | approved |", status)
        self.assertNotIn("| P10 Mainline Closure | in progress |", status)
        self.assertIn("35464e0", review)
        self.assertIn("57294bb", review)
        self.assertIn("terminal P10 closure commit", review)
        self.assertIn("Required: no.", review)
        self.assertNotIn("expected to include", review)

    def test_shipped_package_rows_have_plan_and_review_artifacts(self):
        status = read("docs/MAINLINE_STATUS.md")
        rows = [
            line
            for line in status.splitlines()
            if line.startswith("| P") and "Plan / Evidence" not in line and "---" not in line
        ]
        self.assertTrue(rows)
        for row in rows:
            paths = re.findall(r"`([^`]+)`", row)
            package_label = row.split("|", 2)[1].strip()
            if package_label == "P0 Contract Reality Pass":
                self.assertEqual(paths, ["docs/P0_CONTRACT_REALITY_PASS.md", "tests/test_p0_contracts.py"])
                continue
            self.assertEqual(len(paths), 2, row)
            for path in paths:
                self.assertTrue((ROOT / path).exists(), f"{package_label}: {path}")


if __name__ == "__main__":
    unittest.main()

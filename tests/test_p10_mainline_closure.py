import subprocess
import sys
import unittest
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
        ]:
            self.assertTrue((ROOT / plan).exists(), plan)
            self.assertIn(plan, status)
        self.assertNotIn("P0_UNFREEZE.md", status)
        self.assertNotIn(".omx/plans/", status)

    def test_deferred_surfaces_are_explicit(self):
        status = read("docs/MAINLINE_STATUS.md")
        plan = read("docs/IMPLEMENTATION_PLAN.md")
        deferred = [
            "topology subject add",
            "topology doctor queues",
            "topology doctor public-safe",
            "topology doctor projections",
            "topology doctor canonical-parity",
            "audio/video transcript resolver",
            "deep social thread expansion resolver",
            "Codex topology MCP registration",
            "Claude changed-file lint/writeback hooks",
            "live OpenClaw adapter",
            "OpenClaw private workspace writes",
            "queue leases around external OpenClaw writes",
            "OpenClaw memory-wiki import or live validation",
            "OpenClaw QMD live indexing validation",
            "OpenClaw natural-language runtime context sanitizer",
            "OpenClaw file-ref projection with subject-file index",
        ]
        for item in deferred:
            self.assertIn(item, status)
        self.assertIn("Deferred doctor subcommands", plan)
        self.assertIn("Deferred subject commands", plan)
        self.assertIn("topology MCP registration is deferred", plan)
        self.assertIn("Claude changed-file lint/writeback hooks are deferred", plan)
        self.assertIn("structured-only local runtime projection", plan)

    def test_cli_reality_matches_status(self):
        plan = read("docs/IMPLEMENTATION_PLAN.md")
        top_help = cli("--help")
        for command in ["init", "ingest", "digest", "reconcile", "apply", "compose", "lint", "doctor", "writeback", "agent-guard"]:
            self.assertIn(command, top_help)
            self.assertIn(f"topology {command}", plan)
        self.assertNotIn("subject", top_help)

        compose_help = cli("compose", "--help")
        self.assertIn("builder", compose_help)
        self.assertIn("openclaw", compose_help)

        doctor_help = cli("doctor", "--help")
        self.assertIn("stale-anchors", doctor_help)
        for deferred in ["queues", "public-safe", "projections", "canonical-parity"]:
            self.assertNotIn(deferred, doctor_help)

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


if __name__ == "__main__":
    unittest.main()

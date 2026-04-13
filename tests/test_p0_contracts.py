import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class P0ContractTests(unittest.TestCase):
    def read_doc(self, name: str) -> str:
        path = ROOT / name
        self.assertTrue(path.exists(), f"{name} is missing")
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.endswith("\n"), f"{name} must end with newline")
        return text

    def read_json(self, relative: str) -> dict:
        path = ROOT / relative
        self.assertTrue(path.exists(), f"{relative} is missing")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_p0_governance_docs_exist_and_cross_reference_contracts(self):
        docs = {
            "GIT_PROTOCOL.md": ["Apply rejects stale mutation preconditions", "Lore"],
            "SECURITY.md": ["Untrusted-content workers must not", "path traversal"],
            "RAW_POLICY.md": ["content_mode", "redistributable"],
            "ESCALATIONS.md": ["recommended_default", "safe default"],
            "SCHEMA_EVOLUTION.md": ["schema_version", "fixture"],
            "COMPILE.md": ["Allowed builder traversal edge types", "max nodes"],
            "docs/P0_CONTRACT_REALITY_PASS.md": ["Construction Table", "P0.1 Git protocol"]
        }
        for doc, needles in docs.items():
            text = self.read_doc(doc)
            for needle in needles:
                self.assertIn(needle, text, f"{doc} should mention {needle}")

    def test_raw_policy_fixture_has_safe_defaults(self):
        fixture = self.read_json("tests/fixtures/p0/raw_policy/source_mode_matrix.json")
        defaults = fixture["defaults"]
        self.assertEqual(defaults["article_html"]["default_mode"], "excerpt_only")
        self.assertEqual(defaults["pdf_arxiv"]["default_mode"], "excerpt_only")
        self.assertEqual(defaults["pdf_arxiv"]["blob_mode"], "local_blob")
        self.assertIn("unknown", fixture["redistributable_values"])

    def test_escalation_card_fixture_has_preconditions_and_options(self):
        card = self.read_json("tests/fixtures/p0/escalations/escalation_card.json")
        for field in [
            "id",
            "gate_class",
            "recommended_default",
            "options",
            "evidence_refs",
            "mutation_pack_id",
            "base_canonical_rev",
            "subject_repo_id",
            "subject_head_sha"
        ]:
            self.assertIn(field, card)
        self.assertIn(card["recommended_default"], card["options"])

    def test_security_fixture_denies_privileged_untrusted_actions(self):
        fixture = self.read_json("tests/fixtures/p0/security/threat_denials.json")
        denied = set(fixture["denied_actions"])
        self.assertEqual(fixture["expected_default"], "deny")
        self.assertIn("untrusted_worker_write_canonical", denied)
        self.assertIn("untrusted_worker_run_apply", denied)
        self.assertIn("follow_source_path_traversal", denied)

    def test_compile_fixture_is_bounded_and_excludes_runtime_only_records(self):
        fixture = self.read_json("tests/fixtures/p0/compile/traversal_case.json")
        self.assertLessEqual(fixture["bounds"]["max_traversal_depth"], 2)
        self.assertIn("INVARIANT_FOR", fixture["allowed_edge_types"])
        self.assertIn("runtime_only", fixture["excluded_audiences"])
        self.assertIn("relationship-tests.yaml", fixture["expected_outputs"])

    def test_schema_evolution_fixture_uses_opaque_id_and_schema_version(self):
        node = self.read_json("tests/fixtures/p0/schema_evolution/node_v1.json")
        self.assertEqual(node["schema_version"], "1.0")
        self.assertTrue(node["id"].startswith("nd_"))
        self.assertEqual(node["type"], "invariant")

    def test_git_protocol_fixture_rejects_stale_apply(self):
        fixture = self.read_json("tests/fixtures/p0/git_protocol/stale_apply_conflict.json")
        self.assertEqual(fixture["expected_action"], "reject_stale_and_mark_contested")
        self.assertNotEqual(fixture["base_canonical_rev"], fixture["current_canonical_rev"])
        self.assertIn("re_reconcile_against_current_canonical_rev", fixture["required_recovery_steps"])


if __name__ == "__main__":
    unittest.main()

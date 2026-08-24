from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PRE_PATH = ROOT / "scripts/experiments/inject_fault_scenario.py"
POST_PATH = ROOT / "scripts/experiments/inject_post_fault_scenario.py"
WORKFLOW_PATH = ROOT / ".github/workflows/c0-isolated.yml"
RUNNER_PATH = ROOT / "scripts/github_actions/run_c0_isolated.py"
FINALIZER_PATH = ROOT / "scripts/github_actions/finalize_c0_observation.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PRE = load_module("c0_pre_fixture", PRE_PATH)
POST = load_module("c0_post_fixture", POST_PATH)
FINALIZER = load_module("c0_observation_finalizer", FINALIZER_PATH)


class C0MatchedComparatorTest(unittest.TestCase):
    def make_contract_root(self, content: str) -> tuple[Path, Path, tempfile.TemporaryDirectory]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        contract = root / "transformations/dbt/tests/gold_contract_columns.sql"
        contract.parent.mkdir(parents=True)
        contract.write_text(content, encoding="utf-8")
        evidence = root / "evidence"
        return root, evidence, temporary

    def test_schema_break_fixture_is_relabelled_c0_without_changing_fault(self):
        root, evidence, temporary = self.make_contract_root(
            "select * from (values\n"
            "        ('{{ gold_internal_schema }}', 'gold_customer_order_summary', 11, 'average_order_value'),\n"
            ")\n"
        )
        self.addCleanup(temporary.cleanup)

        payload = PRE.inject_schema_break(
            repo_root=root,
            evidence_dir=evidence,
            condition="C0",
        )

        self.assertEqual(payload["condition"], "C0")
        self.assertEqual(payload["scenario_id"], "schema_break")
        self.assertEqual(payload["fault"]["operation"], "remove_required_contract_column")
        self.assertFalse(payload["safety"]["canonical_data_mutated"])

    def test_pii_fixture_is_relabelled_c0_without_changing_fault(self):
        root, evidence, temporary = self.make_contract_root(
            "select * from (values\n"
            "        ('{{ gold_public_schema }}', 'gold_public_sales_dashboard', 8, 'total_revenue')\n"
            ")\n"
        )
        self.addCleanup(temporary.cleanup)

        payload = PRE.inject_pii_exposure(
            repo_root=root,
            evidence_dir=evidence,
            condition="C0",
        )

        self.assertEqual(payload["condition"], "C0")
        self.assertEqual(payload["scenario_id"], "pii_exposure")
        self.assertEqual(payload["fault"]["column"], "synthetic_email")
        self.assertFalse(payload["safety"]["canonical_data_mutated"])

    def test_policy_false_positive_preserves_safe_ground_truth(self):
        root, evidence, temporary = self.make_contract_root(
            "select * from (values\n"
            "        ('{{ gold_internal_schema }}', 'gold_customer_order_summary', 11, 'average_order_value'),\n"
            ")\n"
        )
        self.addCleanup(temporary.cleanup)
        model = root / "transformations/dbt/models/gold/internal/gold_customer_order_summary.sql"
        model.parent.mkdir(parents=True)
        model.write_text(
            "select\n"
            "    cast(\n"
            "        1 as double\n"
            "    ) as average_order_value\n"
            "\n"
            "from customer_totals as totals\n",
            encoding="utf-8",
        )

        payload = PRE.inject_policy_false_positive(
            repo_root=root,
            evidence_dir=evidence,
            condition="C0",
        )

        self.assertEqual(payload["condition"], "C0")
        self.assertEqual(payload["scenario_id"], "policy_false_positive")
        self.assertEqual(payload["ground_truth"]["classification"], "SAFE")
        self.assertEqual(payload["ground_truth"]["expected_decision"], "ALLOW")

    def test_freshness_fixture_uses_exact_one_second_breach(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "freshness_control.csv"
            output = root / "injected.csv"
            evidence = root / "evidence"
            source.write_text(
                "dataset_name,expected_publish_time,actual_publish_time,freshness_slo_hours,freshness_status,run_id\n"
                "gold_daily_sales,2026-07-07T00:00:00+00:00,2026-07-06T00:00:00+00:00,24,PASS,test-run\n",
                encoding="utf-8",
            )

            payload = POST.inject_freshness_breach(
                source=source,
                output=output,
                evidence_dir=evidence,
                condition="C0",
            )

            self.assertEqual(payload["condition"], "C0")
            self.assertEqual(payload["scenario_id"], "freshness_breach")
            self.assertEqual(payload["injected"]["observed_age_seconds"], 86401.0)
            self.assertEqual(payload["injected"]["maximum_age_seconds"], 86400.0)
            self.assertEqual(source.read_text(encoding="utf-8").count("PASS"), 1)

    def test_quality_fixture_changes_only_the_governed_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "run_results.json"
            output = root / "injected.json"
            evidence = root / "evidence"
            target = "test.thesis_pac_pipeline.gold_financial_reconciliation"
            results = [
                {"unique_id": f"model.thesis_pac_pipeline.model_{index}", "status": "success"}
                for index in range(15)
            ]
            results.extend(
                {"unique_id": target if index == 0 else f"test.thesis_pac_pipeline.test_{index}", "status": "pass", "failures": 0}
                for index in range(41)
            )
            source.write_text(json.dumps({"results": results}) + "\n", encoding="utf-8")

            payload = POST.inject_quality_regression(
                source=source,
                output=output,
                evidence_dir=evidence,
                condition="C0",
            )

            self.assertEqual(payload["condition"], "C0")
            self.assertEqual(payload["scenario_id"], "quality_regression")
            self.assertEqual(payload["injected"]["failed_tests"], 1)
            self.assertEqual(payload["target_test"], target)
            self.assertEqual(json.loads(source.read_text())["results"][15]["status"], "pass")

    def test_c1_condition_remains_the_backward_compatible_default(self):
        root, evidence, temporary = self.make_contract_root(
            "select * from (values\n"
            "        ('{{ gold_internal_schema }}', 'gold_customer_order_summary', 11, 'average_order_value'),\n"
            ")\n"
        )
        self.addCleanup(temporary.cleanup)
        payload = PRE.inject_schema_break(repo_root=root, evidence_dir=evidence)
        self.assertEqual(payload["condition"], "C1")

    def test_workflow_exposes_exact_matched_manual_scenarios(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        scenarios = [
            "schema_break",
            "pii_exposure",
            "freshness_breach",
            "quality_regression",
            "policy_false_positive",
        ]

        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("\n  push:", workflow)
        self.assertNotIn("pull_request", workflow)
        self.assertNotIn("\n  schedule:", workflow)
        self.assertIn("scenario_id:", workflow)
        for scenario in scenarios:
            self.assertEqual(workflow.count(f"          - {scenario}\n"), 1)

    def test_workflow_keeps_condition_controls_separated(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        finalizer = FINALIZER_PATH.read_text(encoding="utf-8")
        forbidden_execution_markers = [
            "open-policy-agent/",
            "opa eval",
            "conftest test",
            "scripts/policy/",
            "scripts/remediation/",
        ]
        for marker in forbidden_execution_markers:
            self.assertNotIn(marker, workflow)
        self.assertIn('"policy_as_code_active": False', finalizer)
        self.assertIn('"self_healing_active": False', finalizer)

    def test_workflow_uploads_evidence_before_observed_failure(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        upload = workflow.index("- name: Upload durable C0 evidence")
        enforce = workflow.index("- name: Preserve observed standard CI/CD conclusion")
        self.assertLess(upload, enforce)
        self.assertIn("experiment-result.json", workflow)
        self.assertIn("finalize_c0_observation.py", workflow)
        self.assertIn("canonical_mutation_performed", FINALIZER_PATH.read_text(encoding="utf-8"))

    def test_finalizer_records_controlled_pre_execution_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "pre-fault-injection").mkdir()
            (root / "c0-runner-exit-code.txt").write_text("1\n", encoding="utf-8")
            (root / "canonical-comparison.json").write_text(
                json.dumps({"changed": False}) + "\n",
                encoding="utf-8",
            )
            (root / "failure.json").write_text(
                json.dumps({"status": "FAIL", "error": "observed standard test failure"}) + "\n",
                encoding="utf-8",
            )
            (root / "pre-fault-injection/fault-injection.json").write_text(
                json.dumps({"condition": "C0", "scenario_id": "schema_break"}) + "\n",
                encoding="utf-8",
            )

            payload = FINALIZER.finalize(
                evidence_root=root,
                scenario="schema_break",
                environment={"GITHUB_RUN_ID": "101", "GITHUB_RUN_ATTEMPT": "1"},
            )

            self.assertEqual(payload["status"], "PASS")
            self.assertEqual(payload["observed_pipeline_outcome"], "FAIL")
            self.assertTrue(payload["pipeline_failure_present"])
            self.assertFalse(payload["canonical_mutation_performed"])
            self.assertTrue((root / "SHA256SUMS").is_file())

    def test_finalizer_records_undetected_post_execution_fault(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "post-fault-injection").mkdir()
            (root / "c0-runner-exit-code.txt").write_text("0\n", encoding="utf-8")
            (root / "canonical-comparison.json").write_text(
                json.dumps({"changed": False}) + "\n",
                encoding="utf-8",
            )
            (root / "final-checkpoint.json").write_text(
                json.dumps({"status": "PASS"}) + "\n",
                encoding="utf-8",
            )
            (root / "post-fault-injection/fault-injection.json").write_text(
                json.dumps({"condition": "C0", "scenario_id": "freshness_breach"}) + "\n",
                encoding="utf-8",
            )

            payload = FINALIZER.finalize(
                evidence_root=root,
                scenario="freshness_breach",
                environment={},
            )

            self.assertEqual(payload["observed_pipeline_outcome"], "PASS")
            self.assertTrue(payload["post_execution_fault_reached_evidence_boundary"])
            self.assertFalse(payload["pipeline_failure_present"])

    def test_finalizer_rejects_missing_canonical_comparison(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "pre-fault-injection").mkdir()
            (root / "c0-runner-exit-code.txt").write_text("1\n", encoding="utf-8")
            (root / "pre-fault-injection/fault-injection.json").write_text(
                json.dumps({"condition": "C0", "scenario_id": "pii_exposure"}) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "Canonical comparison"):
                FINALIZER.finalize(
                    evidence_root=root,
                    scenario="pii_exposure",
                    environment={},
                )

    def test_runner_accepts_only_the_five_matched_scenarios(self):
        runner = RUNNER_PATH.read_text(encoding="utf-8")
        self.assertIn("MATCHED_SCENARIOS = (", runner)
        self.assertIn("if scenario not in MATCHED_SCENARIOS:", runner)
        self.assertNotIn('if scenario != "baseline":', runner)
        self.assertIn('"scenario": scenario,', runner)


if __name__ == "__main__":
    unittest.main()

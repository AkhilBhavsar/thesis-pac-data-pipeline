import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema import FormatChecker


ROOT = Path(__file__).resolve().parents[2]

CATALOG_PATH = (
    ROOT
    / "policies/catalog/c2-remediation-catalog.json"
)

PLAN_SCHEMA_PATH = (
    ROOT
    / "policies/contracts/c2-remediation-plan.schema.json"
)

RESULT_SCHEMA_PATH = (
    ROOT
    / "policies/contracts/c2-remediation-result.schema.json"
)


class C2RemediationContractsTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads(
            CATALOG_PATH.read_text(encoding="utf-8")
        )

        cls.plan_schema = json.loads(
            PLAN_SCHEMA_PATH.read_text(encoding="utf-8")
        )

        cls.result_schema = json.loads(
            RESULT_SCHEMA_PATH.read_text(encoding="utf-8")
        )

        Draft202012Validator.check_schema(
            cls.plan_schema
        )

        Draft202012Validator.check_schema(
            cls.result_schema
        )

        cls.plan_validator = Draft202012Validator(
            cls.plan_schema,
            format_checker=FormatChecker(),
        )

        cls.result_validator = Draft202012Validator(
            cls.result_schema,
            format_checker=FormatChecker(),
        )

    def make_plan(self, scenario_id):
        scenario = self.catalog[
            "scenarios"
        ][scenario_id]

        automatic = scenario[
            "automatic_remediation_permitted"
        ]

        return {
            "schema_version": "1.0.0",
            "condition": "C2",
            "scenario_id": scenario_id,
            "run_key": "test_c2_contract",
            "source_policy_decision_sha256": "a" * 64,
            "source_policy_decision": {
                "evaluation_stage": scenario[
                    "detection_stage"
                ],
                "decision": "DENY",
                "triggered_policy_ids": [
                    "PAC-RELEASE-001"
                ],
                "promotion_blocked": True,
            },
            "controls": {
                "policy_as_code_required": True,
                "self_healing_permitted": True,
                "automatic_remediation_permitted": automatic,
            },
            "plan": {
                "mode": (
                    "automatic"
                    if automatic
                    else "manual"
                ),
                "primary_action": scenario[
                    "primary_action"
                ],
                "fallback_action": scenario[
                    "fallback_action"
                ],
                "max_attempts": scenario[
                    "max_attempts"
                ],
                "timeout_seconds": (
                    300
                    if automatic
                    else 0
                ),
                "target_scope": scenario[
                    "target_scope"
                ],
                "verification": scenario[
                    "verification"
                ],
                "canonical_mutation_before_verification": False,
            },
            "rationale": (
                "Catalog-derived C2 bounded remediation plan."
            ),
        }

    def test_all_catalog_scenarios_produce_valid_plans(self):
        for scenario_id in sorted(
            self.catalog["scenarios"]
        ):
            with self.subTest(
                scenario_id=scenario_id
            ):
                self.plan_validator.validate(
                    self.make_plan(scenario_id)
                )

    def test_catalog_global_attempt_bound(self):
        maximum = self.catalog[
            "principles"
        ][
            "maximum_automatic_attempts"
        ]

        self.assertEqual(maximum, 2)

        for scenario in self.catalog[
            "scenarios"
        ].values():
            self.assertLessEqual(
                scenario["max_attempts"],
                maximum,
            )

    def test_false_positive_is_manual_only(self):
        scenario = self.catalog[
            "scenarios"
        ][
            "policy_false_positive"
        ]

        self.assertFalse(
            scenario[
                "automatic_remediation_permitted"
            ]
        )

        self.assertEqual(
            scenario["max_attempts"],
            0,
        )

        self.assertEqual(
            scenario["primary_action"],
            "manual_review",
        )

        self.plan_validator.validate(
            self.make_plan(
                "policy_false_positive"
            )
        )

    def test_plan_rejects_c1_condition(self):
        payload = self.make_plan(
            "freshness_breach"
        )

        payload["condition"] = "C1"

        self.assertTrue(
            list(
                self.plan_validator.iter_errors(
                    payload
                )
            )
        )

    def test_plan_rejects_unbounded_attempts(self):
        payload = self.make_plan(
            "freshness_breach"
        )

        payload["plan"]["max_attempts"] = 3

        self.assertTrue(
            list(
                self.plan_validator.iter_errors(
                    payload
                )
            )
        )

    def test_plan_rejects_canonical_mutation_before_verification(self):
        payload = self.make_plan(
            "quality_regression"
        )

        payload[
            "plan"
        ][
            "canonical_mutation_before_verification"
        ] = True

        self.assertTrue(
            list(
                self.plan_validator.iter_errors(
                    payload
                )
            )
        )

    def test_valid_verified_recovery_result(self):
        payload = {
            "schema_version": "1.0.0",
            "condition": "C2",
            "scenario_id": "freshness_breach",
            "run_key": "test_c2_recovery",
            "source_remediation_plan_sha256": "b" * 64,
            "mode": "automatic",
            "action": "retry",
            "attempt_count": 1,
            "execution_status": "SUCCEEDED",
            "verification": {
                "required": True,
                "status": "PASS",
                "evidence_sha256": "c" * 64,
            },
            "terminal_state": "RECOVERED",
            "fault_detected_at_utc": "2026-08-19T18:00:00Z",
            "remediation_started_at_utc": "2026-08-19T18:00:01Z",
            "remediation_completed_at_utc": "2026-08-19T18:00:02Z",
            "action_duration_ms": 1000,
            "recovery_time_ms": 2000,
            "promotion_recheck_required": True,
            "canonical_mutation_performed": False,
            "self_healing_performed": True,
            "automatic_remediation_performed": True,
        }

        self.result_validator.validate(payload)

    def test_unverified_recovery_is_rejected(self):
        payload = {
            "schema_version": "1.0.0",
            "condition": "C2",
            "scenario_id": "quality_regression",
            "run_key": "test_c2_recovery",
            "source_remediation_plan_sha256": "b" * 64,
            "mode": "automatic",
            "action": "rollback",
            "attempt_count": 1,
            "execution_status": "SUCCEEDED",
            "verification": {
                "required": True,
                "status": "FAIL",
                "evidence_sha256": "c" * 64,
            },
            "terminal_state": "RECOVERED",
            "fault_detected_at_utc": "2026-08-19T18:00:00Z",
            "remediation_started_at_utc": "2026-08-19T18:00:01Z",
            "remediation_completed_at_utc": "2026-08-19T18:00:02Z",
            "action_duration_ms": 1000,
            "recovery_time_ms": 2000,
            "promotion_recheck_required": True,
            "canonical_mutation_performed": False,
            "self_healing_performed": True,
            "automatic_remediation_performed": True,
        }

        self.assertTrue(
            list(
                self.result_validator.iter_errors(
                    payload
                )
            )
        )

    def test_result_rejects_canonical_mutation(self):
        payload = {
            "schema_version": "1.0.0",
            "condition": "C2",
            "scenario_id": "schema_break",
            "run_key": "test_c2_recovery",
            "source_remediation_plan_sha256": "b" * 64,
            "mode": "automatic",
            "action": "rollback",
            "attempt_count": 1,
            "execution_status": "FAILED",
            "verification": {
                "required": True,
                "status": "FAIL",
                "evidence_sha256": "c" * 64,
            },
            "terminal_state": "FAILED_SAFE",
            "fault_detected_at_utc": "2026-08-19T18:00:00Z",
            "remediation_started_at_utc": "2026-08-19T18:00:01Z",
            "remediation_completed_at_utc": "2026-08-19T18:00:02Z",
            "action_duration_ms": 1000,
            "recovery_time_ms": 2000,
            "promotion_recheck_required": True,
            "canonical_mutation_performed": True,
            "self_healing_performed": False,
            "automatic_remediation_performed": True,
        }

        self.assertTrue(
            list(
                self.result_validator.iter_errors(
                    payload
                )
            )
        )


if __name__ == "__main__":
    unittest.main()

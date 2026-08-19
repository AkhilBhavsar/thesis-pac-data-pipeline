import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from scripts.policy.build_c2_remediation_plan import (
    PlannerError,
    build_remediation_plan,
    validate_catalog,
    validate_schema_document,
    validate_source_decision,
)


ROOT = Path(__file__).resolve().parents[2]

CATALOG_PATH = (
    ROOT
    / "policies/catalog/c2-remediation-catalog.json"
)

PLAN_SCHEMA_PATH = (
    ROOT
    / "policies/contracts/c2-remediation-plan.schema.json"
)


TRIGGERS = {
    "schema_break": [
        "PAC-SCHEMA-001",
        "PAC-RELEASE-001",
    ],
    "pii_exposure": [
        "PAC-PRIVACY-001",
        "PAC-SCHEMA-001",
        "PAC-RELEASE-001",
    ],
    "freshness_breach": [
        "PAC-FRESH-001",
        "PAC-RELEASE-001",
    ],
    "quality_regression": [
        "PAC-QUALITY-001",
        "PAC-RELEASE-001",
    ],
    "policy_false_positive": [
        "PAC-SCHEMA-001",
        "PAC-RELEASE-001",
    ],
}


class C2RemediationPlannerTest(
    unittest.TestCase
):

    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads(
            CATALOG_PATH.read_text(
                encoding="utf-8"
            )
        )

        cls.schema = json.loads(
            PLAN_SCHEMA_PATH.read_text(
                encoding="utf-8"
            )
        )

        Draft202012Validator.check_schema(
            cls.schema
        )

    def make_decision(
        self,
        scenario_id,
    ):
        scenario = self.catalog[
            "scenarios"
        ][
            scenario_id
        ]

        return {
            "schema_version": "1.0.0",
            "condition": "C2",
            "recorded_at_utc": (
                "2026-08-19T18:00:00Z"
            ),
            "run_key": (
                "c2-planner-test-"
                + scenario_id
            ),
            "scenario_id": scenario_id,
            "evaluation_stage": scenario[
                "detection_stage"
            ],
            "promotion_requested": True,
            "decision": "DENY",
            "allow": False,
            "triggered_policy_ids": (
                TRIGGERS[
                    scenario_id
                ]
            ),
            "measurement": {
                "promotion_requested": True,
                "promotion_blocked": True,
            },
        }

    def build(
        self,
        scenario_id,
    ):
        payload = (
            build_remediation_plan(
                decision=self.make_decision(
                    scenario_id
                ),
                catalog=self.catalog,
                decision_sha256="a" * 64,
            )
        )

        validate_schema_document(
            self.schema,
            payload,
        )

        return payload

    def test_catalog_is_valid_for_planner(
        self,
    ):
        validate_catalog(
            self.catalog
        )

    def test_all_five_scenarios_build_valid_plans(
        self,
    ):
        for scenario_id in sorted(
            self.catalog[
                "scenarios"
            ]
        ):
            with self.subTest(
                scenario_id=scenario_id
            ):
                payload = self.build(
                    scenario_id
                )

                scenario = self.catalog[
                    "scenarios"
                ][
                    scenario_id
                ]

                self.assertEqual(
                    payload[
                        "plan"
                    ][
                        "primary_action"
                    ],
                    scenario[
                        "primary_action"
                    ],
                )

                self.assertEqual(
                    payload[
                        "plan"
                    ][
                        "fallback_action"
                    ],
                    scenario[
                        "fallback_action"
                    ],
                )

                self.assertEqual(
                    payload[
                        "plan"
                    ][
                        "max_attempts"
                    ],
                    scenario[
                        "max_attempts"
                    ],
                )

                self.assertEqual(
                    payload[
                        "plan"
                    ][
                        "timeout_seconds"
                    ],
                    scenario[
                        "timeout_seconds"
                    ],
                )

                self.assertEqual(
                    payload[
                        "plan"
                    ][
                        "verification"
                    ],
                    scenario[
                        "verification"
                    ],
                )

    def test_source_projection_is_minimal(
        self,
    ):
        payload = self.build(
            "freshness_breach"
        )

        self.assertEqual(
            set(
                payload[
                    "source_policy_decision"
                ]
            ),
            {
                "evaluation_stage",
                "decision",
                "triggered_policy_ids",
                "promotion_blocked",
            },
        )

    def test_fault_detection_timestamp_is_preserved(
        self,
    ):
        payload = self.build(
            "freshness_breach"
        )

        self.assertEqual(
            payload[
                "fault_detected_at_utc"
            ],
            "2026-08-19T18:00:00Z",
        )

    def test_rejects_missing_detection_timestamp(
        self,
    ):
        decision = self.make_decision(
            "freshness_breach"
        )

        decision.pop(
            "recorded_at_utc"
        )

        with self.assertRaises(
            PlannerError
        ):
            validate_source_decision(
                decision,
                self.catalog,
            )

    def test_source_sha_is_preserved(
        self,
    ):
        payload = self.build(
            "quality_regression"
        )

        self.assertEqual(
            payload[
                "source_policy_decision_sha256"
            ],
            "a" * 64,
        )

    def test_false_positive_is_manual_only(
        self,
    ):
        payload = self.build(
            "policy_false_positive"
        )

        self.assertEqual(
            payload[
                "plan"
            ][
                "mode"
            ],
            "manual",
        )

        self.assertEqual(
            payload[
                "plan"
            ][
                "primary_action"
            ],
            "manual_review",
        )

        self.assertEqual(
            payload[
                "plan"
            ][
                "max_attempts"
            ],
            0,
        )

        self.assertEqual(
            payload[
                "plan"
            ][
                "timeout_seconds"
            ],
            0,
        )

        self.assertFalse(
            payload[
                "controls"
            ][
                "automatic_remediation_permitted"
            ]
        )

    def test_automatic_scenarios_enable_self_healing(
        self,
    ):
        automatic = {
            "schema_break",
            "pii_exposure",
            "freshness_breach",
            "quality_regression",
        }

        for scenario_id in automatic:
            payload = self.build(
                scenario_id
            )

            self.assertEqual(
                payload[
                    "plan"
                ][
                    "mode"
                ],
                "automatic",
            )

            self.assertTrue(
                payload[
                    "controls"
                ][
                    "self_healing_permitted"
                ]
            )

            self.assertTrue(
                payload[
                    "controls"
                ][
                    "automatic_remediation_permitted"
                ]
            )

    def test_rejects_c1_decision(
        self,
    ):
        decision = self.make_decision(
            "freshness_breach"
        )

        decision[
            "condition"
        ] = "C1"

        with self.assertRaises(
            PlannerError
        ):
            validate_source_decision(
                decision,
                self.catalog,
            )

    def test_rejects_allow_decision(
        self,
    ):
        decision = self.make_decision(
            "freshness_breach"
        )

        decision[
            "decision"
        ] = "ALLOW"

        decision[
            "allow"
        ] = True

        with self.assertRaises(
            PlannerError
        ):
            validate_source_decision(
                decision,
                self.catalog,
            )

    def test_rejects_unblocked_promotion(
        self,
    ):
        decision = self.make_decision(
            "quality_regression"
        )

        decision[
            "measurement"
        ][
            "promotion_blocked"
        ] = False

        with self.assertRaises(
            PlannerError
        ):
            validate_source_decision(
                decision,
                self.catalog,
            )

    def test_rejects_stage_mismatch(
        self,
    ):
        decision = self.make_decision(
            "schema_break"
        )

        decision[
            "evaluation_stage"
        ] = "post"

        with self.assertRaises(
            PlannerError
        ):
            validate_source_decision(
                decision,
                self.catalog,
            )

    def test_rejects_duplicate_policy_ids(
        self,
    ):
        decision = self.make_decision(
            "freshness_breach"
        )

        decision[
            "triggered_policy_ids"
        ] = [
            "PAC-FRESH-001",
            "PAC-FRESH-001",
        ]

        with self.assertRaises(
            PlannerError
        ):
            validate_source_decision(
                decision,
                self.catalog,
            )

    def test_rejects_catalog_attempt_bound_violation(
        self,
    ):
        catalog = copy.deepcopy(
            self.catalog
        )

        catalog[
            "scenarios"
        ][
            "freshness_breach"
        ][
            "max_attempts"
        ] = 3

        with self.assertRaises(
            PlannerError
        ):
            validate_catalog(
                catalog
            )

    def test_rejects_catalog_timeout_bound_violation(
        self,
    ):
        catalog = copy.deepcopy(
            self.catalog
        )

        catalog[
            "scenarios"
        ][
            "freshness_breach"
        ][
            "timeout_seconds"
        ] = 301

        with self.assertRaises(
            PlannerError
        ):
            validate_catalog(
                catalog
            )

    def test_canonical_mutation_is_always_forbidden(
        self,
    ):
        for scenario_id in sorted(
            self.catalog[
                "scenarios"
            ]
        ):
            payload = self.build(
                scenario_id
            )

            self.assertFalse(
                payload[
                    "plan"
                ][
                    "canonical_mutation_before_verification"
                ]
            )


if __name__ == "__main__":
    unittest.main()

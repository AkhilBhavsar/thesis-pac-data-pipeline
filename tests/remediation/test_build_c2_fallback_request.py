from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from scripts.remediation.build_c2_fallback_request import (
    EXPECTED_DATA_BUCKET,
    FallbackRequestError,
    build_fallback_request,
    canonical_bytes,
)


ROOT = Path(__file__).resolve().parents[2]

CATALOG = (
    ROOT
    / "policies"
    / "catalog"
    / "c2-remediation-catalog.json"
)

SCHEMA = (
    ROOT
    / "policies"
    / "contracts"
    / "c2-fallback-request-input.schema.json"
)


def sha256(
    path: Path,
) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


class TestBuildC2FallbackRequest(
    unittest.TestCase
):
    def setUp(
        self,
    ):
        self.temp = tempfile.TemporaryDirectory()

        self.root = Path(
            self.temp.name
        )

        self.validator = Draft202012Validator(
            json.loads(
                SCHEMA.read_text(
                    encoding="utf-8"
                )
            )
        )

    def tearDown(
        self,
    ):
        self.temp.cleanup()

    def scenario_contract(
        self,
        scenario: str,
    ):
        catalog = json.loads(
            CATALOG.read_text(
                encoding="utf-8"
            )
        )

        return catalog[
            "scenarios"
        ][
            scenario
        ]

    def write(
        self,
        name: str,
        payload: dict,
    ) -> Path:
        path = (
            self.root
            / name
        )

        path.write_bytes(
            canonical_bytes(
                payload
            )
        )

        return path

    def fixtures(
        self,
        *,
        scenario: str,
        attempt_count: int | None = None,
        recommended_fallback: str | None = None,
        policy_id: str | None = None,
        verified_result_emitted: bool = False,
        verification_status: str = "FAIL",
    ):
        contract = self.scenario_contract(
            scenario
        )

        run_key = (
            f"c2-test-{scenario}"
        )

        automatic = contract[
            "automatic_remediation_permitted"
        ]

        if attempt_count is None:
            attempt_count = (
                1
                if automatic
                else 0
            )

        plan = {
            "schema_version": "1.0.0",
            "condition": "C2",
            "scenario_id": scenario,
            "run_key": run_key,
            "fault_detected_at_utc":
                "2026-08-21T11:00:00Z",

            "plan": {
                "mode": (
                    "automatic"
                    if automatic
                    else "manual"
                ),

                "primary_action":
                    contract[
                        "primary_action"
                    ],

                "fallback_action":
                    contract[
                        "fallback_action"
                    ],

                "max_attempts":
                    contract[
                        "max_attempts"
                    ],
            },
        }

        plan_path = self.write(
            "plan.json",
            plan,
        )

        result = {
            "schema_version": "1.0.0",
            "condition": "C2",
            "scenario_id": scenario,
            "run_key": run_key,
            "source_remediation_plan_sha256":
                sha256(
                    plan_path
                ),

            "mode": (
                "automatic"
                if automatic
                else "manual"
            ),

            "action":
                contract[
                    "primary_action"
                ],

            "attempt_count":
                attempt_count,

            "automatic_remediation_performed":
                automatic,

            "terminal_state": (
                "PENDING_VERIFICATION"
                if automatic
                else "MANUAL_REVIEW"
            ),
        }

        result_path = self.write(
            "result.json",
            result,
        )

        if policy_id is None:
            policy_id = {
                "pii_exposure":
                    "PAC-PRIVACY-001",

                "freshness_breach":
                    "PAC-FRESH-001",

                "quality_regression":
                    "PAC-QUALITY-001",

                "schema_break":
                    "PAC-SCHEMA-001",

                "policy_false_positive":
                    "PAC-SCHEMA-001",
            }[
                scenario
            ]

        fallback = (
            recommended_fallback
            if recommended_fallback is not None
            else contract[
                "fallback_action"
            ]
        )

        verification = {
            "schema_version": "1.0.0",
            "condition": "C2",
            "scenario_id": scenario,
            "run_key": run_key,
            "source_remediation_plan_sha256":
                sha256(
                    plan_path
                ),

            "source_remediation_result_sha256":
                sha256(
                    result_path
                ),

            "verification_status":
                verification_status,

            "promotion_blocked":
                True,

            "recommended_fallback_action":
                fallback,

            "verified_result_emitted":
                verified_result_emitted,

            "triggered_policy_ids": [
                policy_id,
                "PAC-RELEASE-001",
            ],

            "violations": [
                {
                    "policy_id":
                        policy_id,

                    "message":
                        (
                            f"Synthetic {scenario} "
                            "verification violation."
                        ),
                },
                {
                    "policy_id":
                        "PAC-RELEASE-001",

                    "message":
                        "Promotion remains blocked.",
                },
            ],
        }

        verification_path = self.write(
            "verification.json",
            verification,
        )

        return (
            plan_path,
            result_path,
            verification_path,
        )

    def context(
        self,
        scenario: str,
    ):
        return {
            "data_classification":
                "synthetic",

            "evidence_uri":
                (
                    "s3://thesis-pac-dev-data-lake-"
                    "522814714524-eu-west-1/"
                    f"evidence/c2/test/{scenario}/"
                ),

            "source_bucket":
                EXPECTED_DATA_BUCKET,

            "source_dataset":
                f"synthetic_{scenario}",

            "source_key":
                (
                    "experiments/c2/"
                    f"test/{scenario}.json"
                ),

            "source_relation":
                f"c2_test_{scenario}",
        }

    def build(
        self,
        *,
        scenario: str,
        attempt_count: int | None = None,
        recommended_fallback: str | None = None,
        policy_id: str | None = None,
        verified_result_emitted: bool = False,
        verification_status: str = "FAIL",
        context: dict | None = None,
    ):
        (
            plan_path,
            result_path,
            verification_path,
        ) = self.fixtures(
            scenario=scenario,
            attempt_count=attempt_count,
            recommended_fallback=(
                recommended_fallback
            ),
            policy_id=policy_id,
            verified_result_emitted=(
                verified_result_emitted
            ),
            verification_status=(
                verification_status
            ),
        )

        return build_fallback_request(
            plan_path=plan_path,
            result_path=result_path,
            verification_path=verification_path,
            catalog_path=CATALOG,
            schema_path=SCHEMA,
            context=(
                self.context(
                    scenario
                )
                if context is None
                and scenario in {
                    "pii_exposure",
                    "freshness_breach",
                    "quality_regression",
                }
                else context
            ),
        )

    def test_quality_regression_builds_quarantine_request(
        self,
    ):
        payload = self.build(
            scenario="quality_regression",
        )

        self.validator.validate(
            payload
        )

        request = payload[
            "quarantine_request"
        ]

        self.assertEqual(
            payload[
                "fallback_action"
            ],
            "quarantine",
        )

        self.assertEqual(
            len(
                request
            ),
            13,
        )

        self.assertEqual(
            request[
                "policy_id"
            ],
            "PAC-QUALITY-001",
        )

        self.assertEqual(
            request[
                "policy_category"
            ],
            "quality",
        )

        self.assertEqual(
            request[
                "max_retries"
            ],
            1,
        )

        self.assertEqual(
            request[
                "retry_count"
            ],
            1,
        )

    def test_pii_exposure_builds_privacy_quarantine(
        self,
    ):
        payload = self.build(
            scenario="pii_exposure",
        )

        request = payload[
            "quarantine_request"
        ]

        self.assertEqual(
            request[
                "policy_id"
            ],
            "PAC-PRIVACY-001",
        )

        self.assertEqual(
            request[
                "policy_category"
            ],
            "privacy",
        )

    def test_freshness_second_attempt_is_preserved(
        self,
    ):
        payload = self.build(
            scenario="freshness_breach",
            attempt_count=2,
        )

        request = payload[
            "quarantine_request"
        ]

        self.assertEqual(
            request[
                "max_retries"
            ],
            2,
        )

        self.assertEqual(
            request[
                "retry_count"
            ],
            2,
        )

        self.assertEqual(
            request[
                "policy_id"
            ],
            "PAC-FRESH-001",
        )

    def test_schema_break_has_no_quarantine_request(
        self,
    ):
        payload = self.build(
            scenario="schema_break",
        )

        self.validator.validate(
            payload
        )

        self.assertEqual(
            payload[
                "fallback_action"
            ],
            "manual_review",
        )

        self.assertNotIn(
            "quarantine_request",
            payload,
        )

    def test_false_positive_has_no_quarantine_request(
        self,
    ):
        payload = self.build(
            scenario="policy_false_positive",
            verification_status=(
                "MANUAL_REQUIRED"
            ),
        )

        self.validator.validate(
            payload
        )

        self.assertEqual(
            payload[
                "fallback_action"
            ],
            "stop_promotion",
        )

        self.assertNotIn(
            "quarantine_request",
            payload,
        )

    def test_rejects_retry_count_above_plan_budget(
        self,
    ):
        with self.assertRaises(
            FallbackRequestError
        ):
            self.build(
                scenario="quality_regression",
                attempt_count=2,
            )

    def test_rejects_zero_attempt_quarantine_workflow_path(
        self,
    ):
        with self.assertRaises(
            FallbackRequestError
        ):
            self.build(
                scenario="quality_regression",
                attempt_count=0,
            )

    def test_rejects_verifier_fallback_drift(
        self,
    ):
        with self.assertRaises(
            FallbackRequestError
        ):
            self.build(
                scenario="quality_regression",
                recommended_fallback=(
                    "manual_review"
                ),
            )

    def test_rejects_already_verified_recovery(
        self,
    ):
        with self.assertRaises(
            FallbackRequestError
        ):
            self.build(
                scenario="quality_regression",
                verified_result_emitted=True,
            )

        with self.assertRaises(
            FallbackRequestError
        ):
            self.build(
                scenario="quality_regression",
                verification_status="PASS",
            )

    def test_rejects_missing_primary_policy_violation(
        self,
    ):
        with self.assertRaises(
            FallbackRequestError
        ):
            self.build(
                scenario="quality_regression",
                policy_id="PAC-RELEASE-001",
            )

    def test_rejects_source_outside_c2_experiment_boundary(
        self,
    ):
        context = self.context(
            "quality_regression"
        )

        context[
            "source_key"
        ] = (
            "gold/canonical-output.parquet"
        )

        with self.assertRaises(
            FallbackRequestError
        ):
            self.build(
                scenario="quality_regression",
                context=context,
            )

    def test_rejects_wrong_source_bucket(
        self,
    ):
        context = self.context(
            "quality_regression"
        )

        context[
            "source_bucket"
        ] = "other-bucket"

        with self.assertRaises(
            FallbackRequestError
        ):
            self.build(
                scenario="quality_regression",
                context=context,
            )

    def test_output_is_deterministic(
        self,
    ):
        first = self.build(
            scenario="quality_regression",
        )

        second = self.build(
            scenario="quality_regression",
        )

        self.assertEqual(
            canonical_bytes(
                first
            ),
            canonical_bytes(
                second
            ),
        )

    def test_inputs_are_not_mutated(
        self,
    ):
        (
            plan_path,
            result_path,
            verification_path,
        ) = self.fixtures(
            scenario="quality_regression",
        )

        before = {
            "plan":
                plan_path.read_bytes(),

            "result":
                result_path.read_bytes(),

            "verification":
                verification_path.read_bytes(),

            "catalog":
                CATALOG.read_bytes(),
        }

        build_fallback_request(
            plan_path=plan_path,
            result_path=result_path,
            verification_path=verification_path,
            catalog_path=CATALOG,
            schema_path=SCHEMA,
            context=self.context(
                "quality_regression"
            ),
        )

        self.assertEqual(
            plan_path.read_bytes(),
            before[
                "plan"
            ],
        )

        self.assertEqual(
            result_path.read_bytes(),
            before[
                "result"
            ],
        )

        self.assertEqual(
            verification_path.read_bytes(),
            before[
                "verification"
            ],
        )

        self.assertEqual(
            CATALOG.read_bytes(),
            before[
                "catalog"
            ],
        )

    def test_rejects_result_plan_hash_mismatch(
        self,
    ):
        (
            plan_path,
            result_path,
            verification_path,
        ) = self.fixtures(
            scenario="quality_regression",
        )

        result = json.loads(
            result_path.read_text(
                encoding="utf-8"
            )
        )

        result[
            "source_remediation_plan_sha256"
        ] = "0" * 64

        result_path.write_bytes(
            canonical_bytes(
                result
            )
        )

        verification = json.loads(
            verification_path.read_text(
                encoding="utf-8"
            )
        )

        verification[
            "source_remediation_result_sha256"
        ] = sha256(
            result_path
        )

        verification_path.write_bytes(
            canonical_bytes(
                verification
            )
        )

        with self.assertRaises(
            FallbackRequestError
        ):
            build_fallback_request(
                plan_path=plan_path,
                result_path=result_path,
                verification_path=verification_path,
                catalog_path=CATALOG,
                schema_path=SCHEMA,
                context=self.context(
                    "quality_regression"
                ),
            )


if __name__ == "__main__":
    unittest.main()

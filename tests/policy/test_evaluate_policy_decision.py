#!/usr/bin/env python3

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import (
    Draft202012Validator,
    FormatChecker,
)


class UnifiedPolicyDecisionTest(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = (
            Path(__file__)
            .resolve()
            .parents[2]
        )

        cls.script = (
            cls.repo_root
            / "scripts/policy/evaluate_policy_decision.py"
        )

        cls.fixture = (
            cls.repo_root
            / "policies/fixtures/c1-safe-baseline.json"
        )

        cls.decision_schema = json.loads(
            (
                cls.repo_root
                / "policies/contracts/policy-decision.schema.json"
            ).read_text(
                encoding="utf-8"
            )
        )

        opa = os.environ.get(
            "OPA_BIN"
        )

        if not opa:
            raise RuntimeError(
                "OPA_BIN is required"
            )

        cls.opa_bin = Path(opa)

        cls.base = json.loads(
            cls.fixture.read_text(
                encoding="utf-8"
            )
        )

    def run_evaluator(
        self,
        payload: dict,
    ) -> tuple[
        subprocess.CompletedProcess[str],
        dict | None,
    ]:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            input_path = (
                root / "input.json"
            )

            output_path = (
                root / "decision.json"
            )

            input_path.write_text(
                json.dumps(
                    payload,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            process = subprocess.run(
                [
                    sys.executable,
                    str(self.script),
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                    "--opa-bin",
                    str(self.opa_bin),
                ],
                capture_output=True,
                text=True,
                check=False,
                cwd=self.repo_root,
            )

            decision = None

            if output_path.exists():
                decision = json.loads(
                    output_path.read_text(
                        encoding="utf-8"
                    )
                )

            return (
                process,
                decision,
            )

    def validate_decision(
        self,
        decision: dict,
    ) -> None:
        validator = (
            Draft202012Validator(
                self.decision_schema,
                format_checker=FormatChecker(),
            )
        )

        errors = list(
            validator.iter_errors(
                decision
            )
        )

        self.assertEqual(
            errors,
            [],
        )

    def test_safe_baseline_allows(
        self,
    ) -> None:
        payload = copy.deepcopy(
            self.base
        )

        payload[
            "experiment"
        ][
            "run_key"
        ] = "unit-safe"

        process, decision = (
            self.run_evaluator(
                payload
            )
        )

        self.assertEqual(
            process.returncode,
            0,
            process.stderr,
        )

        self.assertIsNotNone(
            decision
        )

        self.validate_decision(
            decision
        )

        self.assertEqual(
            decision["decision"],
            "ALLOW",
        )

        self.assertEqual(
            decision[
                "violation_count"
            ],
            0,
        )

        self.assertEqual(
            decision[
                "triggered_policy_ids"
            ],
            [],
        )

        self.assertEqual(
            len(
                decision[
                    "implemented_policy_ids"
                ]
            ),
            7,
        )

        self.assertEqual(
            decision[
                "unimplemented_policy_ids"
            ],
            [
                "PAC-RUNTIME-001"
            ],
        )

    def test_pre_transform_deny(
        self,
    ) -> None:
        payload = copy.deepcopy(
            self.base
        )

        payload[
            "evaluation_stage"
        ] = "pre"

        payload[
            "experiment"
        ][
            "scenario_id"
        ] = "quality_regression"

        payload[
            "experiment"
        ][
            "run_key"
        ] = "unit-transform-deny"

        payload[
            "release"
        ][
            "promotion_requested"
        ] = True

        payload[
            "transformation"
        ][
            "changed_models"
        ] = [
            "gold_daily_sales"
        ]

        payload[
            "transformation"
        ][
            "unapproved_definitions"
        ] = [
            "gold_daily_sales"
        ]

        process, decision = (
            self.run_evaluator(
                payload
            )
        )

        self.assertEqual(
            process.returncode,
            2,
            process.stderr,
        )

        self.assertIsNotNone(
            decision
        )

        self.validate_decision(
            decision
        )

        self.assertEqual(
            decision["decision"],
            "DENY",
        )

        self.assertEqual(
            decision[
                "triggered_policy_ids"
            ],
            [
                "PAC-RELEASE-001",
                "PAC-TRANSFORM-001",
            ],
        )

        self.assertTrue(
            decision[
                "measurement"
            ][
                "promotion_blocked"
            ]
        )

    def test_post_quality_deny(
        self,
    ) -> None:
        payload = copy.deepcopy(
            self.base
        )

        payload[
            "evaluation_stage"
        ] = "post"

        payload[
            "experiment"
        ][
            "scenario_id"
        ] = "quality_regression"

        payload[
            "experiment"
        ][
            "run_key"
        ] = "unit-quality-deny"

        payload[
            "release"
        ][
            "promotion_requested"
        ] = True

        payload[
            "quality"
        ] = {
            "status": "FAIL",
            "total_tests": 1,
            "failed_tests": 1,
            "critical_failures": [
                "gold_daily_sales:not_null_revenue"
            ],
        }

        payload[
            "freshness"
        ] = {
            "status": "PASS",
            "sources": [],
        }

        process, decision = (
            self.run_evaluator(
                payload
            )
        )

        self.assertEqual(
            process.returncode,
            2,
            process.stderr,
        )

        self.assertIsNotNone(
            decision
        )

        self.validate_decision(
            decision
        )

        self.assertEqual(
            decision[
                "triggered_policy_ids"
            ],
            [
                "PAC-QUALITY-001",
                "PAC-RELEASE-001",
            ],
        )

        outcomes = {
            item["policy_id"]:
            item["outcome"]
            for item in decision[
                "policy_outcomes"
            ]
        }

        self.assertEqual(
            outcomes[
                "PAC-QUALITY-001"
            ],
            "DENY",
        )

        self.assertEqual(
            outcomes[
                "PAC-TRANSFORM-001"
            ],
            "NOT_APPLICABLE",
        )

    def test_invalid_c1_controls_fail(
        self,
    ) -> None:
        payload = copy.deepcopy(
            self.base
        )

        payload[
            "controls"
        ][
            "self_healing_permitted"
        ] = True

        process, decision = (
            self.run_evaluator(
                payload
            )
        )

        self.assertEqual(
            process.returncode,
            1,
        )

        self.assertIsNone(
            decision
        )

        self.assertIn(
            "Policy input validation failed",
            process.stderr,
        )


if __name__ == "__main__":
    unittest.main()

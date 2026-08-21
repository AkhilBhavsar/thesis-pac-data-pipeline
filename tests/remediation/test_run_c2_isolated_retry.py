import copy
import unittest

from scripts.remediation.run_c2_isolated_retry import (
    EXPECTED_BRANCH,
    RetryAdapterError,
    self_test,
    validate_environment,
    validate_invocation,
)


class C2IsolatedRetryAdapterTest(
    unittest.TestCase
):

    def environment(self):
        return {
            "THESIS_GIT_BRANCH": (
                EXPECTED_BRANCH
            ),
            "THESIS_GIT_COMMIT": (
                "a" * 40
            ),
            "THESIS_EXPERIMENT_CONDITION": (
                "C2"
            ),
            "THESIS_SCENARIO_ID": (
                "freshness_breach"
            ),
            "C2_RUN_KEY": (
                "c2-retry-test"
            ),
            "AWS_ACCOUNT_ID": (
                "522814714524"
            ),
            "DATA_LAKE_BUCKET": (
                "data-bucket"
            ),
            "ATHENA_RESULTS_BUCKET": (
                "results-bucket"
            ),
            "DBT_ATHENA_WORKGROUP": (
                "workgroup"
            ),
            "DBT_ATHENA_DATA_DIR": (
                "s3://data-bucket/"
                "experiments/c2/run/data/"
            ),
            "DBT_ATHENA_STAGING_DIR": (
                "s3://results-bucket/"
                "experiments/c2/run/results/"
            ),
            "DBT_ATHENA_SCHEMA": (
                "thesis_pac_c2_run_silver"
            ),
            "DBT_GOLD_INTERNAL_SCHEMA": (
                "thesis_pac_c2_run_internal"
            ),
            "DBT_GOLD_PUBLIC_SCHEMA": (
                "thesis_pac_c2_run_public"
            ),
        }

    def plan(self):
        return {
            "condition": "C2",
            "scenario_id": (
                "freshness_breach"
            ),
            "run_key": (
                "c2-retry-test"
            ),
            "plan": {
                "mode": "automatic",
                "primary_action": "retry",
                "max_attempts": 2,
            },
        }

    def context(self):
        return {
            "condition": "C2",
            "scenario_id": (
                "freshness_breach"
            ),
            "run_key": (
                "c2-retry-test"
            ),
            "workspace": {
                "root": "/tmp/c2-retry",
                "isolated": True,
                "canonical_access_permitted": False,
            },
            "action_context": {
                "action": "retry",
                "runner_profile": (
                    "c2_isolated_pipeline"
                ),
            },
        }

    def test_valid_c2_environment(self):
        config = validate_environment(
            self.environment()
        )

        self.assertEqual(
            config[
                "condition"
            ],
            "C2",
        )

    def test_rejects_c1_condition(self):
        environment = (
            self.environment()
        )

        environment[
            "THESIS_EXPERIMENT_CONDITION"
        ] = "C1"

        with self.assertRaises(
            RetryAdapterError
        ):
            validate_environment(
                environment
            )

    def test_rejects_c1_schema_prefix(self):
        environment = (
            self.environment()
        )

        environment[
            "DBT_ATHENA_SCHEMA"
        ] = "thesis_pac_c1_bad"

        with self.assertRaises(
            RetryAdapterError
        ):
            validate_environment(
                environment
            )

    def test_rejects_c1_s3_boundary(self):
        environment = (
            self.environment()
        )

        environment[
            "DBT_ATHENA_DATA_DIR"
        ] = (
            "s3://data-bucket/"
            "experiments/c1/run/data/"
        )

        with self.assertRaises(
            RetryAdapterError
        ):
            validate_environment(
                environment
            )

    def test_attempt_one_valid(self):
        validate_invocation(
            plan=self.plan(),
            context=self.context(),
            attempt_number=1,
        )

    def test_attempt_two_valid(self):
        validate_invocation(
            plan=self.plan(),
            context=self.context(),
            attempt_number=2,
        )

    def test_attempt_three_rejected(self):
        with self.assertRaises(
            RetryAdapterError
        ):
            validate_invocation(
                plan=self.plan(),
                context=self.context(),
                attempt_number=3,
            )

    def test_manual_mode_rejected(self):
        plan = copy.deepcopy(
            self.plan()
        )

        plan[
            "plan"
        ][
            "mode"
        ] = "manual"

        with self.assertRaises(
            RetryAdapterError
        ):
            validate_invocation(
                plan=plan,
                context=self.context(),
                attempt_number=1,
            )

    def test_self_test_has_no_aws_calls(self):
        result = self_test()

        self.assertEqual(
            result[
                "status"
            ],
            "PASS",
        )

        self.assertFalse(
            result[
                "aws_calls"
            ]
        )

        self.assertFalse(
            result[
                "dagster_execution"
            ]
        )


if __name__ == "__main__":
    unittest.main()

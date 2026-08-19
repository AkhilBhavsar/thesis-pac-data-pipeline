import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]

SCHEMA_PATH = (
    ROOT
    / "policies/contracts/"
    "c2-remediation-execution-context.schema.json"
)


class C2RemediationExecutionContextTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(
            SCHEMA_PATH.read_text(
                encoding="utf-8"
            )
        )

        Draft202012Validator.check_schema(
            cls.schema
        )

        cls.validator = Draft202012Validator(
            cls.schema
        )

    def base(self, action_context):
        return {
            "schema_version": "1.0.0",
            "condition": "C2",
            "scenario_id": "schema_break",
            "run_key": "c2-context-test",
            "remediation_plan_sha256": "a" * 64,
            "workspace": {
                "root": "experiments/c2/workspace",
                "isolated": True,
                "canonical_access_permitted": False,
            },
            "action_context": action_context,
        }

    def assert_valid(self, payload):
        self.validator.validate(payload)

    def assert_invalid(self, payload):
        self.assertTrue(
            list(
                self.validator.iter_errors(
                    payload
                )
            )
        )

    def test_valid_rollback_context(self):
        self.assert_valid(
            self.base(
                {
                    "action": "rollback",
                    "target_relative_path": (
                        "candidate/schema.sql"
                    ),
                    "verified_source_relative_path": (
                        "verified/schema.sql"
                    ),
                }
            )
        )

    def test_valid_redact_republish_context(self):
        payload = self.base(
            {
                "action": "redact_republish",
                "candidate_relative_path": (
                    "public/candidate.sql"
                ),
                "sanitized_source_relative_path": (
                    "verified/public.sql"
                ),
            }
        )

        payload["scenario_id"] = "pii_exposure"

        self.assert_valid(payload)

    def test_valid_retry_context(self):
        payload = self.base(
            {
                "action": "retry",
                "runner_profile": (
                    "c2_isolated_pipeline"
                ),
            }
        )

        payload["scenario_id"] = (
            "freshness_breach"
        )

        self.assert_valid(payload)

    def test_valid_quarantine_context(self):
        payload = self.base(
            {
                "action": "quarantine",
                "rejected_output_relative_path": (
                    "output/rejected.parquet"
                ),
                "quarantine_relative_path": (
                    "quarantine/rejected.parquet"
                ),
            }
        )

        self.assert_valid(payload)

    def test_valid_manual_review_context(self):
        payload = self.base(
            {
                "action": "manual_review",
                "reason": (
                    "Controlled safe-change review."
                ),
            }
        )

        payload["scenario_id"] = (
            "policy_false_positive"
        )

        self.assert_valid(payload)

    def test_rejects_c1_context(self):
        payload = self.base(
            {
                "action": "manual_review",
                "reason": "review",
            }
        )

        payload["condition"] = "C1"

        self.assert_invalid(payload)

    def test_requires_isolated_workspace(self):
        payload = self.base(
            {
                "action": "rollback",
                "target_relative_path": "candidate/a",
                "verified_source_relative_path": "verified/a",
            }
        )

        payload[
            "workspace"
        ][
            "isolated"
        ] = False

        self.assert_invalid(payload)

    def test_forbids_canonical_access(self):
        payload = self.base(
            {
                "action": "rollback",
                "target_relative_path": "candidate/a",
                "verified_source_relative_path": "verified/a",
            }
        )

        payload[
            "workspace"
        ][
            "canonical_access_permitted"
        ] = True

        self.assert_invalid(payload)

    def test_rejects_absolute_target_path(self):
        payload = self.base(
            {
                "action": "rollback",
                "target_relative_path": "/tmp/unsafe",
                "verified_source_relative_path": "verified/a",
            }
        )

        self.assert_invalid(payload)

    def test_rejects_parent_traversal(self):
        payload = self.base(
            {
                "action": "rollback",
                "target_relative_path": "../unsafe",
                "verified_source_relative_path": "verified/a",
            }
        )

        self.assert_invalid(payload)

    def test_retry_runner_is_allowlisted(self):
        payload = self.base(
            {
                "action": "retry",
                "runner_profile": "arbitrary_shell",
            }
        )

        payload["scenario_id"] = (
            "freshness_breach"
        )

        self.assert_invalid(payload)


if __name__ == "__main__":
    unittest.main()

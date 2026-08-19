import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from scripts.remediation.execute_c2_remediation import (
    ExecutorError,
    execute_plan,
    safe_workspace_path,
)


ROOT = Path(__file__).resolve().parents[2]

RESULT_SCHEMA_PATH = (
    ROOT
    / "policies/contracts/"
    "c2-remediation-result.schema.json"
)


def digest(path):
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


class C2RemediationExecutorTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.result_schema = json.loads(
            RESULT_SCHEMA_PATH.read_text(
                encoding="utf-8"
            )
        )

        Draft202012Validator.check_schema(
            cls.result_schema
        )

        cls.validator = Draft202012Validator(
            cls.result_schema
        )

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()

        self.workspace = Path(
            self.temp.name
        )

    def tearDown(self):
        self.temp.cleanup()

    def plan(
        self,
        *,
        scenario,
        action,
        mode="automatic",
        attempts=1,
    ):
        return {
            "schema_version": "1.0.0",
            "condition": "C2",
            "scenario_id": scenario,
            "run_key": "c2-executor-test",
            "fault_detected_at_utc": (
                "2026-08-19T18:00:00Z"
            ),
            "source_policy_decision_sha256": (
                "a" * 64
            ),
            "source_policy_decision": {
                "evaluation_stage": (
                    "post"
                    if scenario in {
                        "freshness_breach",
                        "quality_regression",
                    }
                    else "pre"
                ),
                "decision": "DENY",
                "triggered_policy_ids": [
                    "PAC-RELEASE-001"
                ],
                "promotion_blocked": True,
            },
            "controls": {
                "policy_as_code_required": True,
                "self_healing_permitted": True,
                "automatic_remediation_permitted": (
                    mode == "automatic"
                ),
            },
            "plan": {
                "mode": mode,
                "primary_action": action,
                "fallback_action": (
                    "quarantine"
                    if action != "manual_review"
                    else "stop_promotion"
                ),
                "max_attempts": attempts,
                "timeout_seconds": (
                    300
                    if attempts
                    else 0
                ),
                "target_scope": (
                    "release_state"
                    if mode == "manual"
                    else "isolated_output"
                ),
                "verification": [
                    "release_policy"
                ],
                "canonical_mutation_before_verification": False,
            },
            "rationale": "test",
        }

    def context(
        self,
        *,
        scenario,
        plan_sha,
        action_context,
    ):
        return {
            "schema_version": "1.0.0",
            "condition": "C2",
            "scenario_id": scenario,
            "run_key": "c2-executor-test",
            "remediation_plan_sha256": (
                plan_sha
            ),
            "workspace": {
                "root": "isolated",
                "isolated": True,
                "canonical_access_permitted": False,
            },
            "action_context": action_context,
        }

    def validate_result(self, payload):
        self.validator.validate(
            payload
        )

    def test_rollback_replaces_only_isolated_target(self):
        verified = (
            self.workspace
            / "verified/gold.sql"
        )

        target = (
            self.workspace
            / "candidate/gold.sql"
        )

        verified.parent.mkdir(
            parents=True
        )

        target.parent.mkdir(
            parents=True
        )

        verified.write_text(
            "safe\n",
            encoding="utf-8"
        )

        target.write_text(
            "broken\n",
            encoding="utf-8"
        )

        verified_before = digest(
            verified
        )

        plan = self.plan(
            scenario="schema_break",
            action="rollback",
        )

        result, details = execute_plan(
            plan=plan,
            context=self.context(
                scenario="schema_break",
                plan_sha="b" * 64,
                action_context={
                    "action": "rollback",
                    "target_relative_path": (
                        "candidate/gold.sql"
                    ),
                    "verified_source_relative_path": (
                        "verified/gold.sql"
                    ),
                },
            ),
            workspace_root=self.workspace,
            plan_sha256="b" * 64,
        )

        self.validate_result(result)

        self.assertEqual(
            target.read_text(
                encoding="utf-8"
            ),
            "safe\n",
        )

        self.assertEqual(
            digest(verified),
            verified_before,
        )

        self.assertEqual(
            result["terminal_state"],
            "PENDING_VERIFICATION",
        )

        self.assertFalse(
            result[
                "self_healing_performed"
            ]
        )

        self.assertTrue(
            details["source_unchanged"]
        )

    def test_redact_republish_uses_sanitized_source(self):
        sanitized = (
            self.workspace
            / "verified/public.sql"
        )

        candidate = (
            self.workspace
            / "public/candidate.sql"
        )

        sanitized.parent.mkdir(
            parents=True
        )

        candidate.parent.mkdir(
            parents=True
        )

        sanitized.write_text(
            "select safe_columns\n",
            encoding="utf-8"
        )

        candidate.write_text(
            "select synthetic_email\n",
            encoding="utf-8"
        )

        plan = self.plan(
            scenario="pii_exposure",
            action="redact_republish",
        )

        result, details = execute_plan(
            plan=plan,
            context=self.context(
                scenario="pii_exposure",
                plan_sha="c" * 64,
                action_context={
                    "action": "redact_republish",
                    "candidate_relative_path": (
                        "public/candidate.sql"
                    ),
                    "sanitized_source_relative_path": (
                        "verified/public.sql"
                    ),
                },
            ),
            workspace_root=self.workspace,
            plan_sha256="c" * 64,
        )

        self.validate_result(result)

        self.assertEqual(
            candidate.read_text(
                encoding="utf-8"
            ),
            "select safe_columns\n",
        )

        self.assertEqual(
            details[
                "operation"
            ],
            (
                "replace_with_sanitized_"
                "isolated_candidate"
            ),
        )

    def test_quarantine_moves_rejected_output(self):
        rejected = (
            self.workspace
            / "output/rejected.parquet"
        )

        quarantined = (
            self.workspace
            / "quarantine/rejected.parquet"
        )

        rejected.parent.mkdir(
            parents=True
        )

        rejected.write_bytes(
            b"rejected"
        )

        before = digest(
            rejected
        )

        plan = self.plan(
            scenario="quality_regression",
            action="quarantine",
        )

        result, details = execute_plan(
            plan=plan,
            context=self.context(
                scenario="quality_regression",
                plan_sha="d" * 64,
                action_context={
                    "action": "quarantine",
                    "rejected_output_relative_path": (
                        "output/rejected.parquet"
                    ),
                    "quarantine_relative_path": (
                        "quarantine/rejected.parquet"
                    ),
                },
            ),
            workspace_root=self.workspace,
            plan_sha256="d" * 64,
        )

        self.validate_result(result)

        self.assertFalse(
            rejected.exists()
        )

        self.assertTrue(
            quarantined.is_file()
        )

        self.assertEqual(
            digest(quarantined),
            before,
        )

        self.assertTrue(
            details["source_removed"]
        )

    def test_retry_uses_allowlisted_injected_runner(self):
        called = []

        def runner(plan, context):
            called.append(
                (
                    plan["scenario_id"],
                    context[
                        "action_context"
                    ][
                        "runner_profile"
                    ],
                )
            )

            return True

        plan = self.plan(
            scenario="freshness_breach",
            action="retry",
            attempts=2,
        )

        result, details = execute_plan(
            plan=plan,
            context=self.context(
                scenario="freshness_breach",
                plan_sha="e" * 64,
                action_context={
                    "action": "retry",
                    "runner_profile": (
                        "c2_isolated_pipeline"
                    ),
                },
            ),
            workspace_root=self.workspace,
            plan_sha256="e" * 64,
            retry_runner=runner,
        )

        self.validate_result(result)

        self.assertEqual(
            called,
            [
                (
                    "freshness_breach",
                    "c2_isolated_pipeline",
                )
            ],
        )

        self.assertEqual(
            result["attempt_count"],
            1,
        )

        self.assertEqual(
            details[
                "runner_reported_success"
            ],
            True,
        )

    def test_retry_without_adapter_fails_closed(self):
        plan = self.plan(
            scenario="freshness_breach",
            action="retry",
            attempts=2,
        )

        with self.assertRaises(
            ExecutorError
        ):
            execute_plan(
                plan=plan,
                context=self.context(
                    scenario="freshness_breach",
                    plan_sha="e" * 64,
                    action_context={
                        "action": "retry",
                        "runner_profile": (
                            "c2_isolated_pipeline"
                        ),
                    },
                ),
                workspace_root=self.workspace,
                plan_sha256="e" * 64,
            )

    def test_manual_review_never_mutates(self):
        plan = self.plan(
            scenario="policy_false_positive",
            action="manual_review",
            mode="manual",
            attempts=0,
        )

        result, details = execute_plan(
            plan=plan,
            context=self.context(
                scenario="policy_false_positive",
                plan_sha="f" * 64,
                action_context={
                    "action": "manual_review",
                    "reason": (
                        "Controlled safe change."
                    ),
                },
            ),
            workspace_root=self.workspace,
            plan_sha256="f" * 64,
        )

        self.validate_result(result)

        self.assertEqual(
            result["attempt_count"],
            0,
        )

        self.assertEqual(
            result["execution_status"],
            "NOT_RUN",
        )

        self.assertEqual(
            result["terminal_state"],
            "MANUAL_REVIEW",
        )

        self.assertFalse(
            result[
                "automatic_remediation_performed"
            ]
        )

        self.assertFalse(
            details[
                "automatic_mutation"
            ]
        )

    def test_plan_context_hash_mismatch_rejected(self):
        plan = self.plan(
            scenario="schema_break",
            action="rollback",
        )

        with self.assertRaises(
            ExecutorError
        ):
            execute_plan(
                plan=plan,
                context=self.context(
                    scenario="schema_break",
                    plan_sha="0" * 64,
                    action_context={
                        "action": "rollback",
                        "target_relative_path": (
                            "candidate/a"
                        ),
                        "verified_source_relative_path": (
                            "verified/a"
                        ),
                    },
                ),
                workspace_root=self.workspace,
                plan_sha256="1" * 64,
            )

    def test_action_mismatch_rejected(self):
        plan = self.plan(
            scenario="schema_break",
            action="rollback",
        )

        with self.assertRaises(
            ExecutorError
        ):
            execute_plan(
                plan=plan,
                context=self.context(
                    scenario="schema_break",
                    plan_sha="1" * 64,
                    action_context={
                        "action": "quarantine",
                        "rejected_output_relative_path": (
                            "output/a"
                        ),
                        "quarantine_relative_path": (
                            "quarantine/a"
                        ),
                    },
                ),
                workspace_root=self.workspace,
                plan_sha256="1" * 64,
            )

    def test_workspace_escape_rejected(self):
        with self.assertRaises(
            ExecutorError
        ):
            safe_workspace_path(
                workspace_root=self.workspace,
                relative_name="../outside",
            )


if __name__ == "__main__":
    unittest.main()

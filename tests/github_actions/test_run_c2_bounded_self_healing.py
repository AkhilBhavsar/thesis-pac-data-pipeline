import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]

WRAPPER_PATH = (
    ROOT
    / "scripts/github_actions/"
    "run_c2_bounded_self_healing.py"
)

SPEC = importlib.util.spec_from_file_location(
    "run_c2_bounded_self_healing",
    WRAPPER_PATH,
)

if SPEC is None or SPEC.loader is None:
    raise RuntimeError(
        "Unable to load the C2 wrapper."
    )

wrapper = importlib.util.module_from_spec(
    SPEC
)
SPEC.loader.exec_module(wrapper)


class C2WrapperSemanticExitTest(
    unittest.TestCase
):

    def setUp(self):
        self.temporary = (
            tempfile.TemporaryDirectory()
        )
        self.root = Path(
            self.temporary.name
        )
        self.verification = (
            self.root
            / "recovery-verification.json"
        )
        self.verified_result = (
            self.root
            / "verified-result.json"
        )

    def tearDown(self):
        self.temporary.cleanup()

    def write_verification(
        self,
        *,
        verification_status,
        verified_result_emitted,
        promotion_blocked,
        fallback,
    ):
        self.verification.write_text(
            json.dumps(
                {
                    "verification_status": (
                        verification_status
                    ),
                    "verified_result_emitted": (
                        verified_result_emitted
                    ),
                    "promotion_blocked": (
                        promotion_blocked
                    ),
                    "recommended_fallback_action": (
                        fallback
                    ),
                }
            )
            + "\n",
            encoding="utf-8",
        )

    @patch.object(
        wrapper.subprocess,
        "run",
    )
    def test_run_command_accepts_explicit_semantic_exit(
        self,
        run,
    ):
        run.return_value = SimpleNamespace(
            returncode=2
        )

        returncode = wrapper.run_command(
            ["verifier"],
            allowed_returncodes=(0, 2),
        )

        self.assertEqual(returncode, 2)

    @patch.object(
        wrapper.subprocess,
        "run",
    )
    def test_run_command_rejects_semantic_exit_by_default(
        self,
        run,
    ):
        run.return_value = SimpleNamespace(
            returncode=2
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "exit code 2",
        ):
            wrapper.run_command(
                ["ordinary-component"]
            )

    @patch.object(
        wrapper.subprocess,
        "run",
    )
    def test_technical_failure_is_never_accepted(
        self,
        run,
    ):
        run.return_value = SimpleNamespace(
            returncode=1
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "exit code 1",
        ):
            wrapper.run_command(
                ["verifier"],
                allowed_returncodes=(0, 2),
            )

    def test_manual_required_matches_exit_two(
        self,
    ):
        self.write_verification(
            verification_status=(
                "MANUAL_REQUIRED"
            ),
            verified_result_emitted=False,
            promotion_blocked=True,
            fallback="stop_promotion",
        )

        artifact = (
            wrapper
            .validate_verification_outcome(
                returncode=2,
                verification_output=(
                    self.verification
                ),
                verified_result_output=(
                    self.verified_result
                ),
            )
        )

        self.assertEqual(
            artifact[
                "verification_status"
            ],
            "MANUAL_REQUIRED",
        )

    def test_fail_matches_exit_two(
        self,
    ):
        self.write_verification(
            verification_status="FAIL",
            verified_result_emitted=False,
            promotion_blocked=True,
            fallback="quarantine",
        )

        wrapper.validate_verification_outcome(
            returncode=2,
            verification_output=(
                self.verification
            ),
            verified_result_output=(
                self.verified_result
            ),
        )

    def test_pass_requires_verified_result(
        self,
    ):
        self.write_verification(
            verification_status="PASS",
            verified_result_emitted=True,
            promotion_blocked=False,
            fallback=None,
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "did not create",
        ):
            wrapper.validate_verification_outcome(
                returncode=0,
                verification_output=(
                    self.verification
                ),
                verified_result_output=(
                    self.verified_result
                ),
            )

        self.verified_result.write_text(
            "{}\n",
            encoding="utf-8",
        )

        wrapper.validate_verification_outcome(
            returncode=0,
            verification_output=(
                self.verification
            ),
            verified_result_output=(
                self.verified_result
            ),
        )

    def test_exit_and_status_mismatch_is_rejected(
        self,
    ):
        self.write_verification(
            verification_status=(
                "MANUAL_REQUIRED"
            ),
            verified_result_emitted=False,
            promotion_blocked=True,
            fallback="stop_promotion",
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "exit/status mismatch",
        ):
            wrapper.validate_verification_outcome(
                returncode=0,
                verification_output=(
                    self.verification
                ),
                verified_result_output=(
                    self.verified_result
                ),
            )

    def test_controlled_outcome_rejects_stale_verified_result(
        self,
    ):
        self.write_verification(
            verification_status=(
                "MANUAL_REQUIRED"
            ),
            verified_result_emitted=False,
            promotion_blocked=True,
            fallback="stop_promotion",
        )

        self.verified_result.write_text(
            "{}\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "unexpected verified result",
        ):
            wrapper.validate_verification_outcome(
                returncode=2,
                verification_output=(
                    self.verification
                ),
                verified_result_output=(
                    self.verified_result
                ),
            )


class C2WrapperFixtureHandoffTest(
    unittest.TestCase
):

    def setUp(self):
        self.temporary = (
            tempfile.TemporaryDirectory()
        )
        self.root = Path(
            self.temporary.name
        )

    def tearDown(self):
        self.temporary.cleanup()

    def write_plan(
        self,
        *,
        scenario,
        action,
        mode="automatic",
    ):
        path = self.root / f"{scenario}.json"
        path.write_text(
            json.dumps(
                {
                    "condition": "C2",
                    "scenario_id": scenario,
                    "plan": {
                        "mode": mode,
                        "primary_action": action,
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def context_command(
        self,
        *,
        scenario,
        action,
    ):
        plan = self.write_plan(
            scenario=scenario,
            action=action,
        )
        workspace = (
            self.root
            / scenario
            / "workspace"
        )

        with patch.object(
            wrapper,
            "run_python_script",
        ) as runner:
            wrapper.build_c2_context(
                plan=str(plan),
                schema="context-schema.json",
                workspace_root=str(workspace),
                context_output="context.json",
                preparation_output=(
                    "preparation.json"
                ),
            )

        self.assertEqual(
            runner.call_count,
            1,
        )

        script, arguments = (
            runner.call_args.args
        )

        self.assertEqual(
            script,
            (
                "scripts/remediation/"
                "build_c2_execution_context.py"
            ),
        )

        return workspace, arguments

    def test_rollback_passes_isolated_sources(
        self,
    ):
        for scenario in (
            "schema_break",
            "quality_regression",
        ):
            with self.subTest(
                scenario=scenario
            ):
                workspace, arguments = (
                    self.context_command(
                        scenario=scenario,
                        action="rollback",
                    )
                )

                candidate_index = (
                    arguments.index(
                        "--candidate-source"
                    )
                )
                verified_index = (
                    arguments.index(
                        "--verified-source"
                    )
                )

                candidate = Path(
                    arguments[
                        candidate_index + 1
                    ]
                )
                verified = Path(
                    arguments[
                        verified_index + 1
                    ]
                )

                self.assertTrue(
                    candidate.is_file()
                )
                self.assertTrue(
                    verified.is_file()
                )
                self.assertNotEqual(
                    candidate.read_bytes(),
                    verified.read_bytes(),
                )
                self.assertEqual(
                    candidate.parent,
                    workspace.parent
                    / "fixtures",
                )

                manifest = json.loads(
                    (
                        candidate.parent
                        / "fixture-manifest.json"
                    ).read_text(
                        encoding="utf-8"
                    )
                )

                self.assertTrue(
                    manifest[
                        "synthetic_fixture"
                    ]
                )
                self.assertFalse(
                    manifest[
                        "canonical_data"
                    ]
                )
                self.assertTrue(
                    manifest["isolated"]
                )
                self.assertEqual(
                    manifest[
                        "files"
                    ][
                        "candidate"
                    ][
                        "sha256"
                    ],
                    wrapper.sha256_file(
                        candidate
                    ),
                )
                self.assertEqual(
                    manifest[
                        "files"
                    ][
                        "verified_source"
                    ][
                        "sha256"
                    ],
                    wrapper.sha256_file(
                        verified
                    ),
                )

    def test_redact_republish_passes_sanitized_source(
        self,
    ):
        workspace, arguments = (
            self.context_command(
                scenario="pii_exposure",
                action="redact_republish",
            )
        )

        candidate_index = arguments.index(
            "--candidate-source"
        )
        sanitized_index = arguments.index(
            "--sanitized-source"
        )

        candidate = Path(
            arguments[candidate_index + 1]
        )
        sanitized = Path(
            arguments[sanitized_index + 1]
        )

        candidate_payload = json.loads(
            candidate.read_text(
                encoding="utf-8"
            )
        )
        sanitized_payload = json.loads(
            sanitized.read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(
            candidate.parent,
            workspace.parent / "fixtures",
        )
        self.assertEqual(
            candidate_payload[
                "synthetic_email"
            ],
            "c2-fixture@example.invalid",
        )
        self.assertEqual(
            sanitized_payload[
                "synthetic_email"
            ],
            "[REDACTED]",
        )

    def test_retry_requires_no_file_fixture(
        self,
    ):
        workspace, arguments = (
            self.context_command(
                scenario="freshness_breach",
                action="retry",
            )
        )

        self.assertNotIn(
            "--candidate-source",
            arguments,
        )
        self.assertNotIn(
            "--verified-source",
            arguments,
        )
        self.assertNotIn(
            "--sanitized-source",
            arguments,
        )
        self.assertFalse(
            (
                workspace.parent
                / "fixtures"
            ).exists()
        )

    def test_existing_fixture_directory_is_rejected(
        self,
    ):
        plan = self.write_plan(
            scenario="schema_break",
            action="rollback",
        )
        workspace = (
            self.root
            / "stale"
            / "workspace"
        )
        fixtures = (
            workspace.parent
            / "fixtures"
        )
        fixtures.mkdir(
            parents=True
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "must not already exist",
        ):
            with patch.object(
                wrapper,
                "run_python_script",
            ) as runner:
                wrapper.build_c2_context(
                    plan=str(plan),
                    schema=(
                        "context-schema.json"
                    ),
                    workspace_root=str(
                        workspace
                    ),
                    context_output=(
                        "context.json"
                    ),
                    preparation_output=(
                        "preparation.json"
                    ),
                )

        runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()

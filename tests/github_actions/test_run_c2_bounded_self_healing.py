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


if __name__ == "__main__":
    unittest.main()

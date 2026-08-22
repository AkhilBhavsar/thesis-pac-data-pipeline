import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.remediation.build_c2_execution_context import (
    ContextBuilderError,
    build_context,
    main,
)


def digest(path):
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


class C2ExecutionContextBuilderTest(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()

        self.root = Path(
            self.temp.name
        )

    def tearDown(self):
        self.temp.cleanup()

    def workspace(self, name):
        return (
            self.root
            / name
        )

    def plan(
        self,
        scenario,
        action,
        mode="automatic",
    ):
        return {
            "condition": "C2",
            "scenario_id": scenario,
            "run_key": "c2-context-builder-test",
            "plan": {
                "mode": mode,
                "primary_action": action,
            },
        }

    def test_schema_break_rollback_prepares_isolated_copies(self):
        candidate = self.root / "faulted.sql"
        verified = self.root / "safe.sql"

        candidate.write_text(
            "broken\n",
            encoding="utf-8",
        )

        verified.write_text(
            "safe\n",
            encoding="utf-8",
        )

        workspace = self.workspace(
            "schema-workspace"
        )

        context, preparation = build_context(
            plan=self.plan(
                "schema_break",
                "rollback",
            ),
            plan_sha256="a" * 64,
            workspace_root=workspace,
            candidate_source=candidate,
            verified_source=verified,
        )

        self.assertEqual(
            context[
                "action_context"
            ][
                "action"
            ],
            "rollback",
        )

        self.assertEqual(
            Path(
                context[
                    "workspace"
                ][
                    "root"
                ]
            ),
            workspace.resolve(),
        )

        copied_candidate = (
            workspace
            / context[
                "action_context"
            ][
                "target_relative_path"
            ]
        )

        copied_verified = (
            workspace
            / context[
                "action_context"
            ][
                "verified_source_relative_path"
            ]
        )

        self.assertEqual(
            copied_candidate.read_text(
                encoding="utf-8"
            ),
            "broken\n",
        )

        self.assertEqual(
            copied_verified.read_text(
                encoding="utf-8"
            ),
            "safe\n",
        )

        self.assertEqual(
            preparation[
                "source_fingerprints"
            ][
                "candidate_sha256"
            ],
            digest(candidate),
        )

    def test_pii_adapter_uses_sanitized_source(self):
        candidate = self.root / "unsafe.sql"
        sanitized = self.root / "sanitized.sql"

        candidate.write_text(
            "synthetic_email\n",
            encoding="utf-8",
        )

        sanitized.write_text(
            "safe_columns\n",
            encoding="utf-8",
        )

        context, _ = build_context(
            plan=self.plan(
                "pii_exposure",
                "redact_republish",
            ),
            plan_sha256="b" * 64,
            workspace_root=self.workspace(
                "pii-workspace"
            ),
            candidate_source=candidate,
            sanitized_source=sanitized,
        )

        self.assertEqual(
            context[
                "action_context"
            ][
                "action"
            ],
            "redact_republish",
        )

    def test_freshness_adapter_selects_only_allowlisted_runner(self):
        context, _ = build_context(
            plan=self.plan(
                "freshness_breach",
                "retry",
            ),
            plan_sha256="c" * 64,
            workspace_root=self.workspace(
                "freshness-workspace"
            ),
        )

        self.assertEqual(
            context[
                "action_context"
            ][
                "runner_profile"
            ],
            "c2_isolated_pipeline",
        )

    def test_policy_false_positive_is_manual_only(self):
        context, _ = build_context(
            plan=self.plan(
                "policy_false_positive",
                "manual_review",
                mode="manual",
            ),
            plan_sha256="d" * 64,
            workspace_root=self.workspace(
                "manual-workspace"
            ),
            reason=(
                "Controlled safe-change "
                "policy review."
            ),
        )

        self.assertEqual(
            context[
                "action_context"
            ][
                "action"
            ],
            "manual_review",
        )

    def test_quarantine_prepares_rejected_copy(self):
        rejected = (
            self.root
            / "rejected.parquet"
        )

        rejected.write_bytes(
            b"rejected"
        )

        workspace = self.workspace(
            "quarantine-workspace"
        )

        context, _ = build_context(
            plan=self.plan(
                "quality_regression",
                "quarantine",
            ),
            plan_sha256="e" * 64,
            workspace_root=workspace,
            rejected_output_source=rejected,
        )

        copied = (
            workspace
            / context[
                "action_context"
            ][
                "rejected_output_relative_path"
            ]
        )

        self.assertTrue(
            copied.is_file()
        )

        self.assertTrue(
            rejected.is_file()
        )

    def test_source_files_are_never_mutated(self):
        candidate = self.root / "candidate"
        verified = self.root / "verified"

        candidate.write_bytes(
            b"broken"
        )

        verified.write_bytes(
            b"safe"
        )

        before_candidate = digest(
            candidate
        )

        before_verified = digest(
            verified
        )

        build_context(
            plan=self.plan(
                "schema_break",
                "rollback",
            ),
            plan_sha256="f" * 64,
            workspace_root=self.workspace(
                "copy-workspace"
            ),
            candidate_source=candidate,
            verified_source=verified,
        )

        self.assertEqual(
            digest(candidate),
            before_candidate,
        )

        self.assertEqual(
            digest(verified),
            before_verified,
        )

    def test_requires_empty_workspace(self):
        workspace = self.workspace(
            "nonempty"
        )

        workspace.mkdir()

        (
            workspace
            / "unexpected.txt"
        ).write_text(
            "unexpected",
            encoding="utf-8",
        )

        with self.assertRaises(
            ContextBuilderError
        ):
            build_context(
                plan=self.plan(
                    "freshness_breach",
                    "retry",
                ),
                plan_sha256="a" * 64,
                workspace_root=workspace,
            )

    def test_rejects_c1_plan(self):
        plan = self.plan(
            "freshness_breach",
            "retry",
        )

        plan["condition"] = "C1"

        with self.assertRaises(
            ContextBuilderError
        ):
            build_context(
                plan=plan,
                plan_sha256="a" * 64,
                workspace_root=self.workspace(
                    "c1-workspace"
                ),
            )

    def test_cli_error_path_emits_clean_error(self):
        stderr = io.StringIO()

        arguments = [
            "build_c2_execution_context.py",
            "--plan",
            str(self.root / "missing-plan.json"),
            "--schema",
            str(self.root / "missing-schema.json"),
            "--workspace-root",
            str(self.workspace("cli-workspace")),
            "--context-output",
            str(self.root / "context.json"),
            "--preparation-output",
            str(self.root / "preparation.json"),
        ]

        with (
            patch("sys.argv", arguments),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = main()

        self.assertEqual(
            exit_code,
            1,
        )

        self.assertIn(
            "ERROR: JSON file does not exist",
            stderr.getvalue(),
        )

        self.assertNotIn(
            "NameError",
            stderr.getvalue(),
        )


if __name__ == "__main__":
    unittest.main()

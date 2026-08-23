from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

MODULE_PATH = (
    REPO_ROOT
    / "scripts/remediation/"
    "build_c2_recovery_evidence.py"
)

SPEC = importlib.util.spec_from_file_location(
    "build_c2_recovery_evidence",
    MODULE_PATH,
)

if SPEC is None or SPEC.loader is None:
    raise RuntimeError(
        "Unable to load recovery-evidence builder."
    )

builder = importlib.util.module_from_spec(
    SPEC
)
SPEC.loader.exec_module(builder)


class C2RecoveryEvidenceBuilderTest(
    unittest.TestCase
):

    def setUp(self):
        self.temporary = (
            tempfile.TemporaryDirectory()
        )
        self.workspace = Path(
            self.temporary.name
        ) / "workspace"
        self.workspace.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def result(
        self,
        *,
        execution_status="SUCCEEDED",
        canonical_mutation=False,
        scenario="schema_break",
        action="rollback",
    ):
        return {
            "scenario_id": scenario,
            "run_key": "test-run",
            "execution_status": (
                execution_status
            ),
            "action": action,
            "mode": "automatic",
            "canonical_mutation_performed": (
                canonical_mutation
            ),
            "self_healing_performed": False,
        }

    def pre_evidence(self):
        return {
            "metadata": {
                "required_fields_present": True,
                "resource_count": 15,
            },
            "schema_contract": {},
            "transformation": {},
            "privacy": {},
            "quality": {},
            "freshness": {},
            "runtime": {
                "pipeline_status": "FAIL",
                "canonical_unchanged": True,
                "isolated_output_tables": 15,
                "athena_failed_queries": 2,
            },
        }

    def build(
        self,
        *,
        result=None,
        details=None,
        pre_evidence=None,
        plan=None,
        context=None,
    ):
        return builder.build_evidence(
            plan=(
                plan
                if plan is not None
                else {
                    "scenario_id": "schema_break",
                    "run_key": "test-run",
                    "plan": {
                        "primary_action": "rollback",
                    },
                }
            ),
            context=(
                context
                if context is not None
                else {
                    "scenario_id": "schema_break",
                    "run_key": "test-run",
                    "workspace": {
                        "isolated": True,
                        "canonical_access_permitted": False,
                        "root": str(self.workspace),
                    },
                    "action_context": {
                        "action": "rollback",
                    },
                }
            ),
            workspace_root=self.workspace,
            result=(
                result
                if result is not None
                else self.result()
            ),
            details=(
                details
                if details is not None
                else {
                    "operation": (
                        "restore_verified_"
                        "isolated_candidate"
                    )
                }
            ),
            pre_evidence=(
                pre_evidence
                if pre_evidence is not None
                else self.pre_evidence()
            ),
        )

    def pii_pre_evidence(self):
        evidence = self.pre_evidence()
        evidence["privacy"] = {
            "detected_forbidden_columns": [
                "synthetic_email",
            ],
            "forbidden_columns": [
                "synthetic_email",
            ],
            "public_models": [
                "gold_public_sales_dashboard",
            ],
        }
        evidence["schema_contract"] = {
            "governed_models": [
                {
                    "model": (
                        "gold_public_sales_dashboard"
                    ),
                    "exposure": "public",
                    "expected_column_count": 8,
                    "actual_column_count": 9,
                    "missing_columns": [],
                    "unexpected_columns": [
                        "synthetic_email",
                    ],
                    "incompatible_type_changes": [],
                }
            ]
        }
        return evidence

    def pii_inputs(
        self,
        *,
        include_email=False,
        trusted=True,
    ):
        relative = Path(
            "public/pii_exposure/candidate.json"
        )
        candidate = self.workspace / relative
        candidate.parent.mkdir(
            parents=True,
        )

        payload = {
            "condition": "C2",
            "scenario_id": "pii_exposure",
            "synthetic_fixture": True,
            "canonical_data": False,
            "fixture_role": "sanitized_source",
            "trusted": trusted,
            "state": "redacted_safe",
        }

        if include_email:
            payload["synthetic_email"] = (
                "[REDACTED]"
            )

        candidate.write_text(
            json.dumps(payload) + "\n",
            encoding="utf-8",
        )

        source_sha = builder.hashlib.sha256(
            candidate.read_bytes()
        ).hexdigest()

        plan = {
            "scenario_id": "pii_exposure",
            "run_key": "test-run",
            "plan": {
                "primary_action": (
                    "redact_republish"
                ),
            },
        }
        context = {
            "scenario_id": "pii_exposure",
            "run_key": "test-run",
            "workspace": {
                "isolated": True,
                "canonical_access_permitted": False,
                "root": str(self.workspace),
            },
            "action_context": {
                "action": "redact_republish",
                "candidate_relative_path": str(
                    relative
                ),
            },
        }
        result = self.result(
            scenario="pii_exposure",
            action="redact_republish",
        )
        details = {
            "operation": (
                "replace_with_sanitized_"
                "isolated_candidate"
            ),
            "source_unchanged": True,
            "source_sha256": source_sha,
            "target_sha256_before": "a" * 64,
            "target_sha256_after": source_sha,
        }

        return plan, context, result, details

    def test_pii_projection_uses_verified_removed_field(self):
        plan, context, result, details = (
            self.pii_inputs()
        )
        pre_evidence = self.pii_pre_evidence()

        evidence = self.build(
            plan=plan,
            context=context,
            result=result,
            details=details,
            pre_evidence=pre_evidence,
        )

        self.assertEqual(
            evidence["privacy"][
                "detected_forbidden_columns"
            ],
            [],
        )

        public_model = evidence[
            "schema_contract"
        ]["governed_models"][0]

        self.assertEqual(
            public_model["actual_column_count"],
            8,
        )
        self.assertEqual(
            public_model["unexpected_columns"],
            [],
        )
        self.assertEqual(
            pre_evidence["privacy"][
                "detected_forbidden_columns"
            ],
            ["synthetic_email"],
        )

    def test_pii_projection_rejects_placeholder_field(self):
        plan, context, result, details = (
            self.pii_inputs(
                include_email=True
            )
        )

        with self.assertRaisesRegex(
            builder.EvidenceBuildError,
            "still contains synthetic_email",
        ):
            self.build(
                plan=plan,
                context=context,
                result=result,
                details=details,
                pre_evidence=(
                    self.pii_pre_evidence()
                ),
            )

    def test_pii_projection_rejects_untrusted_fixture(self):
        plan, context, result, details = (
            self.pii_inputs(
                trusted=False
            )
        )

        with self.assertRaisesRegex(
            builder.EvidenceBuildError,
            "invalid trusted",
        ):
            self.build(
                plan=plan,
                context=context,
                result=result,
                details=details,
                pre_evidence=(
                    self.pii_pre_evidence()
                ),
            )

    def test_success_emits_exact_runtime_contract(
        self,
    ):
        evidence = self.build()

        self.assertEqual(
            evidence["runtime"],
            {
                "pipeline_status": "PASS",
                "canonical_unchanged": True,
                "isolated_output_tables": 15,
                "athena_failed_queries": 2,
            },
        )

    def test_runtime_metrics_are_preserved(
        self,
    ):
        source = self.pre_evidence()

        evidence = self.build(
            pre_evidence=source
        )

        self.assertEqual(
            evidence[
                "runtime"
            ][
                "isolated_output_tables"
            ],
            source[
                "runtime"
            ][
                "isolated_output_tables"
            ],
        )
        self.assertEqual(
            evidence[
                "runtime"
            ][
                "athena_failed_queries"
            ],
            source[
                "runtime"
            ][
                "athena_failed_queries"
            ],
        )

    def test_operational_details_are_not_embedded(
        self,
    ):
        runtime = self.build()[
            "runtime"
        ]

        for unsupported in (
            "details",
            "isolated_execution",
            "remediation_action",
            "remediation_mode",
            "self_healing_performed",
        ):
            self.assertNotIn(
                unsupported,
                runtime,
            )

    def test_not_run_maps_to_not_run(
        self,
    ):
        evidence = self.build(
            result=self.result(
                execution_status="NOT_RUN"
            )
        )

        self.assertEqual(
            evidence[
                "runtime"
            ][
                "pipeline_status"
            ],
            "NOT_RUN",
        )

    def test_failed_maps_to_fail(
        self,
    ):
        evidence = self.build(
            result=self.result(
                execution_status="FAILED"
            )
        )

        self.assertEqual(
            evidence[
                "runtime"
            ][
                "pipeline_status"
            ],
            "FAIL",
        )

    def test_canonical_mutation_is_not_hidden(
        self,
    ):
        evidence = self.build(
            result=self.result(
                canonical_mutation=True
            )
        )

        self.assertFalse(
            evidence[
                "runtime"
            ][
                "canonical_unchanged"
            ]
        )

    def test_missing_runtime_section_is_rejected(
        self,
    ):
        pre_evidence = self.pre_evidence()
        del pre_evidence["runtime"]

        with self.assertRaisesRegex(
            builder.EvidenceBuildError,
            "missing sections",
        ):
            self.build(
                pre_evidence=pre_evidence
            )

    def test_missing_runtime_metric_is_rejected(
        self,
    ):
        pre_evidence = self.pre_evidence()
        del pre_evidence[
            "runtime"
        ][
            "athena_failed_queries"
        ]

        with self.assertRaisesRegex(
            builder.EvidenceBuildError,
            "missing required metrics",
        ):
            self.build(
                pre_evidence=pre_evidence
            )

    def test_unknown_execution_status_is_rejected(
        self,
    ):
        with self.assertRaisesRegex(
            builder.EvidenceBuildError,
            "Unsupported remediation execution status",
        ):
            self.build(
                result=self.result(
                    execution_status="UNKNOWN"
                )
            )


if __name__ == "__main__":
    unittest.main()

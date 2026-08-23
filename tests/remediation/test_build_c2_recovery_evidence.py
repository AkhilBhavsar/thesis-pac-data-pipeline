from __future__ import annotations

import importlib.util
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

    def result(
        self,
        *,
        execution_status="SUCCEEDED",
        canonical_mutation=False,
    ):
        return {
            "execution_status": (
                execution_status
            ),
            "action": "rollback",
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
        pre_evidence=None,
    ):
        return builder.build_evidence(
            result=(
                result
                if result is not None
                else self.result()
            ),
            details={
                "operation": (
                    "restore_verified_"
                    "isolated_candidate"
                )
            },
            pre_evidence=(
                pre_evidence
                if pre_evidence is not None
                else self.pre_evidence()
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

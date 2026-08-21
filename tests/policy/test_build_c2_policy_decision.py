from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema import FormatChecker

from scripts.policy.build_c2_policy_decision import (
    ProjectionError,
    build_c2_policy_decision,
    canonical_bytes,
)

from scripts.policy.build_c2_remediation_plan import (
    PlannerError,
    build_remediation_plan,
    validate_source_decision,
)


ROOT = Path(
    __file__
).resolve().parents[2]

CATALOG = json.loads(
    (
        ROOT
        / "policies"
        / "catalog"
        / "c2-remediation-catalog.json"
    ).read_text(
        encoding="utf-8"
    )
)

PROJECTION_SCHEMA = json.loads(
    (
        ROOT
        / "policies"
        / "contracts"
        / "c2-policy-decision-projection.schema.json"
    ).read_text(
        encoding="utf-8"
    )
)

PLAN_SCHEMA = json.loads(
    (
        ROOT
        / "policies"
        / "contracts"
        / "c2-remediation-plan.schema.json"
    ).read_text(
        encoding="utf-8"
    )
)

PROJECTION_VALIDATOR = Draft202012Validator(
    PROJECTION_SCHEMA,
    format_checker=FormatChecker(),
)

PLAN_VALIDATOR = Draft202012Validator(
    PLAN_SCHEMA,
    format_checker=FormatChecker(),
)


TRIGGERS = {
    "schema_break": [
        "PAC-SCHEMA-001",
        "PAC-RELEASE-001",
    ],
    "pii_exposure": [
        "PAC-PRIVACY-001",
        "PAC-SCHEMA-001",
        "PAC-RELEASE-001",
    ],
    "freshness_breach": [
        "PAC-FRESH-001",
        "PAC-RELEASE-001",
    ],
    "quality_regression": [
        "PAC-QUALITY-001",
        "PAC-RELEASE-001",
    ],
    "policy_false_positive": [
        "PAC-SCHEMA-001",
        "PAC-RELEASE-001",
    ],
}


def digest(
    value: dict,
) -> str:
    return hashlib.sha256(
        canonical_bytes(
            value
        )
    ).hexdigest()


class C2PolicyDecisionProjectionTest(
    unittest.TestCase
):
    def source(
        self,
        scenario_id: str,
    ) -> dict:
        scenario = CATALOG[
            "scenarios"
        ][
            scenario_id
        ]

        return {
            "schema_version": "1.0.0",
            "recorded_at_utc": (
                "2026-08-21T12:30:00Z"
            ),
            "condition": "C1",
            "run_key": (
                "gha_12345_1"
            ),
            "scenario_id": scenario_id,
            "evaluation_stage": scenario[
                "detection_stage"
            ],
            "decision": "DENY",
            "allow": False,
            "violation_count": len(
                TRIGGERS[
                    scenario_id
                ]
            ),
            "triggered_policy_ids": list(
                reversed(
                    TRIGGERS[
                        scenario_id
                    ]
                )
            ),
            "input_sha256": "a" * 64,
            "policy_bundle_sha256": "b" * 64,
            "controls": {
                "policy_as_code_required": True,
                "self_healing_permitted": False,
                "automatic_remediation_permitted": (
                    False
                ),
            },
            "promotion_requested": True,
            "measurement": {
                "promotion_requested": True,
                "promotion_blocked": True,
            },
        }

    def project(
        self,
        scenario_id: str,
        source: dict | None = None,
    ) -> dict:
        source = (
            self.source(
                scenario_id
            )
            if source is None
            else source
        )

        projected = build_c2_policy_decision(
            source_decision=source,
            source_decision_sha256=digest(
                source
            ),
            catalog=CATALOG,
        )

        PROJECTION_VALIDATOR.validate(
            projected
        )

        return projected

    def test_all_five_scenarios_project_valid_c2_decisions(
        self,
    ):
        for scenario_id in sorted(
            CATALOG[
                "scenarios"
            ]
        ):
            projected = self.project(
                scenario_id
            )

            self.assertEqual(
                projected[
                    "condition"
                ],
                "C2",
            )

            self.assertEqual(
                projected[
                    "scenario_id"
                ],
                scenario_id,
            )

    def test_detection_identity_is_preserved(
        self,
    ):
        source = self.source(
            "freshness_breach"
        )

        projected = self.project(
            "freshness_breach",
            source,
        )

        self.assertEqual(
            projected[
                "recorded_at_utc"
            ],
            source[
                "recorded_at_utc"
            ],
        )

        self.assertEqual(
            projected[
                "run_key"
            ],
            source[
                "run_key"
            ],
        )

    def test_triggered_policy_ids_are_deterministic(
        self,
    ):
        projected = self.project(
            "pii_exposure"
        )

        self.assertEqual(
            projected[
                "triggered_policy_ids"
            ],
            sorted(
                TRIGGERS[
                    "pii_exposure"
                ]
            ),
        )

    def test_source_provenance_hashes_are_preserved(
        self,
    ):
        source = self.source(
            "quality_regression"
        )

        source_sha = digest(
            source
        )

        projected = build_c2_policy_decision(
            source_decision=source,
            source_decision_sha256=(
                source_sha
            ),
            catalog=CATALOG,
        )

        projection = projected[
            "projection"
        ]

        self.assertEqual(
            projection[
                "source_policy_decision_sha256"
            ],
            source_sha,
        )

        self.assertEqual(
            projection[
                "source_input_sha256"
            ],
            "a" * 64,
        )

        self.assertEqual(
            projection[
                "source_policy_bundle_sha256"
            ],
            "b" * 64,
        )

    def test_c2_controls_follow_catalog(
        self,
    ):
        for scenario_id, scenario in (
            CATALOG[
                "scenarios"
            ].items()
        ):
            projected = self.project(
                scenario_id
            )

            controls = projected[
                "controls"
            ]

            self.assertTrue(
                controls[
                    "self_healing_permitted"
                ]
            )

            self.assertEqual(
                controls[
                    "automatic_remediation_permitted"
                ],
                scenario[
                    "automatic_remediation_permitted"
                ],
            )

    def test_false_positive_remains_manual_only(
        self,
    ):
        projected = self.project(
            "policy_false_positive"
        )

        self.assertFalse(
            projected[
                "controls"
            ][
                "automatic_remediation_permitted"
            ]
        )

    def test_rejects_non_c1_source_condition(
        self,
    ):
        source = self.source(
            "freshness_breach"
        )

        source[
            "condition"
        ] = "C2"

        with self.assertRaises(
            ProjectionError
        ):
            self.project(
                "freshness_breach",
                source,
            )

    def test_rejects_allow_source_decision(
        self,
    ):
        source = self.source(
            "freshness_breach"
        )

        source[
            "decision"
        ] = "ALLOW"

        source[
            "allow"
        ] = True

        with self.assertRaises(
            ProjectionError
        ):
            self.project(
                "freshness_breach",
                source,
            )

    def test_rejects_unblocked_promotion(
        self,
    ):
        source = self.source(
            "quality_regression"
        )

        source[
            "measurement"
        ][
            "promotion_blocked"
        ] = False

        with self.assertRaises(
            ProjectionError
        ):
            self.project(
                "quality_regression",
                source,
            )

    def test_rejects_stage_drift(
        self,
    ):
        source = self.source(
            "schema_break"
        )

        source[
            "evaluation_stage"
        ] = "post"

        with self.assertRaises(
            ProjectionError
        ):
            self.project(
                "schema_break",
                source,
            )

    def test_rejects_duplicate_triggered_policy_ids(
        self,
    ):
        source = self.source(
            "freshness_breach"
        )

        source[
            "triggered_policy_ids"
        ] = [
            "PAC-FRESH-001",
            "PAC-FRESH-001",
        ]

        with self.assertRaises(
            ProjectionError
        ):
            self.project(
                "freshness_breach",
                source,
            )

    def test_rejects_c1_self_healing_enabled(
        self,
    ):
        source = self.source(
            "schema_break"
        )

        source[
            "controls"
        ][
            "self_healing_permitted"
        ] = True

        with self.assertRaises(
            ProjectionError
        ):
            self.project(
                "schema_break",
                source,
            )

    def test_projection_is_deterministic(
        self,
    ):
        source = self.source(
            "quality_regression"
        )

        first = self.project(
            "quality_regression",
            copy.deepcopy(
                source
            ),
        )

        second = self.project(
            "quality_regression",
            copy.deepcopy(
                source
            ),
        )

        self.assertEqual(
            canonical_bytes(
                first
            ),
            canonical_bytes(
                second
            ),
        )

    def test_source_document_is_not_mutated(
        self,
    ):
        source = self.source(
            "pii_exposure"
        )

        before = copy.deepcopy(
            source
        )

        self.project(
            "pii_exposure",
            source,
        )

        self.assertEqual(
            source,
            before,
        )

    def test_projected_decision_is_accepted_by_c2_planner(
        self,
    ):
        source = self.source(
            "freshness_breach"
        )

        with self.assertRaises(
            PlannerError
        ):
            validate_source_decision(
                source,
                CATALOG,
            )

        projected = self.project(
            "freshness_breach",
            source,
        )

        validate_source_decision(
            projected,
            CATALOG,
        )

        plan = build_remediation_plan(
            decision=projected,
            catalog=CATALOG,
            decision_sha256=digest(
                projected
            ),
        )

        PLAN_VALIDATOR.validate(
            plan
        )

        self.assertEqual(
            plan[
                "condition"
            ],
            "C2",
        )

        self.assertEqual(
            plan[
                "plan"
            ][
                "primary_action"
            ],
            "retry",
        )


if __name__ == "__main__":
    unittest.main()

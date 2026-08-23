from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

MODULE_PATH = (
    REPO_ROOT
    / "scripts"
    / "remediation"
    / "verify_c2_recovery.py"
)

SPEC = importlib.util.spec_from_file_location(
    "verify_c2_recovery",
    MODULE_PATH,
)

assert SPEC is not None
assert SPEC.loader is not None

verifier = importlib.util.module_from_spec(
    SPEC
)

SPEC.loader.exec_module(
    verifier
)


def load(relative: str) -> dict[str, Any]:
    return json.loads(
        (
            REPO_ROOT
            / relative
        ).read_text(
            encoding="utf-8"
        )
    )


CATALOG = load(
    "policies/catalog/c2-remediation-catalog.json"
)

PLAN_SCHEMA = load(
    "policies/contracts/c2-remediation-plan.schema.json"
)

RESULT_SCHEMA = load(
    "policies/contracts/c2-remediation-result.schema.json"
)

VERIFICATION_SCHEMA = load(
    "policies/contracts/c2-remediation-verification.schema.json"
)

BASE_INPUT_SCHEMA = load(
    "policies/contracts/policy-input.schema.json"
)


def canonical_sha(
    payload: dict[str, Any],
) -> str:
    return hashlib.sha256(
        verifier.canonical_bytes(
            payload
        )
    ).hexdigest()


def plan_for(
    scenario_id: str,
) -> dict[str, Any]:
    scenario = CATALOG[
        "scenarios"
    ][
        scenario_id
    ]

    automatic = scenario[
        "automatic_remediation_permitted"
    ]

    return {
        "schema_version": "1.0.0",
        "condition": "C2",
        "scenario_id": scenario_id,
        "run_key": (
            f"unit-{scenario_id}"
        ),
        "fault_detected_at_utc": (
            "2026-08-20T12:00:00Z"
        ),
        "source_policy_decision_sha256": (
            "a" * 64
        ),
        "source_policy_decision": {
            "evaluation_stage": scenario[
                "detection_stage"
            ],
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
                automatic
            ),
        },
        "plan": {
            "mode": (
                "automatic"
                if automatic
                else "manual"
            ),
            "primary_action": scenario[
                "primary_action"
            ],
            "fallback_action": scenario[
                "fallback_action"
            ],
            "max_attempts": scenario[
                "max_attempts"
            ],
            "timeout_seconds": scenario[
                "timeout_seconds"
            ],
            "target_scope": scenario[
                "target_scope"
            ],
            "verification": scenario[
                "verification"
            ],
            "canonical_mutation_before_verification": False,
        },
        "rationale": (
            "Unit-test catalog-governed "
            "C2 remediation plan."
        ),
    }


def result_for(
    plan: dict[str, Any],
) -> dict[str, Any]:
    automatic = (
        plan[
            "plan"
        ][
            "mode"
        ]
        == "automatic"
    )

    return {
        "schema_version": "1.0.0",
        "condition": "C2",
        "scenario_id": plan[
            "scenario_id"
        ],
        "run_key": plan[
            "run_key"
        ],
        "source_remediation_plan_sha256": (
            canonical_sha(
                plan
            )
        ),
        "mode": plan[
            "plan"
        ][
            "mode"
        ],
        "action": plan[
            "plan"
        ][
            "primary_action"
        ],
        "attempt_count": (
            1
            if automatic
            else 0
        ),
        "execution_status": (
            "SUCCEEDED"
            if automatic
            else "NOT_RUN"
        ),
        "verification": {
            "required": True,
            "status": (
                "NOT_RUN"
            ),
            "evidence_sha256": None,
        },
        "terminal_state": (
            "PENDING_VERIFICATION"
            if automatic
            else "MANUAL_REVIEW"
        ),
        "fault_detected_at_utc": (
            plan[
                "fault_detected_at_utc"
            ]
        ),
        "remediation_started_at_utc": (
            "2026-08-20T12:00:10Z"
        ),
        "remediation_completed_at_utc": (
            "2026-08-20T12:00:20Z"
        ),
        "action_duration_ms": 10000.0,
        "recovery_time_ms": None,
        "promotion_recheck_required": True,
        "canonical_mutation_performed": False,
        "self_healing_performed": False,
        "automatic_remediation_performed": (
            automatic
        ),
    }


def safe_evidence() -> dict[str, Any]:
    return {
        "metadata": {
            "required_fields_present": True,
            "resource_count": 15,
        },
        "schema_contract": {
            "governed_models": [
                {
                    "model": (
                        "gold_public_sales_dashboard"
                    ),
                    "exposure": "public",
                    "expected_column_count": 8,
                    "actual_column_count": 8,
                    "missing_columns": [],
                    "unexpected_columns": [],
                    "incompatible_type_changes": [],
                }
            ]
        },
        "transformation": {
            "changed_models": [],
            "unapproved_definitions": [],
            "manifest_sha256": (
                "b" * 64
            ),
        },
        "privacy": {
            "public_models": [
                "gold_public_sales_dashboard"
            ],
            "forbidden_columns": [
                "email"
            ],
            "detected_forbidden_columns": [],
        },
        "quality": {
            "status": "PASS",
            "total_tests": 41,
            "failed_tests": 0,
            "critical_failures": [],
        },
        "freshness": {
            "status": "PASS",
            "sources": [
                {
                    "source": "gold_daily_sales",
                    "observed_age_seconds": 60.0,
                    "maximum_age_seconds": 86400.0,
                    "status": "PASS",
                }
            ],
        },
        "runtime": {
            "pipeline_status": "PASS",
            "canonical_unchanged": True,
            "isolated_output_tables": 15,
            "athena_failed_queries": 0,
        },
    }


def allow_evaluator(
    opa_bin: Path,
    payload: dict[str, Any],
    policy_dir: Path,
) -> tuple[
    bool,
    list[dict[str, Any]],
    float,
]:
    assert payload[
        "experiment"
    ][
        "condition"
    ] == "C2"

    assert payload[
        "controls"
    ][
        "self_healing_permitted"
    ] is True

    assert policy_dir.name == "rego"

    return (
        True,
        [],
        1.25,
    )


def test_evaluate_opa_resolves_bare_command_from_path(
    tmp_path,
    monkeypatch,
):
    opa = tmp_path / "opa"

    opa.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' "
        "'{\"result\":[{\"expressions\":[{\"value\":"
        "{\"allow\":true,\"violations\":[]}}]}]}'\n",
        encoding="utf-8",
    )

    opa.chmod(0o755)

    policy_dir = tmp_path / "rego"
    policy_dir.mkdir()

    (
        policy_dir
        / "allow.rego"
    ).write_text(
        "package thesis.pac\n",
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "PATH",
        str(tmp_path),
    )

    allow, violations, evaluation_ms = (
        verifier.evaluate_opa(
            Path("opa"),
            {"synthetic": True},
            policy_dir,
        )
    )

    assert allow is True
    assert violations == []
    assert evaluation_ms >= 0


def test_evaluate_opa_rejects_unresolvable_command(
    tmp_path,
    monkeypatch,
):
    policy_dir = tmp_path / "rego"
    policy_dir.mkdir()

    (
        policy_dir
        / "allow.rego"
    ).write_text(
        "package thesis.pac\n",
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "PATH",
        str(tmp_path),
    )

    with pytest.raises(
        verifier.VerificationError,
        match=(
            "OPA executable cannot be resolved"
        ),
    ):
        verifier.evaluate_opa(
            Path("opa"),
            {"synthetic": True},
            policy_dir,
        )


def run(
    scenario_id: str,
    *,
    evaluator=allow_evaluator,
    plan_override=None,
    result_override=None,
):
    plan = (
        plan_override
        if plan_override is not None
        else plan_for(
            scenario_id
        )
    )

    result = (
        result_override
        if result_override is not None
        else result_for(
            plan
        )
    )

    evidence = safe_evidence()

    return verifier.verify_recovery(
        plan=plan,
        result=result,
        evidence=evidence,
        catalog=CATALOG,
        base_policy_input_schema=(
            BASE_INPUT_SCHEMA
        ),
        plan_schema=PLAN_SCHEMA,
        result_schema=RESULT_SCHEMA,
        verification_schema=(
            VERIFICATION_SCHEMA
        ),
        repo_root=REPO_ROOT,
        branch=(
            "feature/c2-bounded-self-healing"
        ),
        commit=("c" * 40),
        target_layer="gold_public",
        opa_bin=Path(
            "/synthetic/opa"
        ),
        plan_artifact_sha256=(
            canonical_sha(plan)
        ),
        result_artifact_sha256=(
            canonical_sha(result)
        ),
        evidence_artifact_sha256=(
            canonical_sha(evidence)
        ),
        evaluator=evaluator,
        started_at=(
            "2026-08-20T12:00:25Z"
        ),
        completed_at=(
            "2026-08-20T12:00:30Z"
        ),
    )


def test_freshness_pass_derives_recovered_result():
    artifact, verified = run(
        "freshness_breach"
    )

    assert artifact[
        "verification_status"
    ] == "PASS"

    assert artifact[
        "promotion_blocked"
    ] is False

    assert [
        item["check"]
        for item
        in artifact[
            "check_results"
        ]
    ] == [
        "freshness",
        "runtime",
        "release_policy",
    ]

    assert all(
        item["status"] == "PASS"
        for item
        in artifact[
            "check_results"
        ]
    )

    assert verified is not None

    assert verified[
        "terminal_state"
    ] == "RECOVERED"

    assert verified[
        "self_healing_performed"
    ] is True

    assert verified[
        "verification"
    ][
        "status"
    ] == "PASS"

    assert verified[
        "recovery_time_ms"
    ] == 30000.0


def test_pii_pass_requires_privacy_schema_and_release():
    artifact, verified = run(
        "pii_exposure"
    )

    assert artifact[
        "required_checks"
    ] == [
        "privacy",
        "schema_contract",
        "release_policy",
    ]

    assert verified is not None


def test_quality_violation_fails_to_quarantine():
    def deny(
        opa_bin,
        payload,
        policy_dir,
    ):
        return (
            False,
            [
                {
                    "policy_id": (
                        "PAC-QUALITY-001"
                    ),
                    "reason": "quality failed",
                },
                {
                    "policy_id": (
                        "PAC-RELEASE-001"
                    ),
                    "reason": (
                        "promotion blocked"
                    ),
                },
            ],
            2.0,
        )

    artifact, verified = run(
        "quality_regression",
        evaluator=deny,
    )

    assert verified is None

    assert artifact[
        "verification_status"
    ] == "FAIL"

    assert artifact[
        "promotion_blocked"
    ] is True

    assert artifact[
        "recommended_fallback_action"
    ] == "quarantine"


def test_schema_failure_selects_manual_review():
    def deny(
        opa_bin,
        payload,
        policy_dir,
    ):
        return (
            False,
            [
                {
                    "policy_id": (
                        "PAC-SCHEMA-001"
                    ),
                    "reason": (
                        "schema remains unsafe"
                    ),
                },
                {
                    "policy_id": (
                        "PAC-RELEASE-001"
                    ),
                    "reason": (
                        "promotion blocked"
                    ),
                },
            ],
            2.5,
        )

    artifact, verified = run(
        "schema_break",
        evaluator=deny,
    )

    assert verified is None

    assert artifact[
        "recommended_fallback_action"
    ] == "manual_review"


def test_false_positive_remains_manual_without_opa():
    called = False

    def forbidden(
        opa_bin,
        payload,
        policy_dir,
    ):
        nonlocal called
        called = True
        raise AssertionError(
            "OPA must not run for "
            "manual false-positive recovery."
        )

    artifact, verified = run(
        "policy_false_positive",
        evaluator=forbidden,
    )

    assert called is False
    assert verified is None

    assert artifact[
        "verification_status"
    ] == "MANUAL_REQUIRED"

    assert artifact[
        "required_checks"
    ] == [
        "manual_policy_review"
    ]

    assert artifact[
        "recommended_fallback_action"
    ] == "stop_promotion"

    assert artifact[
        "promotion_blocked"
    ] is True


def test_catalog_drift_is_rejected():
    plan = plan_for(
        "freshness_breach"
    )

    plan[
        "plan"
    ][
        "max_attempts"
    ] = 1

    result = result_for(
        plan
    )

    with pytest.raises(
        verifier.VerificationError,
        match="catalog",
    ):
        run(
            "freshness_breach",
            plan_override=plan,
            result_override=result,
        )


def test_non_pending_automatic_result_is_rejected():
    plan = plan_for(
        "freshness_breach"
    )

    result = result_for(
        plan
    )

    result[
        "terminal_state"
    ] = "FAILED_SAFE"

    with pytest.raises(
        verifier.VerificationError,
        match="PENDING_VERIFICATION",
    ):
        run(
            "freshness_breach",
            plan_override=plan,
            result_override=result,
        )


def test_unrelated_blocking_policy_fails_closed():
    def deny(
        opa_bin,
        payload,
        policy_dir,
    ):
        return (
            False,
            [
                {
                    "policy_id": "PAC-META-001",
                    "reason": (
                        "metadata remains unsafe"
                    ),
                }
            ],
            0.75,
        )

    artifact, verified = run(
        "freshness_breach",
        evaluator=deny,
    )

    assert verified is None

    assert artifact[
        "verification_status"
    ] == "FAIL"

    assert artifact[
        "promotion_blocked"
    ] is True


def test_source_result_is_not_mutated():
    plan = plan_for(
        "freshness_breach"
    )

    result = result_for(
        plan
    )

    before = copy.deepcopy(
        result
    )

    artifact, verified = run(
        "freshness_breach",
        plan_override=plan,
        result_override=result,
    )

    assert artifact[
        "verification_status"
    ] == "PASS"

    assert verified is not None
    assert result == before


def test_verified_result_preserves_action_completion_time():
    artifact, verified = run(
        "freshness_breach"
    )

    assert artifact[
        "verification_completed_at_utc"
    ] == "2026-08-20T12:00:30Z"

    assert verified is not None

    assert verified[
        "remediation_completed_at_utc"
    ] == "2026-08-20T12:00:20Z"

    assert verified[
        "recovery_time_ms"
    ] == 30000.0


def test_verification_preserves_source_artifact_hashes():
    plan = plan_for(
        "freshness_breach"
    )

    result = result_for(
        plan
    )

    evidence = safe_evidence()

    plan_sha = canonical_sha(
        plan
    )

    result_sha = canonical_sha(
        result
    )

    evidence_sha = canonical_sha(
        evidence
    )

    artifact, verified = (
        verifier.verify_recovery(
            plan=plan,
            result=result,
            evidence=evidence,
            catalog=CATALOG,
            base_policy_input_schema=(
                BASE_INPUT_SCHEMA
            ),
            plan_schema=PLAN_SCHEMA,
            result_schema=RESULT_SCHEMA,
            verification_schema=(
                VERIFICATION_SCHEMA
            ),
            repo_root=REPO_ROOT,
            branch=(
                "feature/c2-bounded-self-healing"
            ),
            commit=("c" * 40),
            target_layer="gold_public",
            opa_bin=Path(
                "/synthetic/opa"
            ),
            plan_artifact_sha256=(
                plan_sha
            ),
            result_artifact_sha256=(
                result_sha
            ),
            evidence_artifact_sha256=(
                evidence_sha
            ),
            evaluator=allow_evaluator,
            started_at=(
                "2026-08-20T12:00:25Z"
            ),
            completed_at=(
                "2026-08-20T12:00:30Z"
            ),
        )
    )

    assert verified is not None

    assert artifact[
        "source_remediation_plan_sha256"
    ] == plan_sha

    assert artifact[
        "source_remediation_result_sha256"
    ] == result_sha

    assert artifact[
        "source_evidence_sha256"
    ] == evidence_sha


def test_wrong_plan_artifact_hash_is_rejected():
    plan = plan_for(
        "freshness_breach"
    )

    result = result_for(
        plan
    )

    evidence = safe_evidence()

    with pytest.raises(
        verifier.VerificationError,
        match="fingerprint mismatch",
    ):
        verifier.verify_recovery(
            plan=plan,
            result=result,
            evidence=evidence,
            catalog=CATALOG,
            base_policy_input_schema=(
                BASE_INPUT_SCHEMA
            ),
            plan_schema=PLAN_SCHEMA,
            result_schema=RESULT_SCHEMA,
            verification_schema=(
                VERIFICATION_SCHEMA
            ),
            repo_root=REPO_ROOT,
            branch=(
                "feature/c2-bounded-self-healing"
            ),
            commit=("c" * 40),
            target_layer="gold_public",
            opa_bin=Path(
                "/synthetic/opa"
            ),
            plan_artifact_sha256=(
                "d" * 64
            ),
            result_artifact_sha256=(
                canonical_sha(result)
            ),
            evidence_artifact_sha256=(
                canonical_sha(evidence)
            ),
            evaluator=allow_evaluator,
            started_at=(
                "2026-08-20T12:00:25Z"
            ),
            completed_at=(
                "2026-08-20T12:00:30Z"
            ),
        )
